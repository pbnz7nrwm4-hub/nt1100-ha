#!/usr/bin/env bash
# Kafle Apex: drogi (z krętością), budynki, tereny, woda, koleje, miejscowości, stacje + 4 style.
# Użycie: build.sh region.osm.pbf nowy-katalog glyphs-katalog
set -euo pipefail
[[ $# == 3 ]] || { echo 'build.sh region.osm.pbf nowy-katalog glyphs-katalog' >&2; exit 2; }
input=$1 out=$2 glyphs=$3
here=$(cd "$(dirname "$0")" && pwd)
prep="$here/apex-prep-vector.py"
test ! -e "$out"
test -s "$glyphs/Noto Sans Regular/0-255.pbf"
test -s "$glyphs/Noto Sans Regular/256-511.pbf"
test -s "$glyphs/Noto Sans Bold/0-255.pbf"
test -s "$glyphs/Noto Sans Bold/256-511.pbf"
test -f "$here/apex-style-moto-day.json"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# jedna funkcja: filtr osmium -> eksport -> warstwa o schemacie z prep-vector.py
layer() { # nazwa rodzaj typ-geometrii filtry...
  local name=$1 kind=$2 geom=$3; shift 3
  osmium tags-filter "$input" "$@" -o "$tmp/$name.osm.pbf" --overwrite
  osmium export "$tmp/$name.osm.pbf" --geometry-types="$geom" -f geojsonseq -o "$tmp/$name.raw" --overwrite
  python3 "$prep" "$kind" "$tmp/$name.raw" "$tmp/$name.jsonl"
}
layer roads roads linestring w/highway=motorway,trunk,primary,secondary,tertiary,residential,unclassified,living_street,motorway_link,trunk_link,primary_link,secondary_link,service
layer building building polygon a/building
layer landcover landcover polygon a/natural=wood,wetland,grassland,scrub,heath a/landuse=forest,farmland,orchard,meadow,grass,village_green,recreation_ground,residential,industrial,retail,commercial,cemetery a/leisure=park,garden,pitch,playground
layer water water polygon a/natural=water a/landuse=reservoir
layer waterway waterway linestring w/waterway=river,stream,canal
layer rail rail linestring w/railway=rail
layer place place point n/place=city,town,village,suburb
layer poi poi point n/amenity=fuel
tippecanoe -o "$tmp/map.pmtiles" -Z6 -z15 --drop-densest-as-needed --extend-zooms-if-still-dropping \
  -L "{\"file\":\"$tmp/water.jsonl\",\"layer\":\"water\",\"minzoom\":6}" \
  -L "{\"file\":\"$tmp/landcover.jsonl\",\"layer\":\"landcover\",\"minzoom\":8}" \
  -L "{\"file\":\"$tmp/waterway.jsonl\",\"layer\":\"waterway\",\"minzoom\":10}" \
  -L "{\"file\":\"$tmp/rail.jsonl\",\"layer\":\"rail\",\"minzoom\":9}" \
  -L "{\"file\":\"$tmp/roads.jsonl\",\"layer\":\"roads\",\"minzoom\":6}" \
  -L "{\"file\":\"$tmp/building.jsonl\",\"layer\":\"building\",\"minzoom\":14}" \
  -L "{\"file\":\"$tmp/place.jsonl\",\"layer\":\"place\",\"minzoom\":6}" \
  -L "{\"file\":\"$tmp/poi.jsonl\",\"layer\":\"poi\",\"minzoom\":12}"
mkdir "$out"
cp "$tmp/map.pmtiles" "$out/"
for s in moto-day moto-night car-day car-night; do cp "$here/apex-style-$s.json" "$out/style-$s.json"; done
cp "$here/apex-style-moto-day.json" "$out/style.json"
cp -R "$glyphs" "$out/glyphs"
printf '%s\n' '{"version":1,"tiles":"map.pmtiles","style":"style.json","core":"core"}' > "$out/manifest.json"
mkdir "$out/core"
