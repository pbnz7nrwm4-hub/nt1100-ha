# Instalacja od zera

Kolejność ma znaczenie: najpierw dodatek (daje klucz), potem skrzynka i ekran, na końcu
silnik tras (bez niego działa wszystko poza liczeniem tras i mapą).

## 1. Dodatek w Home Assistant

1. Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → **Repozytoria** → dodaj
   `https://github.com/pbnz7nrwm4-hub/nt1100-ha` → Zamknij.
2. Na liście znajdź **NT1100 Jazdy** → Zainstaluj → włącz „Pokaż na pasku bocznym” → Uruchom.
3. Otwórz panel **NT1100 Jazdy** → Ustawienia → **Połączenie ze skrzynką**. Są tam trzy
   rzeczy do przepisania w skrzynce i ekranie: adres w domu, adres spoza domu, klucz.
4. (Zalecane) Dodatek **Mosquitto** w Home Assistant: wtedy powstaje urządzenie NT1100 z encjami.
5. Ustawienia → **Powiadomienie po jeździe**: wybierz swój telefon.

Adres spoza domu działa tylko, gdy port 8098 jest wystawiony przez Cloudflare (tunel)
na Twojej domenie. Bez niego skrzynka wysyła jazdy tylko z domowego Wi-Fi.

## 2. Skrzynka

1. Pierwsze wgranie oprogramowania (tylko raz, kablem) – zrobione przy montażu.
   Później skrzynka aktualizuje się sama z dodatku w domowym Wi-Fi.
2. Na telefonie połącz się z siecią Wi-Fi **NT1100** (hasło pokazuje ekran skrzynki),
   otwórz `http://192.168.4.1`.
3. Ustawienia → **Sieć skrzynki „NT1100”**: ustaw własne hasło (fabryczne jest oznaczone na czerwono).
4. Ustawienia → **Wi-Fi domowe** i **Hotspot telefonu**.
5. Ustawienia → **Wysyłka do Home Assistant**: adres w domu, adres spoza domu i klucz z dodatku.
6. Montaż: skrzynka na rzepie, przewód do gniazda diagnostycznego tylko na liniach CAN
   (skrzynka **tylko słucha**, nic nie wysyła do motocykla); zasilanie z gniazda,
   które gaśnie z zapłonem.

## 3. Ekran nawigacji (5")

1. Pierwsze wgranie – raz, kablem USB-C (obraz pełny ze źródłami). Później z dodatku:
   na postoju zakładka **Menu** → Sprawdź wersję → Aktualizuj (w domowym Wi-Fi).
2. Ekran bez ustawień otwiera sieć **NT1100-Ekran** (hasło pokazuje ekran); połącz się i otwórz
   `http://192.168.4.1`.
3. Wpisz Wi-Fi domowe, hotspot telefonu, adres dodatku w domu, adres spoza domu i klucz.
4. Mapa na kartę: panel dodatku → Motocykl → **Ekran i mapa** → paczka ZIP → rozpakuj na kartę
   ekranu (folder `mapa`). Dalej ekran dociąga zmiany sam.
5. Telefon: iPhone → Ustawienia → Bluetooth → „NT1100 Ekran 5” → zezwól na powiadomienia.
6. Brama i garaż (opcjonalnie): panel → Ustawienia → Planowanie i dom → pola „Brama” i „Garaż”.
7. Ekran ma własny GPS. Skrzynka (od 1.4.4) dosyła mu przez Bluetooth dane z motocykla, bez parowania.

Ekran 2,8" (poprzedni) ustawia się tak samo, ale aktualizację otwiera przytrzymanie ekranu → Menu,
a w Bluetooth nazywa się „NT1100 Ekran”.

## 4. Silnik tras (kontener w Proxmoxie)

Instrukcja: `silnik-tras/README.md`. Po instalacji w panelu dodatku:
Ustawienia → **Ustawienia nawigacji** → adres silnika `http://IP-KONTENERA:8989` i mapy
`http://IP-KONTENERA:8988`, potem Motocykl → Ekran i mapa → „Pobierz mapę z kontenera”.

## 5. Sprawdzenie, że wszystko się widzi

Panel → **Motocykl** → karta „Wersje oprogramowania”: dodatek, skrzynka, ekran i silnik tras
powinny mieć zieloną kropkę. Żółta = jest nowsza wersja albo urządzenie dawno się nie odezwało.
