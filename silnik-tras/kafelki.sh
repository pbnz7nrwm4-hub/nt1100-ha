#!/bin/bash
# Mapa do przeglądarki: kafelki wektorowe (schemat OpenMapTiles) w jednym pliku
# www/kafelki.pmtiles, budowane Planetilerem z tych samych danych OSM co trasy.
# Użycie: kafelki.sh PLIK.osm.pbf   (ustawienia w /opt/nt1100-trasy/obszar.env)
set -euo pipefail
KAT=/opt/nt1100-trasy
. "$KAT/obszar.env"
PBF="$1"
JAVA21="${JAVA21:-java}"
WE="$PBF"

# dodatkowe obszary tylko do oglądania: pobrać i skleić z głównym plikiem
if [ -n "${MAPA_DODATKOWE:-}" ]; then
  LISTA=("$PBF")
  for o in $MAPA_DODATKOWE; do
    f="$KAT/dane/$(echo "$o" | tr '/' '_').osm.pbf"
    echo "$(date '+%F %T') pobieranie $o"
    curl -L --fail -sS -z "$f" -o "$f.nowy" "https://download.geofabrik.de/${o}-latest.osm.pbf"
    [ -s "$f.nowy" ] && mv "$f.nowy" "$f" || rm -f "$f.nowy"
    LISTA+=("$f")
  done
  WE="$KAT/dane/mapa-razem.osm.pbf"
  osmium merge --overwrite -o "$WE" "${LISTA[@]}"
fi

WARSTWY="aeroway,aerodrome_label,boundary,landcover,landuse,park,place,transportation,transportation_name,water,water_name,waterway,mountain_peak"
[ "${MAPA_BUDYNKI:-0}" = "1" ] && WARSTWY="$WARSTWY,building"

echo "$(date '+%F %T') kafelki mapy (Planetiler)"
mkdir -p "$KAT/dane/planetiler"
rm -f "$KAT/www/kafelki.nowe.pmtiles"
"$JAVA21" -Xmx"${PAMIEC_MAPY:-3g}" -jar "$KAT/planetiler.jar" \
  --osm-path="$WE" --download --download-dir="$KAT/dane/planetiler" \
  --tmpdir="$KAT/dane/planetiler/tmp" --storage=mmap --nodemap-type=array \
  --only-layers="$WARSTWY" --maxzoom=14 \
  --output="$KAT/www/kafelki.nowe.pmtiles" --force
mv "$KAT/www/kafelki.nowe.pmtiles" "$KAT/www/kafelki.pmtiles"
rm -rf "$KAT/dane/planetiler/tmp"
[ "$WE" != "$PBF" ] && rm -f "$WE"
echo "$(date '+%F %T') kafelki gotowe: $(du -h "$KAT/www/kafelki.pmtiles" | cut -f1)"
