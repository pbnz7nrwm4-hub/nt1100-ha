#!/bin/bash
# Apex (aplikacja na Androida): paczka mapy = kafle PMTiles + 4 style + glify + core -> www/apex/map.zip i manifest.json.
# Uruchamia aktualizuj.sh po przebudowie mapy, gdy MAPA_APEX=1 w /opt/nt1100-trasy/obszar.env; ręcznie: apex-paczka.sh
# Błąd nie psuje reszty: poprzednia paczka zostaje. Zależności: osmium-tool, tippecanoe (PMTiles), zip, python3.
#
# Obszar paczki (obszar.env, 28.11): BEZ ustawień paczka obejmuje całą mapę silnika (cała Polska: bardzo duża, nie na kontener
# z 6 GB RAM). Zalecane: APEX_BBOX="S,W,N,E" (np. Śląsk 49.3,17.9,51.2,20.1) – wycinek z dane/mapa.osm.pbf, a kafle i core
# powstają z niego; albo APEX_PBF=ścieżka do gotowego wycinka. Z wycinkiem core buduje się od nowa (build_map.py, ~4 min),
# nie kopiuje się z www/mapa. Uwaga: aktualizuj.sh wczytuje obszar.env bez export, więc ten skrypt czyta go sam.
set -euo pipefail
KAT=/opt/nt1100-trasy
[ -f "$KAT/obszar.env" ] && . "$KAT/obszar.env"
BIN="$KAT/bin"
WWW="$KAT/www"
PBF="${APEX_PBF:-$KAT/dane/mapa.osm.pbf}"
BBOX="${APEX_BBOX:-}"
GLYPHS="${APEX_GLYPHS:-$KAT/dane/apex-glyphs}"
[ -s "$PBF" ] || { echo "apex: brak danych OSM ($PBF)"; exit 1; }
if [ -z "$BBOX" ] && [ -z "${APEX_PBF:-}" ]; then
  [ -s "$WWW/mapa/manifest.json" ] || { echo "apex: brak mapy na ekran (www/mapa)"; exit 1; }
fi
if [ -n "$BBOX" ] && ! [[ "$BBOX" =~ ^-?[0-9.]+,-?[0-9.]+,-?[0-9.]+,-?[0-9.]+$ ]]; then
  echo "apex: APEX_BBOX ma mieć postać S,W,N,E (np. 49.3,17.9,51.2,20.1), jest: $BBOX"; exit 1
fi
for z in "Regular" "Bold"; do
  for r in 0-255 256-511 8192-8447; do
    f="$GLYPHS/Noto Sans $z/$r.pbf"
    [ -s "$f" ] && continue
    mkdir -p "$GLYPHS/Noto Sans $z"
    curl -L --fail -sS --retry 3 -o "$f" "https://raw.githubusercontent.com/klokantech/klokantech-gl-fonts/master/KlokanTech%20Noto%20Sans%20$z/$r.pbf" \
      || { rm -f "$f"; echo "apex: brak glifow $z $r (pobieranie nieudane)"; exit 1; }
  done
done
TMP=$(mktemp -d "$KAT/dane/apex-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
SRC="$PBF"
if [ -n "$BBOX" ]; then
  IFS=, read -r S W N E <<< "$BBOX"
  echo "$(date '+%F %T') apex: wycinek $BBOX z $(basename "$PBF")"
  # osmium chce lon_min,lat_min,lon_max,lat_max; strategia complete_ways (drogi przecięte granicą zostają całe)
  osmium extract -b "$W,$S,$E,$N" --strategy=complete_ways "$PBF" -o "$TMP/region.osm.pbf" --overwrite
  SRC="$TMP/region.osm.pbf"
fi
echo "$(date '+%F %T') apex: kafle i style"
"$BIN/apex-build.sh" "$SRC" "$TMP/paczka" "$GLYPHS"
if [ -n "$BBOX" ] || [ -n "${APEX_PBF:-}" ]; then
  echo "$(date '+%F %T') apex: core z wycinka (build_map.py)"
  rmdir "$TMP/paczka/core"
  # build_map.py szuka kafelków DEM w katalogu „dem” obok katalogu wyjściowego, a siec.py w bin/
  ln -s "$WWW/dem" "$TMP/paczka/dem"
  python3 "$BIN/build_map.py" "$SRC" "$TMP/paczka/core"
  rm -f "$TMP/paczka/dem"
else
  echo "$(date '+%F %T') apex: core z mapy ekranu"
  cp -R "$WWW/mapa/." "$TMP/paczka/core/"
fi
for f in a_index.nta manifest.json; do [ -s "$TMP/paczka/core/$f" ] || { echo "apex: core bez $f"; exit 1; }; done
ls "$TMP/paczka/core"/c_*.ntt >/dev/null 2>&1 || { echo "apex: core bez kwadratów c_*.ntt"; exit 1; }
echo "$(date '+%F %T') apex: zip"
( cd "$TMP/paczka" && zip -0 -q -r "$TMP/map.zip" manifest.json map.pmtiles style.json style-moto-day.json style-moto-night.json style-car-day.json style-car-night.json glyphs core )
BYTES=$(stat -c %s "$TMP/map.zip")
SHA=$(sha256sum "$TMP/map.zip" | cut -d' ' -f1)
printf '{"bytes":%s,"sha256":"%s","built":"%s"}\n' "$BYTES" "$SHA" "$(date -u +%FT%TZ)" > "$TMP/manifest.json"
mkdir -p "$WWW/apex"
mv "$TMP/map.zip" "$WWW/apex/map.zip.nowy"
mv "$TMP/manifest.json" "$WWW/apex/manifest.json.nowy"
mv "$WWW/apex/map.zip.nowy" "$WWW/apex/map.zip"
mv "$WWW/apex/manifest.json.nowy" "$WWW/apex/manifest.json"
echo "$(date '+%F %T') apex: gotowe ($BYTES B, $SHA)"
