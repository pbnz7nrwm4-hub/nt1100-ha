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

## Nawigacja (zakładka „Nawigacja”)

Planowanie tras dla ekranu nawigacji na kierownicy. Trasy liczy silnik tras w kontenerze
Proxmox (katalog `silnik-tras/` w repozytorium, instrukcja w jego README); bez niego działa
wczytywanie plików GPX (np. z Kurvigera).

- **Punkty**: start (pozycja motocykla z ekranu albo dom), dowolna liczba punktów po drodze
  i cel; wyszukiwanie miejsc, wklejenie linku z Map Google/Apple albo współrzędnych,
  kliknięcie na mapie, przeciąganie punktów.
- **Warianty**: najszybciej / lekko kręto / kręto / bardzo kręto liczone obok siebie
  (km, czas, krętość, fotoradary, deszcz na trasie); omijanie dróg gruntowych, płatnych,
  autostrad i promów; trasa okrężna o zadanej długości.
- **Wyślij na ekran**: trasa trafia na ekran przy najbliższym połączeniu (dom albo hotspot).
  Zapisane trasy można pokazać, ustawić na ekran, pobrać jako GPX albo usunąć.
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
- **Mapa na kartę ekranu**: dodatek pobiera ją z kontenera (raz dziennie sprawdza nowszą),
  ekran dociąga ją sam w domu po Wi-Fi.
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
Nawigacja (ostatnia pozycja, bateria, wersja) i sam oferuje mu nowsze oprogramowanie
(`ekran.bin`, w domu, przy ładowaniu). Na postoju ekran ma strony Stan / Pogoda / Jazda / Menu
(jasność, pobranie mapy, aktualizacja, Wi-Fi, usunięcie trasy); przytrzymanie ekranu
1,5 s otwiera menu „Objazd 5 km / Pomiń punkt / Objazd 1 km / Tankowanie / Jedzenie”.

**Tankowanie / Jedzenie** (ekran od 1.0.1): ekran sam, z mapy na karcie, znajduje 3 najbliższe
stacje albo miejsca z jedzeniem przed Tobą na trasie (do 40 km, do 1,5 km od trasy; bez trasy:
w promieniu 6 km, najpierw w kierunku jazdy) i pokazuje nazwę, odległość i ile od trasy.
Dotknięcie wybiera miejsce: ekran od razu prowadzi tam z mapy (zielony znacznik i linia),
a gdy jest połączenie, dodatek liczy trasę przez to miejsce i z powrotem na plan. Postój
kończy się po dojechaniu (60 m), nową trasą albo przyciskiem „Koniec postoju” w menu.

## Konfiguracja dodatku

- **powiadomienie**: (starsze) usługa powiadomień bez `notify.`; wybór w panelu ma pierwszeństwo.
- **adres_spoza_domu**: adres dodatku przez Cloudflare (tylko do wyświetlenia na stronie).
- **klucz**: zostaw puste; dodatek wygeneruje klucz sam.
- **mqtt_host / mqtt_port / mqtt_user / mqtt_password**: zostaw puste, by użyć brokera z Home Assistant.
  Własny użytkownik: wpisz tylko `mqtt_user` i `mqtt_password`.
