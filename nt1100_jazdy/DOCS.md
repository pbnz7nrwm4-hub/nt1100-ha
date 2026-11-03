# NT1100 Jazdy

Jazdy ze skrzynki telemetrycznej NT1100 w Home Assistant: ta sama strona co w skrzynce
(panel „NT1100 Jazdy” w menu bocznym, także w aplikacji HA), czujniki ostatniej jazdy
`sensor.nt1100_*` i powiadomienie po każdej nowej jeździe.

- Pliki jazd: folder `share/nt1100/rides` (Samba: udział „share”).
- Skrzynka wysyła na port 8098 (w domu: `http://IP-HA:8098`, w trasie przez Cloudflare).
  Bez poprawnego klucza nic nie zostanie przyjęte.
- Klucz i adresy do wpisania w skrzynce: zakładka **Ustawienia** w panelu dodatku.
- Zdarzenie `nt1100_nowa_jazda` (z podsumowaniem jazdy) do własnych automatyzacji.

## Konfiguracja

- **powiadomienie**: usługa powiadomień telefonu bez `notify.`, np. `mobile_app_iphone_adriana`.
  Puste = powiadomienie w Home Assistant (dzwonek).
- **adres_spoza_domu**: adres dodatku przez Cloudflare (tylko do wyświetlenia na stronie).
- **klucz**: zostaw puste; dodatek wygeneruje klucz sam.
