# MIGRACJA – pakiet przekazania projektu „Telemetria motocykla” (NT1100)

Stan na **2026-11-05 ok. 12:00** (czas PL). Projekt przechodzi do projektu **„Home Assistant - pompa ciepła, PV, dom”** i od teraz tam jest kontynuowany (HA, telemetria motocykla, repo `pbnz7nrwm4-hub/nt1100-ha`).

> **Wersja publiczna (repo).** Repo jest publiczne, więc nazwy podzespołów (płytki, procesory, moduły, sterowniki) są tu zamaskowane znacznikami `[…]`, zgodnie z zasadą „nie ujawniać sprzętu w publicznym repo”. Pełna wersja z nazwami sprzętu leży w folderze projektu: `/mnt/project-files/telemetria/migracja/MIGRACJA-pelna.md`.

Spis treści:
1. Założenia i decyzje
2. Otwarte wątki (stan, kto czeka, linki)
3. Artefakty i pliki projektu
4. Pamięć projektu – pełna treść
5. Dane dostępowe – tylko nazwy i miejsca
6. Plan na najbliższe tygodnie

---

## 1. Założenia i decyzje

### 1.1 Cel i osoba
- Adrian, Honda **NT1100, rocznik 2025, skrzynia manualna** (nie DCT). Cel: efekt „jak aplikacja BMW GS” – zapis jazd (trasa, przechył, przyspieszenia, dane z silnika), przegląd w Home Assistant, nawigacja z własnym ekranem na kokpicie.
- **Adrian nie programuje.** Claude pisze całe oprogramowanie (firmware, dodatek HA, kontener tras). Adrian kupuje, montuje, wgrywa gotowe pliki i przysyła zrzuty/logi.
- **Odpowiadamy po polsku**, prostym językiem, krok po kroku (Adrian pracuje na Macu i iPhonie).
- Bez lutowania (DIY „na wtyk”), minimum ingerencji w motocykl.

### 1.2 Architektura (stan obecny)
```
 [Skrzynka na motocyklu]  --Wi-Fi dom / hotspot iPhone-->  [Dodatek HA „NT1100 Jazdy”]  <--  [Kontener LXC „nawigacja” na Proxmoxie]
   GPS 10 Hz, IMU (przechył),                                  strona jazd (Ingress 8099),       GraphHopper (trasy, :8989),
   CAN/OBD2 500 kbit/s 29-bit (ECM),                           odbiór jazd (8098, klucz),        serwer mapy i kafelków (:8988),
   karta microSD, bateria                                      MQTT (urządzenie NT1100),         mapa na kartę ekranu (.ntt)
        |  radio bezpośrednie (ramki 5 Hz)                     nawigacja/planer, GPX OsmAnd,
        v                                                      aktualizacje skrzynki i ekranu
 [Ekran na kokpicie 2,8"] --BLE--> iPhone (powiadomienia, muzyka, czas)
                                    iPhone + OsmAnd (CarPlay) prowadzi po GPX z dodatku
```
- **Skrzynka** (rejestrator): zapisuje jazdy na kartę, po jeździe wysyła do dodatku HA (lokalnie albo przez Cloudflare z zewnątrz). Strona WWW skrzynki (Strona skrzynki / Skan / ustawienia). Aktualizuje się **sama z dodatku** (podpisany, szyfrowany plik).
- **Dodatek HA „NT1100 Jazdy”** (repo publiczne, sklep dodatków HA → Repozytoria): 4 zakładki (Jazdy, Trasy, Motocykl, Ustawienia), MQTT discovery, pogoda, serwis/przebieg, powiadomienia, nawigacja (planer, warianty szybko/lekko/kręto/bardzo, omijanie, ulubione, tryb motocykl/samochód, GPX dla OsmAnd, korki TomTom), karta „Wersje oprogramowania” w zakładce Stan.
- **Silnik tras**: LXC 100 `nawigacja` na Proxmoxie (Debian 12, 4 rdz., 6 GB RAM, 30 GB), katalog `silnik-tras/` w repo (`install-lxc.sh`, `aktualizuj.sh`, `kafelki.sh`, `build_map.py`, Planetiler `--storage=ram --nodemap-type=sparsearray`, Java 5g).
- **Ekran**: własna płytka 2,8" z dotykiem, akumulator 1000 mAh; nawigacja z mapą (.ntt z kontenera), pogoda, stan, telefon przez BLE. Aktualizacje z dodatku (Menu → Sprawdź wersję) albo kablem.
- **Serwer**: Proxmox na mini PC Fujitsu ESPRIMO Q920 (i5-4590T, 12 GB RAM). VM 101 = Home Assistant OS (zmniejszony do 4 GB), LXC 100 = nawigacja, LXC 110 = drukarka.
- **Aktualne wersje** (z repo, main @ `05ca7be`): dodatek **1.5.13**, skrzynka **1.4.3**, ekran **1.1.2**.

### 1.3 Ustalenia z Adrianem (najważniejsze)
- **STAŁE POLECENIE (2026-11-04):** wątki same scalają swoje PR-y do `main` w `nt1100-ha` (squash, po zielonym CI), bez proszenia Adriana o scalenie ani o zgodę. Dotyczyło **tego projektu i tego repo**; w nowym projekcie warto to potwierdzić u Adriana dla innych repo. HA czyta tylko `main`, więc niescalony PR = brak aktualizacji.
- **Wydanie = podbić `version` w `nt1100_jazdy/config.yaml`** (i w `server.py`), push do main → Adrian klika aktualizację dodatku. Firmware skrzynki/ekranu trafia do `nt1100_jazdy/firmware/*.bin + *.json` (pakowane `tools/fwpack.py` ze źródeł). Adrian **aktualizuje tylko dodatek**; resztę dodatek rozsyła sam.
- Kolejność rozwoju: najpierw testy na sprzęcie, potem rozwój (decyzja 2026-10-30).
- Zmiany wyglądu strony skrzynki – **najpierw w demo** (`telemetria/demo/nt1100-demo.html`), dopiero po akceptacji do firmware.
- Wygląd ekranu – w rundach na zrzutach (render na hoście), **nie wydawać bez akceptacji Adriana**.
- Mapa dodatku: kafelki z własnego kontenera (MapLibre, ciemny styl, szczyty/przełęcze, cieniowanie gór, bez budynków); tylko Polska do czasu wymiany RAM.
- Prowadzenie w aucie i na motocyklu przez **OsmAnd (Maps+)** z GPX z dodatku; ekran pokazuje to, czego aplikacja nie ma (fotoradary, limity, zakręty). W aucie Adrian jeździ z OsmAnd **bez** skrzynki i ekranu.
- Zasilanie skrzynki: na testy ładowarka/powerbank, docelowo gniazdo zapalniczki (sprawdzić, czy gaśnie z zapłonem); pin 16 OBD2 (+12 V stałe) **nie podłączać**.
- Druk 3D: Bambu Lab P2S, **PETG** na motocykl; pliki w `telemetria/druk/`.

### 1.4 Konwencje
- Język: kod/komentarze/commity po polsku jak w repo; tytuły PR „Wersja X.Y.Z: …”.
- Testy: `tests/test_server.py`, `tests/test_nav.py` (fałszywy GraphHopper) – uruchamiać przed pushem; CI w `.github/workflows`.
- Firmware budowane `arduino-cli` (w środowisku wątków: `~/tools`, proxy z `$HTTPS_PROXY`, `SSL_CERT_FILE=/root/.ccr/ca-bundle.crt`, fałszywy ctags). Źródła firmware **nie są w repo** – są w zipach w plikach projektu (`telemetria/nt1100-telemetria-zrodla-*.zip`, najnowszy: `...-1.4.3-ekran-1.1.2.zip`).
- Pliki dla Adriana: wgrywanie skrzynki `ota.bin` przez stronę skrzynki (full.bin tylko USB); ekran przez [narzędzie do wgrywania]: **ota.bin pod 0x10000 bez Erase** (zachowuje ustawienia), **full.bin pod 0x0** (kasuje ustawienia).
- Pamięć projektu: jeden plik na temat, z datą; indeks w `MEMORY.md`.

### 1.5 Czego NIE robić
- **Nie ujawniać sprzętu w publicznym repo** (nazwy płytek, procesorów, modułów, pinów) – Adrian może kiedyś sprzedawać urządzenie. `make_page.py` podmienia nazwy w stronie; LICENSE „wszelkie prawa zastrzeżone”. Historia repo była już raz przepisana z tego powodu.
- **Nigdy nie wrzucać do repo** kluczy podpisu/szyfrowania firmware (`hw/fwkey.h` – tylko w zipie źródeł), haseł, klucza dodatku, klucza TomTom, adresów domowych.
- **Nie wdrażać zebranych uwag Adriana bez polecenia** („zbieraj uwagi, jeszcze nic nie rób”). Tematy zaparkowane (CarPlay „otwórz na iPhonie”, stopka jako koniec jazdy, LTE) – nie budować bez zgody.
- Nie podłączać pinu 16 OBD2; skrzynka nadaje na CAN tylko po potwierdzeniu (domyślnie nasłuch).
- Nie kazać Adrianowi kopiować plików przez Sambę – wszystko przez repo/dodatek.
- Nie zgadywać IP i haseł – pytać albo wskazać, gdzie je odczytać.
- Allegro/kamami/TME blokują pobieranie stron – prosić Adriana o zrzuty ofert.
- Uwaga na pomyłkę z 2026-11-05 w czacie projektu: silnik tras to **LXC 100**, nie 110 (110 = drukarka).

---

## 2. Otwarte wątki

Linki prowadzą do wątków w starym projekcie (`chan_01ByeYHZAwjpoT9UVBYHhpyi`). PR-y: wszystkie #1–#35 są **scalone** do `main` (lista na końcu sekcji). Żaden wątek nie został zamknięty – Adrian zamknie je po potwierdzeniu przejęcia.

| Wątek | Co zrobione | Co czeka | Na kogo |
|---|---|---|---|
| [Zainstalować ekran od zera](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyi8xeDjBf3U3kdDU4fJYX4uu) | Ekran 1.0.0 → **1.1.2** wydany (PR #8–#15, #19, #21, #23, #24, #27); iPhone sparowany i działa (przez nRF Connect); instrukcja `telemetria/ekran/instalacja-ekranu-od-zera.md` | Adrian na 1.0.11 miał problem z Wi-Fi; 2026-11-04 20:20 przez pomyłkę wgrał full.bin pod 0x10000, polecono nadpisać **ota.bin 1.1.2 pod 0x10000** i RESET. Brak potwierdzenia. Do sprawdzenia: mapa .gz/crc, dźwięk, biegunowość wtyczki akumulatora (zdjęcie), miejsce na głośnik w obudowie. Niewydane łatki: `wip/ekran-1.1.2-bluetooth.patch`, `wip/ekran-wifi-diagnoza.patch` | **Adrian** (wgranie i test) |
| [Zbudować nawigację na ekranie i planer w HA](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyi9RQKHqFG4dYjxnS4vJtDie) | Dodatek 1.4.0 → **1.5.13** (PR #2, #4–#7, #16, #18, #20, #22, #25, #26, #28–#35); silnik w LXC 100 działa; mapa na kartę 234 MB gotowa; poprawka NaN przy rysowaniu trasy (1.5.13, PR #35) | Adrian: zaktualizować dodatek do 1.5.13 i policzyć trasę ponownie; dokończyć przebudowę kafelków w kontenerze (było 3/5); przygotować ZIP na kartę ekranu. Nieprzetestowane: piny/kolory na ekranie w jeździe, [radio bezpośrednie] vs hotspot, korki TomTom z telefonu | **Adrian** (test), potem Claude (poprawki) |
| [Podłączyć przewód OBD2 do CAN](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyiXVV5ry9oMUDDT2bSvpFxiP) | Instrukcja okablowania (6→H, 14→L, 4/5→G, 16 izolować); skany CAN (500 kbit/s 29-bit, tylko ECM, P0500); skrzynka 1.3.2–1.4.0 (skan rozszerzony, zakładka Skan, dane z silnika w jeździe) – PR #1 | Pytanie do Adriana (2026-11-04 16:55): czy wszędzie liczyć **wyjazdy zamiast odcinków** (statystyki, licznik „Jazdy” w HA, jedno powiadomienie po wyjeździe). Odłożone: stopka jako koniec jazdy (warianty A/B, rekomendacja A); kontrolki ABS/TC z CAN (porównanie skanów) | **Adrian** (decyzja) |
| [Wybrać tani modem LTE](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyiAZ5ARJPAnWDSgGmp1R7AaS) | Rekomendacja: płytka [modem LTE] Cat-1 (AliExpress ok. 60–80 zł, pasma z B20), alternatywa [producent] [modem LTE] HAT 139 zł (Botland); zasilanie osobne 5 V, starter SIM. Wcześniej: [Wybrać moduł LTE](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyi2234coXwFEkmvEn2uy2qWB) ([modem LTE]) | Decyzja o zakupie; kodu brak („nic nie kupuję ani nie piszę, dopóki nie dasz znać”) | **Adrian** |
| [Przeanalizować kod i GUI (uwagi do dodatku HA)](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyiMLUmF7AWj2ajfnNyzUXWmN) | Przegląd wdrożony (firmware 1.3.0 + dodatek 1.2.0), poprawki map 1.2.1, diagnoza MQTT 1.2.2, **MQTT łączy od razu 1.2.3** | Brak potwierdzenia, że urządzenie NT1100 jest w HA → MQTT. Zebrana uwaga Adriana nr 1: połączone jazdy na jednej mapie – częściowo załatwione widokiem „wyjazdu” w 1.5.x, potwierdzić z Adrianem. Nie wdrażać kolejnych uwag bez polecenia. Niesprawdzone na realnym HA: powiadomienia | **Adrian** (potwierdzenie) |
| [Wybrać nawigację CarPlay (OsmAnd)](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi5FoCmjU6BrkCVtb6Uxcfaz) | Wybór OsmAnd Maps+ (plan B Kurviger Tourer+); instrukcja OsmAnd (artefakt); styl nocny `telemetria/osmand/NT1100.render.xml`; GPX w formacie OsmAnd (1.5.10–1.5.11, PR #31, #32), „Jadę (OsmAnd)” + korki (1.5.9, PR #30) | Adrian ma sprawdzić na telefonie tryb motocykl: ETA i skręty bez „Dołącz do dróg”; styl nocny v1 niesprawdzony. Zaparkowane: przycisk „Wyślij do nawigacji / Otwórz na iPhonie” | **Adrian** (test) |
| Kontener LXC z Claude Code (pytanie w czacie projektu, 2026-11-05 00:17) | Ocena: ma sens jako **dodatek** do czatu projektu, jeden wspólny nieuprzywilejowany LXC dla obu projektów (nie na VM 101), token HA tylko do odczytu, sekrety tylko w kontenerze, próba tydzień, do czasu RAM 1 rdzeń/1 GB | Adrian nie zlecił jeszcze instrukcji zakładania kontenera. Temat przechodzi do nowego projektu | **Adrian** (decyzja) |
| [RAM do Fujitsu Q920](https://claude.ai/code/project/chan_01ByeYHZAwjpoT9UVBYHhpyi?thread=cmsg_01ByeYHZAwjpoT9UVBYHhpyi8ujacJGTwYDyZh5ZBFQfP2) (wątek zasobów Proxmoxa + pytanie w czacie 2026-11-05 07:04) | Zalecenie: **8 GB DDR3L SO-DIMM 1600 (PC3L-12800S, 1,35 V)**, np. Kingston KVR16LS11/8, w miejsce 4 GB Samsung → 16 GB; potem HA 6 GB, nawigacja 7–8 GB, zapas na kontener Claude Code; po wymianie można dodać mapy CZ/SK | Zakup i montaż; potem zmiana przydziałów RAM i `PAMIEC` w kontenerze | **Adrian** (zakup) |

Wątki zakończone (resolved, tylko dla historii): rejestrator telemetrii, ekran nowszych płytek, dane z motocykla, porównanie BMW Motorrad, DIP modułu GNSS, ekran e-ink/IP67, obudowa wskaźnika, RaceCapture, GPS i obsługa skrzynki, ekran na kokpit (płytka i obudowa), wysyłka do chmury, strona jazd w HA, lista zakupów, usypianie skrzynki na biurku, zasoby Proxmoxa, podsumowanie systemu, demo jazdy na ekranie, wersje w jednym miejscu.

### Scalone PR-y (wszystkie w `main`)
| PR | Treść |
|---|---|
| [#1](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/1) | Wersje 1.2.4–1.3.0: skrzynka 1.3.2–1.4.0 (skan rozszerzony, zakładka Skan, dane z silnika) |
| [#2](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/2) | 1.4.0: nawigacja, silnik tras w kontenerze, ekran 1.0.0, skrzynka 1.4.1 |
| [#3](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/3) | 1.4.1: skrzynka 1.4.2 z zapisem powodów restartu |
| [#4](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/4)–[#7](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/7) | 1.4.2–1.4.5: wyszukiwanie adresów, szybkie trasy, Tankowanie/Jedzenie, demo trasy |
| [#8](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/8)–[#15](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/15) | 1.4.6–1.4.13: ekran 1.0.3–1.0.9 (zasilanie, kolory, dotyk, skrzynka 1.4.3, mapa, motyw, makieta, iPhone i dźwięki) |
| [#16](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/16)–[#19](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/19) | 1.4.14–1.4.17: GPX, „Mój plan”, wersje w jednym miejscu, pełny ekran mapy, ekran 1.0.10 |
| [#20](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/20)–[#24](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/24) | 1.5.0–1.5.4: nowy układ 4 zakładek, mapa wektorowa, ekran 1.0.11–1.1.1 |
| [#25](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/25)–[#30](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/30) | 1.5.5–1.5.9: pomijanie miejscowości, kafelki bez pliku morza, ekran 1.1.2, szutry/ulubione, tryb auto, OsmAnd + korki |
| [#31](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/31)–[#35](https://github.com/pbnz7nrwm4-hub/nt1100-ha/pull/35) | 1.5.10–1.5.13: GPX OsmAnd z manewrami i czasami, czytelny błąd silnika, Planetiler w RAM, poprawka NaN |

Ostatni commit na `main`: `05ca7be` (2026-11-05). Historia: `git log --oneline main`.

---

## 3. Artefakty i pliki projektu

### 3.1 Artefakty (strony/dokumenty Claude)
| Artefakt | Co zawiera |
|---|---|
| [OsmAnd: jazda po trasie z dodatku NT1100](https://claude.ai/artifact/MVzx5WFKSZAHNGdumQz7nx) | Instrukcja krok po kroku: import GPX z dodatku do OsmAnd na iPhonie, „Podążaj za trasą”, profil CarPlay |
| [Nowy układ dodatku NT1100](https://claude.ai/artifact/B2FUqSX5Rz6Ja4FDHRQTjh) | Makieta 6 ekranów dodatku 1.5 (Jazdy, Trasy, Motocykl, Ustawienia) – zaakceptowana i zbudowana |
| [System NT1100](https://claude.ai/artifact/P1QyGE4AjFtwH1bP133S5Y) | Podsumowanie całego systemu: skrzynka, ekran, dodatek, kontener – co robi każdy element |
| [Makieta ekranu NT1100](https://claude.ai/artifact/T6V2VSQgP3kgr91qzqhFCW) | Interaktywna makieta ekranu nawigacji (v6), kopia w `telemetria/ekran/makieta-[ekran-płytka].html` |
| [Nawigacja NT1100: propozycja funkcji](https://claude.ai/artifact/HUuNTcWk4gH2qa88vT78V1) | Dokument z funkcjami nawigacji i decyzjami Adriana |
| [NT1100: przegląd i plan usprawnień](https://claude.ai/artifact/G6gLeu5QuN2pubozY4zPTk) | Przegląd kodu i GUI z 2026-11-03 (wdrożony w 1.3.0/1.2.0) |
| [Wysyłka jazd NT1100 do chmury: warianty](https://claude.ai/artifact/SCwkFLVfB3Bz1tZEkx1XLw) | Porównanie wariantów wysyłki (wybrany: własny dodatek HA) |
| [Moduł LTE do skrzynki NT1100](https://claude.ai/artifact/AfkAQnrVB66gwtoVHEijyj) | Porównanie modułów LTE (z 2026-11-01) |
| [NT1100 Jazdy demo](https://claude.ai/artifact/27nDNbhKuLbx6Aqdgi7VB3) | Demo strony skrzynki z przykładowymi jazdami (wersja zaakceptowana v7 w `telemetria/demo/`) |
| [Czarna skrzynka NT1100](https://claude.ai/artifact/PPcgnqGMo6Md1nb7Bohivf) | Wczesny opis skrzynki (2026-10-29) |
| [NT1100 Telemetria – instrukcja uruchomienia](https://claude.ai/artifact/6YcdCMvxfekYp3cuN8Ei6S) | Instrukcja montażu i pierwszego uruchomienia skrzynki (DIP, wgrywanie) |
| [Telemetria motocykla DIY: wykonalność i sprzęt](https://claude.ai/artifact/VrBALHrQocigGGLZKStVts) | Ocena wykonalności i lista sprzętu (2026-10-28) |

### 3.2 Pliki w folderze projektu (`/mnt/project-files/telemetria/`, ok. 208 MB)
**Ważne przy migracji:** źródła firmware skrzynki i ekranu oraz klucze podpisu są **tylko tutaj**, nie w repo. Trzeba je przenieść do nowego projektu (najnowszy zip wystarczy, starsze to historia).

| Ścieżka | Co to jest |
|---|---|
| `nt1100-telemetria-zrodla-1.4.3-ekran-1.1.2.zip` | **Najnowsze źródła**: firmware skrzynki 1.4.3 + ekranu 1.1.2 (`firmware/ekran/`), `tools/fwpack.py`, `hw/fwkey.h` (klucze!), testy hosta, `host/render.sh` |
| `nt1100-telemetria-zrodla-*.zip` (1.2.0 … 1.4.3) | Starsze wersje źródeł (historia) |
| `nt1100-telemetria-*-full.bin / -ota.bin / -ota-podpisany.bin` | Gotowe obrazy skrzynki 1.2.0–1.4.3 |
| `nt1100-ekran-*-full.bin / -ota.bin` | Gotowe obrazy ekranu 1.0.0–1.1.2 |
| `nt1100-atom-1.0.0-full.bin`, `atom-instrukcja.md` | Wskaźnik stanu (nieużywany od wyboru ekranu) |
| `wip/` | Łatki robocze (m.in. `1.3.0-core-wip.patch` – ntfy/raport problemów; `ekran-1.1.2-bluetooth.patch`, `ekran-wifi-diagnoza.patch` – niewydane), harness renderu ekranu |
| `ekran/` | `instalacja-ekranu-od-zera.md`, `mapa-format-1.1.md` (spec mapy), makieta HTML, zrzuty ekranów 1.0.8–1.1.2 |
| `demo/nt1100-demo.html` | Demo strony skrzynki (tu najpierw zmiany strony) |
| `dodatek-1.5/` | Zrzuty porównania stylów mapy dodatku |
| `ha/` | `instrukcja-ha.md`, pierwszy zip dodatku 1.0.0, podglądy |
| `osmand/` | Styl nocny OsmAnd `NT1100.render.xml` + generator |
| `druk/` | STL/skrypty: wkładka skrzynki, obudowa wskaźnika, `druk/ekran/` – obudowa ekranu (korpus, klapka, uchwyty kierownica 28 mm / klin 15°), README |
| `obd2-do-can-unit.md`, `research-can-honda-euro5.md` | Okablowanie OBD2 i rozpoznanie CAN Hondy |
| `porownanie-bmw.md` | 36 funkcji aplikacji BMW Motorrad vs projekt |
| `wyswietlacz-przeglad.md` | Przegląd wyświetlaczy |
| `grafana-nt1100.json` | Dawny pulpit Grafany (nieużywany) |
| `skan-podglad-1.2.2-symulacja.png`, `strona-jazdy-1.2.0.png` | Podglądy |
| `/mnt/project-files/telemetria/migracja/` | Ten pakiet (pełna wersja z nazwami sprzętu) |

---

## 4. Pamięć projektu – pełna treść

Poniżej cała pamięć projektu (`MEMORY.md` + wszystkie pliki tematyczne), bez skracania. Jedyne zmiany: wartości haseł, nazwa sieci domowej, domena, adresy IP w sieci domowej i nazwa karty sieciowej zastąpione znacznikami `[…]` (patrz sekcja 5); w tej publicznej wersji dodatkowo zamaskowano nazwy podzespołów (pełna treść: `telemetria/migracja/MIGRACJA-pelna.md` w folderze projektu).

**Dopisek do migracji:** „STAŁE POLECENIE (2026-11-04, Adrian): wątki same scalają swoje PR-y w repo nt1100-ha” dotyczyło **tego projektu i repo `nt1100-ha`**. W projekcie HA potwierdzić z Adrianem, czy obowiązuje też dla repo `ha-dom` i innych.

### `MEMORY.md`

````markdown
- STAŁE POLECENIE (2026-11-04, Adrian): wątki same scalają swoje PR-y w repo nt1100-ha, bez proszenia Adriana o scalenie ani o zgodę na scalenie.
- Motocykl Adriana: Honda NT1100, rocznik 2025, skrzynia manualna; ma gniazdo (zasilanie). Złącze Honda 6-pin → OBD2.
    - Adrian nie ma doświadczenia w programowaniu: Claude pisze całe oprogramowanie. Ekran na kierownicy zbędny.
    - Adrian ma drukarkę 3D Bambu Lab P2S; filamenty: PLA i PETG (PETG preferowany na motocykl). Pliki STL/3MF w telemetria/druk/.
    - Proponowany sprzęt: [producent] [skrzynka-płytka] ([wersja], pełna wersja) + GNSS ([GPS]) + [moduł CAN] (CAN opcjonalny, Adrian woli minimum ingerencji). Dokument: https://claude.ai/artifact/VrBALHrQocigGGLZKStVts
    - Dodatkowo: [wskaźnik] jako wskaźnik stanu/połączenia skrzynki (dioda), obudowa w projektowaniu (2026-10-31), miejsce montażu na NT1100 do ustalenia.
    - Zakupy: obudowa Kradex 105×105×70 (bez drukowanej wkładki, VHB + pianka PE), męski przewód OBD2 z wolnymi końcami, karta microSD do [skrzynka-płytka]: Adrian faktycznie kupił **16 GB** (nie 32); do ekranu [ekran-płytka] zalecono też 16 GB SDHC FAT32 (2026-11-04). 3M VHB GPH-110GF, Dual Lock SJ3870. Zasilanie: na testy powerbank, docelowo ładowarka USB z gniazda zapalniczki (sprawdzić, czy gaśnie z zapłonem), przetwornica tylko w razie potrzeby.
    - LTE: rekomendowany [producent] [modem LTE] ([modem LTE]), szczegóły w telemetry-hardware-plan.md.
    - Kierunek: podgląd jazd na stronie skrzynki; później strona w chmurze (Cloudflare) przez hotspot iPhone; HA/Grafana jako dodatek. Aplikacja iOS (Adrian ma Maca; synchronizacja po BLE) i modem LTE Cat-1 — do rozważenia po testach.
    - Home Assistant Adriana: Home Assistant OS jako VM na Proxmox (dodatki dostępne); ma MQTT; InfluxDB i Grafany nie ma. Dostęp z zewnątrz przez Cloudflare.
    - Serwer Proxmox (2026-11-04, wątek „Sprawdzić zasoby Proxmoxa pod silnik tras”): Fujitsu ESPRIMO Q920, i5-4590T 4 rdzenie, RAM 12 GB (8+4, max 16 GB, 2 gniazda DDR3L SO-DIMM), 2 dyski HDD (320+500 GB; wolne local-lvm 163 GB, USB1 366 GB). VM 101 HA: 4 rdz., 8 GB; LXC 110 drukarka: 2 rdz., 0,5 GB. Kontener nawigacji potrzebuje 4 rdz., 8 GB RAM, 30 GB — RAM-u brakuje; zalecono kupić 8 GB DDR3L 1600 (PC3L-12800S, np. Kingston KVR16LS11/8) w miejsce kości 4 GB Samsung. Po wymianie: HA 6 GB, nawigacja 7–8 GB.
    - Odpowiadaj po polsku.
    - GPS DIP (2026-11-02, poprawione po schemacie [producent]; wcześniejsze RX4/TX4/PS2 było BŁĘDNE): dla [skrzynka-płytka] RX=tylko 1 ON (G18), TX=tylko 1 ON (G17), PS=tylko 2 ON (G10). GPS wykryty i skonfigurowany; test w aucie 2026-11-02 OK (fix 8–11 sat, kalibracja gotowa po ~3 min, przechył w aucie ±3°).
    - Firmware 1.2.10 (2026-11-02, wgrywane ota.bin): jedno menu (Strona skrzynki / Skan / Wróć), sieć NT1100 zawsze włączona, ustawienia InfluxDB/MQTT na stronie, wykrywanie poruszenia skrzynki i odrzucanie niemożliwych maksimów. Wcześniej 1.2.6–1.2.9: ekrany, QR, przytrzymanie 3 s (też w jeździe), koniec jazdy, łączenie jazd, diagnostyka GPS — telemetry-firmware-126.md; telemetry-lean-calibration.md. Wgrywanie: ota.bin przez stronę (Ustawienia → Aktualizacja), full.bin tylko USB. Następny krok: test na motocyklu (skrzynka sztywno, Dual Lock).
    - Firmware 1.2.5 (2026-11-01): + wskaźnik [wskaźnik] przez [radio bezpośrednie] (atom 1.0.0), pliki i atom-instrukcja.md w /mnt/project-files/telemetria/; szczegóły telemetry-atom-indicator.md. Wcześniej: firmware 1.2.4 (2026-10-31), 1.2.3 = nowa strona z demo, instrukcja: https://claude.ai/artifact/6YcdCMvxfekYp3cuN8Ei6S — telemetry-firmware-status.md, telemetry-page-demo-status.md. Plan 1.3.0: powiadomienia ntfy + raport problemów przy każdej jeździe.
    - 2026-10-30: Adrian zdecydował — najpierw pierwsze testy na sprzęcie, dalszy rozwój po udanych testach.
    - Strona WWW skrzynki: demo v7 zaakceptowane i wgrane do firmware 1.2.3; zmiany strony nadal najpierw w demo — telemetry-page-demo-status.md.- Pomysły z RaceCapture do wdrożenia po testach: telemetry-racecapture-ideas.md
    - Lista rozwoju po testach (1.3.0+progi, mapowanie CAN, chmura, iOS/LTE, podgląd na żywo, wysyłka w trakcie jazdy): telemetry-dev-backlog.md
    - Budowanie firmware w tym środowisku: arduino-cli pobrany z downloads.arduino.cc do ~/tools (= /root/tools), network.proxy=$HTTPS_PROXY i SSL_CERT_FILE=/root/.ccr/ca-bundle.crt, ctags: --build-property runtime.tools.ctags.path=/root/tools/fakectags. Sieć projektu Adrian poszerzył 2026-11-01 (github release assets, [producent-chipu] OK; github.com HTML 403).
    - Wyświetlacz zamiast [wskaźnik] (wątek „Wybrać cienki wyświetlacz zamiast [wskaźnik]”): kandydaci w telemetry-display-choice.md. 2026-11-03 wybór: **[producent-ekranu] [ekran-płytka]** ([procesor], IPS 2,8" 240×320, dotyk pojemnościowy, USB-C, złącze BAT 1,25 mm 2-pin z ładowarką ~290 mA, RGB LED, microSD, 86×50×10,6 mm; dokumentacja: [producent-ekranu]/2.8inch_[procesor]_Display; oferta Elektroweb 117,70 zł) + akumulator **innCraft IN503450 1000 mAh PCM, wtyczka Molex 51021-0200** (Allegro, ~25 zł, zaakceptowany). Alternatywa: [producent] [procesor]-Touch-LCD-2.8 (73×51 mm). Żółta CYD [procesor]-2432S028 odradzona. Szkic obudowy ok. 91×55×20 mm z daszkiem, 4 śruby w rogach płytki, Dual Lock z tyłu; STL gotowe 2026-11-03 w druk/ekran/ (91×55×21 + daszek 20, korpus + klapka, 4× M3×20), uchwyt na kokpit po zdjęciach; po dostawie sprawdzić biegunowość wtyczki na zdjęciu. Allegro zablokowane dla wątków (DataDome 403); botland i strony producentów działają.
    - Nawigacja NT1100 (2026-11-04, wątek „Ocenić nawigację w stylu Kurviger na [procesor]”): ZBUDOWANA w całości, nieprzetestowana na sprzęcie — dodatek 1.4.0 (zakładka Nawigacja, nav.py/navapi.py/ntt.py/nav.js), silnik tras LXC (silnik-tras/), ekran 1.0.0 (firmware/ekran w zipie), skrzynka 1.4.1 (NavFrame) — telemetry-navigation-kurviger.md, wymagania: telemetry-navigation-requirements.md
    - Instalacja ekranu od zera (2026-11-04): telemetria/ekran/instalacja-ekranu-od-zera.md — telemetry-ekran-instalacja.md
    - Wysyłka jazd do HA (2026-11-03): dodatek HA zaakceptowany i zbudowany — telemetry-cloud-upload-options.md
    - Dodatek HA "NT1100 Jazdy" (1.0.4) + firmware 1.2.12 (wysyłka do HA, nt1100.[DOMENA-HA]; odrzuca zapisy bez ruchu <300 m/15 km/h, auto-koniec po 15 min postoju) — telemetry-ha-addon.md. Repo publiczne GitHub pbnz7nrwm4-hub/nt1100-ha (sklep dodatków HA → Repozytoria; przycisk aktualizacji w panelu od 1.0.3). Cloudflared additional_hosts → homeassistant:8098 działa. Od 1.2.14 + dodatek 1.1.0 skrzynka aktualizuje się sama z dodatku.
    - Adrian może kiedyś SPRZEDAWAĆ urządzenie: w publicznym repo nie ujawniać sprzętu ([procesor]/[producent] itp.); LICENSE "wszelkie prawa zastrzeżone".
    - Firmware 1.3.0 + dodatek 1.2.0 (2026-11-03): wdrożony cały przegląd (MQTT urządzenie NT1100, pogoda, krętość, serwis/przebieg, hasło X-Haslo do zmian na stronie, /update tylko podpisany plik, kopie .mtl, markery .hm/.hn/.rep) — telemetry-review-2026-11-03.md
    - Dodatek 1.2.1 + firmware 1.3.1 (2026-11-03): poprawka map w dodatku (mapa jazdy psuła się za 2. otwarciem, mapa wszystkich tras rysowała się w złym miejscu). Uwaga: HA Adriana początkowo widział tylko 1.0.4 — możliwe, że dodatek był zainstalowany jako „lokalny” (wtedy trzeba przeinstalować z repo i wkleić klucz). Niesprawdzone na realnym HA: powiadomienia.
    - Dodatek 1.2.2 (diagnoza MQTT w zakładce Stan) i 1.2.3 (2026-11-03): MQTT na realnym HA nie łączyło się, bo dodatek czekał na start HA przed połączeniem; 1.2.3 łączy od razu, ponawia co 30 s i pokazuje powód. Adrian ma zaktualizować i sprawdzić Stan oraz urządzenie NT1100 w HA → MQTT. Wątek: „Przeanalizować kod i GUI pod kątem usprawnień”.
    - Przewód OBD2 → [moduł CAN] (2026-11-03, wątek „Podłączyć przewód OBD2 do [moduł CAN]”): kabel z Allegro bez rozpiski kolorów — żyły ustalić multimetrem (ciągłość). Pin 6→H, 14→L, 4/5→G; pin 16 (+12 V) NIE podłączać, zaizolować; tulejki 0,25–0,5 mm², skręcić H/L. Zasilanie z pinu 16 odradzone (stałe +12 V, wspólny bezpiecznik); zostaje gniazdo DC. Instrukcja w wątku. Działa też w aucie (OBD2 po CAN, od ~2008; zrobić Skan po zmianie pojazdu). Jeśli po włączeniu zapłonu „nasłuch (cisza)” — kolory + log do wątku.
    - Lista zakupów elektronika (2026-11-03, wątek „Zrobić listę zakupów do sklepu elektronicznego”): skrzynka — 2× dławnica PG9 IP68 (Adrian kupił wcześniej za małą; zmierzyć przewody), wtyk DC 5,5×2,1 męski na śruby (+ w środku), przewód 2×0,5 mm² ~2 m, oprawka bezpiecznika wodoodporna + bezpieczniki 2 A, wtyk zapalniczki z bezpiecznikiem albo fuse tap, tulejki 0,25–0,5 + zaciskarka, termokurczki 3–5 mm, taśma, multimetr. Ekran — kabel USB-C, 4× M3×8 (+ ew. wkładki M3; średnica otworów do potwierdzenia), przewód 1,25 mm 2-pin tylko jeśli biegunowość akumulatora odwrotna.
- UWAGI ADRIANA DO ZEBRANIA (2026-11-03, „zbieraj uwagi, jeszcze nic nie rób” — nie wdrażać bez polecenia):
    1. Dodatek HA, połączone jazdy: nie da się wyświetlić łącznego przebiegu trasy na jednej mapie; trzeba wchodzić w każdy odcinek osobno. Chce widok/odtworzenie całej połączonej trasy naraz.- Wyniki skanu CAN (2026-11-03): 500 kbit/s 29-bit, tylko ECM, motocykl nic nie nadaje sam, P0500 zapisany — telemetry-can-scan-results.md
- Firmware 1.3.2 + dodatek 1.2.4 (2026-11-03): skan rozszerzony UDS — telemetry-firmware-132.md
- Firmware 1.3.3/1.3.4 + dodatek 1.2.5/1.2.6 (2026-11-03): skan ze strony skrzynki (zakładka „Skan”), strona sama na postoju, poprawki bloków 56 B — telemetry-firmware-133.md
- Firmware 1.4.0 + dodatek 1.3.0 (2026-11-03): dane z silnika w jeździe (sprzęgło, stopka, gaz zamknięty, wtrysk → spalanie z mnożnikiem) — telemetry-firmware-140.md
- Demo trasy na ekranie 1.0.2 + symulacja w dodatku 1.4.5; ekran 1.0.3 (zasilanie, 1.4.6), 1.0.4 (kolory, 1.4.7), 1.0.5 (dotyk 180°, 1.4.8); skrzynka 1.4.3 (dodatek 1.4.9); ekran 1.0.6 mapa (1.4.10), 1.0.7 (1.4.11), 1.0.8 wygląd makiety (1.4.12), 1.0.9 iPhone BLE + dźwięki (1.4.13), 1.0.10 szybkie Wi-Fi (1.4.17), 1.0.11 bateria w Stanie (1.5.1), 1.1.0 mapa z tłem (1.5.3), 1.1.1 najpierw skrzynka potem Wi-Fi (1.5.4), 1.1.2 menu Wi-Fi/wersja (1.5.6) (2026-11-04) — telemetry-ekran-demo.md
- Wersje całego oprogramowania w jednym miejscu: karta w dodatku 1.4.15 (zakładka Stan) — telemetry-wersje.md
- Przeprojektowanie GUI dodatku (2026-11-04): makieta 4 zakładek czeka na akceptację — telemetry-addon-redesign.md
- Ekran 1.1.2 (2026-11-04, dodatek 1.5.6, PR #27: „Ustawienia Wi-Fi” = restart do strony ustawień, „Sprawdź wersję” pokazuje wynik na przycisku; łatki z korzenia zipa, nie firmware/ekran). Wcześniej 1.1.1 (1.5.4: skrzynka przed Wi-Fi; 1.1.0 = 1.5.3): nowa mapa (woda, nazwy, CRC/gz), iPhone BLE + dźwięki (1.0.9), szybkie Wi-Fi (1.0.10), bateria w Stanie (1.0.11); czeka na testy Adriana — telemetry-ekran-instalacja.md, telemetry-ekran-plan-ble.md
- Nawigacja CarPlay (2026-11-04): rekomendacja OsmAnd Maps+ (dokładne prowadzenie po GPX), plan B Kurviger — telemetry-carplay-nawigacja.md
````

### `feedback-auto-merge.md`

````markdown
---
name: feedback-auto-merge
description: Adrian (2026-11-04): Claude ma sam scalać swoje PR-y do main w nt1100-ha, bez pytania
metadata:
  type: feedback
---

Po zbudowaniu i przetestowaniu zmian w repo pbnz7nrwm4-hub/nt1100-ha scalaj PR do main samodzielnie (squash), gdy CI jest zielone. Nie proś Adriana o scalenie ani o zgodę.
**Why:** 2026-11-04 Adrian: „to scal wszystko, czemu ja mam to scalać albo cię o to prosić”. HA czyta tylko main, więc niescalony PR = brak aktualizacji.
**How to apply:** po pushu otwórz PR, poczekaj na zielone CI i od razu scal. W odpowiedzi napisz, że jest scalone i że wystarczy zaktualizować dodatek w HA.
````

### `proxmox-host-resources.md`

````markdown
---
name: proxmox-host-resources
description: Zasoby hosta Proxmox Adriana (2026-11-04): i5-4590T 4 rdzenie, 11 GiB RAM, 2 dyski HDD; przydziały VM HA i LXC drukarka; brak RAM na silnik tras
metadata:
  type: project
  modified: 2026-11-04T11:06:14.546Z
---

Odczyt z Shell Proxmoxa 2026-11-04 (wątek „Sprawdzić zasoby Proxmoxa pod silnik tras”):
- Host `pve`: Intel i5-4590T (4 rdzenie, bez HT, 2,0 GHz), RAM 11 GiB (prawdopodobnie 12 GB DDR3L w mini PC), swap 8 GiB (używane 1,1 GiB = już brakuje RAM), dostępne ~3 GiB.
- Dyski: oba talerzowe 2,5" — sda WD 320 GB, sdb WD 500 GB. Magazyny: local (dir) 77 GB wolne, local-lvm (lvmthin) 163 GB wolne, USB1 (dir) 366 GB wolne.
- VM 101 homeassistant: 4 rdzenie, 8192 MB, dysk 48 GB na local-lvm.
- LXC 110 drukarka: 2 rdzenie, 512 MB, swap 256, 4 GB na local-lvm.
- Silnik tras ([[telemetry-navigation-kurviger]]) wymaga 4 rdzenie / 8 GB RAM / 30 GB — dysk i CPU OK, RAM NIE mieści się bez zmian (dokładka RAM do 16 GB albo zmniejszenie HA + PAMIEC=4g).
- Komputer: **Fujitsu ESPRIMO Q920** (mini PC), 2 gniazda SO-DIMM, max 16 GB. Obsadzone: 8 GB Kingston 9905428-087 (DIMM A3) + 4 GB Samsung M471B5173EB0-YK0 (DIMM B4), DDR3L 1600. Zalecono wymianę 4 GB na 8 GB DDR3L PC3L-12800S SO-DIMM (2026-11-04).
- 2026-11-04: realne zużycie HA (Ustawienia → System → Sprzęt) = 1,7 GB / 8 GB. Plan na 12 GB bez zakupów: HA 4 GB (restart VM), LXC nawigacji 6 GB RAM + PAMIEC=5g, 4 rdzenie, 30 GB na local-lvm; swap hosta 8 GB jako zapas przy imporcie. Dokładka RAM do 16 GB opcjonalna.
- Sieć hosta (2026-11-04): Proxmox VE 9.2.2, karta USB `nic0` ([KARTA-SIECIOWA]), most `vmbr0` z `inet dhcp` → GUI pokazuje typ Unknown i NIE oferuje vmbr0 w kreatorze CT/VM. Kontenery tworzyć poleceniem `pct create ... --net0 name=eth0,bridge=vmbr0,ip=dhcp`. Szablon pobrany: local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst.
- Kontener nawigacji (2026-11-04): LXC **100** `nawigacja`, Debian 12, 4 rdzenie, 6144 MB RAM, swap 4096, 30 GB local-lvm, DHCP → **[IP-LXC-NAWIGACJA]** (zalecono rezerwację w routerze). HA (VM 101) zmniejszony do 4 GB. Instalacja: `PAMIEC=5g nohup bash install-lxc.sh > /root/instalacja.log` w /root/nt1100-ha/silnik-tras; adresy dla dodatku: silnik http://[IP-LXC-NAWIGACJA]:8989, mapa http://[IP-LXC-NAWIGACJA]:8988.
- 2026-11-04 13:05: instalacja silnika w LXC 100 zakończona OK (import PL ok. 40 min, graf 7,0 mln węzłów / 8,2 mln krawędzi, szczyt pamięci Javy ok. 2,7 GB z 4,4 GB). Następnie: wpisać adresy w dodatku 1.4.0 i „Pobierz mapę z kontenera”.
````

### `telemetry-addon-redesign.md`

````markdown
---
name: telemetry-addon-redesign
description: Przeprojektowanie GUI dodatku HA NT1100 (1.5.0, 2026-11-04): 4 zakładki, mapa wektorowa z kafelkami z Proxmoxa, decyzje Adriana
metadata:
  type: project
  modified: 2026-11-04T21:00:00.000Z
---

2026-11-04 Adrian: „trzeba spojrzeć holistycznie” → makieta https://claude.ai/artifact/B2FUqSX5Rz6Ja4FDHRQTjh (6 ekranów) — Adrianowi SIĘ PODOBA, budujemy jako dodatek 1.5.0.
- 4 zakładki: Jazdy (Lista|Statystyki), Trasy (mapa na cały ekran + wysuwany panel; „co po drodze” jako pasek, gdy motocykl jedzie), Motocykl (stan 3 urządzeń, przebieg+serwis „Zrobione”, parking, skan, szczegóły techniczne), Ustawienia (wszystkie, lista grup → podstrony).
- Krętość odcinka: przycisk „kręto ▾” między punktami → panel z 4 dużymi opcjami; „Mój plan” z paskiem udziału wariantów.

Mapa (decyzje 2026-11-04):
- Wybrał „od razu kafelki z Proxmoxa” (MapLibre + własny ciemny styl; zrzuty porównań w /mnt/project-files/telemetria/dodatek-1.5/).
- Bez sąsiadów (CZ/SK) na razie; trasy po CZ/SK dopiero po wymianie RAM (GraphHopper ~9–10 GB). W kafelki.sh jest MAPA_DODATKOWE na później.
- ZAAKCEPTOWANE 19:06: mapa dodatku A podstawowa + C szczyty/przełęcze + D cieniowanie gór (DEM w kontenerze), bez budynków; ekran: wgranie przez czytnik kart (paczka z dodatku), aktualizacja tylko zmienionych kwadratów (suma kontrolna w manifeście), kompresja przesyłu, najpierw okolica domu/trasy, + woda i nazwy miejscowości na ekranie.

Stan kodu (2026-11-04 ~19:30): dodatek 1.5.0 (PR #20) i 1.5.2 (PR #22) scalone (1.5.1 = wątek Ekran, bateria ekranu). 1.5.2: crc32 w manifeście mapy, pobieranie tylko zmienionych kwadratów, manifest dla ekranu posortowany dom→trasa→reszta, /api/nav/mapa/<k>.ntt.gz, ZIP na kartę (Motocykl → Ekran i mapa), .ntt część „tło” (bajt 5 bit0: woda/wyspy/rzeki/miejscowości), postęp przebudowy kontenera w www/stan.json. Kafelki: Planetiler dostawał „No route to host” (Java/IPv6) → dane pomocnicze pobiera curl (kafelki.sh). Firmware ekranu (pobieranie .gz z crc, rysowanie tła) robi wątek Ekran wg /mnt/project-files/telemetria/ekran/mapa-format-1.1.md. Firmware ekranu NIE w tym wątku.
Związane: [[telemetry-navigation-kurviger]], [[telemetry-ha-addon]].
Kierunek (Adrian 2026-11-04 19:58): planer w dodatku ma działać bardzo responsywnie i przejrzyście „jak nawigacja”; łatwe przesłanie trasy do docelowej nawigacji CarPlay (wybór aplikacji: wątek „Wybrać nawigację CarPlay do tras”, integrację robi ten wątek); ekranik pokazuje to, czego aplikacja nie ma (fotoradary, limity). 1.5.5: pomiń miejscowość + okrężna km/czas (PR #25).
1.5.7 (PR #28, scalone 2026-11-04): omijanie szutrowych osobno od gruntowych, ulubione miejsca (settings.fav, /api/nav/fav, skrót „jedź do” po nazwie), kontener: Planetiler --nodemap-type=sparsearray (array dawało „No space left” mimo 22 GB wolnego), `aktualizuj.sh --stan`. 1.5.8 (PR #29): tryb motocykl/samochód (settings.vehicle, go_variant=szybko w aucie, ping lean_popup_deg=90). Adrian 20:31: w aucie jeździ z OsmAnd BEZ skrzynki i ekranu (więc nie trzeba oznaczać jazd). 1.5.9 (PR #30): „🚗 Jadę (OsmAnd)” + pilnowanie korków TomTom (klucz wpisany) z pozycji telefonu HA, objazd i powiadomienie z podpisanym linkiem /api/nav/trasa.gpx; niesprawdzone na iPhonie.
Kontener (2026-11-04 23:30): Planetiler musi mieć --storage=ram --nodemap-type=sparsearray, Java 5g (HDD w Proxmoxie: mmap = ~200 dróg/s). 1.5.10–1.5.12: GPX w formacie OsmAnd (rte+osmand:turn, <time> przy trkpt) w obu trybach, czytelny błąd silnika.
````

### `telemetry-atom-indicator.md`

````markdown
---
name: telemetry-atom-indicator
description: Wskaźnik stanu skrzynki na [wskaźnik]: protokół [radio bezpośrednie], kolory diody, przycisk, pliki (stan 2026-11-01)
metadata:
  type: project
---

Ustalone z Adrianem 2026-11-01: [wskaźnik] = tylko wskaźnik stanu skrzynki (nie ma baterii, SD, GPS). Kolory: niebieski oddycha = czeka/postój, zielony = jazda OK, żółty = jazda bez GPS/IMU/OBD, czerwony stały = błąd SD/zapisu, czerwony pulsujący = brak łączności ze skrzynką (Adrian: "czerwony to błąd i tyle", bez kodów błysków), biały mruga = wysyłka. Jasność auto dzień/noc (elewacja słońca z czasu i pozycji GNSS, próg -4°), długie naciśnięcie: auto/ciemno/pełna. Krótkie naciśnięcie = znacznik (event kEvMarker=8 w .mtl; NIE jest jeszcze pokazywany na stronie jazdy — do zrobienia).
Protokół: core/atomlink.h ([wskaźnik] 20 B broadcast co 1 s na kanale 1, podczas wysyłki kanał sieci domowej; [wskaźnik] skanuje kanały 1-13 gdy brak ramek 4 s; [wskaźnik] 5 B unicast, powtarzany do flagi ack).
Pliki (2026-11-01, nieprzetestowane na sprzęcie): /mnt/project-files/telemetria/nt1100-atom-1.0.0-full.bin ([narzędzie do wgrywania] 0x0, reset 2 s → zielona = tryb wgrywania), nt1100-telemetria-1.2.5-{full,ota}.bin, nt1100-telemetria-zrodla-1.2.5.zip (firmware/atom/, build.sh), atom-instrukcja.md.
Firmware skrzynki 1.2.5 trzyma Wi-Fi STA włączone podczas nagrywania ([radio bezpośrednie]).
Powiązane: [[telemetry-firmware-status]], [[telemetry-hardware-plan]], [[telemetry-dev-backlog]]
````

### `telemetry-box-sleep-desk.md`

````markdown
---
name: telemetry-box-sleep-desk
description: 2026-11-04 Adrian: skrzynka "usypia/wyłącza się" na biurku mimo zasilania — analiza kodu 1.4.1, podejrzenie powerbanku
metadata:
  type: project
  modified: 2026-11-04T09:09:16.629Z
---

Kod 1.4.1: powerOff tylko gdy brak VBUS (>4000 mV) — po jeździe (grace 60 s przy bat>=50%, 20 s >=20%, inaczej 3 s), na ekranie postoju (3 s), w trybie strony (10 min bez zapytań). Z zasilaniem nigdy się nie wyłącza. Pozorne "usypianie": ekran 25 po zmroku, 5 na ekranie postoju; po 2 min bez ruchu (kStillPageQuietMs) koniec nagrania i strona skrzynki.
Wniosek wysłany Adrianowi: najpewniej powerbank odcina przy małym poborze. Poproszono o test z ładowarką/komputerem i info, czy ekran tylko ciemny, czy całkiem wyłączony. Zaproponowano (niewdrożone, czeka na zgodę): komunikat "Zniknęło zasilanie USB" + powód końca w raporcie.
Powiązane: [[telemetry-firmware-140]]

2026-11-04 09:27: Adrian — zasilanie z ŁADOWARKI SIECIOWEJ, nie powerbanku; teoria powerbanku odpadła. Zapytano o objawy (dotyk budzi?/czas/co na ekranie) i zaproponowano wersję diagnostyczną (powód restartu esp_reset_reason + napięcie VBUS w zakładce Stan) — czeka na zgodę.
2026-11-04 10:10: Adrian „Zrób” → firmware 1.4.2 (src/hw/powerlog.*: powód restartu/wyłączenia, rejestry 0x20/0x21 układu zasilania, napięcie USB, faza, NVS „pwrlog” 12 wpisów; karta „Zasilanie i restarty” w Stan; RTC ustawiany z GNSS) + dodatek 1.4.1. PR #3 scalony do main 2026-11-04 10:57; pliki 1.4.2 full/ota/źródła w telemetria/. Arduino-cli w /root/tools (instalacja od zera w nowym kontenerze).
````

### `telemetry-can-scan-results.md`

````markdown
---
name: telemetry-can-scan-results
description: Wyniki pierwszego skanu CAN NT1100 (2026-11-03, skan 005/006): 500 kbit/s, 29-bit, tylko ECM, lista PID-ów, kod P0500
metadata:
  type: project
---

2026-11-03 Adrian podłączył przewód OBD2 → [moduł CAN] (Port B) i zrobił skany 005 (zapłon) i 006 (silnik, gaz), firmware 1.3.1.
- Magistrala 500 kbit/s, adresowanie 29-bit (zapytania 18DB33F1, odpowiedź 18DAF110 = ECM "ECM -EngineControl"). Motocykl SAM NIC NIE NADAJE na złączu (cisza bez zapytań) → kontrolek ABS/TC, biegu itp. nie da się podsłuchać z tego złącza; ABS nie odpowiada na standardowe OBD2.
- PID-y mode 01: 02 03 04 05 06 08 0B 0C 0D 0E 0F 11 12 1C 21 41 (obciążenie, temp. płynu, MAP, obroty, prędkość, wyprzedzenie, temp. powietrza, przepustnica). Brak 42 (napięcie) i 01. Firmware jazdy i tak czyta 04/05/0C/0D/0F/11 w 29-bit; bieg liczony z obrotów/prędkości.
- ~14 odpowiedzi/s łącznie.
- Kod zapisany P0500 (czujnik prędkości), PID 21 = 20 km z MIL. Tryb 0A bez odpowiedzi. VIN w pliku skanu (nie wpisywać do publicznego repo).
**How to apply:** nie kasować kodów bez decyzji Adriana; zapytano, czy świeci "check engine" i czy ABS/TC gasną po ruszeniu. Pomysł dekodowania kontrolek z CAN ([[telemetry-dev-backlog]]) nieaktualny dla tego złącza. Zob. [[telemetry-hardware-plan]].
Research 2026-11-03: brak publicznego opisu CAN dla NT1100; projekty open source Hondy (sophienyaa Honda-Motorcycle-Dash, HondaECU) to K-line 4-pin, nie Euro 5. Duonix Bike-Scan 2 Pro (kabel ISO 19689) czyta ABS i dane na żywo w Africa Twin 1100 Euro 5 → ABS osiągalny przez DLC protokołem Hondy. Zaproponowano „skan rozszerzony” 1.3.2 (wykrycie sterowników, kody, dane; tylko odczyt) — czeka na zgodę Adriana.
Pogłębiony research (2026-11-03, raport /mnt/project-files/telemetria/research-can-honda-euro5.md): w Hondach Euro 5 (CB1000R 2021, honda-board.de) CAN złącza łączy się TYLKO z ECM; ABS i BCM są na K-line (pin 6 złącza 6-pin = pin 7 OBD2) z NOWYM, nieopisanym protokołem (stary HDS 10400 bps/FE 04 72 8C nie działa). AiM przez Euro 5 czyta to samo co my. HealTech nie obsługuje ABS Hondy ani Euro 5. Wszystkie projekty OSS = K-line 4-pin 2007–2019. Plan 1.3.2 „skan rozszerzony” (tylko odczyt): (1) przegląd 255 adresów 18DAxxF1 (3E/10 01), (2) UDS 22 xxxx w ECM + porównanie postój/bieg/gaz (bieg), (3) tryb 02 zamrożone dane. Czeka na zgodę Adriana.
````

### `telemetry-carplay-nawigacja.md`

````markdown
---
name: telemetry-carplay-nawigacja
description: Wybór aplikacji CarPlay do prowadzenia po trasie z dodatku (2026-11-04): rekomendacja OsmAnd Maps+, plan B Kurviger, jak wysyłać trasę
metadata:
  type: project
  modified: 2026-11-04T20:00:25.636Z
---

2026-11-04 (wątek „Wybrać nawigację CarPlay do tras”): Adrian chce planować w dodatku HA (responsywnie, „jak nawigacja”), a prowadzić w aplikacji CarPlay na NT1100; ekran [procesor] pokazuje fotoradary/limity.

Rekomendacja: **OsmAnd z Maps+** (CarPlay płatne: Maps+ lub Pro, ok. 10–15 €/rok), bo „Nawigacja po śladzie” (Follow track) trzyma się GPX dokładnie, mapy offline, OSM jak nasz GraphHopper. Plan B: **Kurviger Tourer+** (~30 €/rok; CarPlay od 3.5.7, 2025; import GPX „route + track” tylko zbliżony do śladu). Odrzucone: Google/Apple Maps, Waze (brak GPX, przeliczają), Calimoto (GPX = Premium, przelicza), MyRoute (śledzenie śladu w CarPlay niepewne), Scenic (CarPlay w trakcie migracji), TomTom/Sygic (GPX przez stronę/przeliczanie).
NT1100: CarPlay po USB (bezprzewodowo tylko przystawką).
Wysyłka jednym kliknięciem (do zrobienia przez wątek Nawigacji, nie wdrożone): przycisk „Wyślij do nawigacji” w dodatku → GPX (trk gęsty + rtept) pod linkiem z kluczem → arkusz udostępniania iOS „Otwórz w OsmAnd” albo skrót iOS / powiadomienie HA z akcją.
Powiązane: [[telemetry-navigation-kurviger]], [[telemetry-addon-redesign]]
Instrukcja OsmAnd (Claude Doc): https://claude.ai/artifact/MVzx5WFKSZAHNGdumQz7nx — 2026-11-04 przepisana po skardze Adriana („przyciski nie tam”), ścieżki sprawdzone w docs.osmand.net (iOS): Menu → Moje miejsca → Ślady → folder Import → PRZYTRZYMAJ trasę → Nawigacja → Ustawienia → „Podążaj za trasą” (polskie etykiety ze zrzutu Adriana: Wybierz inną trasę, Odwróć kierunek trasy, Dołącz do dróg, Nawiguj do: Początek trasy/Najbliższy punkt, Rodzaj nawigacji: Linia prosta/Jazda, Zamknij); Menu → Ustawienia → Profil CarPlay; CarPlay: OsmAnd → Ślady. Pisać instrukcje UI tylko po sprawdzeniu w dokumentacji, nie z pamięci.
Styl OsmAnd NT1100 (2026-11-04, Adrian wybrał): /mnt/project-files/telemetria/osmand/NT1100.render.xml + generator zrob_styl_nt1100.py (z default.render.xml OsmAnd-resources master; przekolorowuje TYLKO tryb nocny na paletę narzedzia/mapa_styl.py, trasa #f76707). Wymaga Tryb mapy = Noc. v1 niesprawdzona na telefonie — poprawki po zrzutach Adriana. Prowadzenie z GPX w OsmAnd potwierdzone zrzutem (skręty z nazwami ulic).
````

### `telemetry-cloud-upload-options.md`

````markdown
---
name: telemetry-cloud-upload-options
description: Warianty wysyłki jazd NT1100 do chmury/HA omówione 2026-11-03; rekomendacja: własny dodatek HA "NT1100 Jazdy" z tą samą stroną co skrzynka
metadata:
  type: project
---

2026-11-03: Adrian NIE chce Grafany/InfluxDB; chce rozwijać stronę skrzynki; preferuje wysyłkę do Home Assistant (albo GitHub+HA, albo telefon → HA).
Dokument z porównaniem 5 wariantów: https://claude.ai/artifact/SCwkFLVfB3Bz1tZEkx1XLw
Rekomendacja Claude: własny dodatek HA "NT1100 Jazdy" (instalacja lokalna przez Samba/File editor, bez GitHuba): przyjmuje pliki jazd (POST z kluczem) i serwuje TĘ SAMĄ stronę co skrzynka (te same /api/* , panel w bocznym menu HA, działa w aplikacji HA na iPhonie i przez Cloudflare) + czujniki ostatniej jazdy w HA (może zastąpić ntfy). Krok 1: wysyłka z domowego Wi-Fi (adres lokalny). Krok 2: dodatek w tunelu Cloudflare, wysyłka przez hotspot w trasie. Krok 3: LTE + podgląd na żywo.
Odradzone: GitHub jako pośrednik (token z zapisem na skrzynce, i tak wymaga internetu), telefon jako pośrednik (Safari bez Web Bluetooth, Skróty bez BLE, własna aplikacja = konto Apple/Xcode/limity tła). Cloudflare Worker+R2 = zapas, gdy dom zawodny.
Pytania otwarte do Adriana: czy wystarczy widzieć jazdy po powrocie do domu, czy już w trasie; czy Wi-Fi sięga do miejsca parkowania; zostawić InfluxDB/MQTT jako opcję czy usunąć.
**Why:** firmware 1.2.10 ma już kolejkę wysyłki (Influx/MQTT) — zmienia się tylko adresat.
**How to apply:** nie kodować przed akceptacją Adriana. Zob. [[telemetry-dev-backlog]], [[telemetry-firmware-status]].
2026-11-03 00:09 Adrian: hotspot NA PEWNO (wysyłka w trasie); LTE chce omówić, najtańszy wariant; aplikacja iOS "ciekawa", ale pyta czy ma sens wobec dodatku HA. Odpowiedź Claude: aplikacja zbędna (aplikacja HA + strona na ekranie początkowym), wraca tylko przy potrzebie podglądu offline po BLE. LTE najtaniej: (a) modem USB z Wi-Fi (Huawei E8372 / chińskie "UFI" 4G) z gniazda motocykla = zero zmian w kodzie, ale gaśnie z zapłonem → wysyłka na postoju z zapłonem/w trakcie jazdy; (b) [producent] [modem LTE] HAT 139 zł (Botland) w skrzynce = działa też po zgaszeniu, wymaga PPP w firmware. Plus tania karta SIM na dane (MB/mies.).
2026-11-03 00:15 Podłączenie [producent] [modem LTE] HAT (odpowiedź dla Adriana): bez lutowania przewodem Grove→4×żeński dupont do 40-pin (pin 2=5V, 6=GND, 8=TXD, 10=RXD wg standardu Pi); po stronie [skrzynka-płytka] Port A (G1/G2, czerwony) bo Port C G17/G18 zajął GPS, Port B = CAN. Zworka poziomu na 3V3 (wiki: "B and 3V3 to PWR"). NIEPOTWIERDZONE (schemat [dokumentacja producenta] automatyczne włączanie vs PWRKEY (ew. pin 7 Pi do wolnego pinu [skrzynka-płytka]), rozmiar SIM, prąd szczytowy z 5V [skrzynka-płytka] na baterii. Pasma LTE B1/3/5/7/8/20, 65×30,5 mm.
2026-11-03 00:15 Adrian: LTE ([producent]/modem USB) ODŁOŻONE — zastanawia się nad sensem wydatku. Aplikacja iOS — nie. Hotspot tak. Dalsze prace (dodatek/strona w HA + sposób wysyłki po połączeniu z internetem) w osobnym wątku.
2026-11-03 00:20 Wątek "Zbudować stronę jazd w Home Assistant": wysłany Adrianowi plan dodatku (czeka na OK): wysyłka HTTPS POST pliku jazdy (.trk + .json + .thm + .nam) na /api/ingest dodatku z nagłówkiem X-Klucz (losowy klucz generowany w dodatku, wklejany w Ustawieniach skrzynki); dwa adresy: lokalny (http://IP-HA:8099) w domu, publiczny (https://nt1100.<domena> przez Cloudflare Tunnel, tylko /api/ingest otwarte bez logowania Cloudflare Access) w trasie; pliki w /share/nt1100 (widoczne przez Samba, w kopii zapasowej HA); panel przez Ingress (boczne menu, aplikacja HA); encje sensor.nt1100_* (km, maks. przechył L/P, czas, maks. prędkość, data) przez REST API Supervisora + powiadomienie notify.mobile_app po każdej jeździe; strona = kopia webpage.h z flagą "tryb HA" (bez Skanu/Stanu skrzynki). Influx/MQTT: rekomendacja zostawić w kodzie, schować w "Zaawansowane". Firmware: 1.2.11.
2026-11-03 00:19 Adrian: HA z zewnątrz = https://[DOMENA-HA]/ (domena główna, kupiona w OVH, tunel przez dodatek Cloudflared w HA). Adres wysyłki ze skrzynki w trasie: nt1100.[DOMENA-HA] przez "Additional hosts" dodatku Cloudflared → port dodatku NT1100. Adrian nie rozumiał subdomen — tłumaczyć prosto.
2026-11-03 00:20 Adrian: plan dodatku OK (zaakceptowany), domowe Wi-Fi sięga do miejsca parkowania. Implementacja ruszyła.
````

### `telemetry-dev-backlog.md`

````markdown
---
name: telemetry-dev-backlog
description: Aktualna lista rozwoju skrzynki NT1100 po pierwszych testach (stan 2026-10-31 22:00)
metadata:
  type: project
---

Wszystko po pierwszych testach na sprzęcie (decyzja Adriana 2026-10-30).
1. 1.3.0: raport problemów w jeździe + powiadomienia ntfy; dołączyć progi alarmowe kanałów (pomysł z RaceCapture).
2. ZROBIONE w 1.2.6: przerwa łączenia jazd jako ustawienie (trip_gap_h).
3. Mapowanie kanałów CAN na stronie skrzynki (ID, bajty, mnożnik, offset) — po skanie/nasłuchu ramek Hondy. [[telemetry-racecapture-ideas]]
4. Strona w chmurze (Cloudflare) na domenie Adriana.
5. Decyzja: aplikacja iOS (BLE) lub LTE.
Szczegóły historii: [[telemetry-firmware-status]]
6. (2026-11-02) Podgląd na żywo w trakcie jazdy (Adrian chce): małe pakiety co 5-10 s (pozycja, prędkość, przechył), pełne dane nadal po jeździe. Hotspot iPhone niepewny (bateria, iOS wyłącza), lepiej LTE ([modem LTE]). Konflikt SD + kanał [radio bezpośrednie] [wskaźnik] do rozwiązania. Razem ze stroną w chmurze.
- Trasa GPX z Kurvigera: wgranie do skrzynki, zgodność z planem, pogoda na trasie (30 min / 1 h) na ekranie [ekran-płytka], strzałka do zakrętu — szczegóły [[telemetry-navigation-kurviger]] (2026-11-03).
- (2026-11-03) Adrian chce wyłapać z CAN kontrolki ABS/kontroli trakcji (świecą na postoju, gasną po ruszeniu ~5–10 km/h — normalne): porównać skan na postoju vs po ruszeniu i szukać zmieniającego się bitu. Czeka na pierwszy skan (skan-001).
- ZAPARKOWANE 2026-11-04 (Adrian: „zaparkuj na potem”): trasa z dodatku na CarPlay — GPX z zakładki Nawigacja → OsmAnd/Scenic/Kurviger na iPhonie → CarPlay (dongle albo fabryczny TFT NT1100). Pomysł: przycisk „Otwórz na iPhonie” w dodatku (wysyłka trasy prosto do aplikacji). Nie budować bez polecenia. Ustalone: synchronizacja = tylko wspólny GPX, prowadzenie niezależne (iPhone GPS vs skrzynka); objazd z ekranu nie trafia do CarPlay, żywego połączenia brak (aplikacje zamknięte, Apple wymaga zgody dla firm).
- CarPlay — kształt docelowy wg Adriana (2026-11-04): planuje w dodatku → „Wyślij na ekran” jednocześnie aktualizuje GPX gotowy do pobrania/otwarcia w aplikacji CarPlay na iPhonie (jeden przycisk/link w HA). Wciąż zaparkowane do polecenia.

2026-11-04 (wątek OBD2, po 1.4.0): Adrian odłożył („wróćmy do tego”) temat użycia stopki do końca jazdy. Warianty: A) stopka w górze = nigdy nie kończ jazdy / nie otwieraj strony, czasy bez zmian (15 min koniec, 2/5 min strona); B) A + szybszy koniec (2–10 min) przy stopce w dół i zgaszonym silniku (uwaga: tankowanie 3–5 min dzieliłoby jazdę). Claude rekomenduje A. Inne propozycje bez decyzji: sprzęgło w nauce biegów + statystyka zmian biegów; czas hamowania silnikiem/odcięcia paliwa; przycisk tankowania w dodatku (auto-mnożnik, zasięg); ostrzeżenia (temp. >105 °C, napięcie <13,5 V, stopka przy prędkości); stosunek licznik/GPS.
````

### `telemetry-display-choice.md`

````markdown
---
name: telemetry-display-choice
description: Zmiana koncepcji 2026-11-02: cienki wyświetlacz zamiast [wskaźnik] — przegląd opcji, rekomendacja, czeka na wybór Adriana
metadata:
  type: project
  modified: 2026-11-02T23:39:52.554Z
---

2026-11-02 Adrian chce zamiast [wskaźnik] (sama dioda) cienki wyświetlacz (cz-b lub kolor, bez znaczenia) z informacjami ze skrzynki. Przegląd: /mnt/project-files/telemetria/wyswietlacz-przeglad.md (CoreInk e-papier, StickC Plus2, [wskaźnik] z ekranem, LILYGO T-Display-S3, Unit Mini OLED; ceny z pamięci).
Rekomendacja: [producent] CoreInk (czytelny w słońcu, bateria wystarczy przy budzeniu co kilka s, przyciski); alternatywa [płytka]2 gdy przechył na żywo/noc (wtedy USB).
Łączność: rozszerzyć istniejącą ramkę [radio bezpośrednie] (core/atomlink.h, zob. [[telemetry-atom-indicator]]).
**Why:** Adrian woli minimum ingerencji (bez kabla z puszki), motocykl ma własny zegar z prędkością.
**How to apply:** NIE kodować, dopóki Adrian nie wybierze urządzenia. Zapytano o: miejsce montażu (kierownica/kokpit/szyba), zasilanie (USB czy bateria), co pokazywać (stan+podsumowanie czy przechył na żywo).
2026-11-02: Adrian zapytał o płytki [producent] [procesor]. Zaproponowano: [procesor]-Touch-AMOLED-1.8 (faworyt kolor), [procesor]-ePaper-1.54 (tańszy odpowiednik CoreInk), [procesor]-LCD-1.47 (najtańszy). Wymagają drukowanej obudowy PETG. Czeka na wybór modelu.
2026-11-02: Adrian wskazał [producent] [procesor]-Touch-AMOLED-1.8 (kamami.pl, 368x448). Brak akumulatora w zestawie → doradzono LiPo 3,7 V z wtyczką MX1.25 (500–1000 mAh, sprawdzić biegunowość), docelowo zasilanie USB z motocykla, akumulator jako zapas. Czeka na potwierdzenie wyboru i miejsce montażu.
2026-11-02: AMOLED z akumulatorem: [producent] [procesor]-Touch-AMOLED-2.06 (wersja z baterią; -EN bez), LILYGO [urządzenie] (IP65, 1100 mAh, 63,5×49×22 mm, AXP2101; polecony na motocykl). Czeka na decyzję Adriana.
2026-11-03: Adrian podesłał z kamami 4 płytki [producent] (S3 2" LCD, C6 1.43 AMOLED, S3 1.54 LCD mic, S3 1.43 AMOLED round). Zarekomendowano S3 1.43 AMOLED round lub S3 1.8 AMOLED; LCD słabsze w słońcu, C6 bez sensu vs S3. Kamami nadal blokuje fetch. Czeka na wybór (okrągły vs prostokątny).
2026-11-03: Adrian znalazł [producent] [urządzenie] [wersja] (botland): [procesor]R8, okrągły AMOLED 1,75" 466x466 dotyk ([układ] QSPI, [układ]), akumulator 450 mAh ([biblioteka/układ producenta]), 2 przyciski + power, wibracja, [IMU], [układ] RTC, [kodek audio]. Rekomendowany jako najlepszy (obudowa+bateria, przyciski). Czeka na potwierdzenie i miejsce montażu.
2026-11-03: Adrian ODŁOŻYŁ temat wyświetlacza (nic nie kupuje teraz). Gdy wróci: faworyt [producent] [urządzenie], potem [producent] S3 AMOLED 1.43/1.8, [urządzenie]. Nie kodować bez jego decyzji.
2026-11-03: Adrian zapytał o [producent] [procesor]-AMOLED-1.91 (240x536, kamami): złącze MX1.25 LiPo + ładowanie USB-C, brak baterii. Doradzono LiPo 3,7 V MX1.25 2-pin, 603040 (~700-800 mAh) lub 502535 (~400 mAh), z PCM, sprawdzić biegunowość. Brak dużych przycisków (tylko BOOT). Nadal odłożone/bez decyzji.
2026-11-03: Adrian zapytał o [producent] [procesor]-Touch-AMOLED-1.64 (gotronik.pl; 280x456, [układ]/FT3168, TF, MX1.25 bez baterii, tylko RST/BOOT). Ta sama bateria co 1.91. Wspomniano [producent] 1.75 AMOLED w aluminiowej obudowie (do sprawdzenia bateria).
2026-11-03: Adrian rozważa też tani [procesor] 2,8" LCD (prawdopodobnie CYD [procesor]-2432S028, Allegro). Najpierw odradzony, po pytaniu Adriana skorygowano: nada się (duże cyfry), minusy: LCD blednie w pełnym słońcu (daszek PETG), brak ładowarki → USB z motocykla, dotyk rezystancyjny. Bez decyzji.
Potwierdzone (zrzut z Allegro): CYD [procesor]-2432S028R, [sterownik ekranu] 320x240, dotyk rezystancyjny, moduł 50x86 mm, 5 V ~115 mA, praca -20..70°C, kąt >60°. Uznany za dobrą tanią opcję na USB w osłoniętym miejscu.
CYD cd.: micro-USB (nie USB-C), złącze "4P 1.25 Power port" = wejście 5 V (NIE bateria), dioda RGB (można użyć jako kolor stanu jak [wskaźnik]), [procesor]-WROOM-32.
2026-11-03: [producent] [procesor]-Touch-LCD-2.8 (wiki): S3R8, ST7789 240x320 260 cd/m2, dotyk pojemn. CST328, MX1.25 LiPo z ładowaniem + przycisk zasilania, USB-C, QMI8658, PCF85063, TF, głośnik, 73x51 mm. Polecony zamiast CYD jako "duży ekran"; bateria np. 103040. Nadal bez decyzji.
Akumulator polecony (2026-11-03): Akyga AKY1732 (LiPo 3,7 V 1000 mAh, PCM, 1,25 Molex 2-pin, przewód 150 mm; Ropla), zamiennik AKY1517 (40 mm). Adrian ma przysłać zdjęcie wtyczki do sprawdzenia biegunowości.
Szkic obudowy [producent] 2.8 + LiPo (2026-11-03, tylko podgląd, bez STL): /mnt/project-files/telemetria/druk/ws28/ (koncepcja.py, koncepcja.png, przekroj.png). Ok. 78x56x19 mm + daszek 22 mm; korpus z ramką na LiPo, ramka czołowa z daszkiem na 4 wkręty, Dual Lock jak [wskaźnik]. Założona grubość LCD 4,5 mm, LiPo 50x34x6 — do weryfikacji z rysunkiem 3D [producent].
Adrian znalazł LiPo 523450 (52x34x5 mm, 1000 mAh, PCM, 1,25 mm 2-pin, Allegro) — pasuje; szkic przeliczony (~78x56x18 mm). Uwaga: praca 0–45°C wg oferty, na słońcu ryzyko — jasny PETG, daszek, otwory.
Akumulator wybrany do [producent] 2.8 (2026-11-03): innCraft IN503450 1000 mAh, 51x34x5, Molex 51021-0200, przewód 60 mm, PCM, rozład. -20..60°C, ładow. 0..45°C, ~22 zł. Odrzucony: wersja 3-przewodowa z NTC (3-pin nie pasuje).
Okno ekranu (2026-11-03): zaproponowano bez osobnej szybki — ramka dociska szkło dotyku przez piankę/VHB, plus matowa folia antyrefleksyjna; alternatywa poliwęglan 1 mm w rowku. Przezroczysty PETG odpada (mleczny).
2026-11-03 porównanie ofert Allegro (PDF): Elektroweb [procesor] 2,8" IPS dotyk pojemn. + głośnik/mikrofon 117,70 zł (nieznany model, może [producent] — Adrian ma zapytać sprzedawcę); CYD 99 zł (przepłacony); NerdMiner V2 = CYD powystawowy 119 zł (odpada). Rekomendacja: oryginalny [producent] [procesor]-Touch-LCD-2.8 (botland/kamami).
Elektroweb (Allegro 117,70 zł) = [producent-ekranu] [ekran-płytka] (https://www.[producent-ekranu]/2.8inch_[procesor]_Display): [procesor] N16R8, [sterownik ekranu] IPS 240x320, [sterownik dotyku] (I2C IO15/16, INT17, RST18), 230 cd/m2 z dotykiem, 86x50x10,6 mm, BAT 1,25 mm 2P + TP4054 (~290 mA), USB-C, WS2812 IO42, [kodek audio]+FM8002E, mic, microSD, BOOT IO0; jest rysunek wymiarów i 3D. Polecony na równi z [producent] 2.8 (Adrian ma wybrać).
Szkic obudowy [ekran-płytka] (2026-11-03): /mnt/project-files/telemetria/druk/ws28/koncepcja_[ekran-płytka].py + [ekran-płytka]-koncepcja.png/-przekroj.png; ~91x55x20 mm + daszek 22; płytka na 4 słupkach (otwory w rogach), okno przesunięte (szkło 69,2 mm), USB-C i popychacz BOOT z boku, okienko dla RGB, Dual Lock jak [wskaźnik]. STL po zamówieniu, z [ekran-płytka]_Size.pdf / 3D z [producent-ekranu].
2026-11-03 WYBÓR ADRIANA: [ekran-płytka] (Elektroweb, Allegro) + innCraft IN503450. Obudowa gotowa (nieprzetestowana): /mnt/project-files/telemetria/druk/ekran/ (ekran-korpus.stl, ekran-klapka.stl, ekran_obudowa.py, podglad.py, README.md, PNG). 91x55x21 mm + daszek 20 mm (X=50 strona u góry, USB-C z prawej, krajobraz); korpus 1 wydruk (stoi na końcu USB), klapka + 4x M3x20 stożkowe przez tulejki do narożników; uszczelka pianka 1 mm; otwory BOOT/RESET w klapce. Montaż: kokpit, pomysł klin na panelu obok TFT + Dual Lock lub poprzeczka GPS — czekam na zdjęcia kokpitu z linijką. Firmware wyświetlacza jeszcze nie pisany.
Uchwyty ekranu (2026-11-03): ekran-uchwyt-kierownica-28.stl (siodełko 28,6, 2 opaski) i ekran-uchwyt-klin-15.stl (VHB na panel), płyta 76x44, w druk/ekran/. Szukanie wymiarów kokpitu NT1100 w sieci: tylko TFT 6,5"; brak wymiarów paneli i brak gotowej poprzeczki GPS dla NT1100 (SW-Motech crossbar 10-12/13-16 mm, NT1100 jej nie ma). Szacunek z foto: panele obok dolnego LCD ~70-80 x 45-50 mm — obudowa 55 mm wysoka, może być ciasno.
2026-11-03 23:45 Adrian: "lepiej bez daszka, ale zostaw" → potem "Ale zostaw. Już drukuje" = drukuje wersję Z daszkiem (ekran-korpus.stl bez zmian); dodatkowo ekran-korpus-bez-daszka.stl.
````

### `telemetry-ekran-101.md`

````markdown
---
name: telemetry-ekran-101
description: Ekran nawigacji 1.0.1 + dodatek 1.4.4 — Tankowanie/Jedzenie w menu, postój, rozmiar karty 16 GB
metadata:
  type: project
---

- 2026-11-04 ekran 1.0.1 + dodatek 1.4.4 (PR #6): menu po przytrzymaniu (też bez trasy i na postoju) ma Tankowanie/Jedzenie; `src/core/nearby.*` findPlaces (3 najbliższe przed Tobą na trasie ≤40 km/≤1,5 km od trasy, bez trasy 6 km); wybór → postój offline (A* do miejsca, zielony znacznik) + POST /api/nav/via (stary >3 min nie jest wysyłany). Źródła: /mnt/project-files/telemetria/nt1100-telemetria-zrodla-1.4.2-ekran-1.0.1.zip. Karta 16 GB: mapa 3 województw = 51 MB, cała PL ~300–500 MB → wystarczy z dużym zapasem.

Powiązane: [[telemetry-navigation-kurviger]]

- 2026-11-04 dodatek 1.4.14 (PR #16): GPX do udostępnienia (Web Share na iPhonie; naprawiony Content-Disposition z polskimi literami), suwaki krętości wariantów (ustawienia nav.curvy: glowne/zakrety/dluzej 0–100, domyślne ≈ dawne wagi) i progi opisu (nav.curvy_levels, też dla jazd), „Mój plan” (legs per odcinek → wariant "mix", gh_mix), blokada mapy planera po policzeniu (🔒/⤢). Niesprawdzone na prawdziwym silniku: jak suwaki zmieniają trasy.
````

### `telemetry-ekran-demo.md`

````markdown
---
name: telemetry-ekran-demo
description: Demo trasy na ekranie 1.0.2 + symulacja w dodatku 1.4.5; ekran 1.0.3 (zasilanie) zbudowany na tym; gdzie źródła
metadata:
  type: project
---

2026-11-04, wątek „Zasymulować demo jazdy na ekranie”. Adrian chciał zobaczyć nawigację bez jazdy.
- Ekran 1.0.2 (PR #7, dodatek 1.4.5): przycisk „Demo trasy” na ekranie „Szukam skrzynki...” i w Menu postoju. Jedzie trasę z karty albo wbudowaną Start – Meta 22 km (src/core/demoroute.h, z OSRM; generator host/demoroute_gen.py). Silnik src/core/demo.* (limity, zakręty 4,2 m/s², postój 50 s na 1. punkcie, zjazd 230 m w bok), tap ×1/×4, menu „Koniec demo”, nic nie wysyła do dodatku. Flaga: g_demo.active(), UiState.demo.
- Dodatek 1.4.5: „Dodaj trasę demo” (POST /api/nav/demo, plik nt1100_jazdy/demo-trasa.json), „Symulacja” przy trasie (nav.js, canvas podglądu ekranu), GET /api/nav/route?full=1.
- Ekran 1.0.3 (PR #8, dodatek 1.4.6) = 1.0.2 + patch zasilania z wątku instalacji ekranu (usypianie, ładowanie, słaba bateria); demo nie usypia.
- Ekran 1.0.4 (PR #9, dodatek 1.4.7): cfg.invert = true (kolory). Ekran 1.0.5 (PR #10, dodatek 1.4.8): dotyk offset_rotation 2, powód błędu Wi-Fi. Skrzynka 1.4.3 (PR #11, dodatek 1.4.9): NavFrame „postój” także na stronie skrzynki. Ekran 1.0.6 (PR #12, dodatek 1.4.10): wznawianie pobierania mapy (/mapa/pobieranie.txt), brak usypiania w trakcie pobierania. Najnowsze źródła (skrzynka+ekran): nt1100-telemetria-zrodla-1.4.3-ekran-1.0.6.zip. Ten wątek buduje firmware dla wątku instalacji ekranu (tam brak toolchainu).
- Najnowsze źródła ekranu: /mnt/project-files/telemetria/nt1100-telemetria-zrodla-1.4.2-ekran-1.0.3.zip.
- W kontenerze: arduino-cli 1.1.1 w /root/tools, fakectags musi być KATALOGIEM z plikiem ctags; potrzebny pip pyserial [narzędzie do wgrywania] cryptography. Force push blokowany: po squash-merge rób git merge origin/main na gałęzi.
Nieprzetestowane na sprzęcie. Powiązane: [[telemetry-ekran-101]], [[telemetry-navigation-kurviger]]
- Renderer zrzutów ekranu na komputerze (2026-11-04): patch wip/ekran-render-host.patch (host/render.cpp, render.sh, hostshim.h, mkrender.py; #ifdef HOST_RENDER w display.cpp). Wymaga g++ + libsdl2-dev (apt) + [biblioteka]. Zrzuty 1.0.8 (makieta) w telemetria/ekran/zrzuty-1.0.8/. 1.0.8 = zip 1.0.6 + wip/ekran-1.0.7-makieta.patch, czeka na „wydawaj” od wątku instalacji ekranu.
- Ekran 1.0.8 (PR #14, dodatek 1.4.12): wygląd jak makieta (zip 1.0.6 + wip/ekran-1.0.8-makieta.patch + harness). Baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.8.zip. App 1,79/3 MB. NimBLE-Arduino 2.5.2 zainstalowane (pod 1.0.9 BLE ANCS/AMS/CTS). arduino-cli: po zmianie portu proxy zrób config set network.proxy $HTTPS_PROXY.
- Render: narzędzia w /mnt/project-files/telemetria/wip/render/ (run.sh PATCH = zip 1.0.6 + patch + harness; apply_host.py; render.cpp; prawdziwa mapa OSM Start c_500_190.ntt z api.openstreetmap.org /map + osm2ntt.py; trasa.ntr = demo). Overpass zablokowany, OSM API działa. Wynik: zrzuty-1.0.8/ (X.png ciemny, X-jasny.png, 00-ciemny/00-jasny).

- 2026-11-04: ekran 1.0.9 (iPhone BLE Bluedroid: ANCS/AMS/CTS/BAS, dźwięki [kodek audio], zakładka Telefon, karta w jeździe w prawym górnym rogu) wydany jako dodatek 1.4.13 (PR #15). Binarka 2,41 MB z 3 MB. Baza źródeł teraz zip …-ekran-1.0.9.zip; run.sh renderuje zip 1.0.8 + patch do zrzuty-1.0.9.
- 2026-11-04: ekran 1.0.10 (szybkie Wi-Fi: ostatnia sieć w RTC, jedno skanowanie) = dodatek 1.4.17 (PR #19). Uwaga: inne wątki też podbijają dodatek (1.4.14–1.4.16 były bez zmian ekranu) — zawsze sprawdzić version w config.yaml na main przed podbiciem. Baza źródeł: zip …-ekran-1.0.10.zip.
- ekran 1.0.11 (bateria ekranu w Stanie) = dodatek 1.5.1 (PR #21). run.sh przyjmuje BASE=zip i OUT=katalog zrzutów. Baza źródeł: zip …-ekran-1.0.11.zip.
- ekran 1.1.0 (mapa 1.1: woda, rzeki, nazwy; pobieranie zmian .gz+crc) = dodatek 1.5.3 (PR #23). Dane testowe z tłem: wip/render/dane-1.1 (osm2ntt.py z build_map z main, OSM API bbox 19.06,50.07,19.14,50.11); run.sh: DATA=, BASE=, OUT=. Baza źródeł: zip …-ekran-1.1.0.zip.
- ekran 1.1.1 = dodatek 1.5.4 (PR #24): regresja 1.0.10 (ekran łączył dom. Wi-Fi zanim usłyszał skrzynkę i zostawał tam) — teraz 20 s szukania skrzynki przed Wi-Fi. Baza źródeł: zip …-ekran-1.1.1.zip.
- ekran 1.1.2 = dodatek 1.5.6 (PR #27). Łatki od wątku instalacji mogą mieć ścieżki względem firmware/ekran (nie korzenia zipa) — przerobić sedem przed run.sh. Baza: zip …-ekran-1.1.2.zip.
````

### `telemetry-ekran-instalacja.md`

````markdown
---
name: telemetry-ekran-instalacja
description: Instrukcja instalacji ekranu [ekran-płytka] od zera (2026-11-04) — gdzie leży i kluczowe fakty z kodu
metadata:
  type: project
  modified: 2026-11-04T15:40:43.809Z
---

2026-11-04 wątek „Zainstalować ekran [ekran-płytka] od zera”: pełna instrukcja w /mnt/project-files/telemetria/ekran/instalacja-ekranu-od-zera.md (karta FAT32 MBR na Macu, [narzędzie do wgrywania] full.bin @0x0 (UWAGA: [narzędzie do wgrywania] podpowiada 0x1000 — Adrian raz wgrał pod 0x1000, trzeba zmienić na 0x0 + Erase Flash), formularz NT1100-Ekran/[HASŁO-AP-EKRANU] http://192.168.4.1, mapa: dodatek Nawigacja → Mapa na kartę http://[IP-LXC-NAWIGACJA]:8988 → „Pobierz mapę z kontenera”, ekran sam ściąga w domowym Wi-Fi, parowania ze skrzynką brak (broadcast [radio bezpośrednie]), test, montaż, zasilanie).
Fakty z kodu ekranu 1.0.1: brak auto-wyłączania (na baterii działa do rozładowania); strony Stan/Pogoda/Jazda/Menu tylko gdy jest skrzynka i postój 30 s; bez skrzynki „Szukam skrzynki...”; BOOT przy starcie = tryb ustawień; menu: Pobierz mapę / Sprawdź wersję→Aktualizuj / Ustawienia Wi-Fi / Usuń trasę / Restart. Biegunowość akumulatora nadal niesprawdzona.
Powiązane: [[telemetry-ekran-101]], [[telemetry-navigation-kurviger]]
2026-11-04 16:05: pierwsze uruchomienie na sprzęcie OK (ekran, dotyk, karta). Kolory ODWRÓCONE → cfg.invert=true (do 1.0.4, wydaje wątek „Zasymulować demo jazdy na ekranie”). 1.0.3 (usypianie/bateria/autocapitalize, mój patch wip/ekran-1.0.3-zasilanie.patch) scalony PR #8, dodatek 1.4.6. Wi-Fi: „brak Wi-Fi (dom/hotspot)” — podejrzenie wielkiej litery z iPhone'a; w trakcie diagnozy.
2026-11-04 16:08: 1.0.4 (invert, PR #9, dodatek 1.4.7) wysłany Adrianowi. Sieć domowa [SIEĆ-DOMOWA] (ZTE LTE), skrzynka się z nią łączy → błąd w nazwie/haśle na ekranie. Gotowy, NIEWYDANY patch wip/ekran-wifi-diagnoza.patch (net.cpp: 'dom: nie widzę sieci / złe hasło?', timeout 15 s) do następnej wersji. Uwaga: full.bin (merge_bin) czyści NVS = ustawienia ekranu.
2026-11-04 16:25: Wi-Fi i HA na ekranie DZIAŁAJĄ (1.0.4). Dotyk: piny zgodne z [producent-ekranu] ([sterownik dotyku]), ale zakładki nie reagują — podejrzenie lustrzanych współrzędnych (BSP [repo BSP]: display mirror_x=true, touch bez flag). Test rogów zlecony Adrianowi. Poprawne wejście w ustawienia: puść RESET, potem trzymaj BOOT 3 s (BOOT w chwili RESET = tryb wgrywania, czarny ekran).
2026-11-04 16:30: ekran 1.0.5 (PR #10, dodatek 1.4.8): touch offset_rotation=2 (dotyk był obrócony 180°) + powód błędu Wi-Fi. Baza źródeł: nt1100-telemetria-zrodla-1.4.2-ekran-1.0.5.zip. Wgrywanie z zachowaniem ustawień: ota.bin pod 0x10000 przez [narzędzie do wgrywania] (bez Erase). Skrzynka nie nadaje NavFrame w trybie 'Strona skrzynki' (service mode) — tylko jazda/postój.
2026-11-04 16:35: skrzynka 1.4.3 (PR #11, dodatek 1.4.9): navPageFrame w runServiceMode — NavFrame 1/s (parked, zegar, bez pozycji), AP→AP_STA. Nowa baza źródeł: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.5.zip. Budowanie robił wątek „Zasymulować demo jazdy na ekranie” (u mnie pobranie arduino-cli zablokowane).
2026-11-04 17:00: wygląd 1.0.8 w rundach z Adrianem (ocena 1.0.7: „3/5”). Patch wip/ekran-1.0.8-makieta.patch (względem zipa 1.0.6), render robi wątek demo (harness wip/ekran-render-host.patch), zrzuty w telemetria/ekran/zrzuty-1.0.8/. Runda 2: pasek 32 px, mapa pod strzałką, zoom przy skręcie, duży znak limitu przy +10, motocykl w zakręcie, jasna paleta. Adrian chwali widok pogody. NIE wydawać bez akceptacji Adriana.
2026-11-04 17:16: ekran 1.0.8 WYDANY (PR #14, dodatek 1.4.12, baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.8.zip z host/render.sh). 1.0.9 w toku: wip/ekran-1.0.9-telefon-dzwiek.patch (BLE Bluedroid ANCS/AMS/CTS/BAS, dźwięki [kodek audio]: IO1 enable LOW, I2S MCLK4 BCLK5 LRCK7 DOUT8 DIN6, głośnik w złącze „Horn” 1,25 mm 2P, 4 Ω/2 W; TZ CET dodane — wcześniej ekran pokazywał UTC). Adrian ma głośnik; obudowa nie ma na niego miejsca (do dorobienia).
2026-11-04 17:26: ekran 1.0.9 WYDANY (PR #15, dodatek 1.4.13; baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.9.zip). iPhone BLE (zakładka Telefon, karta w prawym górnym rogu w jeździe, Odbierz/Odrzuć na postoju), dźwięki, TZ. Ustawienia: Telefon (bt) i Dźwięki (sn). NIESPRAWDZONE na sprzęcie: parowanie iOS, [kodek audio]. Adrian testuje.
2026-11-04 19:13: ekran 1.0.10 (szybkie Wi-Fi: RTC BSSID/kanał, skan i dołączanie tylko do widocznych sieci) WYDANY w dodatku 1.4.17 (PR #19). Baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.10.zip. Czekam na test 1.0.9/1.0.10 (iPhone, dźwięk) i zdjęcie wtyczki akumulatora przyłożonej do BAT (+ u góry od UART).
2026-11-04 19:18: Adrian zaakceptował plan nowego formatu mapy (wątek Nawigacji przyśle spec: CRC w manifeście, gzip, dom i trasa najpierw, woda i nazwy miejscowości w .ntt). Zmiany firmware (doMap() w net.cpp, rysowanie w display.cpp) robi wątek instalacji ekranu po otrzymaniu specyfikacji. W toku: 1.0.11 (wiersz bateria w Stanie).
2026-11-04 19:22: ekran 1.0.11 WYDANY w dodatku 1.5.1 (PR #21): wiersz bateria ekranu w Stanie. Baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.0.11.zip.
2026-11-04 19:35: ekran 1.1.0 WYDANY w dodatku 1.5.3 (PR #23): mapa format 1.1 (tło: woda/rzeki/miejscowości; doMap crc32+gz+/mapa/stan.txt). Baza: nt1100-telemetria-zrodla-1.4.3-ekran-1.1.0.zip. Niesprawdzone na sprzęcie: .gz/crc/stan.txt, BLE, dźwięk. Adrian miał kłopot z Wi-Fi ekranu (zalecony full.bin przez USB @0x0, kasuje ustawienia).
2026-11-04 19:44: ekran 1.1.1 WYDANY w dodatku 1.5.4 (PR #24): regresja 1.0.10 — ekran łączył się z Wi-Fi przed usłyszeniem skrzynki i zostawał na kanale sieci; teraz 20 s szukania skrzynki po starcie i wyjście z Wi-Fi bez ramek. Baza: zrodla-1.4.3-ekran-1.1.1.zip. iPhone nie widzi ekranu w Ustawieniach BLE — zalecono nRF Connect (Scan/Connect) i sprawdzenie wersji; jeśli brak w skanie → problem reklamy BLE (raw adv w phone.cpp).
2026-11-04 20:05: iPhone sparowany i DZIAŁA (ekran 1.0.11). Parowanie: iOS Ustawienia nie pokazują ekranu — trzeba nRF Connect → Scan → Connect → Paruj → Zezwól (dopisane do instrukcji). Niewydany patch wip/ekran-1.1.2-bluetooth.patch (krótka nazwa w reklamie, WiFi modem sleep przy BT) — wydać tylko przy problemach z BLE/Wi-Fi.
````

### `telemetry-ekran-plan-ble.md`

````markdown
---
name: telemetry-ekran-plan-ble
description: Plan ekranu po poprawkach wyglądu 1.0.8: Bluetooth z iPhone'em (ANCS powiadomienia, AMS muzyka, czas, „bez telefonu”)
metadata:
  type: project
  modified: 2026-11-04T17:02:53.651Z
---

2026-11-04 Adrian zlecił dopisać do planu ekranu [ekran-płytka] (do zrobienia PO poprawkach wyglądu 1.0.8, bez aplikacji iOS):
- ANCS: powiadomienia o połączeniach, SMS i komunikatorach (pasek „Dzwoni: X”, ikona nieodebranego); akcje ANCS: odrzuć/odbierz połączenie z ekranu (tylko na postoju albo duży przycisk?).
- Treść wiadomości (ANCS Message): w jeździe nadawca + początek treści (jedna linia, kilka s, nie przykrywa skrętu/fotoradaru), pełna treść na postoju (Adrian 17:03); wymaga w iOS Powiadomienia → Pokazuj podglądy = Zawsze/Gdy odblokowany.
- AMS: tytuł utworu, pauza/następny dotykiem.
- Czas z telefonu bez Wi-Fi; ostrzeżenie „odjechałeś bez telefonu”.
- Pomysł: bateria telefonu na pasku.
Ograniczenia: BLE nie włączy hotspotu iPhone'a; CarPlay/interkom bez konfliktu. Do sprawdzenia: BLE + [radio bezpośrednie] + Wi-Fi współdzielą radio [procesor] (pamięć i czas anteny).
Powiązane: [[telemetry-ekran-instalacja]], [[telemetry-ekran-demo]]
````

### `telemetry-firmware-126.md`

````markdown
---
name: telemetry-firmware-126
description: Firmware 1.2.6 (2026-11-02): nowe ekrany, bezpieczny tryb serwisowy, QR, ekran końca jazdy, czekanie na prąd wg baterii, ustawienie łączenia jazd
metadata:
  type: project
---

1.2.6 zbudowany 2026-11-02 (nieprzetestowany na sprzęcie), pliki w /mnt/project-files/telemetria/: nt1100-telemetria-1.2.6-{full,ota}.bin, nt1100-telemetria-zrodla-1.2.6.zip (scratchpad src125 = źródła 1.2.6). Host: 3088 sprawdzeń OK.
Zmiany: 4 ekrany w czasie jazdy (ui.cpp, [biblioteka/układ producenta] w PSRAM): Jazda (łuk przechyłu, maks L/P, km/h, km), Przeciążenia (G-metr + maksima), Stan, Motocykl (tylko canMode=2). Dotknięcie = następny ekran; ustawienie screen_auto (0/5/10/20 s, NVS scrAuto). Tryb serwisowy: przytrzymanie 3 s z paskiem (uiBootHold), menu ma "Wroc do jazdy" + timeout 15 s → [procesor].restart; ekran adresu ma QR (Wi-Fi WIFI:T:WPA;S:NT1100 i URL) i przycisk "Wroc do jazdy" (y>=180). Po zaniku prądu nagrywa dalej 60 s (bateria >=50%), 20 s (>=20%), inaczej 3 s; w nagłówku odliczanie. Po jeździe ekran "Koniec jazdy" 15 s z podsumowaniem i przyciskiem "Pokaz jazdy" (runServiceMode(true)). Ustawienie trip_gap_h (0,1,2,3,4,6,12,24; NVS tripGap, domyślnie 3) w /api/settings i /api/rides, strona łączy wyjazdy wg niego.
Teksty na ekranie bez polskich znaków (fonty GLCD). Build: fakectags musi być KATALOGIEM z plikiem ctags (/root/tools/fakectags/ctags).
Powiązane: [[telemetry-lean-calibration]], [[telemetry-firmware-status]], [[telemetry-dev-backlog]] (pkt 2 zrobiony w 1.2.6).
Decyzja Adriana 2026-11-02 (karta): hotspot po jeździe tylko przy baterii >=50% (inaczej tylko szybka próba sieci domowej); na postoju z prądem ponowna wysyłka co 5 min. Wbudowane w pliki 1.2.6 (przebudowane 22:42).
1.2.7 (2026-11-02 22:52): GPS po 1.2.6 nadal "nie wykryto" mimo DIP RX4/TX4/PS2 (wg zdjęcia). 1.2.7 słucha na wszystkich pinach [skrzynka-płytka] z tabelki modułu (17,18,6,7,13,14,0,10; pary wg pozycji DIP: 17↔18, 6↔14, 13↔7, 0↔10; G14 nigdy nie jest sterowany), wynik na ekranie Stan: "nie wykryto (cisza|G..)" lub "szuka, N sat (Grx/Gtx)". Uwaga: gnssTask ponawia szukanie co ~5 s (nie tylko przy starcie). Pliki 1.2.7 w telemetria/. Czeka na wynik od Adriana.
1.2.8 (2026-11-02 22:55): w czasie nagrywania przytrzymanie ekranu: po 0,6 s pasek "Trzymaj dalej: zaraz wejdziesz w menu", po 3 s endSession + runServiceMode(); krótkie stuknięcie = następny ekran (na puszczenie). Zawiera 1.2.7. Pliki 1.2.8 w telemetria/.
2026-11-02 22:58: 1.2.8 pokazał "nie wykryto (G18 G10)": G10 = PPS (moduł zasilony, PS2 działa), G18 = nierozpoznane bajty (może pływający pin). 1.2.9: pull-up na pinie przy nasłuchu, 8 prędkości, NMEA "$G/$P/$B" x2, diagnostyka na ekranie Stan (wiersz Czas zastąpiony: "G18 38400: 412B próbka"). Czeka na zdjęcie od Adriana.
1.2.10 (2026-11-02 23:45; po teście w aucie, jazda 0016): GPS potwierdzony (DIP RX1/TX1/PS2, "g18/g17"). Zmiany: menu na ekranie tylko "Strona skrzynki / Skan motocykla / Wroc do jazdy" (stary portal WiFiManager wyłączony); sieć NT1100 zawsze włączona (AP_STA obok domowej), ekran adresu z QR do NT1100 + adres w sieci domowej/hotspocie; ustawienia InfluxDB/MQTT/remote_url w zakładce Ustawienia na stronie (/api/settings). Przechył: wykrywanie poruszenia skrzynki (accB.y/g > 0.35, x-aLong > 0.5, albo przechył niezgodny z zakrętem o >25° — 1,5 s → przechył ukryty, kalibracja uczy się od nowa; po 3 s spokoju wraca); maksima przechyłu/lat g liczone z 4 s opóźnieniem i odrzucane przy wykryciu; limity |lean|<=65, |latG|<=1.5, |longG|<=1.2. Replay 0016: maks. 10/7° zamiast 33/49°, lat g 0.62 zamiast 5.76. Pliki 1.2.10 w telemetria/. Wersji 1.3.0 nie używać (zarezerwowana na ntfy).
````

### `telemetry-firmware-132.md`

````markdown
---
name: telemetry-firmware-132
description: Firmware 1.3.2 + dodatek 1.2.4 (2026-11-03): skan rozszerzony (UDS, tylko odczyt) — PR do main czeka na Adriana; wynik na motocyklu nieznany
metadata:
  type: project
---

2026-11-03 wieczór: Adrian zgodził się na „skan rozszerzony”. Zrobione w firmware 1.3.2 (src/core/udsscan.h/.cpp, hw/scan.cpp tryb kScanExtended, 3. przycisk „Rozszerzony (ok. 5 min)” w service.cpp, karta „Skan rozszerzony” w webpage.h/scanView, JSON pole "uds"). Fazy po standardowym skanie: tryb 02 (zamrożone dane P0500), 3E 00 / 10 01 do 254 adresów 18DAxxF1 + 7E0..7E7, 22 F1xx/F4xx/0000..03FF i 21 xx do każdego sterownika, który odpowiedział (odmowa 11/7F/7E = stop usługi), 40 s odczytu na żywo (zmienne bajty). Nic nie pisze/kasuje. Limit 8 min. Testy host 6719 OK, build bez ostrzeżeń.
Pliki: /mnt/project-files/telemetria/nt1100-telemetria-1.3.2-{full,ota,ota-podpisany}.bin, zrodla-1.3.2.zip (zawiera dodatek 1.2.4). Repo: branch claude/project-thread-kt0ejp, commit 38f5d1c „Wersja 1.2.4”; PR do main — Adrian musi scalić, żeby HA zobaczył 1.2.4 (albo wgrać ota-podpisany przez stronę skrzynki).
Build w tym kontenerze: /root/tools/arduino-cli 1.1.1 + [procesor] 3.0.7 + biblioteki zainstalowane (SSL_CERT_FILE=/root/.ccr/ca-bundle.crt, network.proxy ustawione), pip [narzędzie do wgrywania]+cryptography.
**How to apply:** po skanie Adrian przysyła skan-NNN.txt/.csv; szukać sterowników poza 18DAF110 i zmiennych bajtów (bieg). Zob. [[telemetry-can-scan-results]].
````

### `telemetry-firmware-133.md`

````markdown
---
name: telemetry-firmware-133
description: Firmware 1.3.3/1.3.4 + dodatek 1.2.5/1.2.6 (2026-11-03): skan uruchamiany ze strony skrzynki (zakładka „Skan”), strona otwiera się sama na postoju — czeka na test Adriana i analizę bloków 56 B
metadata:
  type: project
---

2026-11-03 późny wieczór, wątek „Podłączyć przewód OBD2 do [moduł CAN]” (Adrian: „rób całość”). Firmware 1.3.3 (następca [[telemetry-firmware-132]]):
- Skan ze strony skrzynki: karta „Skany motocykla” ma przyciski „Skan OBD2 (1,5 min)” i „Skan rozszerzony (ok. 7 min)”; `POST /api/scan?mode=1|2` (hasło X-Haslo spoza sieci NT1100), `GET /api/scanstatus` co 1 s (4 linie ekranu, numer, sekundy). Skan biegnie w pętli serwisowej z callbackiem idle → `g_web->handleClient()`; po skanie przycisk „Pokaż wynik”.
- Strona otwiera się sama na postoju z zasilaniem: 2 min bez zapłonu (brak zmian OBD przez 60 s) albo 5 min z zapłonem (`kStillPageQuietMs/kStillPageLiveMs` w hwconfig.h). Kończy jazdę, `runServiceMode(true, fromRide=true)`: CAN task jest zatrzymywany (`canPause`, naprawia stary konflikt sterownika TWAI przy skanie z przytrzymania 3 s), ruch motocykla (GPS > 8 km/h albo żyroskop > 0,3 rad/s przez 0,5 s, `imuMotionStreak`) → restart do nagrywania; zaległe jazdy wysyłane co 5 min (`uploadNow`, pierwsza próba po 20 s). Konsekwencja: postój > 5 min z zapłonem (np. przejazd kolejowy) dzieli jazdę; stary tryb „zaparkowany 15 min” już praktycznie nie występuje.
- Poprawki skanu rozszerzonego: bloki ECM 56 B w całości (kItemBytes 64), pełne odpowiedzi UDS w CSV („ms,uds,xID,len,hex”), faza na żywo 150 s, limit 10 min, JSON naprawiony (appendf rósł tylko do 256 B).
- Testy host 10140 OK, test_server 9 OK. Pliki: /mnt/project-files/telemetria/nt1100-telemetria-1.3.3-{full,ota,ota-podpisany}.bin, nt1100-telemetria-zrodla-1.3.3.zip. Repo: commit 0cb99a3 „Wersja 1.2.5” na claude/project-thread-kt0ejp, PR #1 (zaktualizowany opis). Źródła robocze w kontenerze: /tmp/z.

**How to apply:** po skanie Adriana (skan-NNN.csv, linie „uds”) analizować bloki DID 0100…0194 z 18DAF110: skorelować zmienne bajty z obrotami/gazem/biegiem/stopką/sprzęgłem/HSTC/napięciem. ABS: temat zamknięty (K-line). Przycisk „Zrób skan” w dodatku HA odłożony na później.

1.3.4 + dodatek 1.2.6 (commit po 0cb99a3, ten sam PR #1): Adrian uznał kartę skanów na liście jazd za bez sensu → skany mają własną zakładkę „Skan” (v-scan, slist/sdetail; w dodatku HA ukryta, gdy brak skanów). Pliki 1.3.4 w /mnt/project-files/telemetria/. Skan nr 8 Adriana (1.3.3): „brak magistrali CAN” — prawdopodobnie zapłon wyłączony.

1.3.5 + dodatek 1.2.7 (2026-11-03 ~22:35): skan 14 (1.3.3) przeanalizowany — blok 0110 ECM: b8-9 obroty (1/LSB), b10 przepustnica raw, b24 IAT raw, b32-33 czas wtrysku (00 00 = odcięcie), b34 wyprzedzenie, b45 0x65/0x25 flaga jałowy/gaz, b47 0x40/0x01 i 0130 b45 0x30/0x00 toggle blokami ~10 s (nieznany), b49 bit2 i b42-43 zmieniły się raz ok. 242 s; 0121 b20-23 wtrysk na cylinder; 0191/0194 krótkie „mignięcia” (kandydaci przełączników); 018x = historie 25 próbek; 0192 = 5-próbkowe historie. Bieg/stopka/sprzęgło/HSTC NIE przypisane → 1.3.5 „skan prowadzony”: 14 kroków (kSteps w scan.cpp, każdy zapisany w CSV jako „# krok N: …”), live filter (tylko 0110,0120,0121,0123,0124,0130,0191,0192,0194 + F40C/F40D/F411). Adrian: trakcji nie da się wyłączyć (tylko poziom), stopka gasi silnik na biegu (na luzie nie). Analiza skanu z 1.3.5: skrypt tabeli per runda — w scratchpadzie sesji (parsowanie linii „uds” + notatek „# krok”).

SKAN 16 (1.3.5, prowadzony, 2026-11-03 22:50) — WYNIK DEKODOWANIA ECM NT1100 (18DAF110, 22 0110 = 56 B, indeksy od 0 w payloadzie po 62 01 10):
- 0110[8..9] obroty 1/LSB; [10] przepustnica raw (=PID 11); [24] IAT raw (=PID 0F); [32..33] czas wtrysku (00 00 = odcięcie); [34] wyprzedzenie raw (=PID 0E); [23] prawdopodobnie napięcie (0x81≈12,9 V? niepewne).
- 0110[45] bitfield: bit6 (0x40) = gaz zamknięty/jałowy (0x65→0x25 przy gazie), bit3 (0x08) = STOPKA OPUSZCZONA (0x65→0x6D). PEWNE.
- 0130[45]: 0x30 = SPRZĘGŁO WCIŚNIĘTE, 0x00 = puszczone. PEWNE.
- 0110[47]: 0x01 = luz + sprzęgło wciśnięte; 0x40 = pozostałe (bieg ze sprzęgłem, albo sprzęgło puszczone). Numer biegu NIE jest dostępny.
- 0121[20..23] czas wtrysku cyl.1/cyl.2 (01 5A → 01 C8 przy gazie, 00 FB przy odcięciu); 0120[14,17] (+[15,18] trim 0x80) para na cylinder.
- 0194[8..11] / 0191 flagi tylko przy gazie. 0110[49] bit0 toggluje bez związku z krokami (nieznane). 018x = historie, 0192 = historie 5 próbek, 0100/0122/0140-0160 statyczne.
- NIE MA w ECM: hamulce, kierunkowskazy, drogowe, klakson, poziom HSTC.
Decyzja Adriana (karta): czy dodać sprzęgło/stopkę/gaz/spalanie z wtrysku do nagrywania jazd — czeka.
````

### `telemetry-firmware-140.md`

````markdown
---
name: telemetry-firmware-140
description: Firmware 1.4.0 + dodatek 1.3.0 (2026-11-03): dane z silnika w jeździe (sprzęgło, stopka, gaz zamknięty, wtrysk → spalanie), mnożnik spalania
metadata:
  type: project
---

2026-11-03 Adrian wybrał na karcie „Tak, dodaj do nagrywania” → firmware 1.4.0 + dodatek 1.3.0 (zbudowane, nieprzetestowane na motocyklu).
- Klient OBD w jeździe (src/core/obd.h/.cpp) czyta też bloki ECM UDS 22 0110 (2 Hz) i 22 0130 (1 Hz), ISO-TP wieloramkowo (FC 30 00 00 na adres fizyczny 18DA10F1 / 7E0+x), po 3 nieodpowiedzianych/odrzuconych próbach blok porzucany (`blocksActive()`). Pseudo-PID-y w ObdRec: 0xA0 wtrysk (surowo 0110[32..33]), 0xA1 sprzęgło (0130[45]!=0), 0xA2 stopka (0110[45] bit3), 0xA3 gaz zamknięty (bit6), 0xA4 sprzęgło do końca (0110[47]==1). Koszt: obroty ~7–8 Hz zamiast 10; ECM bez bloków traci jednorazowo ~2,4 s na starcie.
- OutSample.injection, OutSample.sw (kSwClutch 1, kSwSidestand 2, kSwThrottleClosed 4, kSwClutchFull 8, kSwKnown 0x80). RideSummary: engineData, fuelUnits = Σ wtrysk × obr/60 × dt, fuelK (domyślnie kDefaultFuelK 1.67e-8 l/jednostkę ≈ 1 l/h na luzie — ZGADNIĘTE, kalibracja tankowaniem), clutchPulls, clutchSeconds.
- JSON jazdy: fuel_units, fuel_k, fuel_l, fuel_l100 (null < 1 km), clutch_pulls, clutch_min (tylko gdy engineData). Influx: injection/clutch/sidestand/throttle_closed, w podsumowaniu fuel_l/clutch_pulls/clutch_min. CSV 19 kolumn (stare 17 nadal czytane). .trk 14 kolumn (…,inj,sw; sw = bity bez kSwKnown, sprzęgło trzymane w oknie 1 s). Czujniki HA MQTT: fuel/fuel_l100/clutch_pulls (firmware) i paliwo/spalanie/sprzeglo (dodatek), powiadomienie z „ok. X l/100 km”.
- Ustawienie Settings::fuelK (NVS "fuelK", API fuel_k); strona: „Mnożnik spalania (1 = domyślny)” w sekcji Motocykl; nowy = stary × litry z dystrybutora ÷ litry policzone. Strona: karta „Spalanie (szacunek z wtrysku)” z wykresem l/h, statystyki paliwo/spalanie/użyć sprzęgła, serie własnego wykresu Wtrysk/Sprzęgło/Stopka.
- Nie ma: numeru biegu/luzu (ECM nie podaje — sprawdzone bajt po bajcie w skanie 16, Adrian przyjął 2026-11-03), hamulców, kierunkowskazów.
- Testy: host obd_engine_blocks (FakeEcu obsługuje 22 0110/0130, odmowę i ciszę), format/trk rozszerzone. Zob. [[telemetry-firmware-133]], [[telemetry-ha-addon]].

2026-11-04 00:04 Adrian (karta): PR #1 scalony do main (commit 8bac11f) — main ma dodatek 1.3.0 / skrzynkę 1.4.0. UWAGA: HA czyta TYLKO main; każda kolejna wersja dodatku wymaga nowego PR i scalenia (Adrian zgadza się kartą) albo pushu do main. Lokalna gałąź claude/project-thread-kt0ejp zresetowana na origin/main; kolejne zmiany = nowy PR. Adrian ma zaktualizować dodatek i sprawdzić, czy skrzynka pobrała 1.4.0.
````

### `telemetry-firmware-status.md`

````markdown
---
name: telemetry-firmware-status
description: Stan oprogramowania rejestratora NT1100 (wersja 1.2.0, pliki, instrukcja, co nieprzetestowane)
metadata:
  type: project
  modified: 2026-10-28T23:38:14.860Z
---

Firmware 1.0.0 (2026-10-28) gotowy, nieprzetestowany na prawdziwym sprzęcie. Pliki w /mnt/project-files/telemetria/: full.bin (wgranie 0x0 przez [narzędzie do wgrywania] w Chrome), ota.bin (aktualizacja przez stronę trybu serwisowego), grafana-nt1100.json, zrodla zip (kod: firmware/telemetria src/core + src/hw, host/ symulator i testy).
Instrukcja (Claude Doc): https://claude.ai/artifact/6YcdCMvxfekYp3cuN8Ei6S

Kluczowe decyzje: IMU = wewnętrzny [IMU] [skrzynka-płytka] (0x69), IMU modułu GNSS przestawić DIP na 0x68; UART GNSS autodetekcja (G7/G6, G18/G17); CAN Port B G9/G8, nadawanie tylko po potwierdzeniu bitrate (pamiętany w NVS); po zaniku VBUS 3 s → przeliczenie, upload Influx/MQTT, powerOff. Tryb serwisowy: dotyk ekranu przy starcie.

Wersja 1.1.0 (2026-10-29): tryb serwisowy ma menu (Jazdy i pliki / Ustawienia); strona z jazdami (podsumowania, plik .trk 1 Hz, trasa kolorowana przechyłem bez mapy) przez Wi-Fi domowe, hotspot telefonu albo własne AP "NT1100" (hasło domyślnie [HASŁO-AP-SKRZYNKI]); wysyłka InfluxDB przez hotspot na adres "InfluxDB spoza domu" (HTTPS z pakietem CA), MQTT tylko z domu (zaległe w NVS mqPend). Adrian nie wybrał jeszcze sposobu wystawienia InfluxDB do internetu (DuckDNS+port albo Cloudflare Tunnel). CAN jest opcjonalny (Adrian woli minimalną ingerencję w motocykl).
Build: arduino-cli z --build-property runtime.tools.ctags.path=/home/user/tools/fakectags (bez tego błąd ctags); -fstack-usage przez extra_flags psuje linkowanie.

Otwarte: typ i zasilanie gniazda NT1100 (czy po zapłonie), czy NT1100 odpowiada na OBD mode 01, auto-włączenie [skrzynka-płytka] po VBUS. Po 1. jeździe Adrian ma przysłać zdjęcie ekranu i plik .mtl.
Wizualizacja montażu (czarna skrzynka, połączenia, przepływ danych): https://claude.ai/artifact/PPcgnqGMo6Md1nb7Bohivf
Powiązane: [[telemetry-hardware-plan]]
Dostęp zdalny (2026-10-29): Adrian zostaje przy Cloudflare Tunnel do HA; wysyłka przez hotspot ma iść na host influx.<domena> w tunelu (bez Cloudflare Access, ew. wyłączyć Bot Fight Mode). Instrukcję kroków wysłano 2026-10-29; nie potwierdził jeszcze konfiguracji.
Ustawienie CAN (2026-10-29, w 1.1.0): 0=wyłączony, 1=tylko nasłuch (zapis ramek, zero nadawania), 2=OBD2 (domyślnie). Plan Adriana: najpierw testy bez CAN, potem nasłuch, potem OBD2 po analizie pliku.
Przegląd 1.1.0 (2026-10-29 wieczór): naprawiono utratę domowego Wi-Fi po hotspocie (sieć domowa w Settings homeSsid/homePass, WiFi.persistent(false)), abort szukania Wi-Fi po powrocie VBUS, odporność listy jazd na ucięty .json. Po OTA z 1.0.x może być potrzebne ponowne zapisanie Wi-Fi.

Wersja 1.2.0 (2026-10-30): Adrian chce najpierw działania bez Home Assistant (InfluxDB/Grafany jeszcze nie ma) i strony z trasą w stylu aplikacji BMW Motorrad. Zrobione: strona z jazdami ma miniatury tras (.thm, 1 pkt/20 s), sumę km, mapę Leaflet+OSM gdy telefon ma internet (fallback SVG bez mapy), punkty maks. przechyłu L/P i prędkości, nazwy miejscowości (Nominatim), wykresy prędkości/wysokości/przechyłu, eksport GPX, usuwanie jazdy (POST /api/delete?n=). .trk ma teraz kolumny lat,lon,lean,speed,alt,t. Bez skonfigurowanej wysyłki strona nie pokazuje stanów "czeka na wysyłkę" (pole upload w /api/rides). Pliki 1.2.0 w /mnt/project-files/telemetria/ (1.1.0 usunięte). Build bez ostrzeżeń, 2962 testy OK.
Podgląd zdalny (2026-10-30): Adrian pyta o dane "w świat" i aplikację iOS. Zaproponowano kolejność: (1) strona na skrzynce (własne Wi-Fi NT1100, dodać do ekranu początkowego), (2) własna strona w chmurze Cloudflare Pages+Worker na jego domenie z historią jazd (bez HA) - do zbudowania po pierwszych testach, (3) Grafana w HA jako dodatek. Aplikacja iOS odradzona (konto Apple, Xcode, brak testów na iPhonie).
Powiadomienia o problemach (2026-10-30): Adrian nie chce patrzeć na ekran ani polegać na głośniczku; BLE do iPhone bez aplikacji niemożliwe. Zaproponowano wersję 1.3.0: raport problemów przy jeździe na stronie skrzynki (GPS zniknął, zanik zasilania, straty zapisu) + powiadomienie push po jeździe przez ntfy (temat wymyślony przez Adriana, pole w ustawieniach) lub aplikację HA; opcjonalnie w trakcie jazdy przy włączonym hotspocie. Czeka na zgodę Adriana. Ostrzeżenia o podejrzanych pomiarach dopiero po pierwszej jeździe.
Decyzja 2026-10-30 12:15: Adrian chce najpierw pierwsze testy na 1.2.0, potem rozwój. Wersja 1.3.0 (problemy w jeździe + ntfy, Adrian zaakceptował ntfy) wstrzymana; źródła przywrócone do dokładnie 1.2.0 (zgodne z zip i binarkami). Część rdzenia 1.3.0 (liczniki problemów w RideSummary, rideProblems, rideNotice, ntfyUrl, testy; jeden test gpsLost>=gapMax do poprawy - float vs double) zapisana jako /mnt/project-files/telemetria/wip/1.3.0-core-wip.patch. Brakuje: warstwa hw (plik .msg po jeździe, ntfyPublish, ustawienie ntfyTopic, przycisk testowy, log kEvVbusBack przy krótkim zaniku, strona z raportem problemów). Wrócić po raporcie z pierwszej jazdy. Aplikacja iOS: omówiona (konto Apple Developer ok. 99 USD/rok albo AltStore; alternatywa Bluefy+Web Bluetooth), decyzja po testach.
Lista rozwoju po pierwszych testach (2026-10-30): (1) 1.3.0: raport problemów w jeździe + ntfy; (2) grupowanie jazd w "wyjazd" (przerwa < ~3 h, suma km/czasu, wspólna mapa, postoje; pliki osobne) - dziś każde wyłączenie zapłonu to osobna jazda; (3) chmurowa strona na domenie Adriana; (4) decyzja o aplikacji iOS lub LTE.
Weryfikacja z dokumentacją [producent] (2026-10-30): zgodne: Port B żółty G9=CAN_TX, biały G8=CAN_RX; SD CS4/SCK36/MISO35/MOSI37; I2C wewn. G12/G11, [IMU] 0x69; GNSS 38400 bod, [układ] 0x76; DIP UART GNSS: pary G7/G6 (M-Bus 22/21) i G18/G17 (15/16) obsługiwane; PPS na G10 (M-Bus 2). Problem: od 2026-08-07 [skrzynka-płytka] ma LCD [sterownik ekranu] i wymaga [biblioteka/układ producenta] >= 0.2.27, a build używa [biblioteka/układ producenta] 0.2.3 (/home/user/tools/libs) - nowy egzemplarz może mieć ciemny/zły ekran (nagrywanie działa). GitHub (codeload) zablokowany w sieci środowiska -> Adrian musi dodać github.com/codeload.github.com w Allowed domains, potem podmienić [biblioteka/układ producenta] (i ew. [biblioteka/układ producenta]) i przebudować. Instrukcja poprawiona: POWER 6 s, RST na spodzie, SD oficjalnie max 16 GB, nie zakładać rezystora 120 Ω z [moduł CAN].
2026-10-30 12:40: Adrian zmienił domyślne środowisko projektu (dostęp do GitHub), ale ten wątek nadal ma 403 z codeload.github.com. Wersję 1.2.1 ([biblioteka/układ producenta] >= 0.2.27 dla ekranu [sterownik ekranu]) trzeba zrobić w nowym wątku: pobrać nowe [biblioteka/układ producenta] (+ [biblioteka/układ producenta] zgodne) do /home/user/tools/libs lub odpowiednika, przebudować arduino-cli (FQBN i flagi jak wyżej), merge_bin, podmienić pliki w /mnt/project-files/telemetria/. Źródła 1.2.0 są w nt1100-telemetria-zrodla-1.2.0.zip.

2026-10-30 13:00: Wersja 1.2.1 zbudowana = 1.2.0 + [biblioteka/układ producenta] 0.2.36 / [biblioteka/układ producenta] 0.2.29 (obsługa ekranu [sterownik ekranu] w [skrzynka-płytka] od 08.2026, precharge BUS_OUT). Pliki 1.2.1 full/ota/zrodla w /mnt/project-files/telemetria/ (1.2.0 zostawione), instrukcja zaktualizowana. Środowisko budowania: github.com i release-assets działają przez git/curl, downloads.arduino.cc i [strona producenta] nie; arduino-cli 1.1.1 z GitHub releases, [procesor] core 3.0.7 z lokalnego indeksu bez dfu-util (file:// kopia package_[procesor]_index.json), pusty package_index.json, pip pyserial, fakectags = skrypt 'exit 0'. full.bin = merged.bin obcięty do 0x10000+len(app).

2026-10-30 18:00: Wersja 1.2.2 = 1.2.1 + "Skan motocykla" (3. przycisk w trybie serwisowym; wybór "Nasluch + OBD2" lub "Tylko nasluch"; ok. 1,5 min: 20 s nasłuchu, zapytania OBD2 tryb 01 wszystkie PID-y, 03/07/0A kody, 09 VIN/CALID/nazwa ECU z ISO-TP flow control, 40 s "dodaj gazu" z min/maks). Wyniki /scan/skan-NNN.txt/.json/.csv, widoczne na stronie skrzynki (karta "Skany motocykla"). Kod: src/core/obdscan.*, src/hw/scan.*, canScanOpen w can.cpp. Jazdy bez zmian. Pliki 1.2.2 full/ota/zrodla w /mnt/project-files/telemetria/. Testy hosta 3024 OK (symulowany ECU); nieprzetestowane na sprzęcie. Build: FQBN [procesor]:[procesor]:[płytka] (nie [producent-chipu]:), fakectags musi być KATALOGIEM z plikiem ctags; [procesor] index z github.com/[producent-chipu]/[pakiet płytek]/releases/download/3.0.7/package_[procesor]_index.json ([producent-chipu] zablokowane). Czeka na: Adrian robi skan i odsyła 3 pliki.

2026-10-30 21:15: Porównanie z aplikacją BMW Motorrad Connected: /mnt/project-files/telemetria/porownanie-bmw.md (36 funkcji, tak/może/nie). Brakujące łatwe: odtwarzanie jazdy, wykres/kolor przyspieszenia i hamowania (dodać kolumnę do .trk), statystyki zbiorcze, miejsce parkowania, przypomnienia serwisowe, top zakrętów. Zależne od skanu: obroty, bieg, gaz, temp., paliwo, napięcie.
ABS/TC (2026-10-30): wyjaśniono Adrianowi - nie ma w OBD2, tylko w niejawnych ramkach Hondy na CAN; możliwe przez [moduł CAN] w trybie nasłuchu, jeśli wtyk DLC nie jest za bramką. Plan: skan (20 s nasłuchu) -> jazdy w nasłuchu + nagranie zegarów telefonem -> szukanie ramek, najpierw prędkości kół (poślizg z różnicy kół).
2026-10-31: Sprzęt jeszcze nie dotarł. Adrian prosi o oszczędzanie limitu (zostawić zasoby na poprawki po przyjściu sprzętu). Demo strony jazd bez sprzętu: https://claude.ai/artifact/27nDNbhKuLbx6Aqdgi7VB3 (prawdziwy webpage.h + podmieniony fetch, 4 jazdy z host/sim → replay; generator w scratchpadzie, nietrwały). Demo wykryło błąd: miniatury tras rwały się przy >90 km/h (próg 0,5 km między punktami .thm co 20 s) — poprawione w 1.2.1 (przerwa tylko gdy dt>60 s lub >300 km/h), binarki 1.2.1 przebudowane. Dla 1.2.2 poprawka tylko jako wip/miniatury-fix-1.2.2.patch (nadpisanie plików 1.2.2 zablokowane; czeka na zgodę Adriana). Demo pokazuje stronę 1.2.2 z poprawką, bez skanów.
2026-10-31 09:40: Adrian przysłał zrzuty aplikacji BMW Motorrad (F 850 GS) jako wzorzec (/mnt/project-files/WhatsApp Image 2026-10-31 at 10.35.*.jpeg). Braki względem BMW: odtwarzanie jazdy (play/suwak, strzałka na mapie, zegar przechyłu/prędkości/G), jeden wykres z wyborem 2 serii, nazwy jazd + grupowanie po miesiącach, min. wysokość/temperatura, ciemny motyw. ABS/TC niedostępne (Honda). Adrian wybrał tylko odtwarzanie (reszta po testach). Zrobione w demo (wersja 4): karta "Odtwarzanie jazdy" pod mapą (zegar przechyłu z maks. L/P, prędkość, paski G z pochodnej prędkości, czas/km/wysokość, play/⏮/⏭, tempo ×10-120, suwak, klik w wykres = skok, kursor na wykresach i znacznik na mapie). Zmiany strony 1.2.2 w wip/strona-nowa-1.2.2.patch (jeszcze nie w binarkach).
2026-10-31 09:55: CarPlay odrzucony przez Adriana. Pytał o aplikację iOS + internet przez Bluetooth: wyjaśniono, że [procesor] ma tylko BLE (brak BT PAN), propozycja: aplikacja iOS synchronizuje jazdy po BLE w tle (jak BMW) i sama korzysta z internetu telefonu. Wymaga Maca + konta Apple Dev; decyzja po pierwszych jazdach; zapytano, czy Adrian ma Maca.
2026-10-31 09:56: Adrian MA Maca (aplikacja iOS realna). Opisano własny internet skrzynki: modem LTE Cat-1 na Port C (G17/G18 -> GNSS musi być na G7/G6), antena, SIM danych, zasilanie do 2 A; zalecenie: aplikacja iOS+BLE na co dzień, LTE tylko dla śledzenia/wysyłki bez telefonu; oba po pierwszych jazdach.
2026-10-31 09:57 DECYZJA Adriana: na start jazdy tylko na stronie skrzynki; InfluxDB/Grafana opcjonalne (może wcale). Cel: podgląd jazd przez internet (proponowana strona Cloudflare Pages+Worker na jego domenie, ta sama strona co na skrzynce) albo w aplikacji iOS pobierającej jazdy po BLE (ta sama strona w WebView, opcjonalnie przekazuje do chmury). Kolejność po testach: najpierw Cloudflare, potem aplikacja.
2026-10-31 10:02: Montaż: Adrian ma Dual Lock (klej rzepu wystarcza; VHB tylko na trudne powierzchnie). Dodatkowy czujnik niepotrzebny. Pomysł na po testach: zapis surowych danych z drugiego [IMU] (moduł GNSS, 0x68), ocena uśredniania/kontroli/awaryjności na prawdziwych jazdach; wzajemna kalibracja względem motocykla niemożliwa (ta sama skrzynka).
2026-10-31 10:30: Nowa strona w demo (wersja 6): ciemny motyw (wybór w Ustawieniach, localStorage), pasek zakładek Jazdy/Stan/Ustawienia, plakietki stanu w nagłówku, jazdy grupowane po miesiącach, zakładka Stan (na żywo: akumulator, SD, Wi-Fi, Bluetooth-brak, wersja; ostatnia jazda: GPS, [IMU]+drugi czujnik, kalibracja, CAN/OBD, zaniki zasilania, zapis; wysyłka: oczekujące, ostatni błąd, 'Wyślij teraz'), zakładka Ustawienia (Wi-Fi domowe, hotspot, hasło AP, tryb CAN, aktualizacja). Strona woła NOWE endpointy /api/status, GET/POST /api/settings (JSON, hasła *_pass, flagi *_pass_set), POST /api/upload - firmware ich jeszcze NIE ma (strona pokazuje wtedy komunikat). Wszystko w wip/strona-nowa-1.2.2.patch. Do zrobienia w firmware po akceptacji Adriana (+ zapis stanu ostatniej jazdy, część z 1.3.0-core-wip).

2026-10-31 14:20: [strona producenta] (i shop/[strona producenta]) nadal zablokowane w nowej sesji (403 proxy, WebFetch ENOTFOUND), mimo że miało być dodane. github.com działa: oficjalny przykład [repo producenta] getSensorData używa [IMU] 0x68, [układ] 0x76, GNSS 38400 bod. Numeru przełącznika DIP adresu nie potwierdzono - poproszono Adriana o zdjęcie opisu DIP na module.
````

### `telemetry-ha-addon.md`

````markdown
---
name: telemetry-ha-addon
description: Dodatek HA "NT1100 Jazdy" 1.0.0 + firmware 1.2.11 (wysyłka do HA) zbudowane 2026-11-03; pliki, protokół, stan testów
metadata:
  type: project
---

2026-11-03 zbudowane (nieprzetestowane u Adriana): firmware 1.2.11 + dodatek HA "NT1100 Jazdy" 1.0.0.
Pliki: /mnt/project-files/telemetria/nt1100-telemetria-1.2.11-{full,ota}.bin, nt1100-telemetria-zrodla-1.2.11.zip (zawiera homeassistant/addon/), ha/nt1100_jazdy-dodatek-1.0.0.zip, ha/instrukcja-ha.md, ha/podglad-*.png.
Dodatek (Python stdlib, base ghcr.io/home-assistant/{arch}-base:3.22 + apk python3, instalacja lokalna przez Sambę do /addons, slug local_nt1100_jazdy): Ingress 8099 (ta sama strona co skrzynka, www/index.html = make_page.py z webpage.h; tylko z 172.30.32.2), port 8098 odbiór: GET /api/ping, POST /api/ingest?n&id&ext(trk|thm|nam|json)&size&crc z nagłówkiem X-Klucz; json wysyłany ostatni = zatwierdzenie, numer jazdy = nr ze skrzynki (kolizja → max+1), index.json id→n. Pliki /share/nt1100/rides. Klucz losowy w /data/klucz (pokazany w zakładce Ustawienia). Czujniki sensor.nt1100_* przez Supervisor API co 10 min, notify.<opcja powiadomienie> albo persistent_notification, zdarzenie nt1100_nowa_jazda.
Firmware 1.2.11: ustawienia ha_local/ha_remote/ha_key (NVS haLocal/haRemote/haKey), znacznik NNNN.ha po potwierdzeniu, ping przed wysyłką, CRC-32 (mt::crc32Update, test ha_ingest), Influx/MQTT w "Zaawansowane", strona z względnymi adresami (działa pod Ingress). Hotspot szukany także gdy jest tylko ha_remote.
Cloudflare: dodatek Cloudflared, additional_hosts: nt1100.[DOMENA-HA] → http://IP-HA:8098 (IP HA Adriana nieznane; w instrukcji przykład [IP-HA-PRZYKŁAD]).
Build: arduino-cli w /root/tools (setup.sh), potrzebny pip pyserial+[narzędzie do wgrywania]. Test: host 3097 sprawdzeń OK; symulacja skrzynki → dodatek (zły klucz 401, uszkodzony plik 422, ponowna wysyłka = ta sama jazda bez 2. powiadomienia), Playwright: strona w trybie HA bez błędów.
Następny krok: Adrian instaluje wg instrukcji; czeka na wynik. Zob. [[telemetry-cloud-upload-options]], [[telemetry-firmware-126]].
2026-11-03 00:36 Adrian: NIE chce kopiować ręcznie (Samba) → publiczne repo GitHub `pbnz7nrwm4-hub/nt1100-ha` (zakłada je sam; Claude nie może tworzyć repo) jako repozytorium dodatków HA (Sklep → ⋮ → Repozytoria). Ma dodatek Git pull (ale ten pisze tylko do /config, nie nadaje się do dodatków). Jego repo ha-dom, ha-dom-dane, ecodan-adapter są prywatne.
2026-11-03 00:38 Repo nt1100-ha założone przez Adriana, dodane do projektu, ale push odrzucony (aplikacja Claude GitHub bez dostępu do tego repo) — poproszono Adriana o dodanie repo w instalacji aplikacji. Gotowa zawartość repo: scratchpad /tmp/claude-0/repo (repository.yaml + nt1100_jazdy/). server.py: panel_url() z /addons/self/info (slug zależy od źródła instalacji). Instrukcja ha/instrukcja-ha.md zmieniona na instalację z repozytorium.
2026-11-03 00:45 Dodatek wypchnięty do https://github.com/pbnz7nrwm4-hub/nt1100-ha (main). Nowe wersje dodatku: podbić version w nt1100_jazdy/config.yaml i push → w HA pojawi się aktualizacja. Klon: /home/user/nt1100-ha.
2026-11-03 00:53 Cloudflare: tunel "homeassistant" jest LOKALNIE zarządzany (dodatek Cloudflared w HA; panel CF tylko podgląd, trasa [DOMENA-HA] → http://homeassistant:8123). Trasa NT1100: w dodatku Cloudflared additional_hosts: hostname nt1100.[DOMENA-HA], service http://homeassistant:8098 (przy 502 → IP LAN HA:8098).
2026-11-03 01:00 Dodatek NT1100 Jazdy zainstalowany z repo i uruchomiony u Adriana; https://nt1100.[DOMENA-HA]/api/ping → 401 "zly klucz" (Cloudflared additional_hosts z http://homeassistant:8098 DZIAŁA). Zostało: OTA 1.2.11 na skrzynce + wklejenie adresów/klucza + pierwsza wysyłka.
2026-11-03 01:08 Firmware 1.2.12 (zawiera 1.2.11): sesje bez jazdy (mt::isRealRide: GPS ≥0,3 km, ≥1 min ruchu, ≥15 km/h; albo brak fixu GPS ale obroty >300) po przeliczeniu znikają z listy (surowy .mtl do /pominiete, ostatnie 20; nazwane jazdy zostają), nie są wysyłane; także stare. Klucze localStorage nt-theme/nt-axis (HA miał własne 'theme' → pusty "Motyw"). Dodatek 1.0.1 na GitHubie: lepsze wykrywanie IP (network/info + core config), karta połączenia zwinięta po pierwszej wysyłce, adres domowy opcjonalny. Adrian pytał o start nagrywania dopiero przy ruchu (ładowanie akumulatora, prace przy motocyklu) — odpowiedź: nagrywa, ale sesje bez jazdy usuwane; postój 15 min kończy sesję i skrzynka czeka na ruch.
2026-11-03 01:14 BŁĄD znaleziony u Adriana: skrzynka "Home Assistant nie potwierdzil pliku" — serwer odpowiadał {"ok": true} ze spacją, firmware szuka "ok":true. Naprawione w dodatku 1.0.2 (kompaktowy JSON), firmware bez zmian. Pliki przed potwierdzeniem nie są oznaczane .ha, więc nic nie zginęło.
2026-11-03 01:16 Dodatek 1.0.3: karta "Aktualizacja dodatku" w Ustawieniach panelu (POST api/addon/check → Supervisor /store/reload + /addons/self/info; api/addon/update → /store/addons/<slug>/update), hassio_role: manager. Źródła dodatku w scratchpadzie /tmp/claude-0/w/homeassistant/addon (zip źródeł 1.2.12 zawiera starszą wersję).
2026-11-03 01:27 Adrian: repo ma zostać publiczne, ale bez śladów sprzętu (może kiedyś sprzedawać). Dodatek 1.0.4: make_page.py podmienia nazwy podzespołów ([GPS], [IMU], GNSS/DIP, Bluetooth/iOS, piny) na ogólne; LICENSE "wszelkie prawa zastrzeżone". Stare commity (1.0.0–1.0.3) nadal mają nazwy w historii — force push odmówiony przez auto-mode; czeka na decyzję Adriana (zgoda na przepisanie historii albo usunięcie i ponowne założenie repo). Przy OTA przez dodatek: plik firmware w publicznym repo trzeba szyfrować (AES, klucz w firmware), bo .bin zdradza [procesor].
2026-11-03 01:27 Historia repo nt1100-ha nadpisana za zgodą Adriana (karta): jeden commit 1.0.4, bez nazw podzespołów.
2026-11-03 01:29 PIERWSZA PRAWDZIWA WYSYŁKA OK: panel pokazał 'ostatnio odebrano 02:18' (czas PL). Repo: commit 1.0.4 wcześniej miał przez pomyłkę version 1.0.3 — poprawione kolejnym commitem.

2026-11-03: firmware 1.2.14 + dodatek 1.1.0 (wypchnięty) = aktualizacja skrzynki przez dodatek. Skrzynka pyta GET /api/fw?v= (X-Klucz), pobiera /api/fw/bin (AES-256-CTR+HMAC, klucze w hw/fwkey.h — tylko w zip źródeł w plikach projektu, NIGDY w repo). Kiedy: po wysyłce w domu, co 30 min na postoju/stronie (sieć domowa, VBUS albo bateria >=50%), przycisk „Sprawdź aktualizację w Home Assistant” w zakładce Stan. Rollback, jeśli nowa wersja nie wystartuje. Proces wydania: zbuduj ota.bin → tools/fwpack.py OTA.bin WERSJA homeassistant/addon/nt1100_jazdy/firmware → podbij version w config.yaml i server.py → push do repo → Adrian klika aktualizację dodatku.
````

### `telemetry-hardware-plan.md`

````markdown
---
name: telemetry-hardware-plan
description: Recommended [producent] hardware and architecture for Adrian's DIY motorcycle telemetry (as of 2026-10-28)
metadata:
  type: project
  modified: 2026-10-28T18:11:18.051Z
---

Feasibility assessment delivered 2026-10-28 as a Claude Doc: https://claude.ai/artifact/VrBALHrQocigGGLZKStVts

Recommended kit (final shopping list in doc, 2026-10-28): [producent] [skrzynka-płytka] FULL (not SE: SE has no battery, needed to upload after ignition off; GNSS module IMU must be DIP-moved off 0x69) + Module GNSS ([GPS]) + [moduł CAN] ([układ CAN]), IP67 box, power from bike USB; ~600–750 zł (prices from memory, approximate). Compact alt: [wskaźnik] + [moduł CAN] + GPS Unit. Alt without CAN: ELM327 BLE (iOS needs BLE, not Classic).
Architecture: device logs everything to SD and streams over BLE; iPhone app (Swift) is display/archive.

**Why:** iPhone GPS is 1 Hz and phone IMU doesn't know bike orientation; lean needs gyro+GPS fusion.
Bike: Honda NT1100, 2025 (Euro 5+, red 6-pin Honda DLC, has IMU but lean frames are proprietary). Manual gearbox (not DCT). Bike has a power socket; no handlebar display wanted.
**How to apply:** Adrian has NO programming experience: Claude writes all firmware/config; Adrian only buys, mounts, flashes via browser (no IDE) and sends logs. Still unknown: which OBD PIDs/CAN frames the NT1100 exposes (verify with adapter first). Ask/check before ordering hardware.

Update 2026-10-28: Adrian leans toward skipping the iOS app and viewing rides in Home Assistant. Proposed: [procesor] uploads full log over home Wi-Fi to InfluxDB + Grafana add-ons (Geomap colored by lean, charts), ride summary via MQTT discovery entities; not into HA recorder. RaceChrono Pro as optional live view.
Adrian's Home Assistant has no InfluxDB or Grafana yet (as of 2026-10-28); HA runs as Home Assistant OS VM on Proxmox (confirmed), so add-ons (InfluxDB, Grafana, Mosquitto) are available.
Price checks: allegro.pl i kamami.pl zwracają 403 (allegro: DataDome anty-bot, nie sieć projektu); botland.com.pl działa (2026-11-03); elecena.pl via web-fetch works. Adrian przesyła zrzuty ofert.
Połączenie CAN (2026-10-29): Honda 6-pin → przejściówka (gniazdo OBD2) → przewód OBD2 męski z wolnymi końcami (np. iKKEGOL J1962, do kupienia) → kostka [moduł CAN]: pin6=H, pin14=L, pin4/5=G, pin16 +12V izolować. Adrian ma przysłać tabelkę kolorów żył.
Zasilanie (2026-10-29): zalecane źródło gasnące z zapłonem (gniazdo jeśli przełączane, inaczej fuse tap + przetwornica 12→5 V USB-C); stałe zasilanie rozładuje akumulator (firmware czeka w "Postój"). Adrian ma sprawdzić, czy gniazdo gaśnie z zapłonem. Kupuje [skrzynka-płytka] [wersja] (pełna wersja, OK). Puszka: Hammond 1554F2GYCL (119×89×61; 1554E 89×89 za wąska na [moduł CAN] obok, Sonoff R2 BOX 48 mm za niska). Stos [skrzynka-płytka]+GNSS+[podstawka] ≈ 44,6 mm, 54×54 bez klamry DIN.
Adrian ma drukarkę 3D Bambu Lab P2S (2026-10-29). Wkładka do 1554F wygenerowana 2026-10-29 (manifold3d, /mnt/project-files/telemetria/druk/: wkladka-1554F.stl, wkladka-test.stl, wkladka.py, README). Adrian ma tylko PLA i woli oficjalne wymiary zamiast własnych pomiarów. Następny krok: wydruk próbki i raport dopasowania (ew. CLEAR 0.35→0.5).

Obudowa, tańsze opcje (2026-10-30): Hammond 1554F2GYCL ok. 99 zł w TME. Zaproponowane zamienniki: Kradex ZP105.105.75 JpH TM (PC, przezroczysta pokrywa, ok. 30 zł brutto, Piekarz) jako rekomendacja; Kradex ZP120.80.60 JH TM ABS (27,40 zł, TIM, niska: 60 mm); zwykła puszka 100x100x70 IP65 (10-20 zł). Wymiary wewnętrzne Kradex nieznane (kradex.com.pl i tme.eu blokują fetch) - Adrian ma je podać, wtedy zmienić BOX_L/BOX_W/BOSS_R w print/wkladka.py.
Automatyczna wysyłka poza domem (2026-10-30): Adrian chce zero ręcznej roboty. Bluetooth odpada (iOS nie włączy hotspotu). Zaproponowano: dom Wi-Fi automatycznie; hotspot = otworzyć ekran Hotspot osobisty na minutę; docelowo moduł LTE-M [producent] [modem] (~150-200 zł + SIM IoT) do samodzielnej wysyłki i pozycji na żywo. Decyzja 2026-10-30: Adrian zostaje przy hotspocie; modem LTE ([modem]) do rozważenia jako kolejny krok po testach. Mocowanie: 3M Dual Lock SJ3550 (wyjaśnione 2026-10-30). Strona w chmurze (Cloudflare) czeka na jego "start teraz czy po testach".
Zasilanie (2026-10-30): Adrian ma ładowarkę USB w gnieździe zapalniczki NT1100. Ma sprawdzić, czy gniazdo gaśnie z kluczykiem (test telefonem). Jeśli stałe: nie przetwornica, tylko dodać w firmware tryb uśpienia na postoju (budzenie co ~30 s, sprawdzenie drgań) - do zrobienia na życzenie.
2026-10-31: Adrian ma też [producent] [wskaźnik] ([procesor], bez SD/modemu) - nie daje internetu; możliwe użycie: zapas, przycisk na kierownicy do znaczników, stanowisko testowe Wi-Fi (wymaga osobnego buildu). Internet skrzynki (LTE) i aplikacja iOS odłożone na po testach.
Druk (2026-10-31): Adrian ma już PETG (nie tylko PLA). Obudowa [wskaźnik] v1: korpus+pokrywa z okienkiem 0,6 mm (biały/natural PETG) + adapter klin 15° lub siodełko 22,2 mm na opaski; wkręty M3×10. Firmware [wskaźnik] jako wskaźnika stanu skrzynki jeszcze nie istnieje.
Kierownica NT1100 (2026-10-31): 28,6 mm w zacisku wg Hepco & Becker (riser NT1100 2025-), rura stożkowa → 22,2 mm przy manetkach. Siodełko [wskaźnik]: atom-adapter-kierownica-28.stl. Adrian woli, żebym sprawdzał dane w internecie zamiast kazać mu mierzyć.

2026-11-01: Zestawienie modułów LTE Cat-1 (Claude Doc https://claude.ai/artifact/AfkAQnrVB66gwtoVHEijyj). Rekomendacja: [producent] Gravity CAT1 [modem LTE] ([modem LTE]) — pasma z B20+B28, zasilanie 5 V USB-C lub 5–12 V, UART 3,3–5 V na Port C (złącze Gravity PH2.0 ≠ Grove, potrzebny przewód przejściowy); ok. 38–51 €, polskiej oferty nie znaleziono. Tańsza alternatywa: [producent] [modem LTE] HAT (Botland 31 €, bez B28). [producent] Unit Cat1-CN odpada (pasma chińskie). Niezakupione; decyzja po testach. Do sprawdzenia przed firmware: PPP w [pakiet płytek] 3.x vs fork TinyGSM LilyGO.
2026-11-01 Botland: brak [modem LTE]; jedyny Cat-1 to [producent] [modem LTE] HAT 139 zł (najlepszy wybór w Botlandzie). Są też [producent] U137 [modem] (LTE-M/NB-IoT, Grove, 239 zł; wymaga karty IoT) i [modem] HAT Cat-4 329 zł.
2026-11-01 10:31: Adrian wstrzymał temat LTE (tylko rozpoznanie). [modem LTE] HAT 65×30,5 mm mieści się w Kradexie (z [moduł CAN] trzeba go postawić bokiem lub nad stosem); antena LTE w zestawie. Firmware LTE: modem jako interfejs sieciowy (PPP), Wi-Fi priorytetem, APN/PIN w ustawieniach — dopiero gdy Adrian wróci do tematu.
2026-11-03 zasilanie: Adrianowi doradzono zasilanie przez gniazdo DC 5,5×2,1 w [podstawka] (wg [producent] ok. 9–24 V, do potwierdzenia napisem na podstawie) bezpośrednio 12 V, bez przetwornicy: przewód DC 5,5×2,1 (plus w środku) z bezpiecznikiem 2–3 A, z gniazda 12 V lub fuse tap na bezpieczniku przełączanym zapłonem. Pytanie otwarte: jakie gniazdo ma NT1100 (12 V okrągłe czy tylko USB).

Przewód OBD2 kupiony (2026-11-03): MultiDiag Pro+ 1 m, 16 żył, oferta NIE podaje kolorów; instrukcja ustalenia multimetrem i podłączenia do [moduł CAN]: /mnt/project-files/telemetria/obd2-do-can-unit.md. Pin 16 nie zasila skrzynki (prawdopodobnie stałe 12 V) — zaizolowany.
2026-11-04 (wątek „Wybrać tani modem LTE do skrzynki”): do 100 zł realnie tylko AliExpress: płytka „[modem LTE] core board” (SIM slot, TTL UART, ~60–80 zł z anteną; pasma B1/3/5/7/8/20). Rekomendacja: ta płytka; pewniejsza opcja [producent] [modem LTE] HAT (Botland 139 zł). Zasilanie modemu osobno 5 V/2 A szczytowo. Niezakupione, bez kodu do decyzji Adriana.
````

### `telemetry-lean-calibration.md`

````markdown
---
name: telemetry-lean-calibration
description: Dlaczego ekran skrzynki pokazuje przechył "--" i "uczenie 0%" na postoju (firmware 1.2.5) – zachowanie zamierzone
metadata:
  type: project
---

2026-11-02: Adrian zgłosił, że na ekranie przechył to ciągle "--", a kalibracja "uczenie 0%". Wyjaśnione: to normalne na postoju. Przechył pokazuje się dopiero przy mountValid + filtr >5 s (pipeline.cpp:433). Kalibracja montażu uczy się tylko w jeździe z GPS: oś "góra" 3000 próbek (30 s) przy >8 m/s, prosto, |aLong|<0.4; oś "przód" fwdEnergy 1500 (przyspieszenia i hamowania 0.8–8 m/s²) (estimators.cpp:13-20). Zapis w NVS po jeździe (telemetria.ino:204). DIP 0x68/0x69 nie ma wpływu (używany zawsze wewnętrzny [IMU] 0x69).
Zaproponowano opcjonalny napis na ekranie "jedź, aby skalibrować" zamiast "--"; czeka na decyzję Adriana. Jeśli przy jeździe z fixem 3D nadal 0%, to prawdziwy błąd do zbadania. Zob. [[telemetry-firmware-status]].
2026-11-02: Potwierdzono: kalibracja wczytywana przy starcie (telemetria.ino:263/274), zapisywana po jeździe (rides.cpp:184-186), w tle stale uczona od nowa, zmiana >3° → nowa (pipeline.cpp:357-361). Brak funkcji resetu kalibracji. Adrianowi zaproponowano test w aucie (kalibracja, rondo ~0°, krawężnik vs poziomica iPhone); po teście w aucie pierwsza minuta na motocyklu ze starą kalibracją.
2026-11-02 22:15: Pierwszy test w aucie: ekran "GPS nie wykryto!" (brak danych UART, nie brak fix), więc uczenie 0%. GNSS szukany tylko przy starcie (gnss.cpp:131, piny 7/6,18/17 + odwrotnie, 38400/9600/115200). Podejrzenie: DIP UART na module GNSS lub osadzenie; poproszono o zdjęcia modułu. Bateria pokazała 77% (odczyt działa; wcześniejsze 0% wyjaśnione/nieistotne).
2026-11-02 22:20: Adrian: przypadkowe dotknięcie przy starcie wchodzi w tryb serwisowy bez wyjścia. Zapowiedziano w 1.2.6 (razem z poprawką GPS): wejście przytrzymaniem ~3 s z odliczaniem, w menu "Wróć do jazdy" + timeout 15 s → nagrywanie, w trybie serwisowym przycisk "Wróć do jazdy" (restart).
2026-11-02 22:25: Moduł GNSS: (BŁĘDNE, poprawione 23:05 — patrz niżej) TX4/RX4/PS2. Adrian chce lepszy ekran: zaproponowano 4 ekrany (Jazda, G, Stan, Motocykl/OBD) przełączane dotknięciem lub co X s (wybór w ustawieniach); najpierw obrazki-makiety do akceptacji, potem kod w 1.2.6.
2026-11-02 22:27: Zdjęcie modułu: wszystkie DIP RX/TX/PPS były OFF → przyczyna "GPS nie wykryto". Makiety ekranów: /mnt/project-files/telemetria/ekran/ekrany.{png,html} (scratchpad ekran/, render playwright). Czeka na uwagi Adriana.

2026-11-02 23:05: POPRAWNE DIP wg schematu SCH_Module_GNSS_V1.0 (numery przełączników odwrotnie niż wiersze tabelki na płytce; RX = RXD = TX modułu): RX(SW2) 1=G18, 2=G7, 3=G14, 4=G10; TX(SW1, do RX modułu) 1=G17, 2=G13, 3=G6, 4=G0; PS(SW3) 1=G0, 2=G10, 3=G14. Dla [skrzynka-płytka]: RX 1, TX 1, PS 2. RX4+PS2 = konflikt na G10.
2026-11-02 23:07: Po DIP RX1/TX1/PS2 moduł wykryty (szuka, 0 sat, G18/G17) na 1.2.9. Dalej: test w aucie; bateria raz 77% raz 0% ([podstawka]) — test odłączenia USB do zrobienia.
2026-11-02 23:30: Test w aucie (jazda 0016, 1.2.9): GPS fix cały czas 8-11 sat, kalibracja gotowa ~3 min, przechył ±3° na prostych, rondo (skręt w lewo) +4..6° = przechył auta na zewnątrz (poprawne). Od ~590 s Adrian trzymał skrzynkę w ręce → lean -33/+88, lat_g 5.76 w podsumowaniu. Zapowiedziano na następną wersję: (1) odrzucanie niemożliwych wartości w maksimach (|latG|>~1.5, lean>~65°), (2) wykrywanie poruszenia skrzynki (kierunek siły właściwej w układzie motocykla odbiega od osi z na dłużej) → przechył ukryty i ponowna nauka. Narzędzie: scratchpad tools/dump.cpp (dump surowego .mtl), hb/replay.
````

### `telemetry-navigation-kurviger.md`

````markdown
---
name: telemetry-navigation-kurviger
description: Nawigacja NT1100 (2026-11-03/04): decyzje Adriana, co zbudowano (dodatek 1.4.0, silnik tras LXC, ekran 1.0.0, skrzynka 1.4.1), gdzie pliki, co czeka na testy
metadata:
  type: project
  modified: 2026-11-04T00:40:34.749Z
---

**Historia (skrót):** 2026-11-03 Adrian pytał o „Kurviger na [procesor]” → odpowiedź: pełny routing na [procesor] nie, ale cały system tak. Przeszło przez makiety (artifact T6V2VSQgP3kgr91qzqhFCW v6, kopia telemetria/ekran/makieta-[ekran-płytka].html) i dokument propozycji funkcji (artifact HUuNTcWk4gH2qa88vT78V1). Szczegółowe wymagania Adriana: patrz [[telemetry-navigation-requirements]].

**Decyzje Adriana:** wszystko od razu (etapy = punkty testów); bez przycisku BLE (menu po przytrzymaniu ekranu 1,5 s); silnik tras w kontenerze LXC na Proxmox; trzy wejścia celu: GPX z Kurvigera, planer na stronie dodatku, link z Map Google/Apple (skrót iOS); warianty szybko/lekko/kręto/bardzo liczone naraz; punkty po drodze + na ekranie „P2 18 km · cel 112 km”; omijanie gruntowych/płatnych/autostrad/promów; korki (TomTom, klucz opcjonalny); „inteligentny ekran” bez dotyku w jeździe, stały układ (góra czas/prędkość/stan, dół limit+skręt).

**Zbudowane 2026-11-04 (gałąź claude/project-thread-2sb3h8, PR #2 scalony do main 2026-11-04 na polecenie Adriana; HA widzi dodatek 1.4.0):**
- Dodatek 1.4.0: `nt1100_jazdy/nav.py` (trasy, GraphHopper custom model, GPX, Photon, linki, Open-Meteo, TomTom, zgodność jazdy), `ntt.py` (czytnik kwadratów), `navapi.py` (strona `/api/nav/*`, ekran `/api/nav/ping|route.ntr|mapa/*|traffic|reroute|log|fw|goto` z kluczem), `www/nav.js` (zakładka Nawigacja wstrzykiwana do index.html przez `<script src="nav.js">`), testy `tests/test_nav.py` (fałszywy GraphHopper). DOCS.md sekcja Nawigacja.
- Kontener: `silnik-tras/` (install-lxc.sh, aktualizuj.sh, config.yml GH 10 profil „motocykl” bez CH, motocykl.json, build_map.py → kwadraty .ntt 0,1°, mapa-serwer.py port 8988, GH port 8989). GH 10 sprawdzony lokalnie na syntetycznym PBF (custom_model z curvature, areas, round_trip działają).
- Ekran 1.0.0: `firmware/ekran/` w zipie źródeł (NIE w publicznym repo): core ntr/ntt/guide/localroute (A*) + testy host, hw display ([biblioteka] [sterownik ekranu] SPI + [sterownik dotyku] dotyk), net ([radio bezpośrednie] + Wi-Fi tylko do zadań, task), sdcard (SD_MMC), settings (AP „NT1100-Ekran”/[HASŁO-AP-EKRANU], http://192.168.4.1), fwupdate (ekran.bin podpisany tymi samymi kluczami). FQBN [procesor] PSRAM=opi FlashSize=16M app3M_fat9M_16MB. Czcionki DejaVu 14/20/30/52.
- Skrzynka 1.4.1: NavFrame (core/navlink.h, 37 B) 5 Hz przez [radio bezpośrednie]; `hw::navSend`.
- Nowe pliki w dodatku: firmware/skrzynka.bin 1.4.1 + firmware/ekran.bin 1.0.0 (fwpack.py OTA VER OUT ekran). Biblioteka /mnt/project-files/telemetria/: nt1100-telemetria-zrodla-1.4.1.zip (źródła, w tym firmware/ekran/), nt1100-ekran-1.0.0-full/ota.bin, nt1100-telemetria-1.4.1-full/ota.bin.

**Nieprzetestowane na sprzęcie (wszystko):** piny/kolory [ekran-płytka] (rgb_order), dotyk, kanał [radio bezpośrednie] vs hotspot (ekran rozłącza Wi-Fi, gdy ramki giną), rozmiar mapy PL na karcie (szac. 200–300 MB), czas importu GH (6 GB RAM). Adrian musi: postawić LXC (`bash install-lxc.sh`), wpisać adresy w zakładce Nawigacja, wgrać ekran przez USB (full.bin), wgrać skrzynkę 1.4.1 (dodatek sam ją zaoferuje).

**2026-11-04 13:35:** dodatek 1.4.2 (PR #4, scalony): Photon odrzuca `lang=pl` → wyszukiwanie bez parametru języka. Strona GH `:8989/maps/` to tylko diagnostyka (angielski, bez wyszukiwarki, wysokość 0 m — brak danych wysokości, celowo). Silnik w LXC 100 ([IP-LXC-NAWIGACJA]) działa, trasa Start–Wrocław OK. Następnie: Adrian wpisuje adresy w dodatku i synchronizuje mapę.

**2026-11-04 14:15:** dodatek 1.4.3 (PR #5 scalony): wolne liczenie = Python match_road bez indeksu (100 s → 4 s dzięki siatce odcinków GRID 0,005° w ntt.Map), warianty równolegle, pogoda jednym zapytaniem (WX_CACHE 15 min). Nowe: panel „Po drodze” (GET /api/nav/along), karta „W trasie” (GET /api/nav/nearby, POST /api/nav/via – postój i powrót na trasę 300 m dalej; ekran też POST /api/nav/via z kluczem: lat,lon,plat,plon,name), legenda POI. build_map: getid kod 1 tolerowany. Adrian: tryby „planowanie” vs „decyzje w trasie”; ekran ma pokazywać 3 najbliższe (Tankowanie/Jedzenie w menu) – w toku.

- Ekran 1.0.1 (Tankowanie/Jedzenie): [[telemetry-ekran-101]]
````

### `telemetry-navigation-requirements.md`

````markdown
---
name: telemetry-navigation-requirements
description: Szczegółowe wymagania Adriana do nawigacji NT1100 (2026-11-03): reguły ekranu, priorytety widoków, pogoda, zgodność z planem, objazdy
metadata:
  type: project
  modified: 2026-11-04T00:40:48.414Z
---

Wymagania zebrane 2026-11-03 (wątek „Ocenić nawigację w stylu Kurviger na [procesor]”), wdrożone w [[telemetry-navigation-kurviger]]:
- Bez klikania w jeździe (dotyk niebezpieczny); dotyk działa na postoju (>30 s) – strony stan/pogoda/podsumowanie/menu.
- Priorytety widoków: fotoradar/odcinek ≤1 km (z odliczaniem, odcinek ze średnią) → skręt ≤30 s/500 m (duża strzałka, drugi skręt „potem”) → ostrzeżenie pogodowe (deszcz za ~30 min, raz) → zjazd z trasy >150 m (strzałka/droga powrotu; po 2 km „jadę po swojemu” z auto-powrotem) → wynik zakrętu (pochył ≥ próg, domyślnie 20°, pokazany na prostej ~4 s) → mapa heading-up ze strzałką w dolnym pasku. Min. 4 s na widok, napisy duże, max 3 informacje.
- Stały układ: górny pasek = kolor stanu (zielony OK / żółty brak GPS / czerwony brak skrzynki) + czas + prędkość + „P2 18 km · cel 112 km”; dolny = znak limitu (okrągły) + strzałka i odległość do skrętu + ikona fotoradaru/korki.
- Pogoda na trasie z Open-Meteo przy planowaniu (punkty co ~30 min jazdy), na ekranie z wiekiem prognozy; bez internetu ostatnia prognoza.
- Zgodność jazdy z planem w HA: % na trasie, odstępstwa, przełącznik „pokaż trasę planowaną” w szczegółach jazdy, zdarzenia ekranu (objazd, pominięty punkt).
- Objazdy: „omiń 1/5 km”, „pomiń punkt” (menu po przytrzymaniu 1,5 s); przeliczenie na serwerze przez hotspot, offline lokalny powrót z kwadratów mapy (A*).
- Cała Polska na karcie ekranu (kwadraty 0,1°, drogi+limity+fotoradary+POI), aktualizacja co miesiąc z kontenera przez dodatek.
- Noc wg słońca (flaga ze skrzynki); jasność auto/ciemna/pełna.
- Ekran loguje, co pokazał (dziennik na karcie + POST do dodatku) do dostrajania progów w HA.
````

### `telemetry-page-demo-status.md`

````markdown
---
name: telemetry-page-demo-status
description: Strona WWW skrzynki: demo v7 wgrane do firmware 1.2.3 (2026-10-31), endpointy i pliki; co dalej
metadata:
  type: project
---

Demo strony (działa bez sprzętu): https://claude.ai/artifact/27nDNbhKuLbx6Aqdgi7VB3 (wersja 7, 2026-10-31). Źródło: scratchpad demo/nt1100-jazdy-demo.html, generowane przez demo/gen/build.py z webpage.h. Zmiany firmware'owe strony: /mnt/project-files/telemetria/wip/strona-nowa-1.2.2.patch (webpage.h, format.h/cpp, tests.cpp).

Zawartość strony (wzorzec: aplikacja BMW Motorrad): ciemny motyw, zakładki Jazdy/Statystyki/Stan/Ustawienia, plakietki stanu w nagłówku, lista jazd po miesiącach z miniaturkami, odtwarzanie jazdy (wskaźnik pochylenia + pionowe słupki hamowanie/przyspieszenie), nazwy i ulubione jazdy (POST /api/name, plik .nam), wyjazdy = jazdy z przerwą <3 h grupowane w jedną kartę, wykres własny z wyborem serii (prędkość, pochylenie, obroty, bieg, gaz, temp., G), statystyki ogólne.

Format .trk rozszerzony do 12 kolumn: lat,lon,lean,speed,alt,t,rpm,gear,throttle,coolant,long_g,lat_g (TrackDecimator w format.cpp, testy przechodzą).

2026-10-31 11:05: Adrian zaakceptował demo ("Dla mnie ok") → firmware 1.2.3 gotowy (nieprzetestowany na sprzęcie): /mnt/project-files/telemetria/nt1100-telemetria-1.2.3-{full,ota}.bin, nt1100-telemetria-zrodla-1.2.3.zip, wip/zmiany-1.2.2-do-1.2.3.patch (wip/strona-nowa-1.2.2.patch jest już zawarty). Instrukcja zaktualizowana na 1.2.3. Nowe w firmware: /api/status (live sd/wifi, last z /last.json zapisywanego przy końcu jazdy przez saveReport() w telemetria.ino, upload z NVS upWhen/upErr), GET/POST /api/settings (JSON, mt::jsonString/jsonNumber/jsonBool w core/format), POST /api/upload (wifiConnectAny nie rozłącza, gdy już jest w tej sieci), POST /api/name (/rides/NNNN.nam), name/fav w /api/rides, zegar systemowy z GNSS (settimeofday), liczniki fixMessages/svSum w GnssStatus, zaniki VBUS. Host: 3034 sprawdzeń OK. Skład: scratchpad src123 (pełne źródła), b123 (build).

2026-10-31 13:10: Adrian przysłał zrzuty Garmina, wybrał "Wszystkie" → zrobione w demo v8 i w firmware 1.2.4 (pliki 1.2.4 w /mnt/project-files/telemetria/, instrukcja zaktualizowana; łatka miniatur/cssOk była już w 1.2.3): oś wykresów czas/dystans (localStorage 'axis'), min/średnia/maks nad wykresami + linia średniej, czas w strefach przechyłu (pasma jak legenda mapy C), czasy w ruchu/postój/łącznie (wyjazd: postoje z zapłonem + przerwy), summary JSON: elevation_loss, min_alt, max_alt, uwagi do jazdy (note w .nam, /api/name&note=). Odłożone: pogoda na starcie, tętno z zegarka Garmin przez BLE (po testach). Wznios z GPS (histereza 3 m) do porównania z Garminem Adriana po pierwszych jazdach.

**Why:** Adrian chce oszczędzać limit zużycia na poprawki po dostawie sprzętu; strona była najpierw oceniona w demo.
**How to apply:** Dalsze zmiany strony nadal najpierw w demo (build.py czyta webpage.h ze src122 → przestawić na src123). Kolejna wersja = 1.2.4 albo 1.3.0 (ntfy + raport problemów). Zob. [[telemetry-firmware-status]].
````

### `telemetry-racecapture-ideas.md`

````markdown
---
name: telemetry-racecapture-ideas
description: Pomysły z RaceCapture (Autosport Labs) do wdrożenia w skrzynce NT1100 po pierwszych testach (2026-10-31)
metadata:
  type: project
---

2026-10-31: Adrian NIE chce kupować RaceCapture Mk3 Apex; pytał tylko, co warto przenieść. Zaproponowano (do listy rozwoju po pierwszych testach, kolejność nieustalona):
1. Mapowanie kanałów CAN na stronie skrzynki (ID, bajty, mnożnik, offset, endian) bez przebudowy firmware — najbardziej przydatne po skanie/nasłuchu ramek Hondy.
2. Nakładanie dwóch jazd / "odcinki" jak Strava (ta sama droga, różnica czasu).
3. Progi alarmowe kanałów z kolorem, łączone z ntfy w 1.3.0.
4. Eksport CSV dla RaceRender / Telemetry Overlay.
Odrzucone: Lua, Podium live, lap timing. Firmware RC jest GPL-3 i na STM32 — tylko inspiracja.
autosportlabs.com i wiki są zablokowane w sieci środowiska.
Decyzja Adriana 2026-10-31 22:00: zostaje pkt 1 (mapowanie CAN na stronie) jako osobna funkcja po testach; pkt 3 ok (dołączyć do 1.3.0 z ntfy); pkt 2 i 4 zbędne.
Powiązane: [[telemetry-firmware-status]]
````

### `telemetry-review-2026-11-03.md`

````markdown
---
name: telemetry-review-2026-11-03
description: Przegląd 2026-11-03 wdrożony w całości: firmware 1.3.0 + dodatek HA 1.2.0 (MQTT, pogoda, krętość, serwis, hasło X-Haslo, podpisane aktualizacje)
metadata:
  type: project
  modified: 2026-11-03T02:37:14.507Z
---

Dokument przeglądu: https://claude.ai/artifact/G6gLeu5QuN2pubozY4zPTk. Adrian 2026-11-03 zatwierdził WSZYSTKO; wdrożone tego samego dnia (main repo nt1100-ha, commit "Wersja 1.2.0").

Firmware 1.3.0 → 1.3.1 tego samego dnia (dodatek 1.2.1: poprawka mapy; nazwa funkcji `leaflet` kolidowała z window.leaflet ustawianym przez bibliotekę Leaflet, teraz loadLeaflet). Pliki w /mnt/project-files/telemetria/: -full, -ota, -ota-podpisany, zrodla-1.3.0.zip z fwkey.h i host/):
- wersja na każdym ekranie, polskie fonty VLW (tools/mkfont.py → hw/fonts.h), ekran postoju, noc = jasność 25.
- zmiany przez stronę z sieci domowej/hotspotu wymagają nagłówka X-Haslo = hasło AP (strona pyta i trzyma w localStorage nt-pass); nowa skrzynka losuje hasło AP, stara z [HASŁO-AP-SKRZYNKI] dostaje ostrzeżenie.
- /update przyjmuje TYLKO podpisany plik (…-ota-podpisany.bin = skrzynka.bin z dodatku).
- markery: .ha wysłana, .hm kopia .mtl w HA, .hn nazwa zmieniona po wysyłce, .rep raport jazdy. csv/lp tylko gdy InfluxDB skonfigurowany.
- .mtl do HA: dom albo hotspot gdy bateria ≥50% i zmierzona prędkość ≥ hotspot_min_kbit (domyślnie 1000; przez hotspot pliki >90 MB czekają na dom). Ping wysyła X-SD "total,free" MB i X-Bateria; odpowiedź niesie sd_min_free_pct i hotspot_min_kbit.
- cleanupCard: usuwa najstarsze jazdy z .ha+.hm i bez .hn, tylko gdy ustawienie w dodatku >0 (domyślnie 0 = nigdy; decyzja Adriana: nie kasować automatycznie).

Dodatek 1.2.0: MQTT discovery (urządzenie NT1100, broker z services mqtt:want albo opcje mqtt_host/user/password; fallback REST states), device_tracker.nt1100_parking, przebieg (odo wpisany + jazdy po dacie) i serwis z przyciskami, pogoda Open-Meteo (.wx: start, co 30 min, koniec; forecast ↔ archive), krętość (suma zmian kierunku co 50 m w °/km: <30 prosta, <80 lekko kręta, <150 kręta; zakręty = przechył ≥15° przy ≥15 km/h, top 5), powiadomienie z rekordami/problemami, ustawienia w panelu, testy tests/test_server.py + GitHub Action (strażnik nazw części przez hashe).
Adrian pytał o podstawę krętości (porównał do Calimoto/Kurviger) — wyjaśnione: geometria, nie liczba zakrętów; progi do dostrojenia po prawdziwych jazdach.
**How to apply:** następny krok to test na motocyklu; progi krętości zweryfikować na realnych jazdach. Zob. [[telemetry-ha-addon]], [[telemetry-dev-backlog]].
````

### `telemetry-wersje.md`

````markdown
---
name: telemetry-wersje
description: Gdzie Adrian sprawdza wersje całego oprogramowania (karta „Wersje oprogramowania” w dodatku 1.4.15, /api/versions)
metadata:
  type: project
  modified: 2026-11-04T17:54:57.263Z
---

2026-11-04 Adrian: „nie panuję nad tym, gdzie jest jakie oprogramowanie i czy jest najnowsze”. Wątek „Pokazać wersje oprogramowania w jednym miejscu”.
- Odpowiedź w wątku: tabela (dodatek 1.4.14, skrzynka 1.4.3 sama z dodatku, ekran 1.0.9 z Menu → Sprawdź wersję, silnik tras bez numeru, [wskaźnik] nieużywany). Zasada dla Adriana: aktualizuje tylko dodatek.
- Dodatek 1.4.15 (PR #17, SCALONY 2026-11-04 18:08): karta „Wersje oprogramowania” na górze zakładki Stan + znaczek „nowa wersja” w nagłówku; GET /api/versions (?check=1 przeładowuje sklep). Ekran: wersja z NAV.screen_position()["fw"] (ping ekranu), skrzynka: state box_fw. Podgląd: telemetria/ha/podglad-wersje.png.
- Każde nowe wydanie ekranu/skrzynki trafia tu automatycznie (czyta firmware/*.json) — nic nie trzeba dopisywać.
Powiązane: [[telemetry-ha-addon]], [[telemetry-ekran-demo]]
````


---

## 5. Dane dostępowe – tylko nazwy i miejsca

Żadnych wartości w tym pliku. Gdzie leży / skąd odczytać:

| Nazwa | Do czego | Gdzie jest |
|---|---|---|
| Klucz dodatku (`klucz`, nagłówek `X-Klucz`) | Wysyłka jazd ze skrzynki, ping/mapa/aktualizacje ekranu, podpisane linki GPX | Generowany przez dodatek w `/data/klucz`; widoczny w panelu dodatku → Ustawienia; wpisany w skrzynce (NVS `haKey`) i ekranie |
| Adres spoza domu (`adres_spoza_domu`) | Wysyłka przez Cloudflare (subdomena `nt1100.` na domenie HA Adriana) | Opcje dodatku w HA; tunel w dodatku Cloudflared (`additional_hosts` → `homeassistant:8098`) |
| Domena HA | Dostęp do HA z zewnątrz | Konto OVH Adriana; tunel Cloudflared (lokalnie zarządzany) |
| Adres lokalny HA (`ha_local`) | Wysyłka w domu | Ustawienia skrzynki; dodatek pokazuje go w Ustawieniach |
| Adresy silnika tras i mapy | Planer i mapa | Dodatek → Nawigacja/Ustawienia; IP kontenera LXC 100 z Proxmoxa (`pct list`, router – zalecona rezerwacja DHCP); porty 8989 (GraphHopper) i 8988 (mapa) |
| Klucz TomTom | Korki i objazdy | Dodatek → Ustawienia nawigacji (wpisany przez Adriana) |
| MQTT (`mqtt_host/port/user/password`) | Urządzenie NT1100 w HA | Domyślnie broker z HA (`services: mqtt:want`); własne dane w opcjach dodatku |
| Hasło AP skrzynki (`X-Haslo`) | Sieć „NT1100” i zmiany na stronie skrzynki spoza jej sieci | Ustawienia skrzynki (nowa skrzynka losuje, stara ma domyślne); przeglądarka trzyma w localStorage `nt-pass` |
| Hasło AP ekranu | Sieć ustawień ekranu „NT1100-Ekran” (http://192.168.4.1) | Domyślne w `DOCS.md` dodatku i instrukcji ekranu |
| Wi-Fi domowe / hotspot iPhone (SSID + hasło) | Łączność skrzynki i ekranu | U Adriana; wpisane w ustawieniach skrzynki (`homeSsid/homePass`) i ekranu |
| Klucze podpisu i szyfrowania firmware (AES-256-CTR + HMAC) | Aktualizacje skrzynki i ekranu | `hw/fwkey.h` – **tylko** w zipie źródeł w plikach projektu; nigdy w repo |
| Temat ntfy | Powiadomienia (plan 1.3.x) | Wymyśli Adrian; pole w ustawieniach (jeszcze nie wdrożone) |
| Logowanie do LXC 100 | Kontener nawigacji | Login `root`; hasło ustawia Adrian (`passwd`), wejście bez hasła: Proxmox → węzeł → Shell → `pct enter 100` |
| Proxmox, HA, router | Administracja | U Adriana |
| GitHub | Repo `pbnz7nrwm4-hub/nt1100-ha` (publiczne); prywatne: `ha-dom`, `ha-dom-dane`, `ecodan-adapter` | Konto Adriana; aplikacja Claude GitHub musi mieć dostęp do repo |
| Token HA (przyszły, do odczytu) | Dla kontenera z Claude Code | Do utworzenia w HA → profil → tokeny; trzymać tylko w kontenerze |

---

## 6. Plan na najbliższe tygodnie (w kolejności ważności)

1. **Testy na motocyklu (najważniejsze, od tego zależy reszta).** Skrzynka sztywno na Dual Lock, przewód OBD2 do CAN, zasilanie z gniazda (sprawdzić, czy gaśnie z zapłonem). Pierwsza jazda → wysyłka do HA → sprawdzić stronę jazd, MQTT, powiadomienie, dane z silnika (spalanie z mnożnikiem, sprzęgło, stopka). Zebrać logi i skan „na postoju vs po ruszeniu” (kontrolki ABS/TC).
2. **Ekran 1.1.2 na sprzęcie.** Dokończyć wgranie (ota.bin pod 0x10000), Wi-Fi, mapa z karty/ZIP, dźwięk, BLE w jeździe; zdjęcie wtyczki akumulatora (biegunowość), wydruk obudowy z PETG i montaż na kokpicie.
3. **Nawigacja end-to-end.** Dodatek 1.5.13 → planer → „Wyślij na ekran” → GPX w OsmAnd (CarPlay) → jazda testowa; sprawdzić ETA/skręty w trybie motocykl, korki TomTom, objazd z powiadomieniem; dokończyć kafelki w kontenerze.
4. **Decyzja „wyjazdy zamiast odcinków”** i dokończenie licznika/powiadomień (czeka na Adriana); potem stopka jako koniec jazdy (wariant A).
5. **1.3.x: raport problemów + powiadomienia ntfy** (łatka `wip/1.3.0-core-wip.patch`, progi alarmowe: temp. >105 °C, napięcie <13,5 V, stopka przy prędkości).
6. **Ekran BLE – dopracowanie** (ANCS treść wiadomości na postoju, AMS muzyka, „odjechałeś bez telefonu”, bateria telefonu) – po testach w jeździe; łatki `ekran-1.1.2-bluetooth.patch` tylko przy problemach.
7. **RAM do Proxmoxa** (8 GB DDR3L) → przydziały HA 6 GB / nawigacja 7–8 GB → mapy CZ/SK (`MAPA_DODATKOWE` w `kafelki.sh`).
8. **Kontener LXC z Claude Code** wspólny dla HA i motocykla (po RAM; na próbę tydzień).
9. **LTE** ([modem LTE]) – po decyzji Adriana: podgląd na żywo co 5–10 s, wysyłka w trasie bez hotspotu.
10. **Dalej:** mapowanie kanałów CAN na stronie, strona w chmurze (Cloudflare), przycisk „Otwórz na iPhonie”, pomysły z RaceCapture, ewentualnie aplikacja iOS.
