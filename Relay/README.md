# Relay

**Sprawiedliwa pomoc na trasach, które i tak się dzieją.**

Relay to aplikacja na hackathon: logistyka pomocy humanitarnej w sytuacjach kryzysowych (powódź, trzęsienie ziemi, ewakuacja). Zamiast centralnego dyspozytora i „kolejnego Ubera” Relay wpasowuje dary w przejazdy, które mieszkańcy wykonują niezależnie, i rozdziela pomoc według **sprawiedliwości**, a nie odległości.

> Dokumentacja projektowa i MVP. Plan implementacji: [`docs/PLAN.md`](docs/PLAN.md); architektura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); algorytm: [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

---

## Problem

- Podczas kryzysu zasoby (jedzenie, woda, leki) są rozproszone po domach mieszkańców, a nie w jednym magazynie.
- Służby mają **punkty potrzeb**, ale nie wiedzą, kto i kiedy może coś dowieźć.
- Klasyczne rozwiązanie — centralny optymalizator dyspozycji — jest kosztowne, kruche i **niesprawiedliwe**: wysyła pomoc tam, gdzie jest najbliżej i najłatwiej, zostawiając dalekie oraz pilniejsze punkty bez wsparcia.
- W kryzysie łączność i prąd bywają zerwane, więc rozwiązanie nie może opierać się na ciągłej łączności z chmurą.

## Rozwiązanie — trzy filary

1. **Skrzynka jako jednostka.** Dary standaryzujemy do pojedynczej skrzynki: jedna objętość, jedna kategoria. Darczyńca pakuje skrzynki, kierowca ma *N* wolnych miejsc (slotów). To rozwiązuje problem ładowności bez modelowania wagi i objętości.
2. **Trasy zamiast zleceń.** Mieszkaniec nie dostaje „kursu” jak w Uberze — deklaruje przejazd, który **i tak wykonuje** (`origin → destination`, **budżet objazdu** w minutach, wolne sloty). System tylko dorzuca skrzynki po drodze.
3. **Sprawiedliwość zamiast najkrótszej drogi.** Dopasowanie maksymalizuje **wklęsłą funkcję użyteczności** (proportional fairness), dzięki czemu żaden punkt — nawet daleki i pilny — nie zostaje pominięty kosztem najbliższego.

## Aktorzy

| Aktor | Rola |
|---|---|
| **Mieszkaniec–Darczyńca** | Zgłasza skrzynki (kategoria + lokalizacja). |
| **Mieszkaniec–Kierowca** | Zgłasza przejazd, który i tak wykonuje, wraz z budżetem objazdu i liczbą wolnych slotów. |
| **Administrator / służby** | Tworzy punkty potrzeb z zapotrzebowaniem i wagą pilności (severity). |

Ta sama osoba może być darczyńcą i kierowcą — nie ma osobnych kont.

## Jak to działa (przepływ)

1. Mieszkańcy zgłaszają **skrzynki**, a kierowcy — **przejazdy**.
2. Administrator tworzy **punkty potrzeb** z zapotrzebowaniem i pilnością.
3. Po każdym zdarzeniu system przelicza **sugerowane objazdy**: wokół każdego przejazdu wyznacza korytarz (zależny od budżetu objazdu) i sprawdza, które skrzynki i punkty potrzeb da się wpasować.
4. Kierowca widzi propozycję „weź te skrzynki i zrób +7 min, zawieź do punktu X”.
5. Kierowca **przejmuje** (Claim) propozycję; skrzynki znikają z puli. Brak reakcji = brak rezerwacji, sugestia po prostu znika przy następnym przeliczeniu.

## Model danych

| Pojęcie | Opis |
|---|---|
| **Crate (skrzynka)** | Standardowa jednostka: jedna kategoria, jedna objętość, lokalizacja. |
| **Trip (przejazd)** | `origin`, `destination`, `detour_budget_min`, `slots_free`. |
| **Need-Point (punkt potrzeb)** | Lokalizacja, zapotrzebowanie per kategoria, `severity` (1–5). |
| **Detour (objazd)** | Zestaw skrzynek zebranych wzdłuż korytarza przejazdu i dostarczonych do jednego punktu potrzeb. |
| **Suggested Detour** | Efemeryczna propozycja objazdu przed przejęciem. |
| **Starvation Index** | Metryka: ważony pilnością niedobór niezaspokojonego zapotrzebowania. |

## Algorytm

**Faza 1 — wykonalność (corridor insertion).** Trasa objazdu to łamana `[O, N, D]`; korytarz wokół niej wynika z budżetu objazdu. Zbieramy skrzynki w korytarzu i odrzucamy pary przekraczające budżet. Złożoność `O(przejazdy × punkty × skrzynki)` — bez globalnej macierzy i bez VRP.

**Faza 2 — wybór (proportional fairness).** Maksymalizujemy:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

Wklęsła użyteczność per kategoria sprawia, że każda kolejna skrzynka jest warta mniej, więc solver sam się rozkłada i nie może zagłodzić dalekiego punktu. Wybór jest zachłanny (marginal gain) i szybki. Szczegóły i pełny katalog przypadków: [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

## Demo — serce prezentacji

Przełącznik między dwoma scorerami na tych samych danych:

- **Nearest-fit** (baseline „Uber”): minimalizacja objazdu → wszystko płynie do najbliższego punktu.
- **Fair-share** (nasze): maksymalizacja wklęsłej użyteczności → rozkład + priorytet pilności.

Mapa + wykres zapełnienia punktów + **Starvation Index**. Wskazujemy punkt, który w trybie nearest-fit dostaje 0%, a w fair-share zostaje obsłużony — to 20 sekund, które wygrywają salę.

## Zakres MVP

| Budujemy | Odpuszczamy |
|---|---|
| Mapa Leaflet + OpenStreetMap (bez klucza API) | Prawdziwy routing / Distance Matrix |
| Backend FastAPI + SQLite | Pełne globalne VRP |
| Korytarz + zachłanny solver fairness | Okna czasowe i kolejność |
| Seed syntetycznego miasta | Trwałe propozycje i re-plan |
| Flow „zasugeruj → przejmij” | QR, logowanie, konta, płatności |
| Panel fairness + Starvation Index | Model wagi/objętości (skrzynka = 1 slot) |

## Stos technologiczny

- **Backend:** FastAPI (Python) + SQLite.
- **Solver:** czysty Python (bez zależności chmurowych).
- **Frontend:** pojedyncza strona z mapą (Leaflet + OSM z CDN), bez build-stepu.
- **Dane:** seed przy starcie. Demo nigdy nie zależy od danych wpisywanych na żywo.

## Struktura repozytorium

```
Relay/
├─ app/                       # backend FastAPI + SQLite
│  ├─ config.py               # R, LAT0, SPEED_KMH, DB_PATH, MODES, kategorie
│  ├─ db.py                   # schemat, seed kontrastu, transakcje, Lock
│  ├─ geometry.py             # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py               # faza 1 (korytarz) + faza 2 (greedy fairness)
│  └─ main.py                 # endpointy API + montaż frontendu
├─ web/                       # frontend: Leaflet z CDN, bez build-stepu
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ tests/
│  └─ test_smoke.py           # smoke test E2E (pytest)
├─ pyproject.toml             # projekt uv (zależności + konfiguracja pytest)
├─ requirements.txt           # to samo dla `pip` (opcjonalnie)
├─ run.sh                     # uruchomienie całej aplikacji lokalnie
├─ README.md                  # ten plik
└─ docs/
   ├─ PLAN.md                 # master-plan implementacji (2 h)
   ├─ MANUAL.md               # instrukcja obsługi (jak używać aplikacji)
   ├─ ARCHITECTURE.md         # komponenty, model danych, API, seed
   ├─ ALGORITHM.md            # solver, metryki, katalog przypadków
   ├─ IMPLEMENTATION.md       # kroki wdrożenia i smoke test
   ├─ GLOSSARY.md             # język dziedziny
   └─ adr/                    # decyzje projektowe
```

## Szybki start

Wymagany [`uv`](https://docs.astral.sh/uv/) (zarządza Pythonem i zależnościami).

```bash
cd Relay
./run.sh                        # uv sync + uvicorn (auto-reload)
# przeglądarka: http://127.0.0.1:8000
```

Opcje: `PORT=9000 ./run.sh`, `NO_RELOAD=1 ./run.sh`.
Testy: `uv run pytest`. Reset danych: `POST /reset` lub przycisk w panelu.

> **Jak używać aplikacji?** Zobacz [`docs/MANUAL.md`](docs/MANUAL.md) — albo kliknij **?**
> w prawym górnym rogu panelu. Przy pierwszym wejściu instrukcja otworzy się sama.

## Status

Dokumentacja projektowa kompletna, MVP zaimplementowane wg [`docs/PLAN.md`](docs/PLAN.md).
Backend FastAPI + SQLite, solver dwufazowy, frontend Leaflet, seed scenariusza kontrastu
i smoke test E2E. Uzasadnienia decyzji: [`docs/adr/`](docs/adr/).
