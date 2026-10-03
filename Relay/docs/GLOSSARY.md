# Relay — słownik dziedziny

Wspólny język projektu. Terminy techniczne zostawiamy po angielsku, żeby zgadzały się z kodem i API.

## Aktorzy

**Mieszkaniec (Citizen)**
Zarejestrowana osoba, która może zgłaszać **skrzynki**, **przejazdy**, albo jedno i drugie. Nie ma osobnych kont „darczyńca” i „kierowca”.
_Avoid_: Donor, User (jako typ konta)

**Administrator (Admin)**
Operator służb, który tworzy **punkty potrzeb** i ustawia ich pilność.
_Avoid_: Dispatcher, Operator

## Dostawa

**Skrzynka (Crate)**
Standardowa jednostka darowizny: jedna **kategoria**, jedna objętość, lokalizacja u darczyńcy. Kierowca przewozi skrzynki zajmujące po jednym **slocie**. Kod QR to rozszerzenie poza MVP — w MVP skrzynka ma tylko tekstowy `id`.
_Avoid_: Resource, Item, Donation, Paczka

**Kategoria (Category)**
Jedna z ustalonych wartości (żywność, woda, leki, higiena, inne), wspólna dla skrzynek i zapotrzebowania punktów potrzeb.
_Avoid_: Type

**Przejazd (Trip)**
Deklaracja mieszkańca, że wykonuje trasę `origin → destination`, z **budżetem objazdu** (ile minut gotów dołożyć) i liczbą **wolnych slotów**. Zastępuje dawne „Transport Offer”. W MVP okno czasowe jest pomijane — liczy się wyłącznie geometria i budżet objazdu.
_Avoid_: Transport Offer, Kurs, Zlecenie

**Budżet objazdu (Detour Budget)**
Maksymalny dodatkowy czas, jaki kierowca zgadza się poświęcić na pomoc, wyrażony w minutach. Wyznacza dopuszczalny koszt objazdu i szerokość korytarza.
_Avoid_: Extra time, Limit

**Punkt potrzeb (Need-Point)**
Lokalizacja utworzona przez administratora z **zapotrzebowaniem** (per kategoria) i **pilnością**. Otwarty, dopóki zapotrzebowanie nie zostanie zaspokojone.
_Avoid_: Incident, Site, Demand

**Zapotrzebowanie (Requirement)**
Ilości per kategoria, których punkt potrzeb jeszcze potrzebuje (`remaining = needed − delivered`). Maleje w miarę dostaw; punkt zamyka się, gdy wszystko osiągnie zero.
_Avoid_: Quota, Need

**Pilność (Severity)**
Waga 1–5 przypisana punktowi potrzeb. Steruje sprawiedliwością: wklęsła użyteczność premiuje obsługę punktów o wyższej pilności.
_Avoid_: Priorytet (jako osobny byt)

## Dopasowanie

**Optymalizacja (Run)**
Jedno przeliczenie solvera nad pulą, produkujące zero lub więcej **sugerowanych objazdów**. W MVP odbywa się przy każdym `GET /state` (po każdym zdarzeniu).
_Avoid_: Solve, Batch, Cycle

**Pula (Residual Pool)**
Skrzynki i przejazdy nieprzypisane jeszcze do żadnego przejętego objazdu. Tylko ją widzi optymalizacja.
_Avoid_: Backlog, Queue

**Objazd (Detour)**
Skrzynki zebrane wzdłuż korytarza jednego przejazdu i dostarczone do jednego punktu potrzeb. Powstaje jako **sugerowany objazd**, zanim kierowca go przejmie.
_Avoid_: Route, Trip, Job

**Sugerowany objazd (Suggested Detour)**
Efemeryczna propozycja objazdu przed przejęciem. Nie jest zapisywana w bazie; nie rezerwuje zasobów i znika przy następnym przeliczeniu (zob. ADR 0005). Sugestie w jednym przeliczeniu są wzajemnie rozłączne.
_Avoid_: Proposal, Draft

**Przejęcie (Claim)**
Jawna akceptacja sugerowanego objazdu przez kierowcę. Atomowa transakcja: skrzynki stają się `claimed`, przejazd `used`, zapotrzebowanie maleje.
_Avoid_: Accept, Assignment

## Metryki i UX

**Korytarz (Corridor)**
Obszar wokół łamanej `[O, N, D]` dla pary przejazd–punkt, o szerokości wynikającej z budżetu objazdu. Tylko skrzynki w korytarzu są brane pod uwagę.
_Avoid_: Buffer, Strefa

**Starvation Index**
Ważony pilnością wskaźnik niezaspokojonego zapotrzebowania:
`Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`. Główna metryka sprawiedliwości w demo.
_Avoid_: Deficit, Braki

**Zapełnienie (Fill)**
Procent zaspokojenia punktu potrzeb: `100% · (1 − unmet/capacity)`.
_Avoid_: Completion

**Checkpoint**
Ręczne potwierdzenie przez kierowcę (odebrane / dostarczone). Opcjonalne i poza MVP.
_Avoid_: Status update
