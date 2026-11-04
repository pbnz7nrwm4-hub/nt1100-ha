# Silnik tras NT1100 (kontener Proxmox)

Liczy trasy dla nawigacji (warianty: najszybciej / lekko kręto / kręto / bardzo kręto,
omijanie gruntowych, płatnych, autostrad i promów, trasy okrężne, objazdy) i buduje
mapę na kartę ekranu z danych OpenStreetMap. Dodatek Home Assistant „NT1100 Jazdy”
łączy się z nim w sieci domowej; sam kontener nie musi być widoczny z internetu.

## Instalacja

1. W Proxmoxie utwórz kontener LXC z szablonu Debian 12 (albo 13):
   4 rdzenie, **8 GB RAM**, 30 GB dysku, sieć z dostępem do internetu (DHCP wystarczy,
   ale lepiej stały adres).
2. Skopiuj do kontenera ten katalog (`silnik-tras/`), np.:
   `scp -r silnik-tras root@IP-KONTENERA:/root/`
3. W kontenerze: `cd /root/silnik-tras && bash install-lxc.sh`
   Pierwszy raz trwa kilkanaście–kilkadziesiąt minut (pobranie Polski ~2 GB, budowa
   mapy na kartę i grafu tras).
4. W Home Assistant: dodatek NT1100 Jazdy → zakładka **Nawigacja** → Ustawienia nawigacji:
   - silnik tras: `http://IP-KONTENERA:8989`
   - mapa: `http://IP-KONTENERA:8988`
   Zapisz i kliknij „Pobierz mapę z kontenera”.

Inny obszar niż Polska: `OBSZAR=europe/germany bash install-lxc.sh` (nazwy jak na
download.geofabrik.de). Mniej pamięci: `PAMIEC=4g` (mniejsze obszary).

## Co działa w kontenerze

- `nt1100-trasy.service` – GraphHopper na porcie 8989 (profil „motocykl”, ustawienia
  w `config.yml`, model bazowy `motocykl.json`; warianty przychodzą z dodatku).
- `nt1100-mapa.service` – serwer plików na porcie 8988 z katalogiem `www/mapa`
  (kwadraty 0,1° × 0,1° w formacie ekranu i `manifest.json`).
- cron co miesiąc (2. dnia o 3:15): `aktualizuj.sh` pobiera świeże dane OSM, buduje
  mapę i graf od nowa. Ręcznie: `/opt/nt1100-trasy/bin/aktualizuj.sh`.

Dziennik: `journalctl -u nt1100-trasy -f`, `cat /var/log/nt1100-trasy.log`.

## Pliki

- `install-lxc.sh` – instalacja (pakiety, usługi, pierwsza budowa).
- `aktualizuj.sh` – pobranie danych i budowa mapy + grafu.
- `build_map.py` – mapa na kartę z pliku `.osm.pbf` (wymaga `osmium-tool`).
  Użycie: `build_map.py mapa.osm.pbf KATALOG [--bbox S,W,N,E]`.
- `config.yml`, `motocykl.json` – ustawienia GraphHoppera.
- `mapa-serwer.py` – serwer plików mapy.
