# Relay — implementacja (2 h, 1 agent)

Krok po kroku. Szczegóły algorytmu: `ALGORITHM.md`; komponenty: `ARCHITECTURE.md`.

## Kolejność prac

### Krok 0 — szkielet (0:00–0:05)

- `mkdir -p app web tests`; `requirements.txt`: `fastapi`, `uvicorn`, `pytest`, `httpx`.
- `config.py`: `R`, `LAT0`, `SPEED_KMH`, `SPEED_KM_PER_MIN`, `DB_PATH`, `MODES`.

### Krok 1 — dane i seed (0:05–0:15)

- `db.py`: DDL (5 tabel), `init()` seedujący, jeśli puste; `get_conn()`, `Lock`.
- `seed.py`-owa funkcja w `db.py`: ~6 punktów potrzeb (w tym daleki `severity=5`),
  ~15 skrzynek, ~5 przejazdów z budżetami 5–15 min.
- Checkpoint: `GET /state` (jeszcze bez solvera) zwraca seed.

### Krok 2 — geometria (0:15–0:20)

- `geometry.py`: `xy`, `dist`, `seg_dist` (z przycięciem; `a==b` → odległość do punktu),
  `polyline_dist`.

### Krok 3 — solver (0:20–0:50)

- `solver.py`:
  - `build_candidates(trips, need_points, crates, delivered, mode)` — faza 1,
  - `solve(...)` — faza 2 greedy, zwraca rozłączne sugestie,
  - `metrics(...)` — Starvation Index i fill per punkt.
- Checkpoint: dla seeda widać rozłączne sugestie; tryby `fair_share` i `nearest_fit` różnią się.

### Krok 4 — API (0:50–1:10)

- `main.py`: `GET /state`, `POST /crates|/trips|/need-points|/claim|/mode|/reset`.
- Walidacja wejścia wg tabeli przypadków (sekcja 5a ALGORITHM.md).
- `claim` w transakcji pod `Lock`; zwraca `409` dla nieaktualnych sugestii.
- Smoke test `tests/test_smoke.py`.

### Krok 5 — frontend (1:10–1:35)

- `web/index.html`: kontener mapy + panel; Leaflet i CSS z CDN.
- `web/app.js`: `loadState()` → `fetch('/state')` → rysowanie markerów, tras i sugestii;
  `claim()`; `setMode()`; `reset()`; po każdej akcji `loadState()`.
- `web/style.css`: prosty layout dwukolumnowy.

### Krok 6 — seed kontrastu (1:35–1:50)

- Dostroić pozycje/pilności tak, by w `nearest_fit` daleki punkt miał ~0%,
  a w `fair_share` został obsłużony.
- Zapisać scenariusz narracji demo.

### Krok 7 — freeze (1:50–2:00)

- `run.sh`: `uvicorn app.main:app --reload`.
- README: jak uruchomić. Zamrozić zakres.

## Test dymny (E2E)

```
1. GET /state               -> są sugestie
2. POST /claim (pierwsza)   -> 200
3. GET /state               -> crates claimed, trip used, delivered↑, sugestia zniknęła
4. POST /mode nearest_fit   -> 200, inne uporządkowanie
5. POST /reset              -> 200, stan wraca do seeda
```

## Twarde cięcia

Bez ILP/OR-Tools, bez QR, bez okien czasowych, bez auth, bez animacji, bez wielu objazdów
na przejazd, bez testów jednostkowych.

## Ryzyka i mitygacje

| Ryzyko | Mitygacja |
|---|---|
| Brak kontrastu fair vs nearest w seedzie | poświęć +10 min na seed, to serce demo |
| Zbyt szeroki korytarz (duży budżet) | zróżnicuj budżety przejazdów w seedzie |
| Greedy faworyzuje duże punkty | zaakceptuj; poza zakresem MVP |
| Wyścig przy claim | `Lock` + transakcja, pierwszy wygrywa |
