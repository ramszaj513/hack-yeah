# Sprawdzanie zaznaczonego tekstu

Branch: `codex/selected-text-check`.

## Uruchomienie

1. Uruchom backend zgodnie z SETUP.md. Ustaw `DEMO_MODE=false` i skonfiguruj model oraz dostawców źródeł. Tryb demo nie podkłada wyników filmu pod dowolny tekst.
2. W katalogu `extension` wykonaj `npm run build`.
3. W `chrome://extensions` przeładuj rozszerzenie załadowane z `extension/dist`, a następnie odśwież strony. Rozszerzenie wymaga teraz dostępu do treści zwykłych stron HTTP/HTTPS, żeby wyświetlać przycisk przy zaznaczeniu.
4. Zaznacz od 30 do 3000 znaków. Kliknij przycisk „Zweryfikuj” albo użyj prawego przycisku myszy i opcji „Zweryfikuj zaznaczony tekst”.

Najpierw przy zaznaczeniu pojawia się krótka karta: postęp, a po zakończeniu ocena wyników, maksymalnie dwa zdania podsumowania oraz liczba twierdzeń i unikalnych adresów źródeł. Sygnały perswazji są wskazywane osobno. Podsumowanie jest wyliczane z wyników weryfikacji i nie wymaga dodatkowego zapytania do modelu. „Zobacz szczegóły” otwiera panel z cytatem, źródłami i uzasadnieniami. Karta zamyka się przez × lub Escape i nie otwiera się ponownie przy kolejnych wynikach tej samej analizy. Jeśli strona nie obsługuje karty, otwierany jest widok szczegółowy. Wyjaśnienia z dotychczasowego pipeline'u mogą być po angielsku.

## Zakres i ograniczenia

- Sprawdzenie uruchamia dopiero kliknięcie. Przycisk wysyła zaznaczenie, tytuł, URL bez parametrów i fragmentu oraz do 500 znaków przed i po zaznaczeniu. Menu kontekstowe wysyła zaznaczenie i metadane bez dodatkowego kontekstu.
- Otaczający tekst pomaga interpretować wypowiedź; twierdzenia i sygnały muszą pochodzić z samego zaznaczenia. Nieznana data publikacji nie jest zastępowana dzisiejszą datą.
- Zaznaczenia w edytowalnych polach są pomijane. Przycisk działa na zwykłych stronach, poza stronami chronionymi przez przeglądarkę. Nie obejmuje tekstu rysowanego w canvas, skanów ani zamkniętych shadow roots. Wbudowany czytnik PDF nie jest objęty gwarancją działania.
- Nowe sprawdzenie przerywa poprzednie i odrzuca jego spóźnione wyniki. Cache etapów korzysta z istniejącego `CACHE_ENABLED`; nie dodano trwałej historii zaznaczeń.
- Pewność jest oceną modelu, nie skalibrowanym prawdopodobieństwem. Brak źródeł nie oznacza fałszu; technika retoryczna nie oznacza fałszu.

## Sprawdzenie

Automatycznie: `python -m pytest -q` w backendzie; `npm run typecheck`, `npm run build`, `node --test tests/background.test.mjs` w rozszerzeniu.

Ręcznie w załadowanym rozszerzeniu: zaznaczenie w artykule i komentarzu YouTube, przycisk i menu kontekstowe, Escape i przewijanie, krótkie oraz zbyt długie zaznaczenie, opinia bez twierdzeń, niedostępny backend, dwa kolejne sprawdzenia, zmiana filmu podczas analizy tekstu, ponowienie i kopiowanie. Sprawdź też standardową analizę filmu.
