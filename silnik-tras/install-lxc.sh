#!/bin/bash
# Silnik tras NT1100 w kontenerze LXC (Debian 12/13) na Proxmoxie.
#
# Instaluje GraphHopper (liczenie tras z wariantami krętości), buduje mapę na kartę
# ekranu z danych OpenStreetMap i uruchamia mały serwer mapy dla dodatku Home Assistant.
#
# Kontener: Debian, 4 rdzenie, 8 GB RAM (import Polski potrzebuje ok. 6 GB), 30 GB dysku,
# sieć z dostępem do internetu. Uruchom jako root w katalogu z tymi plikami:
#   bash install-lxc.sh                          (Polska)
#   OBSZAR=europe/germany bash install-lxc.sh    (inny obszar z download.geofabrik.de)
#
# Po instalacji w dodatku „NT1100 Jazdy” → Nawigacja → Ustawienia nawigacji:
#   silnik tras:  http://IP-KONTENERA:8989
#   mapa:         http://IP-KONTENERA:8988
set -euo pipefail

OBSZAR="${OBSZAR:-europe/poland}"
GH_WERSJA="${GH_WERSJA:-10.0}"
KAT=/opt/nt1100-trasy
PAMIEC="${PAMIEC:-6g}"
TU="$(cd "$(dirname "$0")" && pwd)"

echo "== pakiety"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q openjdk-17-jre-headless osmium-tool python3 curl ca-certificates

echo "== katalogi"
mkdir -p "$KAT"/{dane,modele,www/mapa,bin}
cp "$TU/config.yml" "$KAT/config.yml"
cp "$TU/motocykl.json" "$KAT/modele/motocykl.json"
cp "$TU/build_map.py" "$KAT/bin/build_map.py"
cp "$TU/mapa-serwer.py" "$KAT/bin/mapa-serwer.py"
cp "$TU/aktualizuj.sh" "$KAT/bin/aktualizuj.sh"
chmod +x "$KAT/bin/aktualizuj.sh"
printf 'OBSZAR=%s\nPAMIEC=%s\n' "$OBSZAR" "$PAMIEC" > "$KAT/obszar.env"

echo "== GraphHopper $GH_WERSJA"
if [ ! -s "$KAT/graphhopper-web.jar" ]; then
  curl -L --fail -o "$KAT/graphhopper-web.jar" \
    "https://github.com/graphhopper/graphhopper/releases/download/$GH_WERSJA/graphhopper-web-$GH_WERSJA.jar"
fi

echo "== usługi"
cat > /etc/systemd/system/nt1100-trasy.service <<UNIT
[Unit]
Description=NT1100 silnik tras (GraphHopper)
After=network.target

[Service]
WorkingDirectory=$KAT
EnvironmentFile=$KAT/obszar.env
ExecStart=/bin/sh -c 'exec java -Xmx\${PAMIEC} -Xms1g -jar $KAT/graphhopper-web.jar server $KAT/config.yml'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/nt1100-mapa.service <<UNIT
[Unit]
Description=NT1100 mapa na kartę (serwer plików)
After=network.target

[Service]
ExecStart=/usr/bin/python3 $KAT/bin/mapa-serwer.py $KAT/www 8988
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/cron.d/nt1100-trasy <<CRON
# co miesiąc świeże dane OSM: nowa mapa na kartę i nowy graf tras
15 3 2 * * root $KAT/bin/aktualizuj.sh >> /var/log/nt1100-trasy.log 2>&1
CRON

systemctl daemon-reload
systemctl enable nt1100-mapa.service nt1100-trasy.service

echo "== dane OSM i pierwsza budowa (kilkanaście–kilkadziesiąt minut)"
"$KAT/bin/aktualizuj.sh"

IP=$(hostname -I | awk '{print $1}')
echo
echo "Gotowe. W dodatku NT1100 Jazdy → Nawigacja → Ustawienia nawigacji wpisz:"
echo "  silnik tras:  http://$IP:8989"
echo "  mapa:         http://$IP:8988"
echo "Stan: systemctl status nt1100-trasy nt1100-mapa ; dziennik: journalctl -u nt1100-trasy -f"
