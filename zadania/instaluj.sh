#!/bin/bash
# Zadania dzieci w kontenerze (Debian) – instalacja i aktualizacje. Jako root w kontenerze:
#   bash instaluj.sh "Imię administratora" http://<adres HA>:8123 [port]      (port domyślnie 8092)
# Ponowne uruchomienie niczego nie psuje: zostawia bazę, zdjęcia i ustawienia (nowego administratora nie dodaje).
# Połączenie z Home Assistantem (powiadomienia): zadania-ha-token. Lokalne AI: ZD_AI_URL w /etc/zadania/zadania.env.
set -euo pipefail
ADMIN="${1:-}"
HA="${2:-}"
PORT="${3:-8092}"
REPO=https://github.com/pbnz7nrwm4-hub/nt1100-ha
KOD=/opt/zadania
DANE=/var/lib/zadania
ENV=/etc/zadania/zadania.env
IP=$(hostname -I | awk '{print $1}')

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 git curl ca-certificates tzdata sqlite3 >/dev/null

id zadania >/dev/null 2>&1 || useradd --system --home "$DANE" --shell /usr/sbin/nologin zadania
mkdir -p "$DANE" /etc/zadania
chown -R zadania:zadania "$DANE"
chmod 750 "$DANE"
chown root:zadania /etc/zadania
chmod 750 /etc/zadania

if [ -d "$KOD/.git" ]; then
  git -C "$KOD" fetch -q --depth 1 origin main && git -C "$KOD" reset -q --hard origin/main
else
  git clone -q --depth 1 --branch main "$REPO" "$KOD"
fi

# Ustawienia zapisuję tylko za pierwszym razem – późniejsze zmiany (AI, HA) zostają.
if [ ! -f "$ENV" ]; then
  umask 027
  cat > "$ENV" <<EOT
ZD_KATALOG=$DANE
ZD_PORT=$PORT
ZD_ADRES=http://$IP:$PORT
ZD_HA_URL=$HA
ZD_HA_TOKEN=/etc/zadania/ha_token
# Lokalne AI (Ollama, model z widzeniem). Puste = bez oceny AI, rodzic ocenia sam.
ZD_AI_URL=
ZD_AI_MODEL=gemma3:12b
TZ=Europe/Warsaw
EOT
  chown root:zadania "$ENV"
  umask 022
fi

cat > /etc/systemd/system/zadania.service <<EOT
[Unit]
Description=Zadania dzieci (zlecanie, zdjęcia, punkty)
After=network-online.target
Wants=network-online.target

[Service]
User=zadania
EnvironmentFile=$ENV
ExecStart=/usr/bin/python3 -u $KOD/zadania/zadania.py
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

# Klucz do Home Assistanta (powiadomienia) – wpisywany bez pokazywania na ekranie.
cat > /usr/local/sbin/zadania-ha-token <<'EOT'
#!/bin/bash
set -euo pipefail
read -rsp "Wklej token długoterminowy z Home Assistanta i naciśnij Enter: " K; echo
[ -n "$K" ] || { echo "Pusty – nic nie zmieniam."; exit 1; }
umask 027
printf '%s' "$K" > /etc/zadania/ha_token
chown root:zadania /etc/zadania/ha_token
chmod 640 /etc/zadania/ha_token
systemctl restart zadania
echo "Zapisane. Powiadomienia pójdą przez Home Assistanta."
EOT
chmod 750 /usr/local/sbin/zadania-ha-token
ln -sf /usr/local/sbin/zadania-ha-token /usr/local/bin/zadania-ha-token

# Przypomnienie linku osoby (np. gdy ktoś zgubił): zadania-link "Imię"
cat > /usr/local/sbin/zadania-link <<EOT
#!/bin/bash
set -a; . $ENV; set +a
exec runuser -u zadania -- /usr/bin/python3 $KOD/zadania/zadania.py --link "\$1"
EOT
chmod 750 /usr/local/sbin/zadania-link
ln -sf /usr/local/sbin/zadania-link /usr/local/bin/zadania-link

# Awaryjne skasowanie PIN-u (gdy nikt z administratorów nie może wejść): zadania-pin "Imię"
cat > /usr/local/sbin/zadania-pin <<EOT
#!/bin/bash
set -a; . $ENV; set +a
exec runuser -u zadania -- /usr/bin/python3 $KOD/zadania/zadania.py --pin-reset "\$1"
EOT
chmod 750 /usr/local/sbin/zadania-pin
ln -sf /usr/local/sbin/zadania-pin /usr/local/bin/zadania-pin

# Kopia bazy co noc (30 ostatnich) – zdjęć nie kopiuję, zostają w katalogu danych.
cat > /etc/cron.d/zadania-kopia <<EOT
15 2 * * * zadania mkdir -p $DANE/kopie && sqlite3 $DANE/zadania.db ".backup $DANE/kopie/zadania-\$(date +\%F).db" && ls -1t $DANE/kopie/*.db | tail -n +31 | xargs -r rm -f
EOT

# Aktualizacja kodu: co godzinę z main; restart tylko, gdy zmienił się katalog zadania/.
cat > /usr/local/sbin/zadania-aktualizuj <<EOT
#!/bin/bash
set -euo pipefail
cd $KOD
PRZED=\$(git rev-parse HEAD:zadania)
git fetch -q --depth 1 origin main
git reset -q --hard origin/main
PO=\$(git rev-parse HEAD:zadania)
if [ "\$PRZED" != "\$PO" ]; then
  python3 -m py_compile zadania/zadania.py
  systemctl restart zadania
  echo "Zadania zaktualizowane"
fi
EOT
chmod 755 /usr/local/sbin/zadania-aktualizuj
cat > /etc/systemd/system/zadania-aktualizacja.service <<EOT
[Unit]
Description=Zadania dzieci – aktualizacja z repozytorium

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zadania-aktualizuj
EOT
cat > /etc/systemd/system/zadania-aktualizacja.timer <<EOT
[Unit]
Description=Zadania dzieci – sprawdzanie aktualizacji co godzinę

[Timer]
OnBootSec=10min
OnUnitActiveSec=1h
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOT

systemctl daemon-reload
systemctl enable -q --now zadania.service zadania-aktualizacja.timer
systemctl restart zadania.service
sleep 2
systemctl is-active --quiet zadania || { journalctl -u zadania -n 30 --no-pager; exit 1; }
echo "Zadania działają: http://$IP:$PORT"

ILE=$(sqlite3 "$DANE/zadania.db" "SELECT COUNT(*) FROM osoby WHERE admin=1 AND aktywna=1" 2>/dev/null || echo 0)
if [ "$ILE" = "0" ]; then
  if [ -z "$ADMIN" ]; then
    echo "Brak administratora. Uruchom jeszcze raz z imieniem: bash instaluj.sh \"Imię\" http://<adres HA>:8123"
  else
    set -a; . "$ENV"; set +a
    runuser -u zadania -- /usr/bin/python3 "$KOD/zadania/zadania.py" --nowy-admin "$ADMIN"
  fi
fi
[ -s /etc/zadania/ha_token ] || echo "Powiadomienia: wpisz token Home Assistanta poleceniem zadania-ha-token"
