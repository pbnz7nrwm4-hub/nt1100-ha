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
D="$KAT/dane/planetiler"
mkdir -p "$D"
# Dane pomocnicze (morze, generalizacja, jeziora) pobiera curl, a nie Java: Java w kontenerze
# potrafi wybrać adres IPv6 bez trasy („No route to host”). Pobierane raz, potem gdy są nowsze.
pobierz() {  # pobierz NAZWA URL
  echo "$(date '+%F %T') pobieranie $1"
  curl -L --fail -sS --retry 3 -z "$D/$1" -o "$D/$1.nowy" "$2" || { rm -f "$D/$1.nowy"; [ -s "$D/$1" ]; return; }
  if [ -s "$D/$1.nowy" ]; then mv "$D/$1.nowy" "$D/$1"; else rm -f "$D/$1.nowy"; fi
}
WODA="$D/water-polygons-split-3857.zip"
if ! pobierz water-polygons-split-3857.zip https://osmdata.openstreetmap.de/download/water-polygons-split-3857.zip; then
  # serwer morza bywa niedostępny: budujemy bez wypełnienia morza (jeziora i rzeki są z OSM),
  # przy następnej przebudowie skrypt spróbuje znowu
  echo "$(date '+%F %T') brak pliku z morzem (osmdata.openstreetmap.de nie odpowiada): mapa bez morza"
  WODA="$D/morze-zastepcze.zip"
  python3 "$KAT/bin/pusta_woda.py" "$WODA"
fi
pobierz natural_earth_vector.sqlite.zip https://dev.maptiler.download/geodata/omt/natural_earth_vector.sqlite.zip
pobierz lake_centerline.shp.zip https://dev.maptiler.download/geodata/omt/lake_centerline.shp.zip
rm -f "$KAT/www/kafelki.nowe.pmtiles"
rm -rf "$D/tmp"
# Miejsce na dysku: pliki tymczasowe Planetilera to kilka razy rozmiar danych OSM.
POTRZEBA=$(( $(stat -c %s "$WE") * 4 / 1048576 + 3072 ))
WOLNE=$(df -Pm "$D" | awk 'NR==2{print $4}')
if [ "$WOLNE" -lt "$POTRZEBA" ]; then
  echo "$(date '+%F %T') za mało miejsca na dysku: wolne $((WOLNE/1024)) GB, potrzeba ok. $((POTRZEBA/1024 + 1)) GB"
  echo "  powiększ dysk kontenera na Proxmoxie: pct resize <numer kontenera> rootfs +10G"
  exit 3
fi
# Węzły w RAM-ie (--storage=ram): na dysku HDD tryb mmap czytał je losowo i budowa szła
# ~200 dróg/s (dziesiątki godzin). Polska potrzebuje ok. 5 GB pamięci Javy; silnik tras
# stoi na czas budowy, więc kontener z 8 GB RAM wystarcza.
HEAP="${PAMIEC_MAPY:-5g}"
[ "$HEAP" = "3g" ] && HEAP=5g   # stara wartość domyślna z obszar.env
"$JAVA21" -Djava.net.preferIPv4Stack=true -Xmx"$HEAP" -jar "$KAT/planetiler.jar" \
  --osm-path="$WE" \
  --water-polygons-path="$WODA" \
  --natural-earth-path="$D/natural_earth_vector.sqlite.zip" \
  --lake-centerlines-path="$D/lake_centerline.shp.zip" \
  --tmpdir="$D/tmp" --storage=ram --nodemap-type=sparsearray \
  --only-layers="$WARSTWY" --maxzoom=14 \
  --output="$KAT/www/kafelki.nowe.pmtiles" --force || { rm -rf "$D/tmp" "$KAT/www/kafelki.nowe.pmtiles"; exit 1; }
mv "$KAT/www/kafelki.nowe.pmtiles" "$KAT/www/kafelki.pmtiles"
rm -rf "$D/tmp"
[ "$WE" != "$PBF" ] && rm -f "$WE"
echo "$(date '+%F %T') kafelki gotowe: $(du -h "$KAT/www/kafelki.pmtiles" | cut -f1)"
