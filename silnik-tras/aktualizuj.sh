#!/bin/bash
# Pobiera świeże dane OSM, buduje mapę na kartę ekranu, kafelki mapy do przeglądarki
# i przebudowuje graf tras.
# Uruchamiane przez install-lxc.sh i co miesiąc z crona.
set -euo pipefail
KAT=/opt/nt1100-trasy
. "$KAT/obszar.env"
PBF="$KAT/dane/mapa.osm.pbf"
URL="https://download.geofabrik.de/${OBSZAR}-latest.osm.pbf"
STAN="$KAT/www/stan.json"
OD=$(date +%s)
# Postęp dla dodatku (Motocykl → Silnik tras): www/stan.json, serwer mapy podaje go pod /stan.json.
etap() {  # etap "opis" numer
  printf '{"etap":"%s","krok":%d,"z":5,"od":%d,"t":%d,"pracuje":true}\n' "$1" "$2" "$OD" "$(date +%s)" > "$STAN.tmp"
  mv "$STAN.tmp" "$STAN"
  echo "$(date '+%F %T') [$2/5] $1"
}
koniec() {  # koniec true|false "opis"
  printf '{"etap":"%s","od":%d,"t":%d,"pracuje":false,"ok":%s}\n' "$2" "$OD" "$(date +%s)" "$1" > "$STAN.tmp"
  mv "$STAN.tmp" "$STAN"
}
trap 'koniec false "przerwane z błędem (dziennik: /var/log/nt1100-trasy.log)"; systemctl start nt1100-trasy.service nt1100-mapa.service || true' ERR
mkdir -p "$KAT/www"

etap "pobieranie danych OSM" 1
echo "$(date '+%F %T') pobieranie $URL"
curl -L --fail -sS -z "$PBF" -o "$PBF.nowy" "$URL" || { echo "pobieranie nieudane"; koniec false "pobieranie danych OSM nieudane"; exit 1; }
if [ ! -s "$PBF.nowy" ]; then
  echo "dane bez zmian"
  rm -f "$PBF.nowy"
  if [ -d "$KAT/dane/graf" ] && [ -s "$KAT/www/mapa/manifest.json" ]; then
    # graf i mapa na kartę są; dobuduj tylko to, czego brakuje (np. po aktualizacji do 1.5.0)
    systemctl start nt1100-mapa.service
    if [ ! -s "$KAT/www/kafelki.pmtiles" ]; then
      etap "mapa do przeglądarki (trasy nie liczą się)" 3
      systemctl stop nt1100-trasy.service || true
      "$KAT/bin/kafelki.sh" "$PBF" || echo "$(date '+%F %T') kafelki nieudane"
    fi
    systemctl start nt1100-trasy.service
    etap "dane wysokości gór" 4
    python3 "$KAT/bin/dem.py" "$KAT/www" || echo "$(date '+%F %T') dane wysokości niepełne"
    koniec true "gotowe (dane bez zmian)"
    echo "$(date '+%F %T') gotowe"
    exit 0
  fi
else
  mv "$PBF.nowy" "$PBF"
fi

etap "mapa na ekran" 2
rm -rf "$KAT/www/mapa.nowa"
python3 "$KAT/bin/build_map.py" "$PBF" "$KAT/www/mapa.nowa"
rm -rf "$KAT/www/mapa.stara"
[ -d "$KAT/www/mapa" ] && mv "$KAT/www/mapa" "$KAT/www/mapa.stara"
mv "$KAT/www/mapa.nowa" "$KAT/www/mapa"
rm -rf "$KAT/www/mapa.stara"
systemctl start nt1100-mapa.service

# Planetiler i import GraphHoppera potrzebują dużo pamięci: silnik tras stoi na czas budowy.
etap "mapa do przeglądarki (trasy nie liczą się)" 3
systemctl stop nt1100-trasy.service || true
"$KAT/bin/kafelki.sh" "$PBF" || echo "$(date '+%F %T') kafelki nieudane, zostaje poprzednia mapa"
etap "dane wysokości gór (pobiera tylko brakujące)" 4
python3 "$KAT/bin/dem.py" "$KAT/www" || echo "$(date '+%F %T') dane wysokości niepełne"

etap "graf tras (trasy nie liczą się)" 5
rm -rf "$KAT/dane/graf"
cd "$KAT"
java -Xmx"${PAMIEC}" -Xms1g -jar "$KAT/graphhopper-web.jar" import "$KAT/config.yml"
systemctl start nt1100-trasy.service
koniec true "gotowe"
echo "$(date '+%F %T') gotowe"
