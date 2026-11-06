# Silnik tras NT1100 (kontener Proxmox)

Liczy trasy dla nawigacji (warianty: najszybciej / lekko kręto / kręto / bardzo kręto,
omijanie gruntowych, szutrowych, płatnych, autostrad i promów, trasy okrężne, objazdy) i buduje
mapę na kartę ekranu z danych OpenStreetMap. Dodatek Home Assistant „NT1100 Jazdy”
łączy się z nim w sieci domowej; sam kontener nie musi być widoczny z internetu.

## Instalacja

1. W Proxmoxie utwórz kontener LXC z szablonu Debian 12 (albo 13):
   4 rdzenie, **8 GB RAM**, 30 GB dysku, sieć z dostępem do internetu (DHCP wystarczy,
   ale lepiej stały adres).
2. Skopiuj do kontenera ten katalog (`silnik-tras/`), np.:
   `scp -r silnik-tras root@IP-KONTENERA:/root/`
3. W kontenerze: `cd /root/silnik-tras && bash install-lxc.sh`
   Pierwszy raz trwa ok. 1–2 godziny (pobranie Polski ~2 GB, mapa do przeglądarki,
   dane wysokości gór ~2 GB, mapa na kartę i graf tras).
4. W Home Assistant: dodatek NT1100 Jazdy → zakładka **Ustawienia** → Ustawienia nawigacji:
   - silnik tras: `http://IP-KONTENERA:8989`
   - mapa: `http://IP-KONTENERA:8988`
   Zapisz i kliknij „Pobierz mapę z kontenera”.

Inny obszar niż Polska: `OBSZAR=europe/germany bash install-lxc.sh` (nazwy jak na
download.geofabrik.de). Mniej pamięci: `PAMIEC=4g` (mniejsze obszary).

## Aktualizacja kontenera (np. do mapy z dodatku 1.5.0)

W kontenerze:

```
cd /root && rm -rf nt1100-ha-main
curl -L https://github.com/pbnz7nrwm4-hub/nt1100-ha/archive/refs/heads/main.tar.gz | tar xz
cd nt1100-ha-main/silnik-tras && bash install-lxc.sh
```

Skrypt instaluje brakujące rzeczy (Java 21, Planetiler), zachowuje ustawienia
i buduje to, czego jeszcze nie ma. Pierwsza budowa mapy do przeglądarki zajmuje ok.
30–60 minut, dane wysokości gór kolejne kilkanaście minut; w tym czasie trasy się nie liczą.
Dodatek sam zauważy nową mapę (Ustawienia → Silnik tras, mapa, korki).

Co jest w kontenerze (graf tras, mapa na ekran, mapa do przeglądarki, dane gór, wolne miejsce):

```
/opt/nt1100-trasy/bin/aktualizuj.sh --stan
```

Mapa do przeglądarki potrzebuje na czas budowy kilku GB wolnego miejsca; gdy go brakuje,
skrypt pisze ile i podpowiada `pct resize <numer kontenera> rootfs +10G` (na hoście Proxmox).

## Co działa w kontenerze

- `nt1100-trasy.service` – GraphHopper na porcie 8989 (profil „motocykl”, ustawienia
  w `config.yml`, model bazowy `motocykl.json`; warianty przychodzą z dodatku).
- `nt1100-mapa.service` – serwer na porcie 8988: `www/mapa` (kwadraty 0,1° × 0,1°
  w formacie ekranu i `manifest.json`), `kafelki.pmtiles` (mapa do przeglądarki, podawana
  jako kafelki `/kafelki/Z/X/Y.pbf`) i `www/dem` (wysokości do cieniowania gór).
- cron co miesiąc (2. dnia o 3:15): `aktualizuj.sh` pobiera nowe skrypty kontenera
  z repozytorium (gałąź `main`; wyłączenie: `SAMOAKTUALIZACJA=0` w `obszar.env`), świeże dane OSM
  i buduje mapę i graf od nowa. Mapa na ekran jest przebudowywana także bez nowych danych, gdy
  zbudowała ją starsza wersja `build_map.py` (`build_map.py --wersja` ↔ `"wersja"` w `manifest.json`).
  Ręcznie: `/opt/nt1100-trasy/bin/aktualizuj.sh`.

Dziennik: `journalctl -u nt1100-trasy -f`, `cat /var/log/nt1100-trasy.log`.

## Pliki

- `install-lxc.sh` – instalacja (pakiety, usługi, pierwsza budowa).
- `aktualizuj.sh` – pobranie danych i budowa mapy + grafu.
- `build_map.py` – mapa na kartę z pliku `.osm.pbf` (wymaga `osmium-tool`), od wersji 3 razem
  z grafem tras do nawigacji offline na ekranie (`g_*.ntg`), od wersji 4 także z adresami
  (`a_*.nta`, `a_index.nta`).
  Użycie: `build_map.py mapa.osm.pbf KATALOG [--bbox S,W,N,E]`.
- `config.yml`, `motocykl.json` – ustawienia GraphHoppera.
- `kafelki.sh` – mapa do przeglądarki (Planetiler, schemat OpenMapTiles, bez budynków;
  `MAPA_BUDYNKI=1` w `obszar.env` je dodaje).
- `dem.py` – pobranie wysokości (AWS Terrain Tiles, zoom 5–12) do cieniowania gór.
- `mapa-serwer.py` – serwer mapy.
