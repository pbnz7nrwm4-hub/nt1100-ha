#!/bin/bash
# Pojazdy jako aplikacja samodzielna w kontenerze (Debian) – instalacja i aktualizacje.
# Użycie (w kontenerze, jako root):  bash instaluj.sh http://ADRES_HOME_ASSISTANT:8123 [port]
# Ponowne uruchomienie niczego nie psuje: zostawia dane i klucz, odświeża kod i usługi.
set -euo pipefail
HA="${1:-}"
PORT="${2:-8091}"
[ -n "$HA" ] || { echo "Podaj adres Home Assistant, np.: bash instaluj.sh http://ADRES_HA:8123"; exit 1; }
REPO=https://github.com/pbnz7nrwm4-hub/nt1100-ha
KOD=/opt/pojazdy
DANE=/var/lib/pojazdy
ENV=/etc/pojazdy.env

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 git ca-certificates tzdata >/dev/null

id pojazdy >/dev/null 2>&1 || useradd --system --home "$DANE" --shell /usr/sbin/nologin pojazdy
mkdir -p "$DANE/kopie"
chown -R pojazdy:pojazdy "$DANE"
chmod 750 "$DANE"

if [ -d "$KOD/.git" ]; then
  git -C "$KOD" fetch -q --depth 1 origin main && git -C "$KOD" reset -q --hard origin/main
else
  git clone -q --depth 1 --branch main "$REPO" "$KOD"
fi

# Klucz aplikacji: losowy, zostaje przy ponownej instalacji.
KLUCZ=""
[ -f "$ENV" ] && KLUCZ=$(sed -n 's/^PJ_KLUCZ=//p' "$ENV")
[ -n "$KLUCZ" ] || KLUCZ=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
umask 077
cat > "$ENV" <<EOT
PJ_DATA=$DANE
PJ_SHARE=$DANE
PJ_PORT=$PORT
PJ_HA_URL=$HA
PJ_KLUCZ=$KLUCZ
PJ_LAN=1
TZ=Europe/Warsaw
EOT
chown root:pojazdy "$ENV"; chmod 640 "$ENV"
umask 022

cat > /etc/systemd/system/pojazdy.service <<EOT
[Unit]
Description=Pojazdy (tankowania, ładowania, koszty, terminy, polisy)
After=network-online.target
Wants=network-online.target

[Service]
User=pojazdy
EnvironmentFile=$ENV
ExecStart=/usr/bin/python3 -u $KOD/pojazdy/server.py
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DANE
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOT

# Aktualizacja: co godzinę sprawdza main; restart tylko, gdy zmienił się katalog pojazdy/.
cat > /usr/local/sbin/pojazdy-aktualizuj <<EOT
#!/bin/bash
set -euo pipefail
cd $KOD
PRZED=\$(git rev-parse HEAD:pojazdy)
git fetch -q --depth 1 origin main
git reset -q --hard origin/main
PO=\$(git rev-parse HEAD:pojazdy)
if [ "\$PRZED" != "\$PO" ]; then
  python3 -m py_compile pojazdy/server.py pojazdy/baza.py pojazdy/obliczenia.py pojazdy/ladowania.py pojazdy/fuelio.py
  systemctl restart pojazdy
  echo "Pojazdy zaktualizowane: \$(sed -n 's/^version: //p' pojazdy/config.yaml)"
fi
EOT
chmod 755 /usr/local/sbin/pojazdy-aktualizuj
cat > /etc/systemd/system/pojazdy-aktualizacja.service <<EOT
[Unit]
Description=Pojazdy – aktualizacja z repozytorium

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pojazdy-aktualizuj
EOT
cat > /etc/systemd/system/pojazdy-aktualizacja.timer <<EOT
[Unit]
Description=Pojazdy – sprawdzanie aktualizacji co godzinę

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOT

systemctl daemon-reload
systemctl enable -q --now pojazdy.service pojazdy-aktualizacja.timer
systemctl restart pojazdy
sleep 2
ADRES=$(hostname -I | awk '{print $1}')
if python3 - "$PORT" "$KLUCZ" <<'PY'
import sys, urllib.request
r = urllib.request.Request("http://127.0.0.1:%s/api/przenosiny" % sys.argv[1], headers={"X-Pojazdy-Klucz": sys.argv[2]})
print("Aplikacja odpowiada:", urllib.request.urlopen(r, timeout=10).read().decode())
PY
then
  echo
  echo "GOTOWE. W Home Assistant: Ustawienia → Dodatki → Pojazdy → Konfiguracja wpisz:"
  echo "  Adres aplikacji w kontenerze:  http://$ADRES:$PORT"
  echo "  Klucz aplikacji:               $KLUCZ"
  echo "  Token Home Assistant:          (token długoterminowy z profilu HA)"
  echo "i uruchom dodatek ponownie. Dane przeniosą się same."
else
  echo "UWAGA: aplikacja nie odpowiada. Dziennik: journalctl -u pojazdy -n 50"
  exit 1
fi
