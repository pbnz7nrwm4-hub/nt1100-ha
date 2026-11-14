# Pojazdy

Tankowania, ładowania, koszty i terminy pojazdów w jednym panelu Home Assistant – jak aplikacja
Fuelio, ale ładowania auta z wtyczką wpisują się same.

## Zmiany w 1.7.0
- **Polisy OC/AC z ratami.** Terminy → „+ Polisa”: pojazd, zakres (OC, OC + AC, AC…), od–do, składka, liczba rat
  (raty rozkładają się same co 12/n miesięcy, daty i kwoty można poprawić), ubezpieczyciel, numer. Karta polisy pokazuje,
  czy jest ważna, ile rat zapłacono, ile zostało do zapłaty i kiedy następna rata.
- **Zapłacona rata = koszt.** Odhaczenie raty zapisuje koszt „Ubezpieczenie” w Historii (z datą zapłaty); cofnięcie go usuwa.
  Kliknięcie takiego kosztu w Historii otwiera polisę.
- **Przypomnienia (telefon i Telegram):** o racie 14, 7 i 1 dzień przed, w dniu terminu i co 3 dni po terminie, aż ją
  odhaczysz; o końcu ważności 30, 14 i 1 dzień przed oraz w dniu końca. Treść mówi, czy OC wznowi się samo (wszystkie raty
  zapłacone i bez wypowiedzenia) i do kiedy można wypowiedzieć (dzień przed końcem).
- **Start:** przy każdym pojeździe „OC do …” i „raty 2/2”; rata albo koniec ważności w ciągu 30 dni (lub rata po terminie)
  trafia na górę jako ostrzeżenie. Pojazd bez polisy ma „brak polisy · dodaj”.
- **„Zmieniam ubezpieczyciela”** zaznacza, że polisa się nie wznowi (przypomnienie: kup nową), **„Odnów”** tworzy polisę
  na kolejny rok (od dnia po końcu, te same raty – kwoty do poprawy).
- **Stary termin raty** (kategoria Ubezpieczenie albo w nazwie polisa/OC/AC) ma w „Zrobione” przycisk „Zamień na polisę”;
  po zapisaniu polisy termin znika.
- **Czujnik** `sensor.pojazdy_<pojazd>_polisa`: stan = dni do końca ważnej polisy, atrybuty: do kiedy, opis, czy opłacona,
  lista polis z ratami (np. „1/2”), do zapłaty, następna rata.
- Zasady z poradników (rankomat.pl, 2026): niezapłacona rata OC nie kończy ochrony (art. 12 ust. 2 ustawy o ubezpieczeniach
  obowiązkowych), ale grożą odsetki i windykacja; AC po wezwaniu może zostać rozwiązane – zależy od umowy.

## Zmiany w 1.6.0
- **Telegram.** W Więcej → Powiadomienia wpisz numer czatu Telegram (zostaje tylko w bazie dodatku, nie w repozytorium). Przypomnienia o terminach idą wtedy także na Telegram (usługa `telegram_bot.send_message` w HA), obok telefonu.
- **Kotwica przebiegu dla NT1100 Jazdy.** Czujnik `sensor.pojazdy_nt1100_przebieg` ma atrybuty `odczyt_reczny_km` i `odczyt_reczny_data` (ostatni odczyt z tankowania, kosztu albo ręczny, bez telemetrii). NT1100 Jazdy liczy od nich przebieg i dolicza własne jazdy.
- **kWh/100 km z liczników ładowarek (na sucho).** Obok obecnej metody (z baków) pod kartą PHEV i w czujniku `..._zuzycie_pradu_licznik`: kWh z liczników od dnia, w którym HA zaczął je mierzyć, podzielone przez przejechane km. Bez korekty o stan baterii i bez czekania na tankowania; zamiana metody dopiero po porównaniu.

## Zmiany w 1.5.1
- Ładowania z liczników: koniec zdublowanych sesji (ta sama sesja zapisywała się kilka razy z różnym początkiem). Początek sesji liczony od przyrostu, nie od brzegu okna historii; sesja kończy się dopiero po 20 min ciszy; nowa sesja nie zapisze się, jeśli zachodzi na już zapisaną. Stare dublety scalisz przyciskiem „Scal zdublowane ładowania” w Więcej (zostaje wpis z największą energią, przed scaleniem powstaje kopia bazy w /share/pojazdy/kopie).

## Zmiany w 1.5.0
- Historia: tankowania i ładowania z jednego dnia (tego samego pojazdu) są w jednym wierszu z sumą (kWh lub l, zł); kliknięcie rozwija pojedyncze wpisy. Wyłączysz to w Więcej → „Grupuj tankowania i ładowania po dniach”.

## Zmiany w 1.4.0

- **Tankowanie ze zdjęcia dystrybutora (Telegram).** Dodatek ma dwa wywołania dla Home Assistant:
  `POST api/telegram/propozycja` (nic nie zapisuje: składa litry/cenę/kwotę, bierze przebieg z telemetrii,
  ostrzega o niezgodnej kwocie, litrach ponad bak, odległej cenie, przebiegu wstecz) i `POST api/telegram/zapisz`
  (dopisuje wpis ze źródłem „telegram”; ten sam `uid` nie zapisze się dwa razy). Wywołuje je tylko rdzeń HA.
  Sam bot i odczyt zdjęcia przez Maca – osobno, na sucho.

## Zmiany w 1.3.0

- **Zużycie prądu jako zakres.** Przy odcinkach z korektą o baterię panel pokazuje np. „9–12 kWh/100 km”: dolna i górna
  wartość to wynik bez korekty i z korektą przy pojemności brutto. Prawda leży pomiędzy (pojemność użyteczna jest mniejsza
  od brutto, a prąd z silnika i hamowania nie pochodzi z gniazdka). Gdy różnica jest mniejsza niż 0,5, pokazuje się jedna liczba.
- **Pojemność z pomiaru (na sucho).** W statystykach pojawia się „Z gniazdka na 100 % baterii”: kWh z gniazdka na 100 %
  wskaźnika, liczone z ładowań z zapisanym procentem przed i po (przyrost co najmniej 10 punktów, bez wpisów z ekranu auta).
  Obok wartość z ustawień (pojemność ÷ sprawność). Do obliczeń na razie wchodzi ustawienie; po kilku sesjach porównamy i zdecydujemy.

## Zmiany w 1.2.0

- **Prąd w odcinku poprawiany o stan baterii.** Zużycie prądu liczy się od pełnego do pełnego baku. Jeśli
  bak zaczęto z pełną baterią, a skończono z pustą, samo ładowanie z gniazdka zaniżałoby zużycie (i odwrotnie).
  Dodatek zapisuje przy tankowaniu stan baterii (%) – sam, z historii HA (`sensor.eclipse_bateria`), albo
  wpisany ręcznie w polu „Bateria w chwili tankowania”. Gdy oba tankowania odcinka go mają, kWh zmniejsza się
  o przyrost energii w baterii (÷ 88 % sprawności ładowania), a przy spadku zwiększa. Takie odcinki mają
  znaczek „skorygowano o stan baterii”.
- Dla tankowań z Fuelio (sama data) przyjmowane jest południe; przy większej różnicy popraw godzinę lub
  wpisz % ręcznie. Działa od 1.11.2026 (wcześniej HA nie zapisywał procentu).
- Uwaga: gdy silnik doładował baterię w czasie jazdy, jej przyrost nie pochodzi z gniazdka – taki odcinek
  wychodzi z prądem lekko zaniżonym (benzyna tego doładowania jest już w litrach).

## Zmiany w 1.1.0

- **Ładowania z ekranu auta**: historię z ekranu Mitsubishi (Poziom ładowania → historia długo-
  i krótkoterminowa) można wczytać plikiem CSV w „Import z Fuelio”. Kolumny: `od,do,kwh_bateria,notatka`
  (daty RRRR-MM-DD, `do` włącznie; jeden wiersz = dzień albo cały miesiąc). Podgląd pokazuje sumę i od kiedy
  będzie liczone zużycie prądu.
- Auto pokazuje energię **do baterii**; dodatek przelicza ją na energię z gniazdka (÷ 88 %, straty ładowania),
  żeby była porównywalna z ładowaniami z HA. Koszt szacunkowy wg bieżącej „Wartości kWh”.
- Wpis za cały miesiąc dzieli się na baki proporcjonalnie do dni, więc kWh/100 km liczy się też dla starszych
  tankowań. Po imporcie „prąd liczony od” przesuwa się na pierwszy dzień z pliku.
- W historii takie wpisy mają znaczek „z auta · szacunek”; sprawność ładowania liczy się tylko z pomiarów HA.

## Zmiany w 1.0.2

- Edycja tankowania z importu Fuelio: pole daty pokazuje datę (wcześniej było puste), a kwoty są
  zaokrąglone (np. 187,08 zamiast 187,07999999999998). Kwoty już zaimportowane zaokrąglają się same
  przy starcie dodatku.
- Zapis edycji z pustym polem daty zostawia dotychczasową datę (wcześniej wpisywał bieżącą chwilę).

## Zmiany w 1.0.1

- Dodatek szuka klucza do Home Assistant także tam, gdzie zostawia go system startowy kontenera
  (w 1.0.0 u części instalacji ładowania się nie wczytywały: „brak połączenia z Home Assistant”).
- Pod „Ładowania automatycznie” jest teraz dokładny powód, gdy coś nie działa; w dzienniku dodatku
  przy starcie wpis „klucz do HA: jest / BRAK”.

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
- **Polisy OC/AC** z ratami (okres ważności, co zapłacone, następna rata, przypomnienia) – zob. „Zmiany w 1.7.0”.
- **Inne koszty** (serwis, przegląd, opony…) i **terminy** z przypomnieniem w telefonie:
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
`sensor.pojazdy_<pojazd>_spalanie`, `_koszt_100km`, `_koszt_miesiac`, `_przebieg`, `_terminy`, `_polisa`
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
