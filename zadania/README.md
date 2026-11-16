# Zadania dzieci

Aplikacja w sieci domowej (kontener „aplikacje”, port 8092): rodzic zleca zadanie, dziecko potwierdza (zwykle zdjęciem),
komputer w domu podpowiada ocenę, rodzic zatwierdza i przyznaje punkty. Dane i zdjęcia zostają w domu.

## Co umie (wersja 1)
- **Zlecanie**: dla kogo, co, czego oczekuję, termin, punkty, sposób potwierdzenia: zdjęcie po, zdjęcie zeszytu,
  minutnik, na zaufanie (co piąte losowo prosi o zdjęcie).
- **Powtarzanie**: dni szkolne, codziennie albo wybrane dni, z godziną. Pora dnia (poranek, popołudnie, wieczór)
  tworzy rutynę z paskiem postępu.
- **Pula**: zadania dodatkowe, które dziecko samo bierze.
- **Dziecko**: ekran „Dziś” z krokami i czasem do terminu, zdjęcia przed i po, dopisek, seria dni.
- **Rodzic**: lista do zatwierdzenia ze zdjęciem i oceną AI; Zatwierdź, Częściowo (połowa punktów), Do poprawki;
  słowo do dziecka; premia albo odjęcie punktów.
- **Nagrody**: małe nagrody i duży cel; dziecko wymienia punkty za zgodą rodzica i może zaproponować własną nagrodę.
- **Role**: każde dziecko ma swoich opiekunów; każdy opiekun: zleca, zatwierdza albo tylko podgląda.
  Administrator dodaje osoby i daje każdej osobisty link.
- **Powiadomienia** przez Home Assistanta (nowe zadanie, do zatwierdzenia, decyzja, godzina przed terminem).
- **AI (opcjonalnie)**: serwer Ollama w domu z modelem widzącym zdjęcia. Rozpisuje zadanie na kroki i ocenia zdjęcie.
  AI tylko podpowiada, decyduje rodzic. Bez AI wszystko działa, rodzic ocenia sam.

## Wersja 1.1
- **PIN**: pierwsze wejście z osobistego linku – ustawiasz PIN (4–6 cyfr); potem wybierasz imię i wpisujesz PIN.
  Po 5 błędach logowanie tej osoby blokuje się na 15 minut. Zapomniany PIN kasuje administrator albo opiekun dziecka
  (przycisk „Skasuj PIN”); w aplikacji HA nowy PIN ustawia się bez starego.
- **Aplikacja Home Assistant** (dodatek „Zadania dzieci” z tego repozytorium): panel w menu HA, działa też poza domem.
  Konto HA przypisuje administrator w Osobach – wtedy bez PIN-u.
- **Katalog**: 60 gotowych zadań w trzech poziomach (6–9, 10–12, 13+); poziom podpowiada rok urodzenia dziecka.
- **Ze zrzutu ekranu**: zrzut z dziennika szkolnego albo zdjęcie kartki – AI wypisuje zadania i terminy, rodzic wybiera.
- **Popraw z AI**: czego brakuje w poleceniu, lepszy opis, kroki, punkty i forma potwierdzenia z uzasadnieniem.

## Instalacja w kontenerze
Proxmox → Shell, potem `pct enter 140`, i w kontenerze:

```
curl -fsSL https://raw.githubusercontent.com/pbnz7nrwm4-hub/nt1100-ha/main/zadania/instaluj.sh -o /root/zadania.sh
bash /root/zadania.sh "Imię" http://<adres Home Assistanta>:8123
```

Na końcu wypisze link administratora. Otwórz go na swoim telefonie i nie wklejaj nigdzie.
Potem w aplikacji: **Osoby** → dodaj dzieci i dorosłych, przy każdym dziecku zaznacz opiekunów (Z – zleca, A – zatwierdza),
**Link** → otwórz go na telefonie danej osoby, Udostępnij → „Do ekranu początkowego”.

## Panel w aplikacji Home Assistant i powiadomienia
1. HA → Ustawienia → Dodatki → Sklep → repozytorium tego projektu → **Zadania dzieci** → Zainstaluj.
2. W aplikacji Zadania (administrator): **Osoby → Aplikacja Home Assistant** – skopiuj adres i klucz.
3. Dodatek → Konfiguracja: wklej adres i klucz, dodaj token długoterminowy HA (profil → Bezpieczeństwo). Zapisz, uruchom.
   Token trafia do aplikacji sam (powiadomienia). Bez dodatku token można wpisać w kontenerze: `zadania-ha-token`.
3. W aplikacji, **Osoby**: przy każdej osobie wpisz usługę powiadomień, np. `mobile_app_iphone_zosi`
   (Narzędzia deweloperskie → Akcje → wpisz „notify.”).

## Lokalne AI
W `/etc/zadania/zadania.env` ustaw `ZD_AI_URL=http://<adres serwera Ollama>:11434` i `ZD_AI_MODEL` (model widzący zdjęcia),
potem `systemctl restart zadania`.

## Obsługa
- Awaryjnie, gdy nikt z administratorów nie może wejść: `zadania-pin "Imię"` (kasuje PIN, wypisuje link).
- Zgubiony link: `zadania-link "Imię"` albo w aplikacji **Osoby** → Nowy link (stary przestaje działać).
- Kopia bazy co noc: `/var/lib/zadania/kopie/` (30 ostatnich). Zdjęcia zakończonych zadań kasują się po 90 dniach (`ZD_ZDJECIA_DNI`).
- Aktualizacje same co godzinę z gałęzi main. Ręcznie: `zadania-aktualizuj`.
- Dziennik: `journalctl -u zadania -n 50`.
- Bezpośrednio (adres kontenera) strona działa tylko w sieci domowej; spoza domu – przez aplikację HA.
