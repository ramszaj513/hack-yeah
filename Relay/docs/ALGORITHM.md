# Relay — algorytm i przypadki

Opis dwufazowego solvera, metryk oraz pełnego katalogu przypadków. Powiązane decyzje:
ADR 0002 (korytarz), ADR 0003 (fairness), ADR 0005 (sugestie efemeryczne).

## Cel

Dobrać skrzynki do przejazdów, które „i tak się dzieją”, i rozdzielić pomoc sprawiedliwie,
nie minimalizując odległości. Maksymalizujemy:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

`deliveredₙ,c` to liczba skrzynek kategorii `c` już dostarczonych do punktu `n`.
Wklęsłość per kategoria sprawia, że każda kolejna skrzynka jest warta mniej, więc solver
sam się rozkłada i nie może zagłodzić dalekiego, pilnego punktu.

## Faza 1 — generowanie kandydatów

Dla każdej pary (przejazd `t` status `available`, punkt `N` status `open`):

1. Policz `detour_km(t,N) = dist(O,N) + dist(N,D) − dist(O,D)`.
   Jeśli `> allowance_km(t)` → odrzuć.
2. Trasa objazdu = łamana `[O, N, D]`. Zbierz skrzynki `available`, dla których
   `polyline_dist(crate, [O,N,D]) ≤ corridor_half_km(t)`.
3. Odfiltruj skrzynki, których kategoria ma `remaining == 0` w `N`.
4. `s = min(slots_free, Σ remaining(N))`. Wybierz `s` skrzynek zachłannie:
   - wybierz kategorię o największym zysku marginalnym
     `Δ(c) = severity_N · [log(1+delivered_c+1) − log(1+delivered_c)]`,
   - z tej kategorii weź najbliższą skrzynkę (tie-break: `id`).
   Mieszanie kategorii w jednym objazdzie jest dozwolone.
5. Jeśli wybrano ≥ 1 skrzynkę → kandydat `(t, N, crate_ids, extra_minutes, utility_gain)`.

Złożoność: `O(przejazdy × punkty × skrzynki)` — bez globalnej macierzy i bez VRP.

## Faza 2 — zachłanny wybór (sugestie rozłączne)

```
used_trips, claimed_crates = ∅
while True:
    best = argmax over candidates(score, tie_breaks)
    if best is None: break
    emit best
    used_trips += best.trip
    claimed_crates += best.crates
    zaktualizuj delivered/remaining w pamięci
    zamknij N, jeśli wszystkie remaining == 0
    przebuduj kandydatów pomijając used_trips i claimed_crates
```

Scorery (przełącznik trybu):

| Tryb | `score` | tie-breaks |
|---|---|---|
| `fair_share` | `utility_gain` | `(−extra_minutes, trip_id, need_id)` |
| `nearest_fit` | `−extra_minutes` | `(utility_gain, trip_id, need_id)` |

Sugestie są rozłączne (żadna skrzynka ani przejazd nie występuje w dwóch), więc klient może
przejąć dowolny podzbiór bez niespodzianek. Po `claim` pula się zmienia i `GET /state`
przelicza nowy, rozłączny zestaw.

## Metryki

- `unmet_n = Σ_c remaining(n,c)`
- `capacity_n = Σ_c needed(n,c)`
- `Starvation Index = Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`
  (dla `capacity_n == 0` punkt jest zamknięty i pomijany)
- `fill_n = 100% · (1 − unmet_n/capacity_n)`

Panel pokazuje `Starvation Index` globalnie i `fill_n` per punkt.

## Katalog przypadków

### Wejście / walidacja

| # | Przypadek | Zachowanie |
|---|---|---|
| 1 | Nieznana kategoria | `422` |
| 2 | Współrzędne poza zakresem | `422` |
| 3 | `detour_budget_min ≤ 0` lub `slots_free ≤ 0` | `422` |
| 4 | `severity` poza 1..5 | `422` |
| 5 | Wszystkie `needed == 0` przy tworzeniu punktu | `closed` od razu |
| 6 | Duplikat `id` | `409` |
| 7 | Brak treści / zły JSON | `422` |

### Generowanie kandydatów

| # | Przypadek | Wynik |
|---|---|---|
| 8 | Brak skrzynek / przejazdów / otwartych punktów | brak sugestii |
| 9 | `O == D` (trasa punktowa) | `seg_dist` liczy odległość do punktu |
| 10 | `detour_km > allowance` | para odrzucona |
| 11 | Brak skrzynek w korytarzu `[O,N,D]` | para odrzucona |
| 12 | Skrzynki są, ale kategoria niepotrzebna | odrzucone |
| 13 | `slots_free` mniejsze niż potrzeba | bierzemy `slots_free` |
| 14 | Mniej skrzynek niż potrzeba | bierzemy wszystkie dostępne |
| 15 | Skrzynka w korytarzu wielu przejazdów | kandydat dla każdego; greedy przypisze raz |
| 16 | `delivered_c ≥ needed_c` | kategoria wykluczona |
| 17 | Równe zyski marginalne | tie-break po `id` |
| 18 | Punkt w pełni zaspokojony | `closed`, pominięty |

### Greedy / konflikty

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

### Claim

| # | Przypadek | Zachowanie |
|---|---|---|
| 27 | `trip_id` już `used` | `409` |
| 28 | Skrzynka już `claimed` | `409` |
| 29 | Ilość skrzynek kategorii > `remaining` | `409` |
| 30 | Punkt `closed` | `409` |
| 31 | Poprawny claim | transakcja: crates→claimed, trip→used, delivered += n, ewentualnie need→closed |
| 32 | Dwa szybkie claimy | `Lock` + transakcja; pierwszy wygrywa |

### Sterowanie

| # | Przypadek | Zachowanie |
|---|---|---|
| 33 | `mode` nieznany | `400` |
| 34 | Zmiana trybu | zapis w `settings`; `/state` przelicza |
| 35 | `POST /reset` | `DELETE` tabel + seed; `200` |
| 36 | Brak seeda po restarcie | `db.init()` seeduje, jeśli puste |

## Znane ograniczenia MVP

- Zachłanność nie daje optimum globalnego (świadomy kompromis — patrz ADR 0003).
- Suma `log` per kategoria faworyzuje punkty z wieloma kategoriami; akceptowalne na demo.
- Korytarz liczony po łamanej `[O,N,D]`, nie po realnych drogach (ADR 0002).
