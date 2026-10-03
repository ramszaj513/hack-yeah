# Relay — plan implementacji (2 h, 1 agent kodowania)

Master-plan projektu. Dokumentacja referencyjna: `ARCHITECTURE.md`, `ALGORITHM.md`,
`IMPLEMENTATION.md`, `GLOSSARY.md`, `adr/`.

## 0. Zablokowane decyzje

| Obszar | Decyzja |
|---|---|
| Stack | Python + FastAPI + SQLite; frontend `index.html` + Leaflet z CDN, bez build-stepu |
| Czas | Tylko geometria; okno odjazdu pomijamy |
| Objązdy | 1 przejazd = dokładnie 1 objazd |
| Fairness | `U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)` |
| Dostawy | Częściowe, min. 1 skrzynka |
| Wyzwalanie | Po każdym zdarzeniu; `GET /state` przelicza sugestie |
| Skala | Obszar ~30×30 km, prędkość 50 km/h (0,8333 km/min) |
| Widoki | Tylko mapa admina |
| Porównanie | Globalny przełącznik `fair_share` / `nearest_fit` |
| Testy | Jeden smoke test E2E |
| QR | Pominięte; skrzynka ma tekstowy `id` |

Sugestie są **efemeryczne** — nie zapisujemy ich w bazie, przeliczamy je w `GET /state`
(zob. ADR 0005). „Auto-run po zdarzeniu” = front odświeża `/state` po każdym POST/claim.

## 1. Architektura

```
Relay/
├─ app/
│  ├─ config.py     # R, LAT0, SPEED_KMH, DB_PATH, MODES
│  ├─ db.py         # schemat SQLite, seed, zapytania, transakcje, Lock
│  ├─ geometry.py   # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py     # faza 1 (kandydaci), faza 2 (greedy), metryki
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

Przepływ: `POST` → walidacja → SQLite → front woła `GET /state` → serwer liczy kandydatów
i greedy → zwraca rozłączne sugestie → `POST /claim` (transakcja) → refetch.

Jeden worker uvicorn + `threading.Lock` wokół mutacji i przeliczeń = brak wyścigów.

## 2. Model danych

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

## 3. Geometria i stałe

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

Rzut lokalny jest przy 30 km równoważny „prostej linii” (ADR 0002).

## 4. Algorytm

### Faza 1 — generowanie kandydatów (per para przejazd × punkt)

1. Policz `detour_km(t,N)`; jeśli `> allowance_km(t)` → odrzuć.
2. Trasa objazdu = łamana `[O, N, D]`; zbierz skrzynki `available` z
   `polyline_dist(crate, [O,N,D]) ≤ corridor_half_km(t)`.
3. Odfiltruj kategorie, których `N` już nie potrzebuje (`remaining == 0`).
4. `s = min(slots_free, Σ remaining(N))`; wybierz `s` skrzynek zachłannie: najpierw
   kategoria o największym `Δ(c) = severity_N · [log(1+delivered_c+1) − log(1+delivered_c)]`,
   potem najbliższa skrzynka tej kategorii (tie-break `id`). Mieszane kategorie dozwolone.
5. Jeśli wybrano ≥ 1 skrzynkę → kandydat `(t, N, crate_ids, extra_minutes, utility_gain)`.

### Faza 2 — zachłanny wybór (sugestie rozłączne)

```
used_trips, claimed_crates = ∅
while True:
    best = argmax over candidates(score, tie_break)
    if none: break
    emit best
    used_trips += best.trip; claimed_crates += best.crates
    zaktualizuj delivered/remaining w pamięci; zamknij N jeśli pełny
    przebuduj kandydatów pomijając used_trips i claimed_crates
```

- `fair_share`: `score = utility_gain`, tie-break `(−extra_minutes, trip_id, need_id)`.
- `nearest_fit`: `score = −extra_minutes`, tie-break `(utility_gain, trip_id, need_id)`.

Sugestie są rozłączne → klient może przejąć dowolny podzbiór bez niespodzianek.

### Metryki

- `unmet_n = Σ_c remaining(n,c)`; `capacity_n = Σ_c needed(n,c)`.
- `Starvation Index = Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`.
- Panel: % zapełnienia per punkt + globalny index.

## 5. Katalog przypadków

### 5a. Wejście / walidacja

| # | Przypadek | Zachowanie |
|---|---|---|
| 1 | Nieznana kategoria | `422` |
| 2 | Współrzędne poza zakresem | `422` |
| 3 | `detour_budget_min ≤ 0` lub `slots_free ≤ 0` | `422` |
| 4 | `severity` poza 1..5 | `422` |
| 5 | Wszystkie `needed == 0` przy tworzeniu punktu | `closed` od razu, nigdy kandydat |
| 6 | Duplikat `id` | `409` |
| 7 | Brak treści / zły JSON | `422` |

### 5b. Generowanie kandydatów

| # | Przypadek | Wynik |
|---|---|---|
| 8 | Brak skrzynek / przejazdów / otwartych punktów | brak sugestii |
| 9 | `O == D` (trasa punktowa) | segment zdegenerowany; `seg_dist` → odległość do punktu |
| 10 | `detour_km > allowance` | para odrzucona |
| 11 | Brak skrzynek w korytarzu `[O,N,D]` | para odrzucona |
| 12 | Skrzynki są, ale kategoria niepotrzebna | odrzucone |
| 13 | `slots_free` mniejsze niż potrzeba | bierzemy `slots_free` |
| 14 | Mniej skrzynek niż potrzeba | bierzemy wszystkie dostępne |
| 15 | Skrzynka w korytarzu wielu przejazdów | kandydat dla każdego; greedy przypisze raz |
| 16 | `delivered_c ≥ needed_c` | kategoria wykluczona |
| 17 | Równe zyski marginalne | tie-break po `id` |
| 18 | Punkt w pełni zaspokojony | `closed`, pominięty |

### 5c. Greedy / konflikty

| # | Przypadek | Handling |
|---|---|---|
| 19 | Przejazd już użyty w sugestii | pomijany |
| 20 | Skrzynka już przypisana | pomijana |
| 21 | Punkt zamknięty w trakcie pętli | pomijany |
| 22 | Kandydat unieważniony | pomijany przy przebudowie |
| 23 | Brak nowego kandydata w przebiegu | koniec pętli |
| 24 | Punkt obsłużony częściowo przez kilka przejazdów | dozwolone |
| 25 | Równe `detour` w `nearest_fit` | tie-break `utility_gain`, potem `id` |
| 26 | Wszystkie przejazdy zużyte | brak dalszych sugestii |

### 5d. Claim

| # | Przypadek | Zachowanie |
|---|---|---|
| 27 | `trip_id` już `used` | `409` |
| 28 | Skrzynka już `claimed` | `409` |
| 29 | Ilość skrzynek kategorii > `remaining` | `409` |
| 30 | Punkt `closed` | `409` |
| 31 | Poprawny claim | transakcja: crates→claimed, trip→used, delivered += n, ewentualnie need→closed |
| 32 | Dwa szybkie claimy | `Lock` + transakcja; pierwszy wygrywa |

### 5e. Sterowanie

| # | Przypadek | Zachowanie |
|---|---|---|
| 33 | `mode` nieznany | `400` |
| 34 | Zmiana trybu | zapis w `settings`; `/state` przelicza |
| 35 | `POST /reset` | `DELETE` tabel + seed; `200` |
| 36 | Brak seeda po restarcie | `db.init()` seeduje, jeśli puste |

## 6. API

| Metoda | Ścieżka | Body → Response |
|---|---|---|
| `GET` | `/state` | `{mode, crates, trips, need_points, suggestions, metrics}` |
| `POST` | `/crates` | `{category, lat, lon}` → `{id}` |
| `POST` | `/trips` | `{olat,olon,dlat,dlon,detour_budget_min,slots_free}` → `{id}` |
| `POST` | `/need-points` | `{name,lat,lon,severity,requirements:{cat:qty}}` → `{id}` |
| `POST` | `/claim` | `{trip_id, need_id, crate_ids}` → `200` / `409` |
| `POST` | `/mode` | `{mode}` → `200` / `400` |
| `POST` | `/reset` | — → `200` |

## 7. Frontend

- Mapa Leaflet (OSM), środek `LAT0`, zoom na ~30 km.
- Punkty potrzeb: okrąg, kolor wg `severity`, rozmiar wg unmet.
- Przejazdy: szare linie `O→D`.
- Sugestie: łamana `O→skrzynki→N→D`, w panelu przycisk **Przejmij**.
- Panel: `Starvation Index`, słupki zapełnienia, przełącznik trybu, `Reset`.
- Po każdym POST/claim: `fetch('/state')` → przerysowanie (to realizuje auto-run).

## 8. Seed (scenariusz kontrastu)

- ~6 punktów potrzeb w kwadracie 30×30 km, w tym daleki o `severity=5`.
- ~15 skrzynek w korytarzach przejazdów.
- ~5 przejazdów przecinających centrum, budżety zróżnicowane 5–15 min.
- Dobór tak, by `nearest_fit` obsłużył bliski punkt o niskiej pilności, a `fair_share`
  dotarł do dalekiego `severity=5`. To moment demo.

## 9. Smoke test (`tests/test_smoke.py`)

1. `GET /state` → są sugestie.
2. `POST /claim` pierwszej sugestii → `200`.
3. `GET /state` → crates `claimed`, trip `used`, `delivered` wzrosło, sugestia zniknęła.
4. `POST /mode {nearest_fit}` → `200`, inne uporządkowanie.
5. `POST /reset` → stan wraca do seeda.

## 10. Harmonogram 2 h

| Czas | Krok | Checkpoint |
|---|---|---|
| 0:00–0:15 | `config`, `db` (DDL + seed) | `GET /state` zwraca seed bez solvera |
| 0:15–0:50 | `geometry` + `solver` | rozłączne sugestie fair vs nearest |
| 0:50–1:10 | `main` (endpointy + claim + Lock) | smoke test przechodzi |
| 1:10–1:35 | frontend: mapa, panel, toggle, claim | klikanie E2E |
| 1:35–1:50 | seed pod kontrast + ręczne demo | różnica trybów widoczna |
| 1:50–2:00 | polish, freeze, README run | `./run.sh` startuje od zera |

## 11. Ryzyka

- **Brak kontrastu w seedzie** → największe ryzyko demo; +10 min na seed.
- **Zbyt szeroki korytarz** → wszystko wpada do jednego kandydata; zróżnicuj budżety.
- **Greedy faworyzuje duże punkty** (suma log per kategoria) → akceptowalne w MVP.

## 12. Twarde cięcia

Bez ILP/OR-Tools, bez QR, bez okien czasowych, bez auth, bez animacji, bez wielu objazdów
na przejazd, bez testów jednostkowych.
