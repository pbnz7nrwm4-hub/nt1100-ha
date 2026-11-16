# Zadania dzieci – panel w Home Assistant

Dodatek nie przechowuje danych. Pokazuje w menu Home Assistanta aplikację Zadania dzieci, która działa w kontenerze w domu,
więc działa też poza domem (przez aplikację HA na telefonie). Kto jest zalogowany w HA, tego aplikacja rozpoznaje sama.

## Ustawienie (raz)
1. W aplikacji Zadania (w domu, jako administrator): **Osoby → Aplikacja Home Assistant** – skopiuj adres i klucz.
2. Tutaj: **Konfiguracja** – wklej adres i klucz, dodaj token długoterminowy HA (profil → Bezpieczeństwo). Zapisz, uruchom.
3. Każdy domownik raz otwiera **Zadania** w menu HA. Potem administrator w aplikacji (Osoby → Konto HA) przypisuje
   konto do osoby – albo domownik sam wpisuje swój PIN i konto łączy się samo.

Panel jest widoczny także dla użytkowników HA bez praw administratora (dzieci).
