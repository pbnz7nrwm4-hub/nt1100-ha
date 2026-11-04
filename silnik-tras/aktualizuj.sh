#!/bin/bash
# Pobiera świeże dane OSM, buduje mapę na kartę ekranu, kafelki mapy do przeglądarki
# i przebudowuje graf tras.
# Uruchamiane przez install-lxc.sh i co miesiąc z crona.
set -euo pipefail
KAT=/opt/nt1100-trasy
. "$KAT/obszar.env"
PBF="$KAT/dane/mapa.osm.pbf"
URL="https://download.geofabrik.de/${OBSZAR}-latest.osm.pbf"

echo "$(date '+%F %T') pobieranie $URL"
curl -L --fail -sS -z "$PBF" -o "$PBF.nowy" "$URL" || { echo "pobieranie nieudane"; exit 1; }
if [ ! -s "$PBF.nowy" ]; then
  echo "dane bez zmian"
  rm -f "$PBF.nowy"
  if [ -d "$KAT/dane/graf" ] && [ -s "$KAT/www/mapa/manifest.json" ] && [ -s "$KAT/www/kafelki.pmtiles" ]; then
    systemctl start nt1100-mapa.service nt1100-trasy.service
    exit 0
  fi
else
  mv "$PBF.nowy" "$PBF"
fi

echo "$(date '+%F %T') mapa na kartę"
rm -rf "$KAT/www/mapa.nowa"
python3 "$KAT/bin/build_map.py" "$PBF" "$KAT/www/mapa.nowa"
rm -rf "$KAT/www/mapa.stara"
[ -d "$KAT/www/mapa" ] && mv "$KAT/www/mapa" "$KAT/www/mapa.stara"
mv "$KAT/www/mapa.nowa" "$KAT/www/mapa"
rm -rf "$KAT/www/mapa.stara"
systemctl start nt1100-mapa.service

# Planetiler i import GraphHoppera potrzebują dużo pamięci: silnik tras stoi na czas budowy.
systemctl stop nt1100-trasy.service || true
"$KAT/bin/kafelki.sh" "$PBF" || echo "$(date '+%F %T') kafelki nieudane, zostaje poprzednia mapa"

echo "$(date '+%F %T') graf tras (import GraphHopper)"
rm -rf "$KAT/dane/graf"
cd "$KAT"
java -Xmx"${PAMIEC}" -Xms1g -jar "$KAT/graphhopper-web.jar" import "$KAT/config.yml"
systemctl start nt1100-trasy.service
echo "$(date '+%F %T') gotowe"
