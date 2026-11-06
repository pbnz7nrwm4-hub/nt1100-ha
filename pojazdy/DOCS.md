# Pojazdy

Tankowania, ładowania, koszty i terminy pojazdów w jednym panelu Home Assistant – jak aplikacja
Fuelio, ale ładowania auta z wtyczką wpisują się same.

## Co robi

- **Tankowania** dodajesz ręcznie (pomarańczowy przycisk „+ Tankowanie”): data, przebieg, litry, cena
  albo kwota (dwie z trzech wystarczą), „do pełna”, stacja. Cena i stacja podpowiadają się z ostatniego
  tankowania. Przy motocyklu pole przebiegu ma wartość z telemetrii (encja przebiegu pojazdu) – zawsze
  możesz ją poprawić.
- **Ładowania** auta z wtyczką dopisują się same co 10 minut z historii Home Assistant: z liczników
  energii ładowarek (dom i hala), z bilansu sieci (część z nadwyżki PV), z cen stref G13 i z % baterii
  auta. Ładowanie poza domem dodajesz ręcznie (Historia → „+ Ładowanie”).
- **Spalanie** liczone metodą „od pełnego do pełnego baku”, jak w Fuelio: litry wszystkich tankowań
  między dwoma pełnymi bakami ÷ przejechane km. „Pominąłem poprzednie tankowanie” przerywa liczenie.
- **Auto z wtyczką (PHEV)**: osobno paliwo (l/100 km), prąd (kWh/100 km, liczone z gniazdka, czyli
  razem ze stratami ładowania) i łączny koszt zł/100 km. Prąd liczony tylko dla baków zaczętych po dniu,
  od którego HA zapisuje ładowania (ustawienie `dane_pradu_od`, domyślnie 1.11.2026).
  Porównanie z jazdą na samej benzynie używa spalania wpisanego w danych pojazdu.
- **Koszty**: miesiąc, rok, ostatnie 12 miesięcy, całość; wykres miesięczny paliwo / prąd / inne, zł/km.
- **Inne koszty** (serwis, OC/AC, przegląd, opony…) i **terminy** z przypomnieniem w telefonie:
  30, 7 i 1 dzień przed datą albo 500 i 100 km przed przebiegiem. „Zrobione” przesuwa termin o okres
  i może od razu zapisać koszt.

## Jak liczony koszt prądu

Dla każdej godziny ładowania:

1. Strefa G13 (Tauron): w dni robocze przedpołudnie 7–13, popołudnie 16–21 (kwiecień–wrzesień 19–22),
   reszta i weekendy/święta – strefa tania. Liczone w dodatku tak samo jak `sensor.g13_strefa` w HA.
2. Bilans godzinowy domu: pobrane minus oddane z liczników sieci. Gdy w tej godzinie dom więcej oddał,
   niż pobrał, ładowanie szło z nadwyżki PV i kosztuje 0 zł. Ostrożnie: cały pobór z sieci w danej godzinie
   przypisujemy najpierw autu (koszt raczej zawyżony niż zaniżony).
3. Koszt = kWh z sieci × cena strefy (encje `input_number.cena_*` w HA, w chwili ładowania).

Druga wycena („Wartość kWh”) mnoży całą energię przez `sensor.wartosc_kwh`, który uwzględnia magazyn
net‑meteringu. Każde automatyczne ładowanie można otworzyć, poprawić koszt albo wykluczyć.

## Encje w Home Assistant

Dodatek wystawia czujniki (co 10 minut i po każdej zmianie), dla każdego pojazdu:
`sensor.pojazdy_<pojazd>_spalanie`, `_koszt_100km`, `_koszt_miesiac`, `_przebieg`, `_terminy`
(stan = liczba pilnych terminów, atrybuty: lista terminów), dla aut z wtyczką także `_zuzycie_pradu`.
Można je dodać do dowolnego pulpitu.

Dodatek NT1100 Jazdy (od 1.5.27) czyta terminy motocykla z `sensor.pojazdy_nt1100_terminy`: pokazuje
„serwis za … km”, a przypomnienia wysyła już tylko dodatek Pojazdy. Przy pierwszym uruchomieniu Pojazdy
przenoszą pozycje serwisu z NT1100 Jazdy (olej, łańcuch, przegląd) do Terminów.

## Ustawienia (zakładka Więcej)

- **Import z Fuelio**: plik `.fuelio` (Fuelio → Ustawienia → Kopia zapasowa → Eksport) albo CSV pojazdu.
  Najpierw podgląd: liczba tankowań, zakres dat, podejrzane kwoty (kwota niezgodna z litrami × cena,
  np. literówka) i wybór, do którego pojazdu trafia każdy pojazd z pliku (albo „Pomiń”). Powtórny import
  pomija to, co już jest.
- **Eksport**: plik `.fuelio` (ten sam format) – do Fuelio albo jako kopia.
- **Kopia**: co noc (po 2:00) do `/share/pojazdy/kopie`: baza `pojazdy-RRRR-MM-DD.db` i `pojazdy-RRRR-MM-DD.fuelio`,
  30 ostatnich. Baza dodatku (`/data/pojazdy.db`) wchodzi też do zwykłej kopii Home Assistant.
- **Pojazdy**: nazwa, rodzaj, bak, bateria, spalanie na samej benzynie, encja przebiegu.
- **Powiadomienia**: usługa telefonu (np. `mobile_app_iphone`); puste = powiadomienie w HA.
- **Ładowarki** (domyślnie): `sensor.ladowarka_auta_energia_licznik` (dom) i
  `sensor.ladowarka_w_hali_energia_licznik` (hala), sieć: `sensor.siec_pobrana_licznik`,
  `sensor.siec_oddana_licznik`, bateria auta: `sensor.eclipse_bateria`. Inne encje można ustawić przez
  `POST api/ustawienia` (np. `{"ladowarki": [...]}`).

## Gdy coś nie działa

- **Brak automatycznych ładowań**: Więcej → „Sprawdź ładowania teraz”. Komunikat pod listą ładowarek
  mówi, co jest nie tak (np. brak połączenia z HA). Ładowanie pojawia się 15 minut po końcu.
- **Spalanie „–”**: potrzebne są dwa tankowania do pełna z przebiegiem.
- **Prąd „–” przy PHEV**: pierwszy pełny bak zatankowany po 1.11.2026 jeszcze się nie skończył.
- **Dane**: dodatek nic nie wysyła poza Home Assistant. Dane zostają w HA i w kopiach.
