# NT1100 Jazdy

Jazdy ze skrzynki telemetrycznej NT1100 w Home Assistant: panel „NT1100 Jazdy” w menu bocznym
(także w aplikacji HA; strona skrzynki ma tylko listę jazd i jej ustawienia), urządzenie **NT1100**
z encjami (MQTT), pogoda na trasie, przebieg i serwis oraz powiadomienie po każdej jeździe.

- Pliki jazd: folder `share/nt1100/rides` (Samba: udział „share”), razem z kopią
  surowego zapisu (`.mtl`), raportem skrzynki (`.rep`) i pogodą (`.wx`).
- Skrzynka wysyła na port 8098 (w domu: `http://IP-HA:8098`, w trasie przez Cloudflare).
  Bez poprawnego klucza nic nie zostanie przyjęte.
- Klucz i adresy do wpisania w skrzynce: zakładka **Ustawienia** w panelu dodatku.
- Zdarzenie `nt1100_nowa_jazda` (z podsumowaniem i problemami jazdy) do własnych automatyzacji.

## Przed wyjazdem, w trasie, po powrocie, gdy coś padnie

**Przed wyjazdem (w domu, w Wi-Fi)**
1. Panel → Motocykl → „Wersje oprogramowania”: wszystkie kropki zielone (dodatek, skrzynka, ekran).
2. Trasy → zaplanuj i „Wyślij na ekran”; ekran pobiera trasę i mapę w domowym Wi-Fi.
3. Bateria ekranu (NP-F) naładowana; iPhone połączony z ekranem (Bluetooth).
4. Zapas na wszelki wypadek: w OsmAnd na iPhonie pobrana mapa Polski, a trasa jako GPX („🚗 Jadę (OsmAnd)” albo link z powiadomienia).

**W trasie**
- Bez internetu ekran prowadzi wgraną trasą, pokazuje limity, fotoradary i stacje z mapy na karcie,
  wraca na trasę z bliska i prowadzi „Do domu” po przejechanej drodze.
- Nowa trasa, objazd z domu, korki, ceny paliw i pogoda na bieżąco – tylko z hotspotem iPhone'a
  (w ustawieniach ekranu wpisany hotspot i adres spoza domu).
- Skrzynka zapisuje jazdę na kartę; wyśle ją przez hotspot albo po powrocie do domu.

**Po powrocie**
- Jazdy przychodzą same po wjeździe w domowe Wi-Fi; powiadomienie po jeździe w telefonie.
- Ekran w domu sam pobiera nowsze oprogramowanie i mapę (przy ładowaniu).

**Gdy coś padnie**

| Co | Co się dzieje | Co zrobić |
|---|---|---|
| Brak internetu w trasie | ekran prowadzi wgraną trasą; nowej trasy nie policzy | jedź wgraną trasą albo przełącz na OsmAnd |
| Brak prądu albo internetu w domu | planer i odbiór jazd czekają; motocykl jedzie normalnie | nic – skrzynka wyśle zaległe jazdy sama |
| Padnie zasilanie motocykla | ekran działa na baterii; skrzynka kończy zapis | ładuj baterię ekranu przed wyjazdem |
| Awaria ekranu | brak nawigacji na kierownicy | OsmAnd na iPhonie z GPX trasy |
| Awaria skrzynki | ekran prowadzi na własnym GPS; jazda się nie zapisze | po powrocie sprawdź kartę skrzynki |
| Planer nie liczy tras | silnik tras w domu wyłączony albo w przebudowie | Motocykl → „Ekran i mapa” pokazuje powód; ekran ma ostatnią mapę |
| Zginął ekran | na ekranie jest klucz do dodatku | Ustawienia → Połączenie ze skrzynką i ekranem → **Nowy klucz ekranu** i zaznacz „Ekran tylko z własnym kluczem”; skrzynka działa dalej |

Więcej objawów i przyczyn: `docs/problemy.md` w repozytorium.

## Zmiany w 1.5.40 (ekran 2.2.1)
- Ekran Tab5 pokazuje na pasku u góry ikonę serwera: zielona = silnik tras liczy trasy (korki, alternatywy z serwera), pomarańczowa = dodatek odpowiada, silnik nie (np. w nocy w czasie przebudowy mapy), szara = brak połączenia, trasy liczy ekran z karty. Dodatek sprawdza silnik w tle najwyżej raz na minutę.

## Zmiany w 1.5.39
- Formularz trasy: strzałki w górę i w dół przy każdym przystanku zamieniają go z sąsiednim (trasa liczy się od nowa).
- Karta „Trwa jazda w OsmAnd” wyjaśnia, że nowa trasa nie zastąpi trwającej jazdy, i ma przycisk „Zakończ jazdę”.

## Zmiany w 1.5.38 (skrzynka 1.4.7)

- **Postój w domu**: skrzynka na biurku rozpoznaje postój także wtedy, gdy GPS w budynku „skacze” (0–4 km/h),
  jeśli przez minutę się nie rusza (czujnik ruchu). Strona skrzynki otwiera się sama po 2–3 minutach, a z nią sprawdzanie aktualizacji.
- **Test auta bez dotyku**: na stronie skrzynki, zakładka Stan, przycisk „Test auta (osobny profil)”. Nie trzeba otwierać obudowy.

## Zmiany w 1.5.37 (kłódka i pełny ekran na mapach jazd)
- Mapy w jeździe, w całym wyjeździe i mapa wszystkich tras mają te same przyciski co mapa Tras: 🔒 kłódka (na telefonie
  domyślnie zamknięta: jeden palec przewija stronę, mapę powiększasz dwoma palcami), ⤢ cała trasa, ⛶ pełny ekran mapy.

## Zmiany w 1.5.36 (skrzynka 1.4.6: jednorazowy test auta)

- Skrzynka dostaje wersję **1.4.6**. Dla motocykla nic się nie zmienia. W ekranie skanu jest nowy przycisk
  **„Test auta (osobny profil)”**: to jednorazowy sprawdzian, co pokazuje złącze diagnostyczne samochodu.
- W profilu auto skrzynka nie nagrywa jazd, nie uczy się kalibracji, niczego nie wysyła i nie zmienia ustawień
  motocykla. Pliki trafiają tylko do folderu `/auto` na karcie i nie pojawiają się w dodatku.
- Domyślnie skrzynka tylko słucha (nic nie nadaje). Zapytania OBD2 są pod osobnym przyciskiem i wymagają potwierdzenia.
- Powrót do motocykla: przycisk „Wróć do motocykla”, a skrzynka wraca też sama po 10 uruchomieniach.

## Zmiany w 1.5.35 (porządki i osobny klucz ekranu)

- **Osobny klucz ekranu**: Ustawienia → Połączenie ze skrzynką i ekranem pokazuje „Klucz ekranu”, przycisk
  „Nowy klucz ekranu” (stary przestaje działać od razu) i „Ekran tylko z własnym kluczem”. Dopóki tego nie
  zaznaczysz, ekran wchodzi też starym kluczem skrzynki, więc nic nie trzeba zmieniać od razu.
- Oprogramowania ekranu 2,8" w dodatku już nie ma (zszedł z motocykla); karta wersji porównuje tylko ekran 5".
- Nowa sekcja „Przed wyjazdem, w trasie, po powrocie, gdy coś padnie” (wyżej).

## Układ panelu (od 1.5.0)

Cztery zakładki na dole ekranu:

- **Jazdy**: lista jazd i **Statystyki** (przełącznik u góry).
- **Trasy**: mapa na cały ekran z wysuwanym panelem (pociągnij uchwyt albo stuknij go:
  pół ekranu → cały → sama mapa). Nad mapą pole „Dokąd jedziesz?”, w panelu trzy zakładki:
  **Planuj** (Start i Cel jak w nawigacji), **Moje trasy**, **W trasie**. Gdy motocykl jedzie albo stoi
  ponad 2 km od domu, u góry pasek „W trasie”.
- **Motocykl**: na górze cztery kafle (przebieg, najbliższy serwis, skrzynka, ekran), niżej stan skrzynki, ekranu i silnika tras, przebieg i serwis, parking, skan,
  wersje oprogramowania.
- **Ustawienia**: wszystkie ustawienia w zwijanych grupach, razem z ustawieniami nawigacji.

**Mapa** w panelu jest wektorowa, w barwach dodatku (ciemna albo jasna według motywu panelu), z cieniowaniem
gór oraz szczytami i przełęczami. Gdy silnik tras w kontenerze zbudował własne kafelki, mapa
pochodzi w całości z domu (przez dodatek); wcześniej korzysta z OpenFreeMap, a bez internetu
dla przeglądarki ze zwykłej mapy OpenStreetMap.

## Zmiany w 1.5.34 (ceny paliw w panelu)
- Na mapie w panelu (warstwa „Stacje”) i na liście „Po drodze” stacje paliw pokazują cenę Pb95 z Google (ten sam klucz co dla ekranu, w Ustawieniach nawigacji). Cena pojawia się w dymku stacji po kliknięciu, a na liście przy pierwszych sześciu stacjach. Pamięć ceny to 1 godzina, więc kolejne podglądy nie kosztują zapytań. Bez klucza lub bez ceny stacja wygląda jak dotąd.
- W Ustawieniach nawigacji, pod kluczem Google, jest licznik zapytań do Google w bieżącym miesiącu (liczone są tylko zapytania, które naprawdę poszły, nie te z pamięci). Od 500 zapytań napis robi się czerwony. Alert budżetu nadal ustawia się w Google Cloud (Rozliczenia → Budżety i alerty).

## Zmiany w 1.5.33 (ekran 5" 2.0.4: odcinki trasy w kolorach wariantów)

Ekran rysuje linię trasy w kolorach odcinków jak panel (szybko niebiesko, lekko kręto zielono, kręto pomarańczowo, bardzo kręto czerwono, fioletowa obwódka „Mojego planu”), na stronie Trasa pokazuje kolejne warianty, a na liście tras szkic wybranej trasy w tych kolorach; działa offline, bo warianty są w paczce trasy na karcie. Droga powrotu liczona bez internetu jest teraz turkusowa, żeby nie myliła się z fioletem planu.

## Zmiany w 1.5.32 (warianty odcinków dla ekranu)
- Paczka trasy dla ekranu niesie wariant trasy i wariant każdego odcinka „Mojego planu” (kręto, szybko…),
  żeby ekran 5" mógł rysować odcinki w tych samych kolorach co panel. Starszy program ekranu czyta paczkę jak dawniej.

## Zmiany w 1.5.31 („Mój plan” w kolorach odcinków)
- Trasa „Mój plan” (odcinki o różnych wariantach) jest na mapie rysowana w kolorach odcinków: kręto pomarańczowo,
  szybko niebiesko, bardzo kręto czerwono itd., z fioletową obwódką „Mojego planu”. Kolory zgadzają się z paskiem na karcie.
  Tak samo wygląda zapisana trasa otwarta z „Moich tras”.

## Zmiany w 1.5.30 (mapa w jeździe i wyjeździe)
- Naprawiona mapa w pojedynczej jeździe i w całym wyjeździe: od 1.5.26 zamiast mapy z podkładem pokazywał się
  sam szkic trasy (linia na szarym tle). Teraz jest znowu prawdziwa mapa z kafelkami z kontenera, jak w Trasach.

## Zmiany w 1.5.29 (cały wyjazd jak pojedyncza jazda)
- Widok „Cały wyjazd” ma to samo co pojedyncza jazda: odtwarzanie (przechył, prędkość, przeciążenia, suwak),
  wykresy prędkości, wysokości, przechyłu i spalania (czas | dystans), strefy przechyłu i własny wykres.
- Jazdy wyjazdu idą w nim jedna po drugiej; przerwy między nimi są pominięte, więc odtwarzanie nie stoi na postojach.
- Pojedyncze jazdy dalej otwierasz z listy „Jazdy w tym wyjeździe”, która jest teraz zaraz pod mapą.

## Zmiany w 1.5.28 (krętość tras: bez skrzyżowań, mocniejsze „kręto”)
- °/km zaplanowanej trasy nie liczy już skrętów na skrzyżowaniach (±40 m od skrętu z silnika tras),
  więc trasa przez miasto nie wygląda na krętą tylko dlatego, że skręca na wielu rogach.
- Gdy dwa warianty wychodzą tą samą drogą (różnica poniżej 0,3 km i 1 min), pokazuje się jedna
  karta, np. „Kręto = Bardzo kręto”, zamiast dwóch takich samych.
- Wariant „kręto” mocniej szuka zakrętów (suwak „zakręty” domyślnie 80 zamiast 60). Pomiar na
  6 trasach z domu: kręto jest teraz zawsze między „lekko” a „bardzo kręto”. Własne ustawienia
  suwaków zapisane w panelu zostają bez zmian.
- Narzędzie `narzedzia/kretosc_diag.py` liczy te same trasy w każdym wariancie i porównuje krętość.

## Zmiany w 1.5.27 (serwis w dodatku Pojazdy)

Gdy zainstalowany jest dodatek **Pojazdy** (to samo repozytorium), serwis motocykla prowadzi on: terminy
(data i/lub przebieg), przypomnienia w telefonie i koszty. NT1100 Jazdy w zakładce Stan dalej pokazuje,
ile zostało do każdej pozycji, ale nie wysyła już własnych przypomnień, a jego encje serwisu
(`sensor.nt1100_serwis_*`, przyciski „zrobiony”) znikają – zastępują je encje Pojazdów
(`sensor.pojazdy_nt1100_terminy`). Pozycje serwisu przenoszą się same przy pierwszym uruchomieniu
Pojazdów. Bez dodatku Pojazdy wszystko działa jak dotąd.
## Zmiany w 1.5.26 (wygląd panelu: cel jak w nawigacji, cały wyjazd na mapie)

- **Planowanie trasy** jak w nawigacji: pola **Start** (domyślnie pozycja motocykla albo dom) i **Dokąd jedziesz?**,
  „+ przystanek”, „⇅” zamienia start z celem, ✕ usuwa punkt. Dotknięcie pola (albo „Dokąd jedziesz?” nad mapą)
  otwiera wyszukiwarkę na cały ekran: podpowiedzi w trakcie pisania (bez Entera), na górze pozycja motocykla,
  dom, moja pozycja z telefonu, „Wskaż na mapie”, ulubione i ostatnio wybrane. Wyniki to adresy i miejscowości
  (przez internet) oraz **miejsca z mapy na kartę** (stacje, jedzenie, noclegi…, działają bez internetu).
  Link z Map Google/Apple albo współrzędne też działają. Po wybraniu celu trasa liczy się sama.
- Dotknięcie mapy pokazuje małe menu: **Jedź tutaj**, **Przystanek**, **Start stąd** (nic się nie dodaje przypadkiem).
- **Pinezki**: zielona start, niebieskie przystanki z numerem, czerwona z flagą cel (bez ucinanych napisów).
- Panel Tras w zakładkach **Planuj · Moje trasy · W trasie**; przełącznik **Do celu | Pętla z powrotem**
  (pętla na km albo na czas, także własna długość). „Pomiń miejscowość” → „+ omiń miejscowość” z tą samą wyszukiwarką.
- Warianty tras: duży czas i km, jeden główny przycisk „Wyślij na ekran”. **Moje trasy**: dotknięcie = pokaż,
  obok „Na ekran” i menu ⋯ (symulacja, GPX, usuń).
- **Jazdy → wyjazd** (jazdy połączone przerwą krótszą niż ustawiona): „Cały wyjazd na mapie” z przełącznikiem
  **Kolory: przechył | jazdy** (każda jazda swoim kolorem, numery na początku jazd). W szczegółach jazdy, która
  należy do wyjazdu, przycisk „Cały wyjazd · N jazdy ›”. Lista jazd wyjazdu bez powtórzonej godziny.
- Mapy jazd nie rysują „gwiazdy” z dryfu GPS na postoju (poniżej 5 km/h pozycja stoi, skoki szybsze niż 250 km/h
  są pomijane). Dystans i liczby jazdy się nie zmieniają.
- Motocykl: na górze cztery kafle (przebieg, najbliższy serwis, skrzynka, ekran).
- Do zrobienia po aktualizacji: nic. Ustawienia zostają; „ostatnio wybrane” pamięta przeglądarka telefonu.

## Zmiany w 1.5.25 (ekran 5" 2.0.3: pozycja z własnego GPS, gdy skrzynka nie ma fixu)

Ekran 5" dotąd czekał na pozycję ze skrzynki, nawet gdy ta jeszcze jej nie miała. Teraz, gdy skrzynka jest słyszana, ale od 3 s nie podaje pozycji (zimny start, garaż), ekran jedzie na własnym GPS, a przechył i dane silnika dalej bierze ze skrzynki.

## Zmiany w 1.5.24 (ekran 5" 2.0.2: paliwo, ceny, kalendarz; skrzynka 1.4.5: upadek na sucho)

- **Zatankuj, zanim będzie za późno**: ekran 5" porównuje zasięg z motocykla (skrzynka) ze stacjami
  na trasie z mapy na karcie. Gdy po najbliższej stacji nie ma już żadnej w zasięgu (minus 15 km
  zapasu), albo zasięg spadł poniżej 30 km, nad mapą pojawia się na 20 s żółty pasek
  „Zatankuj: … za 12 km” z dźwiękiem. Każda stacja ogłaszana raz. Bez skrzynki (brak zasięgu) nic się nie dzieje.
- **Stacje z cenami**: na postoju Trasa → „Stacja” przy każdej z 3 stacji cena Pb95 i wiek ceny
  („6,19 zł · 2 h temu”), gdy ekran ma internet (hotspot). Ceny z Google (zgłaszane przez kierowców);
  trzeba wpisać **klucz Google Places** w Ustawieniach nawigacji (Google Cloud, włączone „Places API (New)”;
  darmowy limit miesięczny wystarcza na zwykłe użycie). Bez klucza stacje bez cen, jak dotąd. Dodatek
  pamięta cenę stacji przez godzinę. Dla ekranu: `POST /api/nav/fuel_prices {"places":[{lat,lon,name}]}`.
- **Kalendarz na postoju**: zakładka Dom pokazuje dwa najbliższe wydarzenia z kalendarza HA (np. iCloud
  przez integrację CalDAV): „dziś 14:00 Dentysta”. Encja `calendar.…` w Ustawieniach nawigacji → Planowanie i dom.
- **Nowy cel z telefonu**: gdy trasa przyjdzie z dodatku (skrót iPhone’a „Wyślij na motocykl”, „Wyślij na
  ekran” w panelu), ekran pokazuje na 8 s „Nowy cel: …” (przy nowej wersji tej samej trasy: „Trasa: …”).
- **Skrzynka 1.4.5 – podejrzenie upadku, na sucho**: czujnik ruchu i prędkość: (1) uderzenie ≥ 5 g
  i leżenie ≥ 55° przez 2 s, (2) uderzenie przy ≥ 25 km/h i zatrzymanie w 15 s, (3) leżenie zaraz po jeździe
  bez uderzenia. Skrzynka **nic nie robi** poza wpisem w dzienniku jazdy i w raporcie jazdy („problemy”
  w szczegółach jazdy w panelu: „podejrzenie upadku (na sucho) po 12 min: …”). Po kilku jazdach ocenimy
  fałszywe alarmy, dopiero wtedy ekran zapyta „jesteś cały?” i wyśle wiadomość.
- Zakładka Dom na ekranie: kafle bramy i garażu niższe, pod nimi kalendarz i linia połączenia.
## Zmiany w 1.5.23 (szukanie miejsc po nazwie offline, codzienne sprawdzenie kontenera)

- Kontener dokłada do mapy na kartę **spis nazwanych miejsc** z całej mapy (mapa w wersji 5): stacje,
  restauracje, kawiarnie, noclegi, widoki, przełęcze, serwisy motocyklowe, ładowarki, miejsca odpoczynku,
  z nazwą, marką i miejscowością. Ekran 5" znajdzie je bez internetu po kawałkach słów, bez polskich
  znaków: „orlen bier” = Orlen w Bieruniu, „pod lip” = Karczma Pod Lipą. Najbliższe najpierw.
- Dla sprawdzenia: `/api/nav/miejsca?q=…&lat=…&lon=…` szuka tak, jak ekran.
- Kontener sprawdza codziennie o 4:45 nowe skrypty z repozytorium i, gdy zmienił się format mapy na kartę,
  przebudowuje ją z obecnych danych OSM (bez pobierania i bez zatrzymywania tras). Świeże dane OSM nadal
  raz w miesiącu. Starsze kontenery dopiszą sobie to sprawdzenie przy najbliższej aktualizacji.
- Mapa w panelu dodatku się nie zmienia (wektorowa, ciemna albo jasna, z cieniowaniem gór).

## Zmiany w 1.5.22 (adresy na karcie, cel z ekranu przez hotspot)

- Kontener dokłada do mapy na kartę **spis adresów** (mapa w wersji 4): miejscowości, ulice i numery
  z OpenStreetMap. Ekran 5" wybierze z niego cel bez internetu (wpisujesz bez polskich znaków,
  np. „lakowo”, potem ulicę i numer). Wsie bez ulic (np. „Wola 12”) też są. Dwie miejscowości
  o tej samej nazwie – najpierw bliższa.
- Gdy ekran ma internet (hotspot), pyta dodatek, a dodatek silnik tras w domu: cel wybrany na
  ekranie razem z wariantem i omijaniem, które wybrałeś na ekranie, oraz szukanie w internecie
  (firmy, miejsca) i w ulubionych. Kontener nie jest wystawiony do internetu; drogą jest dodatek
  (adres HA spoza domu wpisany w ustawieniach ekranu).
- Dla sprawdzenia: `/api/nav/adres?miasto=…&ulica=…&nr=…` szuka tak, jak ekran.
- Kontener przebuduje mapę przy najbliższej aktualizacji (od 1.5.23 sprawdza codziennie). Program ekranu z wyszukiwaniem adresów przyjdzie w osobnej
  wersji ekranu.

## Zmiany w 1.5.21 (graf tras do nawigacji offline)

- Kontener dokłada do mapy na kartę **graf tras** (pliki `g_*.ntg` obok kwadratów mapy, mapa
  w wersji 3). Z nim ekran 5" będzie liczył trasę sam, bez internetu: z wyborem wariantu (szybko,
  lekko, kręto, bardzo kręto) i omijania (autostrady, płatne, gruntowe, szutrowe) według tych samych
  suwaków co planer. Graf ma też jednokierunkowe i zakazy skrętu. Korków offline nie ma; gdy ekran
  ma internet, może zapytać dodatek o trasę z silnika w domu.
- Kontener sam przebuduje mapę po aktualizacji skryptów (raz, ok. godziny). Mapa na kartę
  urośnie o graf, szacunkowo o kilkaset MB dla całej Polski. Dodatek pobierze go razem z mapą,
  doda do paczki ZIP na kartę i do pobierania przez Wi-Fi (tylko zmienione kwadraty).
- Program ekranu, który z grafu korzysta, przyjdzie w osobnej wersji ekranu. Do tego czasu graf
  leży na karcie i nic nie zmienia.
- Dla sprawdzenia: `/api/nav/offline?from=lat,lon&to=lat,lon&variant=kreto&avoid=autostrady`
  liczy trasę tak, jak policzy ją ekran (długość, czas, punkty).

## Zmiany w 1.5.20 (ekran 5" 2.0.1)

- Ekran 5" 2.0.1: w jeździe małe ikony stacji paliw i restauracji przy trasie (do 150 m od trasy przed
  motocyklem; bez trasy wszystkie w pobliżu). Stacje mają ikonę dystrybutora zamiast litery „P”.

## Zmiany w 1.5.19 (ekran 5" jako główny)

- Ekran 5" jest teraz głównym ekranem na kierownicy. Opis (rozdział „Ekran nawigacji”), instrukcja
  instalacji i lista problemów dotyczą go w pierwszej kolejności. Ekran 2,8" zszedł z motocykla;
  jego opis został niżej jako „Ekran 2,8" (poprzedni)”.
- Tryb **Samochód**: przy policzonej trasie pierwszy jest teraz przycisk „Wyślij na ekran” (ekran 5"
  ma własny GPS, więc prowadzi też w aucie bez skrzynki). „🚗 Jadę (OsmAnd)” zostaje jako zapas.
- Karta „Wersje oprogramowania” porównuje ekran z właściwą paczką (5" z `ekran5`, 2,8" z `ekran`)
  i podaje, gdzie na danym ekranie jest „Sprawdź wersję”.
- Ekran 5" nie był jeszcze sprawdzony na biurku ani w jeździe.

## Zmiany w 1.5.18 (ekran 5")

- Dodatek obsługuje nowy ekran 5" (oprogramowanie 2.x) obok obecnego 2,8". Każdy ekran dostaje
  tylko swoją aktualizację.
- **Brama i garaż**: Ustawienia → Planowanie i dom → pola „Brama” i „Garaż” (encja `cover.…`,
  `button.…`, `switch.…` albo `lock.…`). Ekran 5" pokazuje ich stan na zakładce Dom, a w jeździe
  blisko domu (poniżej 300 m i 15 km/h) dwa duże przyciski. Przycisk działa jak pilot: brama w ruchu
  = stop.
- **Inna trasa na postoju**: ekran 5" dostaje listę 8 ostatnich tras. W domu kopiuje je na kartę,
  więc w trasie można przełączyć się na inną także bez internetu.
- **Do domu**: ekran 5" prosi dodatek o trasę do domu z miejsca, w którym stoi. Bez internetu wraca
  po przejechanej drodze.
- **Oprogramowanie w paczce**: ekran 5" 2.0.0 (mapa lekko pochylona, z drzewkami i numerami dróg,
  teren z mapy 1.5.17) i rejestrator 1.4.4 (wysyła ekranowi 5" pozycję i dane silnika przez
  Bluetooth). Ekran 2,8" zostaje na 1.1.3.

## Zmiany w 1.5.17 (teren w mapie na ekran)

Dotyczy kontenera silnika tras; ekran i dodatek działają jak dotąd.

- Kwadraty mapy na ekran dostają warstwę terenu: lasy (z polanami), łąki i parki, osiedla, przemysł,
  mokradła, cmentarze i boiska. Z niej nowy ekran rysuje mapę w stylu B (pochylona, z drzewkami).
  Obecny ekran tę część pomija. Pola uprawne nie są zapisywane (to tło mapy).
- `aktualizuj.sh` sam pobiera nowe skrypty kontenera z repozytorium (gałąź `main`) i przebudowuje mapę
  na ekran, gdy powstała starszą wersją budowy, także gdy dane OSM się nie zmieniły.
  Wyłączenie: `SAMOAKTUALIZACJA=0` w `/opt/nt1100-trasy/obszar.env`.

## Zmiany w 1.5.16 (ekran 1.1.3)

Dodatek wiezie nowe oprogramowanie ekranu 1.1.3. Ekran zaproponuje je sam (w domu, przy ładowaniu)
albo w Menu → „Sprawdź wersję” → „Aktualizuj 1.1.3”.

- Dolny pasek mówi słowami, co dalej: „w prawo: Wschodnia”, „rondo, 2. zjazd”, „meta: …”, „punkt: …”,
  a przy dalekim manewrze dodaje „· za 12 km”.
- Bez sygnału ze skrzynki pasek pokazuje tylko „brak pozycji” (nie stary manewr ani ograniczenie).
- Menu na postoju: jeden rozmiar napisów, „Restart” i „Usuń trasę” na czerwono. Trasa znika dopiero
  po przytrzymaniu „Usuń trasę” przez 2 s (zwykłe dotknięcie tylko o tym przypomina).
- Ustawienia Wi-Fi ekranu: hasło sieci „NT1100-Ekran” jest nowe przy każdym otwarciu (pokazuje je ekran),
  a zapisane hasła i klucz nie wracają na stronę – puste pole oznacza „zostaw jak jest”.

## Zmiany w 1.5.15 (wygląd)

- Panel nazywa się wszędzie „NT1100 Jazdy”. Plakietka u góry pokazuje, kiedy skrzynka ostatnio się odezwała
  i jej baterię (żółta po 3 dniach ciszy). Trzy kafelki podsumowania w jednym rzędzie.
- Karta jazdy: nazwa albo „skąd → dokąd”, trzy duże liczby (dystans, czas, największy przechył) i jedna szara linia.
  Liczby z przecinkiem. Numer przejazdu tylko w szczegółach.
- Szczegóły jazdy: cztery duże liczby w dwóch rzędach.
- Motocykl: serwis od najbliższego terminu, z paskiem zużycia (żółty od 75%, czerwony po terminie) i małym „✓ Zrobione”.
  Karta „Ekran i mapa” w tym samym układzie co reszta zakładki.
- Trasy: pasek „W trasie” tylko w jeździe albo daleko od domu (wcześniej wisiał zawsze). Gdy mapa się nie wczyta,
  komunikat jest na środku mapy z przyciskiem „Spróbuj jeszcze raz”.
- Motyw domyślnie „jak w telefonie” (ręczny wybór w Ustawieniach → Wygląd zostaje).
- Pole „adres_spoza_domu” w konfiguracji jest domyślnie puste. Jeśli w Ustawieniach panelu adres spoza domu
  jest pusty, wpisz go w Home Assistant: Ustawienia → Dodatki → NT1100 Jazdy → Konfiguracja.

## Zmiany w 1.5.14

- Jazda sprzed zaplanowania trasy nie pokazuje już „Trasa planowana … zgodność 0%”.
- Długie polskie nazwy tras i ulic na ekranie nie kończą się krzaczkiem.
- Objazd korka i „Objazd 1 km” z ekranu nie wpływają na trasę planowaną w tej samej chwili w panelu.
- Szybsze wczytywanie dużych plików GPX i listy jazd; port dla skrzynki odrzuca zapytania bez klucza
  zanim przeczyta ich treść.
- Pełna dokumentacja w repozytorium: katalog `docs/` (architektura, instalacja od zera, problemy, wydanie).

## Wersje oprogramowania

Zakładka **Motocykl** → karta „Wersje oprogramowania” pokazuje w jednym miejscu dodatek, skrzynkę,
ekran i silnik tras: zainstalowaną wersję, najnowszą i co zrobić, gdy jest nowsza (żółta kropka,
u góry strony znaczek „nowa wersja”). Aktualizujesz tylko dodatek: skrzynka pobiera swoją wersję
sama w domowym Wi-Fi, a ekran z zakładki Menu → Sprawdź wersję → Aktualizuj (ekran 2,8":
przytrzymaj ekran → Menu).

## Urządzenie NT1100 (MQTT)

Gdy w Home Assistant działa broker MQTT (dodatek Mosquitto), dodatek sam pobiera jego adres
i login, a encje pojawiają się jako urządzenie „NT1100” (Ustawienia → Urządzenia i usługi → MQTT):
ostatnia jazda (dystans, czas, prędkości, przechyły, paliwo i spalanie szacowane z wtrysku, użycia sprzęgła,
krętość, temperatura, problemy),
kilometry razem i w tym roku, przebieg, serwis (km do terminu + przycisk „zrobione”),
parking (`device_tracker.nt1100_parking`, miejsce końca ostatniej jazdy) i stan skrzynki
(oprogramowanie, ostatni kontakt, bateria, wolne miejsce na karcie).

Bez MQTT najważniejsze czujniki `sensor.nt1100_*` są ustawiane bezpośrednio (jak w 1.1).

## Ustawienia w panelu dodatku

- **Powiadomienie po jeździe**: wybór telefonu z listy. Powiadomienie ma dystans, czas,
  pogodę, krętość trasy, nowe rekordy i problemy jazdy. Osobne przychodzi, gdy do serwisu
  zostaje mniej niż 300 km.
- **Karta pamięci skrzynki**: pojemność i wolne miejsce; opcjonalnie „usuwaj najstarsze jazdy,
  gdy wolnego jest mniej niż X%” (domyślnie nigdy; usuwane są tylko jazdy z pełną kopią w HA).
- **Kopia surowego zapisu przez hotspot**: minimalna zmierzona prędkość (domyślnie 1 Mbit/s,
  „tylko w domu” wyłącza) i bateria skrzynki od 50%.
- **Pogoda na trasie**: Open-Meteo (historia, bez konta) dla startu, co ok. 30 min i końca.
- **Przebieg i serwis**: stan licznika wpisany raz, dalej liczony z jazd; pozycje serwisowe.

## Nawigacja (zakładka „Trasy”)

Planowanie tras dla ekranu nawigacji na kierownicy (ekran 5", także w samochodzie). Trasy liczy silnik tras w kontenerze
Proxmox (katalog `silnik-tras/` w repozytorium, instrukcja w jego README); bez niego działa
wczytywanie plików GPX (np. z Kurvigera).

- **Punkty**: start (pozycja motocykla z ekranu albo dom), dowolna liczba punktów po drodze
  i cel; wyszukiwanie miejsc, wklejenie linku z Map Google/Apple albo współrzędnych,
  kliknięcie na mapie, przeciąganie punktów.
- **Warianty**: najszybciej / lekko kręto / kręto / bardzo kręto liczone obok siebie
  (km, czas, krętość, fotoradary, deszcz na trasie); omijanie dróg gruntowych (polnych,
  leśnych), szutrowych (publicznych z nawierzchnią szutrową – osobna opcja), płatnych,
  autostrad i promów; trasa okrężna o zadanej długości.
- **Motocykl / samochód**: przełącznik na górze „Nowa trasa”. W samochodzie liczona jest
  najszybsza trasa (inne warianty można włączyć ręcznie), skrót „jedź do”, objazdy i powroty
  na trasę też liczą się najszybciej, a ekran nie pokazuje wyniku zakrętu. Główna droga w aucie:
  „Wyślij na ekran” i ekran 5" przełożony do samochodu (prowadzi na własnym GPS).
- **Zapas: jazda z OsmAnd (korki)** – gdy ekranu nie ma pod ręką. W trybie samochód przycisk
  „🚗 Jadę (OsmAnd)” zapisuje
  trasę i otwiera arkusz udostępniania (wybierz OsmAnd). Potem dodatek co „Sprawdzanie korków”
  minut patrzy na korki (TomTom) przed telefonem – pozycja z aplikacji Home Assistant
  (`device_tracker` telefonu; domyślnie ten od celu powiadomień, można wpisać w Ustawienia
  nawigacji → Jazda autem). Gdy korek kosztuje co najmniej ustawione minuty, dodatek liczy
  objazd; jeśli jest szybszy, przychodzi powiadomienie – dotknięcie otwiera nowy GPX
  (link z „Adres spoza domu”, podpisany tylko dla tej trasy), dalej „Otwórz w OsmAnd”.
  Jeśli objazd nie jest szybszy, powiadomienie mówi, żeby zostać na trasie. Ten sam korek
  nie wraca co kilka minut. Sprawdzanie kończy się samo 800 m od celu (albo po 8 h,
  albo „Zakończ” na pasku nad punktami). iPhone nie pozwala podmienić trasy w OsmAnd w tle.
  GPX z dodatku (motocykl i samochód) ma też manewry w zapisie OsmAnd (skręty, ronda z numerem
  zjazdu) i czas przy każdym punkcie, więc OsmAnd prowadzi głosowo po trasie z dodatku bez
  „Dołącz do dróg” i pokazuje dobry czas przyjazdu.
- **Ulubione miejsca** (szkoła, praca...): gwiazdka ☆ przy wyniku wyszukiwania albo przy punkcie
  trasy zapisuje miejsce. Nad punktami trasy są przyciski ulubionych (i domu) – dotknięcie dodaje je
  do trasy; na mapie żółte kropki. Zmiana nazwy, kolejność i usuwanie: Ustawienia nawigacji →
  Planowanie i dom. Skrót iPhone’a „jedź do” rozumie samą nazwę, np. `text=Praca`.
- **Pomiń miejscowość**: przy wyniku wyszukiwania przycisk „Pomiń” (albo wpisz „pomiń Wadowice”),
  albo „+ pomiń miejscowość” i dotknij mapy. Trasa omija koło wokół miejscowości (czerwone
  przerywane na mapie); dotknięcie ✕ usuwa. Objazdy z ekranu też je omijają.
- **Trasa okrężna jednym dotknięciem**: 50 / 100 / 150 / 200 km albo 30 min / 1 h / 1,5 h / 2 h / 3 h
  od startu (bez startu: od domu). Na czas: dodatek dobiera długość tak, żeby czas jazdy
  wyszedł bliski wybranemu (każdy wariant krętości osobno).
- **Krętość po swojemu**: w ustawieniach nawigacji suwaki każdego wariantu (unikaj głównych,
  szukaj zakrętów, dłuższa trasa) i progi opisu krętości w °/km (prosta / lekko kręta /
  kręta / bardzo kręta; dotyczą tras i jazd).
- **Mój plan**: przy 3 i więcej punktach między każdymi dwoma punktami jest przycisk krętości
  odcinka; stuknięcie otwiera wybór (najszybciej / lekko kręto / kręto / bardzo kręto / jak cała
  trasa), a odcinki na mapie mają kolor wybranego wariantu (np. dojazd szybko, potem bardzo kręto). Dodatek liczy każdy odcinek osobno i skleja je w dodatkową
  trasę „Mój plan” (pierwsza karta, z paskiem udziału wariantów); objazd z ekranu zachowuje wariant pozostałych odcinków.
- **Mapa po policzeniu jest zablokowana** dla punktów: przesuwasz i powiększasz ją normalnie,
  ale kliknięcie nie dodaje punktów, a punktów nie da się przeciągnąć. 🔒 w rogu odblokowuje
  edycję, ⤢ wraca do widoku całej trasy, ⛶ chowa panel (sama mapa). Gest „wstecz” w aplikacji HA
  nie wyrzuca z zakładki Trasy.
- **Wyślij na ekran**: trasa trafia na ekran przy najbliższym połączeniu (dom albo hotspot).
  Zapisane trasy można pokazać, ustawić na ekran, pobrać jako GPX albo usunąć.
- **GPX dla kolegi**: przycisk „GPX” przy policzonym wariancie (zapisuje trasę bez wysyłania
  na ekran) albo przy zapisanej trasie. Na telefonie otwiera się arkusz udostępniania
  (Wiadomości, WhatsApp, Pliki), na komputerze plik się pobiera.
- **Skrót iPhone’a „Wyślij na motocykl”**: udostępnij miejsce z Map do skrótu, który
  otwiera adres `ADRES-SPOZA-DOMU/api/nav/goto?klucz=KLUCZ&text=LINK` (klucz i adres
  w zakładce Ustawienia). Trasa liczy się z pozycji motocykla domyślnym wariantem.
- **Po drodze**: po wybraniu policzonego wariantu albo „Pokaż” przy zapisanej trasie pod
  planerem pojawia się lista miejsc do 2 km od trasy (stacje, jedzenie, kawa, nocleg, widoki,
  serwis moto, ładowarki) z nazwą, kilometrem trasy i odległością od trasy; „Dodaj” wstawia
  miejsce jako punkt po drodze we właściwej kolejności.
- **W trasie** (karta na górze zakładki, wygodna na telefonie): pozycja motocykla z ekranu
  (gdy łączy się przez hotspot) albo z telefonu i najbliższe miejsca przed Tobą na bieżącej
  trasie (bez trasy: wokół). „Jedź tam” wysyła miejsce na ekran jako postój: ekran prowadzi
  do niego i wraca na trasę ok. 300 m dalej, reszta planu zostaje bez zmian.
- **POI na mapie**: kolorowe punkty z legendą; przy dużym obszarze pokazana jest równomierna
  część punktów (przybliż, żeby zobaczyć wszystkie).
- **Mapa na kartę ekranu**: dodatek pobiera ją z kontenera (raz dziennie sprawdza nowszą), za
  każdym razem tylko kwadraty, które się zmieniły (suma kontrolna w manifeście). Pierwsze wgranie
  najszybciej z paczki ZIP: zakładka Motocykl → „Ekran i mapa” → paczka ZIP na kartę, rozpakuj ją na
  kartę ekranu (folder `mapa`). Dalej ekran dociąga w domu po Wi-Fi tylko zmienione kwadraty,
  najpierw okolicę domu i bieżącej trasy. Mapa ekranu ma też wodę, rzeki i nazwy miejscowości.
- **Przebudowa w kontenerze**: w tej samej karcie widać etap (np. „mapa do przeglądarki 3/5”)
  i czas od startu; w tym czasie trasy mogą się nie liczyć.
- **Korki**: opcjonalny klucz TomTom (darmowy limit dzienny wystarcza); ekran sprawdza
  zdarzenia na trasie co kilka minut przez hotspot.
- **Zgodność jazdy z planem**: w szczegółach jazdy pojawia się trasa planowana, procent
  zgodności, odstępstwa i zdarzenia z ekranu (objazdy, pominięte punkty).
- **Ustawienia nawigacji**: adresy silnika i mapy, klucz TomTom, domyślny wariant,
  próg pochyłu dla wyniku zakrętu, częstość korków, próg zjazdu z trasy, dom.

### Ekran nawigacji (5")

Główny ekran na kierownicy to ekran 5" (oprogramowanie 2.x). Ma własny GPS, więc prowadzi także
bez skrzynki (np. przełożony do samochodu). Na motocyklu skrzynka (od 1.4.4) dosyła mu przez
Bluetooth swoją pozycję i dane z motocykla (obroty, bieg, gaz, temperatura, kody błędów); skrzynka
zaczyna nadawać ok. 20 s po włączeniu zapłonu. Trasę, mapę, ustawienia i nowe oprogramowanie
ekran dostaje z dodatku (port 8098, ten sam klucz co skrzynka), w domu przez Wi-Fi, w trasie przez
hotspot telefonu.

**Pierwsze uruchomienie.** Program wgrywa się raz kablem USB-C (obraz pełny `ekran5-…-full.bin`
leży razem ze źródłami, nie ma go w tym repozytorium). Ekran bez ustawień otwiera sieć Wi-Fi
„NT1100-Ekran” (hasło pokazuje sam ekran, przy każdym wejściu w ustawienia nowe). Na stronie
`http://192.168.4.1` wpisz Wi-Fi domowe, hotspot telefonu, adres dodatku w domu (`http://IP-HA:8098`),
adres spoza domu i klucz; tam też jasność, wygląd (ciemny / jasny w dzień / jasny), telefon
i dźwięki. Mapa: paczka ZIP na kartę (zakładka Motocykl → „Ekran i mapa”). Później dodatek sam
oferuje nowsze oprogramowanie (`ekran5.bin`), a w domu wgrywa na kartę ulubione i ostatnie trasy.

**Zakładki na postoju**: Trasa, Pogoda, Dom, Motocykl, Muzyka, Telefon, Menu.
- **Trasa**: Objazd 1 km (korek, roboty), Objazd 5 km (zamknięta droga), Pomiń punkt, Inna trasa
  (z karty, bez internetu), Stacja, Jedzenie, Do domu, Koniec (usunięcie trasy: przytrzymaj 2 s).
- **Pogoda**: prognoza na trasie z planowania (deszcz, wiatr, temperatura).
- **Dom**: brama i garaż (encje z Ustawień → Planowanie i dom), drugi dotyk = Stop. Blisko domu
  (poniżej 300 m i 15 km/h) te przyciski pojawiają się same.
- **Motocykl**: dane ze skrzynki i kody błędów; **Muzyka** i **Telefon**: z iPhone’a.
- **Menu**: jasność, Pobierz mapę, Sprawdź wersję / Aktualizuj, dźwięk, Ustawienia Wi-Fi, Demo trasy,
  Restart.

**W jeździe** przytrzymanie ekranu 1,5 s otwiera stronę Trasa z dużymi przyciskami.
Mapa jest lekko pochylona, z drzewkami, numerami dróg i terenem z mapy na karcie; gdy ekran nie
nadąża z rysowaniem, sam przechodzi na płaską. W jeździe kurs jest u góry, na postoju północ.

**Telefon**: iPhone → Ustawienia → Bluetooth → „NT1100 Ekran 5” → zezwól na powiadomienia.
Odpowiedź na wiadomość głosem przez Siri w kasku.

**Zasilanie**: ekran gaśnie, gdy skrzynka milczy 3 min (30 min przy ładowaniu) albo po 10 min postoju,
i budzi się dotykiem, gdy skrzynka znów nadaje albo gdy ruszysz. Zgaszony na samej baterii wyłącza się
całkiem po 20 min, a na zasilaniu 12 V po 6 h.

### Ekran 2,8" (poprzedni)

Zszedł z motocykla. Od wersji 1.5.35 dodatek nie ma już jego oprogramowania (paczki `ekran`) i niczego mu nie proponuje; ekran zostaje na 1.1.3. Opis poniżej dotyczy tylko jego.

Ekran 2,8" dostaje pozycję ze skrzynki (od oprogramowania skrzynki 1.4.1), a trasę,
mapę i ustawienia z dodatku (port 8098, ten sam klucz co skrzynka). Pierwsze uruchomienie:
ekran otwiera własną sieć Wi-Fi „NT1100-Ekran” (hasło pokazuje sam ekran; od ekranu 1.1.3 przy każdym
uruchomieniu ustawień jest nowe, 8 cyfr, wcześniej stałe `nt1100ekran`); na stronie
`http://192.168.4.1` wpisz Wi-Fi domowe, hotspot telefonu, adres dodatku w domu
(`http://IP-HA:8098`), adres spoza domu i klucz. Dodatek pokazuje ekran w zakładce
Motocykl (ostatnia pozycja, bateria, wersja) i sam oferuje mu nowsze oprogramowanie
(`ekran.bin`, w domu, przy ładowaniu). Na postoju ekran ma strony Stan / Pogoda / Jazda / Menu
(jasność, pobranie mapy, aktualizacja, Wi-Fi, restart, usunięcie trasy – od 1.1.3 dopiero po przytrzymaniu 2 s); przytrzymanie ekranu
1,5 s otwiera menu „Objazd 5 km / Pomiń punkt / Objazd 1 km / Tankowanie / Jedzenie”.

**Tankowanie / Jedzenie** (ekran od 1.0.1): ekran sam, z mapy na karcie, znajduje 3 najbliższe
stacje albo miejsca z jedzeniem przed Tobą na trasie (do 40 km, do 1,5 km od trasy; bez trasy:
w promieniu 6 km, najpierw w kierunku jazdy) i pokazuje nazwę, odległość i ile od trasy.
Dotknięcie wybiera miejsce: ekran od razu prowadzi tam z mapy (zielony znacznik i linia),
a gdy jest połączenie, dodatek liczy trasę przez to miejsce i z powrotem na plan. Postój
kończy się po dojechaniu (60 m), nową trasą albo przyciskiem „Koniec postoju” w menu.

**Strona skrzynki a ekran** (skrzynka od 1.4.3): skrzynka nadaje do ekranu także w trybie strony skrzynki. Ekran widzi ją wtedy jako postój, bez pozycji.

Ekran od 1.0.7 jest domyślnie ciemny (jak makieta); w ustawieniach ekranu „Wygląd” można wybrać: ciemny zawsze, jasny w dzień (ciemny w nocy) albo jasny zawsze. Od 1.0.8 wygląd odpowiada makiecie: górny pasek w kolorze stanu (zielony, żółty „brak GPS”, czerwony „brak skrzynki”), widok dzielony (strzałka + mapa) przed skrętem, zoom zależny od odległości do skrętu, przechylony motocykl w wyniku zakrętu.

**Telefon (ekran 1.0.9).** Ekran łączy się z iPhone’em przez Bluetooth, bez żadnej aplikacji: pokazuje wiadomości i połączenia (na postoju można odebrać albo odrzucić), steruje muzyką (poprzedni, pauza, następny), bierze z telefonu godzinę i pokazuje jego baterię. Parowanie jeden raz: iPhone → Ustawienia → Bluetooth → „NT1100 Ekran” → zezwól na powiadomienia. W Ustawieniach → Powiadomienia ustaw „Pokazuj podglądy” na „Zawsze” albo „Gdy odblokowany”, inaczej zamiast treści przyjdzie samo „Powiadomienie”. Potem telefon łączy się sam. Na postoju jest piąta zakładka „Telefon”; w jeździe wiadomość pojawia się na chwilę w prawym górnym rogu mapy, nie zasłaniając strzałki. W ustawieniach ekranu są pola „Telefon” (włącz/wyłącz) i „Dźwięki”.

**Szybsze Wi-Fi (ekran 1.0.10).** Ekran pamięta ostatnią sieć, do której się połączył, i łączy się z nią od razu, bez skanowania. Gdy jej nie ma, robi jedno krótkie skanowanie i wybiera najsilniejszą znaną sieć w zasięgu, zamiast czekać na każdą po kolei. Hotspot iPhone’a (czasem niewidoczny w skanie) próbuje „na ślepo” tylko w jeździe. Od 1.1.1 ekran po włączeniu najpierw przez 20 s szuka skrzynki, a dopiero potem łączy się z Wi-Fi; gdy na sieci nie słyszy skrzynki, po skończonych zadaniach rozłącza się (także w domu) i wraca do szukania, więc nie trzeba wyłączać i włączać skrzynki.

**Bateria ekranu (ekran 1.0.11).** W zakładce Stan jest wiersz „bateria ekranu”: procent, napięcie i „ładuje się”, a bez podłączonego akumulatora „brak akumulatora”.

**Menu ekranu (ekran 1.1.2, układ od 1.1.3).** „Sprawdź wersję” pokazuje na przycisku „Sprawdzam...”, potem „Masz najnowszą”, „Brak Wi-Fi” albo „Brak odpowiedzi”; gdy jest nowsza wersja, przycisk zmienia się na podświetlone „Aktualizuj X”. „Ustawienia Wi-Fi” uruchamiają ekran ponownie prosto w stronę ustawień.

**Mapa z tłem (ekran 1.1.0).** Ekran rysuje pod drogami wody (jeziora, zbiorniki, z wyspami), rzeki i kanały, a na mapie nazwy miejscowości (przy oddaleniu tylko większe). Aktualizując mapę, pobiera tylko kwadraty, które się zmieniły (porównuje rozmiar i sumę kontrolną), w wersji skompresowanej, a kwadraty spoza mapy usuwa. Mapa skopiowana na kartę z ZIP-a jest przyjmowana bez ponownego pobierania.

**Demo trasy** (ekran od 1.0.2): ekran jedzie trasę sam, bez skrzynki i bez wychodzenia
z domu. Bez skrzynki dotknij „Demo trasy” pod napisem „Szukam skrzynki...” (albo na postoju:
strona Menu → „Demo trasy”). Jedzie trasę, która jest na ekranie, a gdy jej nie ma, wbudowaną
trasę próbną (22 km). „Motocykl” trzyma limity, zwalnia przed zakrętami (pochył
do ok. 23°), raz zjeżdża ok. 230 m w bok („wróć na trasę”) i stoi 50 s na pierwszym punkcie po
drodze (pojawiają się strony postoju). Na mapie widać plakietkę DEMO; dotknięcie w trakcie
jazdy przełącza tempo ×1 / ×4. Przytrzymanie 1,5 s: menu z „Szybciej ×4”, „Koniec demo”,
Tankowanie / Jedzenie. Demo niczego nie wysyła do dodatku i kończy się samo minutę po
dojechaniu do celu. Mapa na karcie jest potrzebna tylko do tła mapy, nazw dróg i Tankowania.

**Usypianie i bateria** (ekran od 1.0.3): ekran gaśnie 3 min po tym, jak skrzynka przestanie nadawać (30 min przy ładowaniu), albo po 10 min postoju bez ruchu. Wcześniej przez 10 s pokazuje „Wyłączam się”, a dotknięcie to odwołuje. Nie gaśnie w trakcie pobierania ani w trybie demo. Budzi się dotykiem, po podłączeniu ładowania i sam po włączeniu motocykla (co 30 s nasłuchuje skrzynki, po 6 h co 2 min). Ikonka baterii ma błyskawicę przy ładowaniu (ładowanie jest rozpoznawane z napięcia). Poniżej 15% ekran pokazuje „Słaba bateria”, a poniżej 3,4 V wyłącza się.

**Symulacja w przeglądarce** (dodatek od 1.4.5): w zakładce Trasy → Zapisane trasy
przycisk „Dodaj trasę demo” zapisuje tę samą trasę próbną (z fotoradarem,
odcinkowym pomiarem i postojem; „Na ekran” wysyła ją na ekran). Przycisk „Symulacja” przy
każdej trasie odtwarza przejazd na mapie i obok pokazuje uproszczony podgląd ekranu
(skręty, fotoradary, limit, wynik zakrętu), w tempie ×1 / ×4 / ×10.

## Konfiguracja dodatku

- **powiadomienie**: (starsze) usługa powiadomień bez `notify.`; wybór w panelu ma pierwszeństwo.
- **adres_spoza_domu**: adres dodatku przez Cloudflare (np. `https://nt1100.twojadomena.pl`); pokazywany w Ustawieniach
  i używany w linkach do tras GPX poza domem. Domyślnie pusty.
- **klucz**: zostaw puste; dodatek wygeneruje klucz sam.
- **mqtt_host / mqtt_port / mqtt_user / mqtt_password**: zostaw puste, by użyć brokera z Home Assistant.
  Własny użytkownik: wpisz tylko `mqtt_user` i `mqtt_password`.
