# NT1100 Telemetria – dodatki Home Assistant

Repozytorium dodatków Home Assistant dla skrzynki telemetrycznej Hondy NT1100.

Instalacja: Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria → dodaj
`https://github.com/pbnz7nrwm4-hub/nt1100-ha` → NT1100 Jazdy → Zainstaluj.

- `nt1100_jazdy/` – strona jazd w Home Assistant (panel w menu bocznym), odbiór jazd ze skrzynki
  (port 8098, tylko z kluczem), urządzenie NT1100 przez MQTT, pogoda na trasie, przebieg
  i serwis, powiadomienie po jeździe z rekordami.
- `pojazdy/` – dodatek **Pojazdy** (jak Fuelio): tankowania (ręcznie), ładowania auta z wtyczką
  (same, z historii Home Assistant: liczniki ładowarek, bilans PV, strefy G13, % baterii), spalanie
  l/100 km i kWh/100 km, koszty miesięczne i roczne, inne koszty, terminy z przypomnieniem, polisy OC/AC z ratami, import
  i eksport w formacie Fuelio, nocna kopia. Instrukcja: `pojazdy/DOCS.md`.
- `silnik-tras/` – silnik tras nawigacji do uruchomienia w kontenerze Proxmox (GraphHopper
  + mapa na kartę ekranu z OpenStreetMap); instrukcja w `silnik-tras/README.md`.

Dokumentacja (architektura, instalacja od zera, gdy coś nie działa, wydanie): katalog [`docs/`](docs/README.md).
