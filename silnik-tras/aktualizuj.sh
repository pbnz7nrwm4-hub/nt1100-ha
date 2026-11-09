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
  # 1.5.48: config.yml i motocykl.json z repozytorium leżą w bin/ jako wzór; do użytku wchodzą dopiero przy budowie
  # grafu (krok 5), bo działający silnik musi pasować do swojego grafu (np. tryb LM z e3)
  for plik in build_map.py siec.py mapa-serwer.py aktualizuj.sh kafelki.sh dem.py pusta_woda.py pomiar_mapy.py config.yml motocykl.json; do
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
# 1.5.48: także po przejściu na nowy aktualizuj.sh (NT1100_SKRYPTY=1) – stara wersja nie znała config.yml
# i motocykl.json, więc nowa pobiera je sama; aktualizuj.sh jest już ten sam, więc nie ma drugiego przejścia
if [ "${SAMOAKTUALIZACJA:-1}" != 0 ]; then
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
# 1.5.48: WYMUS=1 (Adrian 9.11: jedna pełna przebudowa) – pełna budowa także bez nowych danych OSM
if [ ! -s "$PBF.nowy" ] && [ -n "${WYMUS:-}" ] && [ -s "$PBF" ]; then
  echo "$(date '+%F %T') dane OSM bez zmian, ale WYMUS=1: pełna przebudowa z obecnych"
  rm -f "$PBF.nowy"
elif [ ! -s "$PBF.nowy" ]; then
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
# 1.5.48: ustawienia silnika z repozytorium (e3 LM, e5, wysokości) wchodzą razem z nowym grafem; gdy import się nie
# uda, wracają poprzedni graf i poprzednie ustawienia – silnik tras dodatku zawsze ma działający graf
rm -rf "$KAT/dane/graf.stary"
[ -d "$KAT/dane/graf" ] && mv "$KAT/dane/graf" "$KAT/dane/graf.stary"
cp "$KAT/config.yml" "$KAT/config.yml.stary"
cp "$KAT/modele/motocykl.json" "$KAT/modele/motocykl.json.stary"
[ -s "$KAT/bin/config.yml" ] && cp "$KAT/bin/config.yml" "$KAT/config.yml"
[ -s "$KAT/bin/motocykl.json" ] && cp "$KAT/bin/motocykl.json" "$KAT/modele/motocykl.json"
mkdir -p "$KAT/dane/srtm"
cd "$KAT"
if java -Xmx"${PAMIEC}" -Xms1g -jar "$KAT/graphhopper-web.jar" import "$KAT/config.yml"; then
  echo "$(date '+%F %T') graf tras: nowy z ustawieniami z repozytorium"
  rm -rf "$KAT/dane/graf.stary" "$KAT/config.yml.stary" "$KAT/modele/motocykl.json.stary"
else
  echo "$(date '+%F %T') graf tras: import NIEUDANY – wraca poprzedni graf i ustawienia"
  rm -rf "$KAT/dane/graf"
  [ -d "$KAT/dane/graf.stary" ] && mv "$KAT/dane/graf.stary" "$KAT/dane/graf"
  mv "$KAT/config.yml.stary" "$KAT/config.yml"
  mv "$KAT/modele/motocykl.json.stary" "$KAT/modele/motocykl.json"
  BLAD="${BLAD:+$BLAD, }nowy graf tras nieudany (działa poprzedni)"
fi
systemctl start nt1100-trasy.service
podsumuj "gotowe"
echo "$(date '+%F %T') gotowe"
