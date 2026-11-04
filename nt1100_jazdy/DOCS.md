# NT1100 Jazdy

Jazdy ze skrzynki telemetrycznej NT1100 w Home Assistant: ta sama strona co w skrzynce
(panel „NT1100 Jazdy” w menu bocznym, także w aplikacji HA), urządzenie **NT1100**
z encjami (MQTT), pogoda na trasie, przebieg i serwis oraz powiadomienie po każdej jeździe.

- Pliki jazd: folder `share/nt1100/rides` (Samba: udział „share”), razem z kopią
  surowego zapisu (`.mtl`), raportem skrzynki (`.rep`) i pogodą (`.wx`).
- Skrzynka wysyła na port 8098 (w domu: `http://IP-HA:8098`, w trasie przez Cloudflare).
  Bez poprawnego klucza nic nie zostanie przyjęte.
- Klucz i adresy do wpisania w skrzynce: zakładka **Ustawienia** w panelu dodatku.
- Zdarzenie `nt1100_nowa_jazda` (z podsumowaniem i problemami jazdy) do własnych automatyzacji.

## Układ panelu (od 1.5.0)

Cztery zakładki na dole ekranu:

- **Jazdy**: lista jazd i **Statystyki** (przełącznik u góry).
- **Trasy**: mapa na cały ekran z wysuwanym panelem (pociągnij uchwyt albo stuknij go:
  pół ekranu → cały → sama mapa). Wyszukiwarka nad mapą, gdy motocykl jest w trasie,
  u góry pasek „W trasie”.
- **Motocykl**: stan skrzynki, ekranu i silnika tras, przebieg i serwis, parking, skan,
  wersje oprogramowania.
- **Ustawienia**: wszystkie ustawienia w zwijanych grupach, razem z ustawieniami nawigacji.

**Mapa** jest wektorowa, w barwach dodatku (ciemna albo jasna według motywu HA), z cieniowaniem
gór oraz szczytami i przełęczami. Gdy silnik tras w kontenerze zbudował własne kafelki, mapa
pochodzi w całości z domu (przez dodatek); wcześniej korzysta z OpenFreeMap, a bez internetu
dla przeglądarki ze zwykłej mapy OpenStreetMap.

## Wersje oprogramowania

Zakładka **Motocykl** → karta „Wersje oprogramowania” pokazuje w jednym miejscu dodatek, skrzynkę,
ekran i silnik tras: zainstalowaną wersję, najnowszą i co zrobić, gdy jest nowsza (żółta kropka,
u góry strony znaczek „nowa wersja”). Aktualizujesz tylko dodatek: skrzynka pobiera swoją wersję
sama w domowym Wi-Fi, a ekran z Menu → Sprawdź wersję → Aktualizuj.

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

Planowanie tras dla ekranu nawigacji na kierownicy. Trasy liczy silnik tras w kontenerze
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
  na trasę też liczą się najszybciej, a ekran nie pokazuje wyniku zakrętu.
- **Jazda autem z OsmAnd (korki)**: w trybie samochód przycisk „🚗 Jadę (OsmAnd)” zapisuje
  trasę i otwiera arkusz udostępniania (wybierz OsmAnd). Potem dodatek co „Sprawdzanie korków”
  minut patrzy na korki (TomTom) przed telefonem – pozycja z aplikacji Home Assistant
  (`device_tracker` telefonu; domyślnie ten od celu powiadomień, można wpisać w Ustawienia
  nawigacji → Jazda autem). Gdy korek kosztuje co najmniej ustawione minuty, dodatek liczy
  objazd; jeśli jest szybszy, przychodzi powiadomienie – dotknięcie otwiera nowy GPX
  (link z „Adres spoza domu”, podpisany tylko dla tej trasy), dalej „Otwórz w OsmAnd”.
  Jeśli objazd nie jest szybszy, powiadomienie mówi, żeby zostać na trasie. Ten sam korek
  nie wraca co kilka minut. Sprawdzanie kończy się samo 800 m od celu (albo po 8 h,
  albo „Zakończ” na pasku nad punktami). iPhone nie pozwala podmienić trasy w OsmAnd w tle.
  GPX z dodatku (motocykl i samochód) ma manewry w zapisie OsmAnd (skręty, ronda z numerem
  zjazdu) i czas przy każdym punkcie, więc OsmAnd prowadzi głosowo po trasie z dodatku bez
  „Dołącz do dróg” i pokazuje dobry czas przyjazdu.
- **Ulubione miejsca** (szkoła, praca...): gwiazdka ☆ przy wyniku wyszukiwania albo przy punkcie
  trasy zapisuje miejsce. Nad punktami trasy są przyciski ulubionych (i domu) – dotknięcie dodaje je
  do trasy; na mapie żółte kropki. Zmiana nazwy, kolejność i usuwanie: Ustawienia nawigacji →
  Planowanie i dom. Skrót iPhone’a „jedź do” rozumie samą nazwę, np. `text=Praca`.
- **Pomiń miejscowość**: przy wyniku wyszukiwania przycisk „Pomiń” (albo wpisz „pomiń Pszczyna”),
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

### Ekran nawigacji

Ekran na kierownicy dostaje pozycję ze skrzynki (od oprogramowania skrzynki 1.4.1), a trasę,
mapę i ustawienia z dodatku (port 8098, ten sam klucz co skrzynka). Pierwsze uruchomienie:
ekran otwiera własną sieć Wi-Fi „NT1100-Ekran” (hasło `nt1100ekran`); na stronie
`http://192.168.4.1` wpisz Wi-Fi domowe, hotspot telefonu, adres dodatku w domu
(`http://IP-HA:8098`), adres spoza domu i klucz. Dodatek pokazuje ekran w zakładce
Motocykl (ostatnia pozycja, bateria, wersja) i sam oferuje mu nowsze oprogramowanie
(`ekran.bin`, w domu, przy ładowaniu). Na postoju ekran ma strony Stan / Pogoda / Jazda / Menu
(jasność, pobranie mapy, aktualizacja, Wi-Fi, usunięcie trasy); przytrzymanie ekranu
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

**Menu ekranu (ekran 1.1.2).** „Sprawdź wersję” pokazuje na przycisku „Sprawdzam...”, potem „Masz najnowszą”, „Brak Wi-Fi” albo „Brak odpowiedzi”; gdy jest nowsza wersja, przycisk zmienia się na podświetlone „Aktualizuj X”. „Ustawienia Wi-Fi” uruchamiają ekran ponownie prosto w stronę ustawień.

**Mapa z tłem (ekran 1.1.0).** Ekran rysuje pod drogami wody (jeziora, zbiorniki, z wyspami), rzeki i kanały, a na mapie nazwy miejscowości (przy oddaleniu tylko większe). Aktualizując mapę, pobiera tylko kwadraty, które się zmieniły (porównuje rozmiar i sumę kontrolną), w wersji skompresowanej, a kwadraty spoza mapy usuwa. Mapa skopiowana na kartę z ZIP-a jest przyjmowana bez ponownego pobierania.

**Demo trasy** (ekran od 1.0.2): ekran jedzie trasę sam, bez skrzynki i bez wychodzenia
z domu. Bez skrzynki dotknij „Demo trasy” pod napisem „Szukam skrzynki...” (albo na postoju:
strona Menu → „Demo trasy”). Jedzie trasę, która jest na ekranie, a gdy jej nie ma, wbudowaną
trasę Bieruń – Pszczyna (22 km). „Motocykl” trzyma limity, zwalnia przed zakrętami (pochył
do ok. 23°), raz zjeżdża ok. 230 m w bok („wróć na trasę”) i stoi 50 s na pierwszym punkcie po
drodze (pojawiają się strony postoju). Na mapie widać plakietkę DEMO; dotknięcie w trakcie
jazdy przełącza tempo ×1 / ×4. Przytrzymanie 1,5 s: menu z „Szybciej ×4”, „Koniec demo”,
Tankowanie / Jedzenie. Demo niczego nie wysyła do dodatku i kończy się samo minutę po
dojechaniu do celu. Mapa na karcie jest potrzebna tylko do tła mapy, nazw dróg i Tankowania.

**Usypianie i bateria** (ekran od 1.0.3): ekran gaśnie 3 min po tym, jak skrzynka przestanie nadawać (30 min przy ładowaniu), albo po 10 min postoju bez ruchu. Wcześniej przez 10 s pokazuje „Wyłączam się”, a dotknięcie to odwołuje. Nie gaśnie w trakcie pobierania ani w trybie demo. Budzi się dotykiem, po podłączeniu ładowania i sam po włączeniu motocykla (co 30 s nasłuchuje skrzynki, po 6 h co 2 min). Ikonka baterii ma błyskawicę przy ładowaniu (ładowanie jest rozpoznawane z napięcia). Poniżej 15% ekran pokazuje „Słaba bateria”, a poniżej 3,4 V wyłącza się.

**Symulacja w przeglądarce** (dodatek od 1.4.5): w zakładce Trasy → Zapisane trasy
przycisk „Dodaj trasę demo” zapisuje tę samą trasę Bieruń – Pszczyna (z fotoradarem,
odcinkowym pomiarem i postojem; „Na ekran” wysyła ją na ekran). Przycisk „Symulacja” przy
każdej trasie odtwarza przejazd na mapie i obok pokazuje uproszczony podgląd ekranu
(skręty, fotoradary, limit, wynik zakrętu), w tempie ×1 / ×4 / ×10.

## Konfiguracja dodatku

- **powiadomienie**: (starsze) usługa powiadomień bez `notify.`; wybór w panelu ma pierwszeństwo.
- **adres_spoza_domu**: adres dodatku przez Cloudflare (tylko do wyświetlenia na stronie).
- **klucz**: zostaw puste; dodatek wygeneruje klucz sam.
- **mqtt_host / mqtt_port / mqtt_user / mqtt_password**: zostaw puste, by użyć brokera z Home Assistant.
  Własny użytkownik: wpisz tylko `mqtt_user` i `mqtt_password`.
