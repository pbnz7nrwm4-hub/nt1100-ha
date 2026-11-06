# Architektura

## Cztery części

```
 motocykl                                   dom
┌──────────────────────────┐   Wi-Fi    ┌────────────────────────────────────────┐
│ SKRZYNKA (rejestrator)   │──────────▶ │ HOME ASSISTANT                         │
│  GPS, czujnik ruchu,     │  jazdy     │  dodatek „NT1100 Jazdy”                │
│  dane z motocykla (CAN,  │  port 8098 │   • panel w menu (Ingress, port 8099)  │
│  tylko słucha), karta SD │            │   • odbiór jazd i paczek (port 8098)   │
│        │ pozycja, silnik │            │   • urządzenie NT1100 (MQTT)           │
│        ▼ (Bluetooth)     │            │   • powiadomienia, pogoda, serwis      │
│ EKRAN NAWIGACJI 5"       │◀────────── │   • planer tras, mapa, korki, brama    │
│  własny GPS, trasa, mapa │  trasa,    └───────────────┬────────────────────────┘
│  z karty, telefon (BT)   │  mapa, fw                  │ sieć domowa
└──────────────────────────┘  port 8098                 ▼
                                        ┌────────────────────────────────────────┐
                                        │ SILNIK TRAS (kontener w Proxmoxie)     │
                                        │  8989 – liczenie tras (GraphHopper)    │
                                        │  8988 – mapa ekranu, kafelki, wysokości│
                                        └────────────────────────────────────────┘
```

- **Skrzynka** zapisuje jazdę na kartę (surowy zapis `.mtl`), po jeździe liczy z niego ślad
  (`.trk`), miniaturę (`.thm`), podsumowanie (`.json`) i raport (`.rep`). Po powrocie do domu
  (albo przez hotspot telefonu) wysyła je do dodatku. Ma własną stronę WWW (sieć Wi-Fi „NT1100”).
- **Ekran** 5" na kierownicy ma własny GPS (działa też w samochodzie, bez skrzynki); na motocyklu
  skrzynka dosyła mu przez Bluetooth pozycję i dane silnika. Trasę, mapę, ustawienia, stan bramy
  i nowe oprogramowanie dostaje z dodatku. W trasie pyta dodatek o objazdy i korki (przez hotspot).
  Poprzedni ekran 2,8" brał pozycję tylko ze skrzynki (radio ESP-NOW) i ma osobną paczkę `ekran`.
- **OsmAnd** na telefonie to zapas: dodatek daje GPX z manewrami i w aucie pilnuje korków.
- **Dodatek** przechowuje jazdy, pokazuje je w panelu, tworzy encje w Home Assistant,
  planuje trasy i rozsyła oprogramowanie.
- **Silnik tras** liczy trasy i buduje mapę z danych OpenStreetMap (raz w miesiącu).

## Połączenia

| Kto → do kogo | Adres | Zabezpieczenie |
|---|---|---|
| skrzynka → dodatek | `http://IP-HA:8098` w domu, adres spoza domu przez Cloudflare w trasie | nagłówek `X-Klucz` (klucz z panelu dodatku), suma CRC każdego pliku |
| ekran → dodatek | ten sam port 8098 | `X-Klucz` albo `?klucz=`: osobny klucz ekranu (`/data/klucz_ekranu`, od 1.5.35); klucz skrzynki działa dla ekranu, dopóki nie zaznaczono „Ekran tylko z własnym kluczem” |
| telefon → panel dodatku | przez Home Assistant (Ingress) | logowanie Home Assistant |
| dodatek → silnik tras | `http://IP-KONTENERA:8989` i `:8988` | tylko sieć domowa |
| link GPX z powiadomienia | `/api/nav/trasa.gpx?...&t=...` | podpis tylko dla tej trasy i jej wersji |
| skrzynka/ekran ← nowe oprogramowanie | `/api/fw/bin`, `/api/nav/fw/bin` (`&k=ekran5` dla ekranu 5") | plik zaszyfrowany i podpisany; urządzenie przyjmuje tylko podpisany |
| ekran 5" → brama / garaż | `POST /api/nav/dom` | klucz; dodatek przełącza encję z Ustawień |

## Gdzie leżą dane

| Miejsce | Co |
|---|---|
| `/share/nt1100/rides/NNNN.*` | jazdy: `.trk .thm .json .nam .rep .mtl .wx` (folder `share` jest w kopii zapasowej HA) |
| `/share/nt1100/index.json` | które jazdy ze skrzynki już są (ta sama jazda wysłana drugi raz nie dubluje się) |
| `/share/nt1100/nawigacja/` | trasy (`trasy/<id>.json` i `.ntr` dla ekranu), mapa ekranu (`mapa/`), dziennik ekranu (`ekran/`) |
| `/data/stan.json` | ustawienia z panelu (serwis, przebieg, nawigacja, powiadomienia) |
| `/data/klucz` | klucz skrzynki (gdy nie wpisano własnego w konfiguracji) |
| `/data/klucz_ekranu` | klucz ekranu (Ustawienia → „Nowy klucz ekranu” tworzy nowy) |

## Pliki w repozytorium

| Plik | Co robi |
|---|---|
| `nt1100_jazdy/server.py` | serwer dodatku: odbiór jazd, panel, encje, powiadomienia, pogoda, serwis, aktualizacje |
| `nt1100_jazdy/navapi.py` | adresy HTTP nawigacji (panel i ekran), jazda autem z korkami |
| `nt1100_jazdy/nav.py` | planer: silnik tras, GPX, paczka `.ntr` dla ekranu, mapa, korki, zgodność jazdy z planem |
| `nt1100_jazdy/ntt.py` | odczyt mapy ekranu (kwadraty `.ntt`) |
| `nt1100_jazdy/adresy.py` | spis adresów `.nta` na karcie i szukanie miejscowość → ulica → numer oraz nazwanych miejsc (wzorzec dla ekranu) |
| `nt1100_jazdy/graf.py` | graf tras `.ntg` i liczenie trasy offline (wzorzec dla ekranu, te same reguły co planer) |
| `nt1100_jazdy/www/index.html` | panel: jazdy, statystyki, stan, ustawienia |
| `nt1100_jazdy/www/nav.js` | panel: zakładka Trasy (Start/Cel, wyszukiwarka miejsc, pinezki, zakładki Planuj/Moje trasy/W trasie), układ 4 zakładek, kafle i „Ekran i mapa” w Motocyklu |
| `pojazdy/server.py` | dodatek Pojazdy: panel, API, ładowania z historii HA, terminy i powiadomienia, czujniki `sensor.pojazdy_*`, kopia |
| `pojazdy/obliczenia.py` | spalanie „od pełnego do pełnego”, prąd w odcinkach (PHEV), koszty okresów, terminy |
| `pojazdy/ladowania.py` | sesje ładowania z liczników energii, strefa G13, część z PV z bilansu godzinowego, % baterii |
| `pojazdy/fuelio.py` | import i eksport kopii Fuelio (`.fuelio` = ZIP z CSV pojazdów) |
| `pojazdy/baza.py` | baza SQLite `/data/pojazdy.db` |
| `pojazdy/www/index.html` | panel Pojazdy (telefon): Start, Historia, Statystyki, Terminy, Więcej |
| `nt1100_jazdy/firmware/` | gotowe, podpisane obrazy skrzynki i ekranu z numerem wersji |
| `silnik-tras/` | instalacja i aktualizacja kontenera z silnikiem tras i mapą |
| `tests/` | testy (uruchamia je GitHub przy każdej zmianie) |

## Formaty

- `.trk` – CSV, punkt na sekundę: `lat,lon,lean,speed,alt,t,rpm,gear,throttle,coolant,long_g,lat_g`.
- `.thm` – ten sam układ, rzadziej (miniatura, mapa wszystkich tras).
- `.ntr` – trasa dla ekranu (binarnie, little-endian): nagłówek `NTR1` + punkty, skręty,
  limity, fotoradary, pogoda, punkty po drodze; teksty w UTF-8 obcinane bez przecinania liter
  (`nav.pack_ntr`). Od 1.5.32 bajt po wersji w nagłówku = wariant trasy, a bajt po `kind` przystanku = wariant
  odcinka kończącego się na tym przystanku (`nav.VARIANT_CODE`: 1 szybko, 2 lekko, 3 kręto, 4 bardzo, 5 Mój plan; 0 = brak).
- `.nta` – adresy: `a_index.nta` (spis miejscowości) i `a_*.nta` (ulice i numery miejscowości,
  których środek leży w kwadracie); opis bajtów na górze `silnik-tras/build_map.py`. W `manifest.json`
  pod `"addr": {"cells": [...]}`. Tam też `a_poi.nta` (od mapy w wersji 5): nazwane miejsca całej mapy
  do szukania po nazwie offline (`adresy.Addresses.places`).
- `.ntg` – graf tras tego samego kwadratu (skrzyżowania, odcinki dróg z długością, prędkością,
  klasą, nawierzchnią, krętością, zakazy skrętu); opis bajtów na górze `silnik-tras/build_map.py`,
  liczenie w `nt1100_jazdy/graf.py`. W `manifest.json` pod `"graph": {"cells": [...]}`.
- `.ntt` – kwadrat mapy 0,1° × 0,1° (drogi, limity, fotoradary, POI, tło, teren); `manifest.json`
  ma rozmiar i CRC każdego kwadratu, więc ekran pobiera tylko zmienione.

## Dodatek Pojazdy

Osobny dodatek w tym samym repozytorium (osobny kontener, osobne dane `/data/pojazdy.db`, osobny panel).
Nie łączy się ze skrzynką ani z NT1100 Jazdy bezpośrednio – wszystko idzie przez Home Assistant:

- czyta z HA (API Supervisora): przebieg motocykla (`sensor.nt1100_przebieg`), historię liczników energii
  ładowarek i sieci, ceny stref G13, „Wartość kWh”, % baterii auta,
- publikuje do HA czujniki `sensor.pojazdy_*` (REST API, co 10 min i po zmianie) – w tym
  `sensor.pojazdy_nt1100_terminy`, z którego NT1100 Jazdy (od 1.5.27) bierze serwis motocykla,
- powiadomienia o terminach wysyła przez usługę `notify` w HA.
