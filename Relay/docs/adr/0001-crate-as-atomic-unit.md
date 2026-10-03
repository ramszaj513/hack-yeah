# Skrzynka jako atomowa jednostka zamiast abstrakcyjnej ilości

Dary modelujemy jako **skrzynki**: jednostkowa objętość, jedna kategoria, kod QR, lokalizacja darczyńcy. `Resource` z pierwotnego modelu to abstrakcyjna ilość bez objętości, a `Transport Offer` nie deklaruje ładowności — w efekcie solver mógł zaplanować trasę, której żaden samochód fizycznie nie przewiezie. Zamiast dodawać wymiar wagowo-objętościowy rozważaliśmy dwie alternatywy: skalar „mieści N standardowych jednostek” oraz prawdziwy model waga+objętość. Oba wymagają zbierania nowych danych od każdego mieszkańca i dokładają realny wymiar do solvera. Wybraliśmy jedną standardową skrzynkę, bo sprowadza ładowność do liczenia slotów i daje fizyczny, skanowalny artefakt na demo.

## Consequences

- Ładowność = liczba **wolnych slotów** przejazdu; problem nieprzewidywalnej ładowności znika.
- Standaryzacja ogranicza nietypowe dary — wszystko musi zmieścić się w jednej objętości skrzynki.
- Skrzynka nie niesie wagi, więc teoretycznie kierowca może dostać ładunek cięższy niż wygodny; przyjmujemy to jako świadomy kompromis skali hackathonu.
- Kod QR otwiera drogę do późniejszej weryfikacji łańcucha dostaw (proof-of-impact) bez zmiany modelu.
