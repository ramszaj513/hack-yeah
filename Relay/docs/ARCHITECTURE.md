# Relay — architektura

Konkretna architektura MVP budowanego w ~2 h przez jednego agenta. Bez zależności chmurowych.

## Przegląd komponentów

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (index.html + Leaflet z CDN)                   │
│  - mapa OSM, seed, przełącznik trybu, panel fairness     │
│  - po każdym POST/claim: fetch('/state')                 │
└───────────────────────────┬──────────────────────────────┘
                            │ REST / JSON
┌───────────────────────────▼──────────────────────────────┐
│  Backend (FastAPI, jeden worker + threading.Lock)        │
│  - GET /state  → liczy sugestie (auto-run)               │
│  - POST /crates /trips /need-points /claim /mode /reset  │
│  - SQLite: crates, trips, need_points, requirements      │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│  Solver (solver.py)                                      │
│  Faza 1: kandydaci (korytarz + koszt objazdu)            │
│  Faza 2: greedy proportional fairness / nearest-fit      │
└──────────────────────────────────────────────────────────┘
```

## Układ plików

```
Relay/
├─ app/
│  ├─ config.py     # R, LAT0, SPEED_KMH, DB_PATH, MODES
│  ├─ db.py         # schemat SQLite, seed, zapytania, transakcje, Lock
│  ├─ geometry.py   # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py     # faza 1, faza 2, metryki
│  └─ main.py       # FastAPI, walidacja, endpointy
├─ web/
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ tests/
│  └─ test_smoke.py
├─ requirements.txt # fastapi, uvicorn, pytest, httpx
└─ run.sh
```

## Model danych (SQLite)

```sql
CREATE TABLE crates(
  id TEXT PRIMARY KEY, category TEXT NOT NULL, lat REAL, lon REAL,
  status TEXT NOT NULL DEFAULT 'available');       -- available | claimed

CREATE TABLE trips(
  id TEXT PRIMARY KEY, olat REAL, olon REAL, dlat REAL, dlon REAL,
  detour_budget_min REAL NOT NULL, slots_free INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'available');       -- available | used

CREATE TABLE need_points(
  id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL,
  severity INTEGER NOT NULL DEFAULT 1,             -- 1..5
  status TEXT NOT NULL DEFAULT 'open');            -- open | closed

CREATE TABLE requirements(
  need_id TEXT, category TEXT, needed INTEGER NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(need_id, category));

CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);  -- mode
```

`remaining(need,cat) = max(0, needed − delivered)`. Punkt zamyka się, gdy wszystkie
`remaining == 0`.

## Geometria i stałe

```python
R = 6371.0; LAT0 = 52.2297                      # Warszawa jako środek mapy
SPEED_KMH = 50.0; SPEED_KM_PER_MIN = SPEED_KMH/60.0

def xy(lat, lon):                               # lokalny płaski układ w km
    return (R*radians(lon)*cos(radians(LAT0)), R*radians(lat))
def dist(a, b): ...                             # km (Euclid w xy)
def seg_dist(p, a, b): ...                      # rzut z przycięciem (obsługa a==b)
def polyline_dist(p, pts): min(seg_dist(...))   # odległość od trasy O→N→D
```

- `allowance_km(t) = detour_budget_min × SPEED_KM_PER_MIN`
- `corridor_half_km(t) = allowance_km(t) / 2`
- `detour_km(t,N) = dist(O,N) + dist(N,D) − dist(O,D)`
- `extra_minutes = detour_km / SPEED_KM_PER_MIN`

Przy skali 30 km rzut lokalny jest równoważny „prostej linii” (zgodnie z ADR 0002).

## API

| Metoda | Ścieżka | Body → Response |
|---|---|---|
| `GET` | `/state` | `{mode, crates, trips, need_points, suggestions, metrics}` |
| `POST` | `/crates` | `{category, lat, lon}` → `{id}` |
| `POST` | `/trips` | `{olat,olon,dlat,dlon,detour_budget_min,slots_free}` → `{id}` |
| `POST` | `/need-points` | `{name,lat,lon,severity,requirements:{cat:qty}}` → `{id}` |
| `POST` | `/claim` | `{trip_id, need_id, crate_ids}` → `200` / `409` |
| `POST` | `/mode` | `{mode}` → `200` / `400` |
| `POST` | `/reset` | — → `200` |

`GET /state` jest jednocześnie „auto-runem”: za każdym razem przelicza kandydatów i greedy
na bieżącej puli. Nie ma osobnego endpointu `/optimize` ani trwałych propozycji
(zob. ADR 0005).

## Frontend

- Mapa Leaflet (OSM), środek `LAT0`, zoom obejmujący ~30 km.
- Punkty potrzeb: okrąg, kolor wg `severity`, rozmiar wg unmet.
- Przejazdy: szare linie `O→D`.
- Sugestie: łamana `O→skrzynki→N→D`, w panelu przycisk **Przejmij**.
- Panel: `Starvation Index`, słupki zapełnienia per punkt, przełącznik trybu, `Reset`.
- Po każdym POST/claim: `fetch('/state')` → przerysowanie.

## Współbieżność

Jeden worker uvicorn. Mutacje (POST / claim / reset) i przeliczenia solvera chronione
`threading.Lock`. Zapisy przez transakcje SQLite. Claim jest atomowy: pierwszy wygrywa.

## Dane demonstracyjne (seed)

Skrypt seedujący tworzy scenariusz kontrastu:

- ~6 punktów potrzeb w kwadracie 30×30 km, w tym daleki o `severity=5`,
- ~15 skrzynek w korytarzach przejazdów,
- ~5 przejazdów przecinających centrum, budżety 5–15 min.

Cel: `nearest_fit` obsługuje bliski punkt o niskiej pilności, a `fair_share` dociera do
dalekiego `severity=5`.

## Zasady (non-goals)

- Bez realnego routingu i kluczy API — odległości przybliżone (ADR 0002).
- Bez globalnego VRP — solver lokalny i przyrostowy (ADR 0002).
- Bez trwałych propozycji i re-planu — model „zasugeruj → przejmij” (ADR 0004, 0005).
- Bez QR, okien czasowych, logowania, kont i płatności.
- Bez ILP/OR-Tools i testów jednostkowych (tylko smoke test).
