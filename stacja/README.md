# Stacja ekranu

Strona w sieci domowej do obsługi ekranu nawigacji bez terminala: **Wgraj** (najnowszą albo wybraną wersję,
tylko przy zgodnej sumie SHA256), **Demo** (nagrywanie dziennika od pierwszej sekundy, także w trakcie wgrywania),
**Ratuj ekran** (czeka do 90 s na ekran po RESET i wgrywa ostatnią dobrze wgraną wersję), **Dzienniki**
(restarty, awarie, klatki na minutę, najmniej wolnej pamięci; „Pokaż Claude” daje tekst do wklejenia w czacie)
i **Historia**. Mapa i przycisk budowy to fala 2.

Ekran jest podłączony kablem USB do serwera, a stacja działa w kontenerze „aplikacje” (port 8990).

## Instalacja (w kontenerze, jako root)

Na serwerze Proxmox najpierw `pct enter 140` (znak zachęty `root@kronika`), dopiero potem polecenia poniżej.

```
apt-get update && apt-get install -y curl   # świeży Debian w kontenerze nie ma curl
curl -fsSL https://raw.githubusercontent.com/pbnz7nrwm4-hub/nt1100-ha/main/stacja/instaluj.sh -o /root/stacja.sh && bash /root/stacja.sh 8990
```

Instalator zakłada użytkownika `stacja` (grupa `dialout`), kod w `/opt/stacja`, esptool w `/opt/stacja-venv`,
dane w `/var/lib/stacja` (archiwum budów, dzienniki, historia), usługę `stacja` i sprawdzanie aktualizacji kodu
co godzinę. Ponowne uruchomienie zostawia dane i klucz.

Od 1.0.5 na dole strony jest **„Zaktualizuj teraz”** (Stacja zostawia znacznik, jednostka `stacja-aktualizacja.path`
uruchamia aktualizację, gdy nic się nie wgrywa). Gdy zmieni się sam instalator, aktualizator uruchamia go ponownie,
więc konsola nie jest potrzebna. Instalacje sprzed 1.0.5 potrzebują jednego ręcznego `bash /opt/stacja/stacja/instaluj.sh`.

## Klucz do budów (tylko do odczytu)

Budowy ekranu leżą w prywatnym repozytorium firmware (gałąź z wynikami). Stacja pobiera je co 5 minut kluczem,
który może tylko czytać to jedno repozytorium.

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Repository access: **Only select repositories** → repozytorium firmware.
3. Permissions → Repository permissions → **Contents: Read-only** (nic więcej).
4. W kontenerze: `stacja-klucz` i wklej klucz (nie widać go na ekranie, nie trafia do historii powłoki).

Klucz leży tylko w `/etc/stacja/github_token` (czyta go wyłącznie stacja). Nie wklejaj go do czatu ani do repo.
Gdy klucz wygaśnie, strona pokaże „klucz nie ma dostępu” – wystarczy nowy przez `stacja-klucz`.

Gałąź z wynikami trzyma tylko ostatnią budowę, dlatego stacja zapisuje każdą pobraną wersję u siebie
(`/var/lib/stacja/budowy/<wersja>`). Stąd „Wgraj wybraną” i ratunek ostatnią dobrą wersją.

## USB

Ekran przy każdym resecie na chwilę znika z USB i może wrócić pod innym numerem (`ttyACM0`, `ttyACM1`…), np. gdy
ktoś trzymał port otwarty w chwili resetu. Zwykłe przekazanie urządzenia (`dev0`) wymagałoby wtedy restartu kontenera.
Dlatego kontener dostaje katalog stałych węzłów `ttyACM0`–`ttyACM3` (166:0–3) z dysku serwera, a Stacja wybiera ten,
za którym jest teraz urządzenie (`/sys/class/tty/ttyACMn`, bez otwierania portu, bo otwarcie resetuje ekran).

Na serwerze Proxmox (jako root; kontener nieuprzywilejowany: root i dialout w kontenerze to 100000 i 100020 na serwerze):

```
mkdir -p /var/lib/stacja-usb && for i in 0 1 2 3; do [ -e /var/lib/stacja-usb/ttyACM$i ] || mknod -m 660 /var/lib/stacja-usb/ttyACM$i c 166 $i; chown 100000:100020 /var/lib/stacja-usb/ttyACM$i; done
```

W `/etc/pve/lxc/<id>.conf` (przed sekcjami migawek):

```
lxc.cgroup2.devices.allow: c 166:* rwm
lxc.mount.entry: /var/lib/stacja-usb dev/stacja none bind,create=dir 0 0
```

Potem `pct reboot <id>` i sprawdzenie: `pct exec <id> -- ls -l /dev/stacja /sys/class/tty/` (węzły `root dialout 166, n`).
Stacja szuka portu kolejno w `/dev/stacja/ttyACM*`, `/dev/serial/by-id/*` i `/dev/ttyACM*` (zmienna `STACJA_PORT`).
Nagranie przy wgrywaniu startuje dopiero po esptool – otwarty port w czasie resetu zmieniał numer ekranu.

## Bez ekranu

`python3 tests/test_stacja.py` – port to pty, esptool to atrapa, repozytorium budów to lokalny serwer.

**1.0.6:** przycisk **„Pobierz dziennik z karty ekranu”** (sekcja Demo). Stacja wysyła ekranowi polecenie `DZIENNIK` na USB (ekran 2.17.0 lub nowszy) i zapisuje końcówki `awarie.txt`, `funkcje.txt` i `pamiec.txt` jako dziennik „demo-karta-…” z „Pokaż Claude”. Nie działa w trakcie nagrywania ani wgrywania; karty nie trzeba wyjmować.
