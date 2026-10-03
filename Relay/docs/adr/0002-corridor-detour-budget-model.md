# Model korytarza i budżetu objazdu zamiast globalnego VRP

Dopasowanie liczymy lokalnie: każdy **przejazd** to odcinek `origin → destination` z **budżetem objazdu**, a skrzynki i punkty potrzeb wpadają w wyznaczony wokół niego **korytarz**. Zamiast tworzyć nowe kursy (jak w modelu dyspozytorskim) wykorzystujemy przejazdy, które i tak się dzieją. Rozważaliśmy klasyczne podejście — jeden globalny solve nad całą pulą (stary ADR 0004) — oraz niezależne solve per punkt potrzeb (stary ADR 0003). Odrzuciliśmy oba: globalny solve rośnie kosztowo z całym popytem, a per‑punkt gubi konkurencję o te same zasoby. Model korytarza jest z natury przyrostowy, lokalny i tani obliczeniowo.

## Consequences

- Złożoność rzędu `O(przejazdy × pobliskie skrzynki)` — bez macierzy odległości i bez solvera VRP.
- Jakość dopasowania zależy od jakości zadeklarowanych przejazdów; jeśli nikt nie jedzie w danym kierunku, dana skrzynka poczeka.
- Odległości są przybliżone (Haversine), więc `extra_minutes` to szacunek — zawsze pokazujemy go jawnie na mapie.
- Model jest odporny na brak łączności: przejazdy i korytarze można przeliczyć lokalnie, bez chmury.
