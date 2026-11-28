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

**1.1.0:** „Odczytaj kartę” (ekran 2.19.1+) pobiera też najnowszy zrzut awarii z karty (`awaria-….bin`, zapis obok dziennika w katalogu dzienników) i dłuższy dziennik (funkcje.txt do 96 KB, czas oczekiwania 60 s). Działa przy podłączonym ekranie, bez wyjmowania karty; zrzut rozszyfrowuje się plikiem .elf tej budowy.

**1.0.9:** w tabeli dzienników przy „RAM min” widać, od której sekundy po starcie ekranu pamięć po raz pierwszy zeszła do najniższej wartości, i różnicę względem poprzedniego dziennika z odczytem pamięci (np. „od 25 min od startu · −129 KB wobec poprzedniego”). Powód: w demo 2.19.0 RAM min spadło do 106 KB (wzorzec 235 KB) i trzeba wskazać moment spadku.

**1.0.8:** instalator zawsze startuje od nowa obie jednostki aktualizatora (`stacja-aktualizacja.timer` i `.path`) i sprawdza, że działają; zegar aktualizacji jest kalendarzowy (co godzinę). Strona pokazuje czerwone ostrzeżenie, gdy aktualizator nie biegł od ponad 3 h albo przycisk „Zaktualizuj teraz” czeka ponad 5 min. Powód: 17–22.11 jednostki stały i Stacja nie aktualizowała się przez 5 dni.

**1.0.7:** kafelek **Mapa** ma odnośnik do strony serwera map (`:8988/info`: wersja, wiek danych, Buduj kandydata). Widok „kandydat kontra wzorzec” dojdzie po zmianach ekranu.

**1.0.6:** przycisk **„Pobierz dziennik z karty ekranu”** (sekcja Demo). Stacja wysyła ekranowi polecenie `DZIENNIK` na USB (ekran 2.17.0 lub nowszy) i zapisuje końcówki `awarie.txt`, `funkcje.txt` i `pamiec.txt` jako dziennik „demo-karta-…” z „Pokaż Claude”. Nie działa w trakcie nagrywania ani wgrywania; karty nie trzeba wyjmować.

## Apex – serwer aplikacji nawigacji na Androida (od 1.2.0)

Strona `/apex` (zakładka „Apex” obok „Ekran Tab5”) i adresy `/api/nav/apex/…` dla tabletu. Tylko sieć domowa (żądanie
z adresu spoza sieci prywatnej albo ze śladem serwera pośredniego, np. tunelu, dostaje 403); dostęp spoza domu osobno.

**Pierwsze uruchomienie:** otwórz `/apex`, ustaw PIN (4–12 cyfr), w „Klucze” kliknij „Generuj nowy” (klucz aplikacji) i wklej
klucz TomTom, potem „Pokaż” przy kluczu aplikacji i wpisz go na tablecie (Apex → Ustawienia → Połączenia, razem z adresem Stacji).
Klucze i skrót PIN-u leżą tylko w `/var/lib/stacja/apex/ustawienia.json` (0600), nigdy w repozytorium, logach ani w stanie strony.

**Wgrywanie wersji:** pobierz artefakt `nt1100-debug` z GitHub Actions, rozpakuj ZIP i wgraj `app-debug.apk`. Stacja odczytuje
pakiet, `versionCode` i `versionName` z pliku; odrzuca inny pakiet niż `pl.nt1100` oraz `versionCode` nie większy od najnowszego
(Android nie zaktualizuje do niższej; „wymuś” tylko świadomie). Gdy wersji nie da się odczytać, wpisz ją ręcznie (też z „wymuś”).
Nowo wgrana wersja jest bieżąca; „Ustaw jako bieżącą” cofa wydanie. Usunięcie: z potwierdzeniem, bieżącej i jedynej wersji tylko z ostrzeżeniem.

**Kontrakt (nagłówek `X-Klucz`, brak/zły = 401):** `GET …/app/manifest.json` (`versionCode`, `versionName`, `bytes`, `sha256`; 404 gdy
brak wersji), `GET …/app/apex.apk` (Range: 206/416), `GET …/config` (`{"tomtomKey": …}`), `POST …/log` (tekst albo zip do 5 MB,
nazwa z datą i wersją z `User-Agent: Apex/<wersja>`), `POST …/route.ntr` (501). Dzienniki: `/var/lib/stacja/apex/dzienniki/`
(ostatnie 200), w GUI podgląd i pobranie. Pliki wersji: `/var/lib/stacja/apex/wersje/<versionCode>/` (kopia katalogu danych Stacji
obejmuje je razem z resztą).
