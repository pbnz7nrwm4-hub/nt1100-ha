# Stacja ekranu

Strona w sieci domowej do obsługi ekranu nawigacji bez terminala: **Wgraj** (najnowszą albo wybraną wersję,
tylko przy zgodnej sumie SHA256), **Demo** (nagrywanie dziennika od pierwszej sekundy, także w trakcie wgrywania),
**Ratuj ekran** (czeka do 90 s na ekran po RESET i wgrywa ostatnią dobrze wgraną wersję), **Dzienniki**
(restarty, awarie, klatki na minutę, najmniej wolnej pamięci; „Pokaż Claude” daje tekst do wklejenia w czacie)
i **Historia**. Mapa i przycisk budowy to fala 2.

Ekran jest podłączony kablem USB do serwera, a stacja działa w kontenerze „aplikacje” (port 8990).

## Instalacja (w kontenerze, jako root)

```
curl -fsSL https://raw.githubusercontent.com/pbnz7nrwm4-hub/nt1100-ha/main/stacja/instaluj.sh -o /root/stacja.sh && bash /root/stacja.sh 8990
```

Instalator zakłada użytkownika `stacja` (grupa `dialout`), kod w `/opt/stacja`, esptool w `/opt/stacja-venv`,
dane w `/var/lib/stacja` (archiwum budów, dzienniki, historia), usługę `stacja` i sprawdzanie aktualizacji kodu
co godzinę. Ponowne uruchomienie zostawia dane i klucz.

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

Ekran przy każdym resecie na chwilę znika z USB, więc zwykłe przekazanie urządzenia do kontenera (`dev0`)
po resecie wymaga restartu kontenera. Ustawienie, które to przeżywa, przygotujemy po odczycie z serwera
z podłączonym ekranem (`lsusb`, `/dev/serial/by-id`, `dmesg`). Stacja szuka portu kolejno w `/dev/serial/by-id/*`
i `/dev/ttyACM*` (zmienna `STACJA_PORT`).

## Bez ekranu

`python3 tests/test_stacja.py` – port to pty, esptool to atrapa, repozytorium budów to lokalny serwer.
