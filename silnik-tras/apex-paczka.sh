#!/bin/bash
# Apex (aplikacja na Androida): paczka mapy = kafle PMTiles + 4 style + glify + core (www/mapa) -> www/apex/map.zip i manifest.json.
# Uruchamia aktualizuj.sh po przebudowie mapy, gdy MAPA_APEX=1 w /opt/nt1100-trasy/obszar.env; ręcznie: apex-paczka.sh
# Błąd nie psuje reszty: poprzednia paczka zostaje. Zależności: osmium-tool, tippecanoe (PMTiles), zip, python3.
set -euo pipefail
KAT=/opt/nt1100-trasy
BIN="$KAT/bin"
WWW="$KAT/www"
PBF="$KAT/dane/mapa.osm.pbf"
GLYPHS="${APEX_GLYPHS:-$KAT/dane/apex-glyphs}"
[ -s "$PBF" ] || { echo "apex: brak danych OSM"; exit 1; }
[ -s "$WWW/mapa/manifest.json" ] || { echo "apex: brak mapy na ekran (www/mapa)"; exit 1; }
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
echo "$(date '+%F %T') apex: kafle i style"
"$BIN/apex-build.sh" "$PBF" "$TMP/paczka" "$GLYPHS"
echo "$(date '+%F %T') apex: core z mapy ekranu"
cp -R "$WWW/mapa/." "$TMP/paczka/core/"
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
