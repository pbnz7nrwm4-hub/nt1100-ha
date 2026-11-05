# Architektura

## Cztery części

```
 motocykl                                   dom
┌──────────────────────────┐   Wi-Fi    ┌────────────────────────────────────────┐
│ SKRZYNKA (rejestrator)   │──────────▶ │ HOME ASSISTANT                         │
│  GPS, czujnik ruchu,     │  jazdy     │  dodatek „NT1100 Jazdy”                │
│  dane z motocykla (CAN,  │  port 8098 │   • panel w menu (Ingress, port 8099)  │
│  tylko słucha), karta SD │            │   • odbiór jazd i paczek (port 8098)   │
│        │ pozycja         │            │   • urządzenie NT1100 (MQTT)           │
│        ▼ (radio)         │            │   • powiadomienia, pogoda, serwis      │
│ EKRAN NAWIGACJI          │◀────────── │   • planer tras, mapa, korki           │
│  trasa, mapa z karty,    │  trasa,    └───────────────┬────────────────────────┘
│  telefon przez Bluetooth │  mapa, fw                  │ sieć domowa
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
- **Ekran** na kierownicy dostaje pozycję ze skrzynki, a trasę, mapę, ustawienia i nowe
  oprogramowanie z dodatku. W trasie pyta dodatek o objazdy i korki (przez hotspot).
- **Dodatek** przechowuje jazdy, pokazuje je w panelu, tworzy encje w Home Assistant,
  planuje trasy i rozsyła oprogramowanie.
- **Silnik tras** liczy trasy i buduje mapę z danych OpenStreetMap (raz w miesiącu).

## Połączenia

| Kto → do kogo | Adres | Zabezpieczenie |
|---|---|---|
| skrzynka → dodatek | `http://IP-HA:8098` w domu, adres spoza domu przez Cloudflare w trasie | nagłówek `X-Klucz` (klucz z panelu dodatku), suma CRC każdego pliku |
| ekran → dodatek | ten sam port 8098 | `X-Klucz` albo `?klucz=` |
| telefon → panel dodatku | przez Home Assistant (Ingress) | logowanie Home Assistant |
| dodatek → silnik tras | `http://IP-KONTENERA:8989` i `:8988` | tylko sieć domowa |
| link GPX z powiadomienia | `/api/nav/trasa.gpx?...&t=...` | podpis tylko dla tej trasy i jej wersji |
| skrzynka/ekran ← nowe oprogramowanie | `/api/fw/bin`, `/api/nav/fw/bin` | plik zaszyfrowany i podpisany; urządzenie przyjmuje tylko podpisany |

## Gdzie leżą dane

| Miejsce | Co |
|---|---|
| `/share/nt1100/rides/NNNN.*` | jazdy: `.trk .thm .json .nam .rep .mtl .wx` (folder `share` jest w kopii zapasowej HA) |
| `/share/nt1100/index.json` | które jazdy ze skrzynki już są (ta sama jazda wysłana drugi raz nie dubluje się) |
| `/share/nt1100/nawigacja/` | trasy (`trasy/<id>.json` i `.ntr` dla ekranu), mapa ekranu (`mapa/`), dziennik ekranu (`ekran/`) |
| `/data/stan.json` | ustawienia z panelu (serwis, przebieg, nawigacja, powiadomienia) |
| `/data/klucz` | klucz dla skrzynki i ekranu (gdy nie wpisano własnego w konfiguracji) |

## Pliki w repozytorium

| Plik | Co robi |
|---|---|
| `nt1100_jazdy/server.py` | serwer dodatku: odbiór jazd, panel, encje, powiadomienia, pogoda, serwis, aktualizacje |
| `nt1100_jazdy/navapi.py` | adresy HTTP nawigacji (panel i ekran), jazda autem z korkami |
| `nt1100_jazdy/nav.py` | planer: silnik tras, GPX, paczka `.ntr` dla ekranu, mapa, korki, zgodność jazdy z planem |
| `nt1100_jazdy/ntt.py` | odczyt mapy ekranu (kwadraty `.ntt`) |
| `nt1100_jazdy/www/index.html` | panel: jazdy, statystyki, stan, ustawienia |
| `nt1100_jazdy/www/nav.js` | panel: zakładka Trasy, układ 4 zakładek, „Ekran i mapa” |
| `nt1100_jazdy/firmware/` | gotowe, podpisane obrazy skrzynki i ekranu z numerem wersji |
| `silnik-tras/` | instalacja i aktualizacja kontenera z silnikiem tras i mapą |
| `tests/` | testy (uruchamia je GitHub przy każdej zmianie) |

## Formaty

- `.trk` – CSV, punkt na sekundę: `lat,lon,lean,speed,alt,t,rpm,gear,throttle,coolant,long_g,lat_g`.
- `.thm` – ten sam układ, rzadziej (miniatura, mapa wszystkich tras).
- `.ntr` – trasa dla ekranu (binarnie, little-endian): nagłówek `NTR1` + punkty, skręty,
  limity, fotoradary, pogoda, punkty po drodze; teksty w UTF-8 obcinane bez przecinania liter
  (`nav.pack_ntr`).
- `.ntt` – kwadrat mapy 0,1° × 0,1° (drogi, limity, fotoradary, POI, tło, teren); `manifest.json`
  ma rozmiar i CRC każdego kwadratu, więc ekran pobiera tylko zmienione.
