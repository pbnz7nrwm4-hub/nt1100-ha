# Wydanie nowej wersji

Home Assistant czyta tylko gałąź `main`. Niescalona zmiana = brak aktualizacji.

## Dodatek

1. Zmiany na gałęzi, testy lokalnie: `python3 -m unittest discover -s tests`
   (do testu mapy potrzebny `osmium-tool`; bez niego jeden test jest pomijany).
2. Podbij **oba** numery na ten sam: `version` w `nt1100_jazdy/config.yaml`
   i `VERSION` w `nt1100_jazdy/server.py`.
3. Dopisz w `nt1100_jazdy/DOCS.md`, co się zmieniło dla użytkownika (prostym językiem).
4. Pull request o tytule **„Wersja X.Y.Z: …”**. GitHub uruchamia testy (w tym strażnika,
   który pilnuje, żeby w plikach nie było nazw części).
5. Po zielonych testach scal (squash). Użytkownik: Ustawienia → Dodatki → NT1100 Jazdy → Aktualizuj
   (albo przycisk w panelu: Ustawienia → Aktualizacja dodatku).

Bez podbicia numeru Home Assistant nie zobaczy aktualizacji.

## Oprogramowanie skrzynki i ekranu

Źródła i klucze podpisu **nie są** w tym repozytorium (prywatne archiwum właściciela).
Do repozytorium trafiają tylko gotowe, zaszyfrowane i podpisane obrazy:

1. Zbuduj obraz z prywatnych źródeł (instrukcja w prywatnym archiwum) i przetestuj
   na komputerze (testy rdzenia) oraz na urządzeniu.
2. Zaszyfruj i podpisz narzędziem z prywatnego archiwum → `skrzynka.bin` + `skrzynka.json`
   albo `ekran.bin` + `ekran.json` (wersja i rozmiar).
3. Podmień pliki w `nt1100_jazdy/firmware/` i wydaj nową wersję **dodatku** (jak wyżej).
   Dodatek sam zaproponuje urządzeniom nowszą wersję.

Zmiany wyglądu strony skrzynki, ekranu i panelu najpierw pokazuje się na makiecie lub zrzutach
i wydaje dopiero po akceptacji właściciela.
