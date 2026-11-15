#!/bin/bash
# Stacja ekranu w kontenerze (Debian) – instalacja i aktualizacje. Jako root w kontenerze:
#   bash instaluj.sh [port_www]          (domyślnie 8990)
# Ponowne uruchomienie niczego nie psuje: zostawia dane, archiwum budów i klucz.
# Klucz do repozytorium budów (tylko do odczytu) wpisuje się osobno poleceniem: stacja-klucz
set -euo pipefail
PORT="${1:-8990}"
REPO=https://github.com/pbnz7nrwm4-hub/nt1100-ha
KOD=/opt/stacja
DANE=/var/lib/stacja
ENV=/etc/stacja/stacja.env

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv git curl ca-certificates tzdata >/dev/null

id stacja >/dev/null 2>&1 || useradd --system --home "$DANE" --shell /usr/sbin/nologin stacja
usermod -aG dialout stacja
mkdir -p "$DANE" /etc/stacja
chown -R stacja:stacja "$DANE"
chmod 750 "$DANE"
chown root:stacja /etc/stacja
chmod 750 /etc/stacja

if [ -d "$KOD/.git" ]; then
  git -C "$KOD" fetch -q --depth 1 origin main && git -C "$KOD" reset -q --hard origin/main
else
  git clone -q --depth 1 --branch main "$REPO" "$KOD"
fi

# esptool w osobnym środowisku (bez mieszania z pakietami systemu)
[ -x "$KOD-venv/bin/python" ] || python3 -m venv "$KOD-venv"
"$KOD-venv/bin/pip" install -q --upgrade pip >/dev/null
"$KOD-venv/bin/pip" install -q "esptool>=4.8,<6" >/dev/null

umask 027
cat > "$ENV" <<EOT
STACJA_KATALOG=$DANE
STACJA_PORT_WWW=$PORT
STACJA_ESPTOOL=$KOD-venv/bin/python -m esptool
STACJA_KLUCZ=/etc/stacja/github_token
TZ=Europe/Warsaw
EOT
chown root:stacja "$ENV"
umask 022

cat > /etc/systemd/system/stacja.service <<EOT
[Unit]
Description=Stacja ekranu (wgrywanie, demo, dzienniki)
After=network-online.target
Wants=network-online.target

[Service]
User=stacja
SupplementaryGroups=dialout
EnvironmentFile=$ENV
ExecStart=$KOD-venv/bin/python -u $KOD/stacja/stacja.py
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

# Wpisanie klucza bez pokazywania go na ekranie i bez zapisu w historii powłoki.
cat > /usr/local/sbin/stacja-klucz <<'EOT'
#!/bin/bash
set -euo pipefail
read -rsp "Wklej klucz GitHub (tylko do odczytu, repo z firmware) i naciśnij Enter: " K; echo
[ -n "$K" ] || { echo "Pusty – nic nie zmieniam."; exit 1; }
umask 027
printf '%s' "$K" > /etc/stacja/github_token
chown root:stacja /etc/stacja/github_token
chmod 640 /etc/stacja/github_token
systemctl restart stacja
echo "Zapisane. Stacja sprawdzi budowy za kilka sekund."
EOT
chmod 750 /usr/local/sbin/stacja-klucz
# pct enter daje PATH bez /usr/local/sbin – skrót w /usr/local/bin, żeby działało samo „stacja-klucz”
ln -sf /usr/local/sbin/stacja-klucz /usr/local/bin/stacja-klucz

# Aktualizacja kodu: co godzinę z main; restart tylko, gdy zmienił się katalog stacja/ i nic się nie wgrywa.
cat > /usr/local/sbin/stacja-aktualizuj <<EOT
#!/bin/bash
set -euo pipefail
cd $KOD
PRZED=\$(git rev-parse HEAD:stacja)
git fetch -q --depth 1 origin main
git reset -q --hard origin/main
PO=\$(git rev-parse HEAD:stacja)
if [ "\$PRZED" != "\$PO" ]; then
  python3 -m py_compile stacja/stacja.py
  for i in \$(seq 1 60); do
    curl -fsS http://127.0.0.1:$PORT/api/stan 2>/dev/null | grep -q '"zadanie": null' && break
    sleep 10
  done
  systemctl restart stacja
  echo "Stacja zaktualizowana"
fi
EOT
chmod 755 /usr/local/sbin/stacja-aktualizuj
cat > /etc/systemd/system/stacja-aktualizacja.service <<EOT
[Unit]
Description=Stacja ekranu – aktualizacja z repozytorium

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/stacja-aktualizuj
EOT
cat > /etc/systemd/system/stacja-aktualizacja.timer <<EOT
[Unit]
Description=Stacja ekranu – sprawdzanie aktualizacji co godzinę

[Timer]
OnBootSec=10min
OnUnitActiveSec=1h
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOT

systemctl daemon-reload
systemctl enable -q --now stacja.service stacja-aktualizacja.timer
systemctl restart stacja.service
sleep 2
systemctl is-active --quiet stacja && echo "Stacja działa: http://$(hostname -I | awk '{print $1}'):$PORT" || { journalctl -u stacja -n 30 --no-pager; exit 1; }
[ -s /etc/stacja/github_token ] || echo "Brak klucza do budów. Wpisz go poleceniem: stacja-klucz"
ls /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null || echo "Ekranu nie widać w kontenerze (USB do ustawienia na Proxmoxie)."
