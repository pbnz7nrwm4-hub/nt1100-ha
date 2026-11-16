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
- **AI (opcjonalnie)**: lokalny serwer z modelem widzącym zdjęcia (Ollama albo API zgodne z OpenAI, np. llama-swap). Ocenia zdjęcie; kroki rozpisuje tylko na życzenie (pole w „Więcej”).
  AI tylko podpowiada, decyduje rodzic. Bez AI wszystko działa, rodzic ocenia sam.

## Wersja 1.1
- **PIN**: pierwsze wejście z osobistego linku – ustawiasz PIN (4–6 cyfr); potem wybierasz imię i wpisujesz PIN.
  Po 5 błędach logowanie tej osoby blokuje się na 15 minut. Zapomniany PIN kasuje administrator albo opiekun dziecka
  (przycisk „Skasuj PIN”); w aplikacji HA nowy PIN ustawia się bez starego.
- **Aplikacja Home Assistant** (dodatek „Zadania dzieci” z tego repozytorium): panel w menu HA, działa też poza domem.
  Konto HA przypisuje administrator w Osobach – wtedy bez PIN-u.
- **Katalog**: 60 gotowych zadań w trzech poziomach (6–9, 10–12, 13+); poziom podpowiada rok urodzenia dziecka.
- **Ze zrzutu ekranu**: zrzut z dziennika szkolnego albo zdjęcie kartki – AI wypisuje zadania i terminy, rodzic wybiera.
- **Od 1.3**: krótki formularz zlecania (reszta pod „Więcej”), szybkie zatwierdzanie zadań bez zdjęcia z listy, historia punktów,
  „Pierwsze kroki” dla administratora, telefon do powiadomień wybierany z listy z HA, podsumowanie tygodnia w niedzielę o 18:00.
- **Od 1.4/1.5**: „Pomóż mi zacząć” (AI podpowiada dziecku pierwszy krok), licznik prób, „Dziś nie dam rady” z decyzją rodzica,
  zgłoszenie własnego zadania, własne przypomnienia dziecka, ponaglenie rodzica po 2 h, punkty jako kieszonkowe (opcja).
- **Od 1.7**: ekran „Ustawienia” dla administratora (link na dole strony) zastępuje polecenia w konsoli: adres i model AI,
  adres i token Home Assistanta, sprawdzenie połączeń, „Zobacz jako dziecko”, „Sprawdź i zaktualizuj teraz”. Ustawienia z
  aplikacji mają pierwszeństwo przed plikiem instalatora. Po zmianie instalatora aktualizacja uruchamia go sama.
- **Od 1.6**: zakładka „Nauka” u dziecka – „Przepytaj mnie”, „Wytłumacz mi”, „Test przed sprawdzianem”. Dziecko robi zdjęcie
  notatek (do 3 stron), AI pyta i sprawdza tylko na ich podstawie; bez materiałów korzysta z własnej wiedzy i wyraźnie to
  oznacza („to nie wynika z Twoich materiałów”). Rodzic widzi temat, czas i wynik, bez treści odpowiedzi.
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
W kontenerze uruchom `zadania-ai` i podaj adres, model i klucz API (klucz nie pokazuje się na ekranie, trafia do
`/etc/zadania/ai_klucz`). Adres kończący się na `/v1` = API zgodne z OpenAI (llama-swap, llama.cpp, LM Studio),
inny = Ollama (`http://<adres>:11434`). Polecenie sprawdza, czy model odpowiada, i restartuje usługę. Puste = AI wyłączone.

## Obsługa
- Awaryjnie, gdy nikt z administratorów nie może wejść: `zadania-pin "Imię"` (kasuje PIN, wypisuje link).
- Zgubiony link: `zadania-link "Imię"` albo w aplikacji **Osoby** → Nowy link (stary przestaje działać).
- Kopia bazy co noc: `/var/lib/zadania/kopie/` (30 ostatnich). Zdjęcia zakończonych zadań kasują się po 90 dniach (`ZD_ZDJECIA_DNI`).
- Aktualizacje same co godzinę z gałęzi main. Ręcznie: `zadania-aktualizuj`.
- Dziennik: `journalctl -u zadania -n 50`.
- Bezpośrednio (adres kontenera) strona działa tylko w sieci domowej; spoza domu – przez aplikację HA.
