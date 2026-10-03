# Relay — instrukcja obsługi

Przewodnik po aplikacji: co pokazuje, co oznaczają poszczególne elementy i jak
przeprowadzić demo. Wersja skrócona jest też dostępna w aplikacji pod przyciskiem **?**
w prawym górnym rogu panelu.

---

## 1. Po co to jest (w 30 sekund)

W kryzysie dary są rozproszone po domach mieszkańców, a służby nie wiedzą, kto i kiedy
może coś dowieźć. Relay **wpasowuje pomoc w przejazdy, które i tak się dzieją** — ktoś
jedzie z punktu A do B, a my po drodze dorzucamy mu skrzynki.

Klasyczny optymalizator wysyła pomoc tam, gdzie jest **najbliżej i najłatwiej** — dalekie,
pilne punkty zostają bez wsparcia. Relay rozdziela pomoc **sprawiedliwie**: żaden punkt,
nawet daleki i pilny, nie zostaje zagłodzony kosztem najbliższego.

Cała idea jest w jednym przełączniku: **Nearest-fit** (tak działa „kolejny Uber”) vs
**Fair-share** (tak działa Relay). Przełączasz, patrzysz na mapę i metrykę — i widzisz różnicę.

---

## 2. Słownik pojęć

| Pojęcie | Znaczenie |
|---|---|
| **Skrzynka** (crate) | Standardowa jednostka daru: jedna kategoria, jedna objętość, jedna lokalizacja. Zajmuje 1 slot. |
| **Przejazd** (trip) | Deklaracja: „jadę z `origin` do `destination`”. Ma **budżet objazdu** i **wolne sloty**. |
| **Budżet objazdu** | Ile minut kierowca gotów jest dołożyć (5–15 min). Wyznacza, jak szeroki korytarz łapiemy. |
| **Punkt potrzeb** (need-point) | Miejsce z zapotrzebowaniem na kategorie i **pilnością** (1–5). |
| **Zapotrzebowanie** | Ile jeszcze danej kategorii brakuje punktowi. Punkt zamyka się, gdy brak = 0. |
| **Pilność** (severity) | Waga 1–5. Steruje sprawiedliwością: wyższa pilność = mocniejszy priorytet. |
| **Korytarz** | Obszar wokół trasy `O → punkt → D`. Tylko skrzynki w korytarzu wchodzą do objazdu. |
| **Sugerowany objazd** | Propozycja: „weź te skrzynki i zrób +X min, zawieź do punktu Y”. Efemeryczna — znika przy przeliczeniu. |
| **Przejęcie** (claim) | Kliknięcie „Przejmij”. Skrzynki stają się zajęte, przejazd zużyty, a dostawa zapisana na stałe. |
| **Starvation Index** | Wskaźnik niezaspokojonego zapotrzebowania ważony pilnością. Im niższy, tym lepiej. |
| **Zapełnienie** (fill) | Procent zaspokojenia punktu. |

---

## 3. Mapa — co jest czym

| Symbol na mapie | Znaczenie |
|---|---|
| **Szara przerywana linia** | Przejazd (`O → D`), który i tak się dzieje. |
| **Mała kolorowa kropka** | Skrzynka. Kolor = kategoria (żywność, woda, leki, higiena, inne). |
| **Duże kolorowe koło** | Punkt potrzeb. **Kolor = pilność** (zielony → czerwony). **Rozmiar = braki** (im większe, tym więcej brakuje). |
| **Pomarańczowa linia** | Sugerowany objazd: `O → skrzynki → punkt potrzeb → D`. |
| **Numerowany pomarańczowy znacznik** | Numer sugestii — odpowiada numerowi na liście w panelu. |

Kliknij dowolny obiekt na mapie, żeby zobaczyć szczegóły (np. punkt potrzeb pokaże
zapełnienie teraz i po sugestiach).

Legenda symboli jest też dostępna bezpośrednio na mapie (prawy górny róg).

---

## 4. Panel — co jest czym

1. **Tryb dopasowania** — przełącznik dwóch algorytmów:
   - **Fair-share** (nasz) — maksymalizuje sprawiedliwość, sięga po dalekie i pilne punkty.
   - **Nearest-fit** (baseline „Uber”) — minimalizuje objazd, wszystko płynie do najbliższego.
2. **Starvation Index** — `stan → po sugestiach`. Pierwsza liczba to rzeczywisty stan bazy;
   druga to stan, gdybyś przejął wszystkie widoczne sugestie. Poniżej słupki per punkt.
3. **Sugerowane objazdy** — karty propozycji. Każda ma numer, czas objazdu, przejazd,
   punkt docelowy, zysk użyteczności, listę skrzynek i przycisk **Przejmij**.
4. **Sterowanie** — **Reset do seeda** przywraca scenariusz demonstracyjny.

Przycisk **?** (prawy górny róg) otwiera skróconą instrukcję w aplikacji.

---

## 5. Jak korzystać — krok po kroku

1. Otwórz `http://127.0.0.1:8000` (`./run.sh`) i poczekaj, aż mapa się narysuje.
2. Zobacz stan startowy: punkty potrzeb na czerwono/zielono, szare trasy, kropki skrzynek.
3. Wybierz tryb **Fair-share**. Spójrz na **Sugerowane objazdy** — pojawi się propozycja do
   dalekiego punktu „Rembertów-Wschód” (pilność 5).
4. Kliknij **Przejmij** przy wybranej sugestii. Mapa i panel odświeżą się:
   - skrzynki znikną z puli,
   - przejazd zmieni status na `used`,
   - zapotrzebowanie punktu zmaleje, a **Starvation Index** spadnie.
5. Kliknij **Reset do seeda**, żeby wrócić do punktu wyjścia.
6. Przełącz na **Nearest-fit** i porównaj: te same dane, inny zestaw sugestii —
   daleki punkt nie jest obsługiwany, a **Starvation Index jest wyższy**.

> **Zasada:** sugerowane objazdy są tylko propozycjami. Nic nie jest zarezerwowane, dopóki
> nie klikniesz **Przejmij**. Dwóch kierowców może zobaczyć tę samą propozycję — wygrywa
> ten, kto pierwszy kliknie (serwer odrzuci nieaktualne przejęcie).

---

## 6. Scenariusz demo (20 sekund, które robią wrażenie)

1. Ustaw **Fair-share**.
2. W panelu zwróć uwagę na daleki punkt **„Rembertów-Wschód” (severity 5)** — ma 0% na starcie,
   ale sugestia go obejmuje, więc „po sugestiach” pokazuje 100%.
3. **Przejmij** pierwszy objazd. Starvation Index spada.
4. **Reset do seeda** → przełącz na **Nearest-fit**.
5. Ten sam daleki punkt nadal ma **0%** i nie ma dla niego żadnej sugestii — pomoc utknęła
   w najbliższych punktach. Porównaj **Starvation Index** (znacznie wyższy).
6. Wróć na **Fair-share** — różnica jest widoczna na mapie, w słupkach i w metryce.

To jest teza projektu: sprawiedliwość zamiast najkrótszej drogi.

---

## 7. Jak czytać metryki

- **Starvation Index** = `Σ severity · (braki / pojemność) / Σ severity · 100%`.
  `0%` = nikt nie głoduje, `100%` = nic nie dotarło. Niższy = lepszy.
- **`stan → po sugestiach`** — pierwsza wartość to baza, druga to **projekcja**, gdyby
  wszystkie aktualne sugestie zostały przejęte. Projekcja pozwala porównać tryby bez
  klikania „Przejmij”.
- **Słupki punktów** — jasna część to stan obecny, półprzezroczysta to przyrost z sugestii.
  Etykieta `X% → Y%` czyta się identycznie.
- **Zysk użyteczności** na karcie sugestii to wartość funkcji celu (wklęsła użyteczność)
  dla danej propozycji — wyższa = cenniejsza z punktu widzenia sprawiedliwości.

---

## 8. Fair-share vs Nearest-fit — o co chodzi

Cel Fair-share:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

Każda kolejna skrzynka dla już obsłużonego punktu jest warta **coraz mniej**
(efekt malejących przychodów). Dzięki temu solver sam się rozkłada i nie może
systematycznie zagłodzić odległego, pilnego punktu.

Nearest-fit minimalizuje wyłącznie objazd, więc „kupuje” najtańsze dostawy i szybko
zużywa przejazdy — zostawiając daleki punkt bez transportu. Oba tryby liczą **te same
sugestie** z tej samej puli; różni je tylko sposób wyboru.

---

## 9. Dodawanie własnych danych (API)

Demo nie potrzebuje wpisywania na żywo, ale API jest w pełni sprawne.
Kategorie: `food`, `water`, `meds`, `hygiene`, `other`.

```bash
# Skrzynka: kategoria + lokalizacja
curl -X POST http://127.0.0.1:8000/crates \
  -H 'Content-Type: application/json' \
  -d '{"category":"food","lat":52.23,"lon":21.01}'

# Przejazd: origin → destination, budżet objazdu (min), wolne sloty
curl -X POST http://127.0.0.1:8000/trips \
  -H 'Content-Type: application/json' \
  -d '{"olat":52.20,"olon":21.00,"dlat":52.27,"dlon":21.05,"detour_budget_min":10,"slots_free":3}'

# Punkt potrzeb: pilność 1–5 + zapotrzebowanie per kategoria
curl -X POST http://127.0.0.1:8000/need-points \
  -H 'Content-Type: application/json' \
  -d '{"name":"Nowy punkt","lat":52.25,"lon":21.03,"severity":4,"requirements":{"water":3,"food":2}}'

# Zmiana trybu / reset / podgląd stanu
curl -X POST http://127.0.0.1:8000/mode -H 'Content-Type: application/json' -d '{"mode":"nearest_fit"}'
curl -X POST http://127.0.0.1:8000/reset
curl http://127.0.0.1:8000/state
```

Interaktywna dokumentacja API: `http://127.0.0.1:8000/docs`.

Po dodaniu danych odśwież stronę (albo wykonaj dowolny POST w panelu) — `GET /state`
przelicza sugestie od nowa.

---

## 10. Częste pytania i problemy

**Nie widzę żadnych sugestii.**
Brak sugestii jest poprawny, gdy nie ma jednocześnie: dostępnych skrzynek, wolnych przejazdów
i otwartych punktów potrzeb. Sprawdź, czy skrzynki mają potrzebną kategorię i leżą w korytarzu
przejazdu (blisko łamanej `O → punkt → D`), oraz czy budżet objazdu wystarcza.

**Klikam „Przejmij”, ale dostaję błąd.**
Sugestie są efemeryczne — jeśli stan zmienił się między wygenerowaniem a kliknięciem
(np. ktoś inny przejął zasoby albo kliknąłeś dwa razy), serwer zwróci konflikt.
Odśwież i spróbuj ponownie; wygrywa pierwsze przejęcie.

**Zmieniłem tryb, ale metryka „stan” się nie zmieniła.**
To normalne: „stan” to baza, a porównanie trybów widać w wartości **„po sugestiach”**
oraz w samych sugestiach. Przejmij sugestię, żeby zmienić stan trwały.

**Po restarcie serwera dane wróciły do seeda.**
Baza tworzy się/przygotowuje przy starcie; `POST /reset` (lub przycisk) też przywraca seed.

**Chcę zacząć od zera.**
Kliknij **Reset do seeda** w panelu albo `curl -X POST http://127.0.0.1:8000/reset`.

**Zmienić port?**
`PORT=9000 ./run.sh`. Bez auto-reloadu: `NO_RELOAD=1 ./run.sh`.
