# Gdy coś nie działa

Najpierw: panel dodatku → **Motocykl**. Karty „Wersje oprogramowania”, „Skrzynka”,
„Dodatek Home Assistant” i „Ekran i mapa” pokazują większość przyczyn kolorem kropki.
Dziennik dodatku: Ustawienia → Dodatki → NT1100 Jazdy → **Dziennik**.

| Objaw | Najczęstsza przyczyna | Co zrobić |
|---|---|---|
| Jazdy nie przychodzą do HA | skrzynka nie łączy się z Wi-Fi albo ma zły klucz | w dzienniku dodatku szukaj „Odrzucono: zly klucz” → przepisz klucz z panelu (Ustawienia → Połączenie ze skrzynką) do skrzynki |
| Jazda przychodzi tylko w domu | brak adresu spoza domu albo hotspot za słaby | Ustawienia skrzynki → Wysyłka; Ustawienia dodatku → „Kopia surowego zapisu przez hotspot” (próg prędkości) |
| „plik dotarł niepełny albo uszkodzony” | przerwane połączenie | nic – skrzynka wyśle ponownie przy następnym połączeniu |
| Brak urządzenia NT1100 w HA | nie działa Mosquitto albo zły login | panel → Motocykl → „Encje w Home Assistant (MQTT)” pokazuje powód; bez MQTT czujniki `sensor.nt1100_*` i tak są ustawiane |
| Brak powiadomienia po jeździe | nie wybrano telefonu | Ustawienia → Powiadomienie po jeździe; dziennik: „Powiadomienie nieudane” |
| Trasy się nie liczą | silnik tras wyłączony albo w przebudowie | Motocykl → Ekran i mapa pokazuje etap przebudowy; w kontenerze `systemctl start nt1100-trasy` |
| Mapa w panelu pusta | brak internetu w przeglądarce i brak kafelków z kontenera | poczekaj na koniec budowy mapy w kontenerze (raz w miesiącu, ok. 1–2 h) |
| Ekran 5": „Szukam GPS…” | ekran pod dachem albo GPS dopiero startuje | wyjedź pod niebo, pierwsza pozycja może zająć kilka minut |
| Ekran 5": brak danych silnika | skrzynka nie nadaje (ok. 20 s po zapłonie) albo ma starsze oprogramowanie niż 1.4.4 | włącz zapłon; ekran i tak prowadzi na własnym GPS |
| Ekran 5": brama „stan nieznany” | brak połączenia z dodatkiem albo nie ustawiono encji | Ustawienia → Planowanie i dom → Brama / Garaż; poza domem potrzebny hotspot |
| Ekran 2,8": „brak skrzynki” | skrzynka wyłączona albo ekran za daleko | włącz zapłon; ekran szuka skrzynki 20 s po włączeniu |
| Ekran nie pobiera trasy | ekran nie ma Wi-Fi (dom / hotspot) | Menu → Ustawienia Wi-Fi; na iPhonie włącz „Maksymalizuj zgodność” hotspotu |
| Ekran pokazuje starą wersję | aktualizacja tylko w domu i przy ładowaniu | zakładka Menu (2,8": przytrzymaj ekran → Menu) → Sprawdź wersję → Aktualizuj |
| „Zgodność z planem” przy jeździe bez planu | (naprawione w 1.5.14) | – |
| Korki nie działają | brak klucza TomTom | Ustawienia → Ustawienia nawigacji → klucz TomTom |

Czego nie robić: nie podłączać zasilania z gniazda diagnostycznego (pin stałego zasilania),
nie usuwać ręcznie plików w `share/nt1100` przy włączonym dodatku.
