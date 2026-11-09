#!/bin/bash
# Pobiera świeże dane OSM, buduje mapę na kartę ekranu, kafelki mapy do przeglądarki
# i przebudowuje graf tras.
# Uruchamiane przez install-lxc.sh i co miesiąc z crona. Z --sprawdz (cron codziennie): tylko nowe
# skrypty z repozytorium i przebudowa mapy na kartę, gdy nowy build_map.py ma nowszą wersję mapy
# (bez pobierania OSM i bez zatrzymywania silnika tras).
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
BLAD=""
podsumuj() {  # na końcu: gotowe albo lista tego, co się nie udało (też w stan.json dla dodatku)
  if [ -n "$BLAD" ]; then
    koniec false "trasy działają, ale: $BLAD (dziennik: /var/log/nt1100-trasy.log)"
    echo "$(date '+%F %T') UWAGA: $BLAD – szczegóły wyżej"
  else
    koniec true "$1"
    echo "$(date '+%F %T') gotowe"
  fi
  sprawdz
}
sprawdz() {  # co jest w kontenerze
  echo "Stan kontenera:"
  [ -d "$KAT/dane/graf" ] && echo "  [OK] graf tras" || echo "  [BRAK] graf tras"
  [ -s "$KAT/www/mapa/manifest.json" ] && echo "  [OK] mapa na ekran ($(du -sh "$KAT/www/mapa" | cut -f1))" || echo "  [BRAK] mapa na ekran"
  [ -s "$KAT/www/kafelki.pmtiles" ] && echo "  [OK] mapa do przeglądarki ($(du -h "$KAT/www/kafelki.pmtiles" | cut -f1))" || echo "  [BRAK] mapa do przeglądarki"
  [ -d "$KAT/www/dem" ] && echo "  [OK] dane gór ($(du -sh "$KAT/www/dem" | cut -f1))" || echo "  [BRAK] dane gór"
  echo "  wolne miejsce: $(df -Ph "$KAT" | awk 'NR==2{print $4}')"
}
[ "${1:-}" = "--stan" ] && { sprawdz; exit 0; }
# jedno uruchomienie naraz (codzienne sprawdzenie nie wchodzi w miesięczną budowę)
exec 9>/run/nt1100-aktualizuj.lock
flock -n 9 || { echo "$(date '+%F %T') aktualizacja już trwa"; exit 0; }
# codzienne sprawdzenie w cronie (kontenery zainstalowane przed 1.5.23 miały tylko miesięczne)
if [ -f /etc/cron.d/nt1100-trasy ] && ! grep -q -- "--sprawdz" /etc/cron.d/nt1100-trasy; then
  echo "45 4 * * * root $KAT/bin/aktualizuj.sh --sprawdz >> /var/log/nt1100-trasy.log 2>&1" >> /etc/cron.d/nt1100-trasy
fi
trap 'koniec false "przerwane z błędem (dziennik: /var/log/nt1100-trasy.log)"; systemctl start nt1100-trasy.service nt1100-mapa.service || true' ERR
# przerwanie (Ctrl+C, zamknięte okno konsoli): silnik tras nie zostaje wyłączony
trap 'koniec false "przerwane"; systemctl start nt1100-trasy.service nt1100-mapa.service || true; exit 130' INT TERM HUP
mkdir -p "$KAT/www"

# Skrypty kontenera z repozytorium (gałąź main): poprawki budowy mapy dochodzą same, bez ponownej
# instalacji. Wyłączenie: SAMOAKTUALIZACJA=0 w obszar.env. Ustawień (obszar.env, config.yml) nie rusza.
REPO_TAR="https://github.com/pbnz7nrwm4-hub/nt1100-ha/archive/refs/heads/main.tar.gz"
aktualizuj_skrypty() {
  local tmp zmiany="" plik
  tmp=$(mktemp -d)
  if ! curl -L --fail -sS -m 120 -o "$tmp/repo.tgz" "$REPO_TAR" \
     || ! tar -xzf "$tmp/repo.tgz" -C "$tmp" --strip-components=2 --wildcards '*/silnik-tras/*' \
     || ! bash -n "$tmp/aktualizuj.sh" || ! python3 -m py_compile "$tmp/build_map.py" "$tmp/mapa-serwer.py" "$tmp/siec.py"; then
    echo "$(date '+%F %T') skrypty z repozytorium niedostępne, zostają obecne"
    rm -rf "$tmp"; return 0
  fi
  for plik in build_map.py siec.py mapa-serwer.py aktualizuj.sh kafelki.sh dem.py pusta_woda.py pomiar_mapy.py; do
    [ -s "$tmp/$plik" ] || continue
    if ! cmp -s "$tmp/$plik" "$KAT/bin/$plik"; then
      cp "$tmp/$plik" "$KAT/bin/$plik.nowy" && mv "$KAT/bin/$plik.nowy" "$KAT/bin/$plik"
      zmiany="$zmiany $plik"
    fi
  done
  chmod +x "$KAT/bin/aktualizuj.sh" "$KAT/bin/kafelki.sh"
  rm -rf "$tmp"
  [ -z "$zmiany" ] && return 0
  echo "$(date '+%F %T') nowe skrypty:$zmiany"
  case "$zmiany" in *mapa-serwer.py*) systemctl restart nt1100-mapa.service || true ;; esac
  case "$zmiany" in *aktualizuj.sh*) exec env NT1100_SKRYPTY=1 "$KAT/bin/aktualizuj.sh" "$@" ;; esac
}
if [ "${SAMOAKTUALIZACJA:-1}" != 0 ] && [ -z "${NT1100_SKRYPTY:-}" ]; then
  [ "${1:-}" = "--sprawdz" ] || etap "aktualizacja skryptów" 1
  aktualizuj_skrypty "$@"
fi

# Mapa na ekran zbudowana starszym build_map.py (np. bez warstwy terenu) jest przebudowywana,
# nawet gdy dane OSM się nie zmieniły.
mapa_aktualna() {
  local jest chce
  chce=$(python3 "$KAT/bin/build_map.py" --wersja 2>/dev/null || echo 0)
  jest=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("wersja", 0))' \
         "$KAT/www/mapa/manifest.json" 2>/dev/null || echo 0)
  [ "$jest" -ge "$chce" ] 2>/dev/null
}
buduj_mape() {
  etap "mapa na ekran" 2
  # Budowa mapy (Python, 1–3 GB) obok silnika tras (Java do PAMIEC) nie mieści się w RAM kontenera:
  # silnik szedł do swapu i potem nie liczył tras. Na czas budowy silnik stoi; wraca też po błędzie (trap).
  systemctl stop nt1100-trasy.service || true
  trap 'systemctl start nt1100-trasy.service || true' EXIT
  rm -rf "$KAT/www/mapa.nowa"
  python3 "$KAT/bin/build_map.py" "$PBF" "$KAT/www/mapa.nowa"
  rm -rf "$KAT/www/mapa.stara"
  [ -d "$KAT/www/mapa" ] && mv "$KAT/www/mapa" "$KAT/www/mapa.stara"
  mv "$KAT/www/mapa.nowa" "$KAT/www/mapa"
  rm -rf "$KAT/www/mapa.stara"
  systemctl start nt1100-mapa.service
  systemctl start nt1100-trasy.service || true
}

if [ "${1:-}" = "--sprawdz" ]; then
  if [ -s "$KAT/www/mapa/manifest.json" ] && [ -s "$PBF" ] && ! mapa_aktualna; then
    echo "$(date '+%F %T') nowa wersja mapy na ekran – przebudowa z obecnych danych OSM"
    buduj_mape
    podsumuj "gotowe (nowa wersja mapy na ekran)"
  fi
  exit 0
fi

etap "pobieranie danych OSM" 1
echo "$(date '+%F %T') pobieranie $URL"
curl -L --fail -sS -z "$PBF" -o "$PBF.nowy" "$URL" || { echo "pobieranie nieudane"; koniec false "pobieranie danych OSM nieudane"; exit 1; }
if [ ! -s "$PBF.nowy" ]; then
  echo "dane bez zmian"
  rm -f "$PBF.nowy"
  if [ -d "$KAT/dane/graf" ] && [ -s "$KAT/www/mapa/manifest.json" ]; then
    # graf i mapa na kartę są; dobuduj tylko to, czego brakuje (np. po aktualizacji do 1.5.0)
    systemctl start nt1100-mapa.service
    if ! mapa_aktualna; then
      echo "$(date '+%F %T') mapa na ekran w starszym formacie – przebudowa"
      buduj_mape
    fi
    if [ ! -s "$KAT/www/kafelki.pmtiles" ]; then
      etap "mapa do przeglądarki (trasy nie liczą się)" 3
      systemctl stop nt1100-trasy.service || true
      "$KAT/bin/kafelki.sh" "$PBF" || { echo "$(date '+%F %T') kafelki nieudane"; BLAD="mapa do przeglądarki nieudana"; }
    fi
    systemctl start nt1100-trasy.service
    etap "dane wysokości gór" 4
    python3 "$KAT/bin/dem.py" "$KAT/www" || { echo "$(date '+%F %T') dane wysokości niepełne"; BLAD="${BLAD:+$BLAD, }dane gór niepełne"; }
    podsumuj "gotowe (dane bez zmian)"
    exit 0
  fi
else
  mv "$PBF.nowy" "$PBF"
fi

buduj_mape

# Planetiler i import GraphHoppera potrzebują dużo pamięci: silnik tras stoi na czas budowy.
etap "mapa do przeglądarki (trasy nie liczą się)" 3
systemctl stop nt1100-trasy.service || true
"$KAT/bin/kafelki.sh" "$PBF" || { echo "$(date '+%F %T') kafelki nieudane, zostaje poprzednia mapa"; BLAD="mapa do przeglądarki nieudana"; }
etap "dane wysokości gór (pobiera tylko brakujące)" 4
python3 "$KAT/bin/dem.py" "$KAT/www" || { echo "$(date '+%F %T') dane wysokości niepełne"; BLAD="${BLAD:+$BLAD, }dane gór niepełne"; }

etap "graf tras (trasy nie liczą się)" 5
rm -rf "$KAT/dane/graf"
cd "$KAT"
java -Xmx"${PAMIEC}" -Xms1g -jar "$KAT/graphhopper-web.jar" import "$KAT/config.yml"
systemctl start nt1100-trasy.service
podsumuj "gotowe"
echo "$(date '+%F %T') gotowe"
