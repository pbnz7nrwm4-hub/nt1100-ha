#!/usr/bin/env python3
"""Stacja ekranu nawigacji – strona w sieci domowej, ekran podłączony kablem USB do serwera (kontener „aplikacje”).

Fala 1 (kabel): Wgraj (najnowszą albo wybraną wersję, tylko przy zgodnej sumie), Ratuj ekran (czeka na port do 90 s),
Nagrywaj demo (od pierwszej sekundy, także w trakcie wgrywania), Dzienniki z podsumowaniem, Historia.
Budowy: gałąź z wynikami prywatnego repo firmware, pobierane kluczem tylko do odczytu (plik poza repo), archiwum
wersji w katalogu stacji (gałąź z wynikami trzyma tylko ostatnią budowę, a „Wgraj poprzednią” potrzebuje starszych).
Tylko biblioteka standardowa; port szeregowy przez termios; wgrywanie przez esptool.
Uruchom: python3 stacja.py [--port-www 8990]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import select
import subprocess
import sys
import termios
import threading
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WERSJA = "1.0.7"
KAT = os.path.expanduser(os.environ.get("STACJA_KATALOG", "/var/lib/stacja"))
BUDOWY = os.path.join(KAT, "budowy")
DZIENNIKI = os.path.join(KAT, "dzienniki")
AKT_JEDNOSTKA = os.environ.get("STACJA_AKT_JEDNOSTKA", "/etc/systemd/system/stacja-aktualizacja.path")
HISTORIA = os.path.join(KAT, "historia.jsonl")
ESPTOOL = os.environ.get("STACJA_ESPTOOL", sys.executable + " -m esptool").split()
# Najpierw stała nazwa z /dev/serial/by-id (gdy jest), potem zwykły port USB CDC.
PRZED = os.environ.get("STACJA_PRZED", "usb-reset")  # sposób wejścia w tryb pobierania (esptool --before)
WZORY_PORTU = os.environ.get("STACJA_PORT", "/dev/stacja/ttyACM*:/dev/serial/by-id/*:/dev/ttyACM*").split(":")
REPO = os.environ.get("STACJA_REPO", "pbnz7nrwm4-hub/nt1100-firmware")
GALAZ = os.environ.get("STACJA_GALAZ", "wyniki")
PLIK_KLUCZA = os.environ.get("STACJA_KLUCZ", "/etc/stacja/github_token")
API = os.environ.get("STACJA_API", "https://api.github.com")
CO_ILE_S = int(os.environ.get("STACJA_SPRAWDZAJ_S", "300"))
WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
WZOR_BIN = re.compile(r"^nt1100-ekran5-(\d+(?:\.\d+)+)-app-0x10000\.bin$")

STAN = {"zadanie": None, "komunikat": "Gotowa.", "nagrywa": None, "log": [], "sprawdzono": None, "blad_budow": ""}
BLOKADA = threading.Lock()


def teraz():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def wpis_historii(**kw):
    os.makedirs(KAT, exist_ok=True)
    with open(HISTORIA, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict({"ts": teraz()}, **kw), ensure_ascii=False) + "\n")


def historia(n=40):
    try:
        with open(HISTORIA, encoding="utf-8") as f:
            w = [json.loads(x) for x in f if x.strip()]
    except OSError:
        return []
    return list(reversed(w))[:n]


def komunikat(t):
    STAN["komunikat"] = t
    STAN["log"] = (STAN["log"] + [time.strftime("%H:%M:%S ") + t])[-40:]


def wersja_klucz(v):
    return tuple(int(x) for x in v.split("."))


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- budowy (archiwum wersji)

def czytaj_sumy(tekst):
    out = {}
    for linia in tekst.splitlines():
        c = linia.split()
        if len(c) >= 2 and re.fullmatch(r"[0-9a-f]{64}", c[0]):
            out[os.path.basename(c[-1].lstrip("*"))] = c[0]
    return out


def czytaj_wynik(tekst):
    out = {}
    for linia in tekst.splitlines():
        m = re.match(r"^(wersja|commit|wynik|czas)\s+(.+)$", linia.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def budowy():
    """Wersje w archiwum, od najnowszej: [{"wersja", "plik", "suma", "wynik", "czas", "commit"}]."""
    out = []
    for d in glob.glob(os.path.join(BUDOWY, "*")):
        try:
            with open(os.path.join(d, "budowa.json"), encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            continue
        p = os.path.join(d, b.get("plik", ""))
        if os.path.exists(p) and re.fullmatch(r"\d+(?:\.\d+)+", b.get("wersja", "")):
            out.append(dict(b, sciezka=p))
    out.sort(key=lambda b: wersja_klucz(b["wersja"]), reverse=True)
    return out


def klucz():
    try:
        with open(PLIK_KLUCZA, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def gh(path, surowe=False, limit=64 << 20):
    k = klucz()
    if not k:
        raise RuntimeError("brak klucza do repozytorium budów (plik %s)" % PLIK_KLUCZA)
    r = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + k, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "stacja-ekranu",
        "Accept": "application/vnd.github.raw" if surowe else "application/vnd.github+json"})
    with urllib.request.urlopen(r, timeout=120) as f:
        d = f.read(limit + 1)
    if len(d) > limit:
        raise RuntimeError("plik za duży")
    return d if surowe else json.loads(d)


def sprawdz_budowy():
    """Pobiera nową budowę z gałęzi wyników, gdy jej jeszcze nie ma w archiwum. Zwraca wersję nowej albo None."""
    STAN["sprawdzono"] = teraz()
    try:
        pliki = {x["name"]: x for x in gh("/repos/%s/contents/?ref=%s" % (REPO, GALAZ)) if x.get("type") == "file"}
        sumy = czytaj_sumy(gh("/repos/%s/contents/SHA256SUMS?ref=%s" % (REPO, GALAZ), True).decode("utf-8", "replace"))
        wynik = {}
        if "WYNIK.txt" in pliki:
            wynik = czytaj_wynik(gh("/repos/%s/contents/WYNIK.txt?ref=%s" % (REPO, GALAZ), True).decode("utf-8", "replace"))
        nowa = None
        for nazwa in pliki:
            m = WZOR_BIN.match(nazwa)
            if not m:
                continue
            v = m.group(1)
            d = os.path.join(BUDOWY, v)
            if os.path.exists(os.path.join(d, "budowa.json")):
                continue
            if nazwa not in sumy:
                raise RuntimeError("budowa %s bez sumy w SHA256SUMS – pomijam" % v)
            dane = gh("/repos/%s/contents/%s?ref=%s" % (REPO, nazwa, GALAZ), True)
            if hashlib.sha256(dane).hexdigest() != sumy[nazwa]:
                raise RuntimeError("budowa %s: pobrany plik ma inną sumę niż SHA256SUMS – pomijam" % v)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, nazwa), "wb") as f:
                f.write(dane)
            b = {"wersja": v, "plik": nazwa, "suma": sumy[nazwa], "pobrano": teraz(),
                 "wynik": wynik.get("wynik") if wynik.get("wersja") == v else None,
                 "czas": wynik.get("czas") if wynik.get("wersja") == v else None,
                 "commit": (wynik.get("commit") or "")[:7] if wynik.get("wersja") == v else None}
            with open(os.path.join(d, "budowa.json"), "w", encoding="utf-8") as f:
                json.dump(b, f, ensure_ascii=False)
            wpis_historii(co="budowa", wersja=v, wynik=b["wynik"], commit=b["commit"])
            komunikat("Nowa budowa ekranu %s pobrana (suma zgodna)." % v)
            nowa = v
        STAN["blad_budow"] = ""
        return nowa
    except urllib.error.HTTPError as e:
        STAN["blad_budow"] = ("klucz nie ma dostępu do repozytorium budów (HTTP %d) – sprawdź klucz" % e.code
                              if e.code in (401, 403, 404) else "GitHub: HTTP %d" % e.code)
    except Exception as e:
        STAN["blad_budow"] = str(e)
    return None


def petla_budow():
    while True:
        if not STAN["zadanie"]:
            sprawdz_budowy()
        time.sleep(CO_ILE_S)


# ---------------------------------------------------------------- port

def obecny(p):
    """Czy za węzłem jest teraz urządzenie. Kontener dostaje stałe węzły ttyACM0–3 (166:n) – po resecie ekran
    może dostać inny numer, więc o obecności decyduje /sys/class/tty (bez otwierania portu, które resetuje ekran)."""
    try:
        rdev = os.stat(p).st_rdev
    except OSError:
        return False
    if os.major(rdev) != 166 or not os.path.isdir("/sys/class/tty"):
        return True
    return os.path.exists("/sys/class/tty/ttyACM%d" % os.minor(rdev))


def znajdz_port(czekaj_s=0):
    koniec = time.time() + czekaj_s
    while True:
        for w in WZORY_PORTU:
            porty = sorted(p for p in glob.glob(w) if os.path.exists(p) and obecny(p))
            if porty:
                return porty[0]
        if time.time() >= koniec:
            return None
        time.sleep(0.5)


def otworz_port(port, zapis=False):
    fd = os.open(port, (os.O_RDWR if zapis else os.O_RDONLY) | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        a = termios.tcgetattr(fd)
        a[0] = 0
        a[1] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[3] = 0
        a[4] = a[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, a)
    except termios.error:
        pass  # pty w testach
    return fd


class Nagranie(threading.Thread):
    def __init__(self, wersja):
        super().__init__(daemon=True)
        self.stop = False
        self.wersja = wersja
        self.start_ts = time.time()
        os.makedirs(DZIENNIKI, exist_ok=True)
        self.plik = os.path.join(DZIENNIKI, "demo-%s-%s.txt" % (wersja, time.strftime("%Y%m%d-%H%M%S")))
        self.bajty = 0

    def run(self):
        with open(self.plik, "ab") as out:
            out.write(("# Stacja: nagranie %s, wersja %s\n" % (teraz(), self.wersja)).encode())
            fd = None
            while not self.stop:
                if fd is None:
                    p = znajdz_port(0)
                    if not p or STAN["zadanie"] == "wgrywanie":  # port znika przy restarcie; esptool ma wyłączny dostęp
                        time.sleep(0.3)
                        continue
                    try:
                        fd = otworz_port(p)
                        out.write(("\n# [port %s otwarty %s]\n" % (p, time.strftime("%H:%M:%S"))).encode())
                    except OSError:
                        time.sleep(0.5)
                        continue
                try:
                    r, _, _ = select.select([fd], [], [], 0.3)
                    if r:
                        d = os.read(fd, 4096)
                        if not d:
                            raise OSError("koniec")
                        out.write(d)
                        out.flush()
                        self.bajty += len(d)
                    if STAN["zadanie"] == "wgrywanie":
                        raise OSError("wgrywanie")
                except OSError:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    fd = None
                    out.write(("\n# [port zamknięty %s]\n" % time.strftime("%H:%M:%S")).encode())
            if fd is not None:
                os.close(fd)


def pobierz_karte():
    """1.0.6: polecenie DZIENNIK na porcie ekranu (firmware 2.17.0+) – ekran wypisuje końcówki dzienników z karty
    (awarie, funkcje, pamięć). Zapis jako dziennik „demo-karta-…”, widoczny na liście z „Pokaż Claude”.
    Nie w trakcie nagrywania ani wgrywania (port ma wtedy inny właściciel)."""
    if STAN["nagrywa"] or STAN["zadanie"]:
        komunikat("Najpierw zatrzymaj nagrywanie albo poczekaj na koniec wgrywania.")
        return False
    p = znajdz_port(0)
    if not p:
        komunikat("Nie widzę ekranu na USB.")
        return False
    try:
        fd = otworz_port(p, True)
    except OSError as e:
        komunikat("Nie mogę otworzyć portu ekranu: %s" % e)
        return False
    dane = b""
    try:
        os.write(fd, b"\nDZIENNIK\n")
        koniec = time.time() + 20
        while time.time() < koniec and b"=== KARTA KONIEC ===" not in dane:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                d = os.read(fd, 4096)
                if not d:
                    break
                dane += d
    except OSError:
        pass
    finally:
        os.close(fd)
    i = dane.find(b"=== KARTA POCZATEK ===")
    if i < 0:
        komunikat("Ekran nie odpowiedział (potrzebna wersja 2.17.0 lub nowsza).")
        return False
    os.makedirs(DZIENNIKI, exist_ok=True)
    plik = os.path.join(DZIENNIKI, "demo-karta-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
    with open(plik, "wb") as f:
        f.write(("# Stacja: nagranie %s, wersja karta\n" % teraz()).encode())
        f.write(dane[i:])
    wpis_historii(co="karta", plik=os.path.basename(plik), bajty=len(dane) - i)
    komunikat("Odczytano dzienniki z karty (%d KB): %s" % ((len(dane) - i) // 1024, os.path.basename(plik)))
    return True


def nagrywaj_start(wersja=None):
    if STAN["nagrywa"]:
        return
    n = Nagranie(wersja or ostatnio_wgrana() or "nieznana")
    STAN["nagrywa"] = n
    n.start()
    komunikat("Nagrywam dziennik: %s" % os.path.basename(n.plik))


def nagrywaj_stop():
    n = STAN["nagrywa"]
    if not n:
        return
    n.stop = True
    n.join(5)
    STAN["nagrywa"] = None
    p = podsumowanie(n.plik)
    wpis_historii(co="nagranie", plik=os.path.basename(n.plik), bajty=n.bajty, wersja=p["wersja"],
                  minut=p["minut"], restarty=p["restarty"], awarie=p["awarie"])
    komunikat("Zapisano dziennik (%d min, restartów %d, awarii %d)." % (p["minut"] or 0, p["restarty"], p["awarie"]))


def ostatnio_wgrana():
    for d in historia(500):
        if d.get("co") == "wgranie" and d.get("wynik") == "ok":
            return d.get("wersja")
    return None


# ---------------------------------------------------------------- wgrywanie

def wgraj(wersja=None, ratunek=False):
    lst = budowy()
    if not lst:
        komunikat("Brak pobranej budowy ekranu. Sprawdź klucz do repozytorium budów.")
        return False
    if wersja:
        b = next((x for x in lst if x["wersja"] == wersja), None)
        if not b:
            komunikat("Nie ma budowy %s w archiwum." % wersja)
            return False
    elif ratunek and ostatnio_wgrana() and any(x["wersja"] == ostatnio_wgrana() for x in lst):
        b = next(x for x in lst if x["wersja"] == ostatnio_wgrana())  # ostatnia dobrze wgrana
    else:
        b = lst[0]
    v, p = b["wersja"], b["sciezka"]
    s = sha256(p)
    if s != b.get("suma"):
        komunikat("Ekran %s: suma NIE zgadza się z budową – nie wgrywam." % v)
        wpis_historii(co="wgranie", wersja=v, wynik="zla suma")
        return False
    if ratunek:
        komunikat("Ratowanie: przytrzymaj RESET ok. 2 s, aż zielona dioda zacznie szybko migać. Czekam na port do 90 s…")
    port = znajdz_port(90 if ratunek else 3)
    if not port:
        komunikat("Nie widzę ekranu na USB. Podłącz kabel USB-C (albo użyj „Ratuj ekran”).")
        return False
    STAN["zadanie"] = "wgrywanie"  # trwające nagranie zamyka port (esptool potrzebuje go na wyłączność)
    komunikat("Wgrywam ekran %s na %s – nie odłączaj kabla…" % (v, port))
    time.sleep(0.8)
    t0 = time.time()
    try:
        # Tab5 (ESP32-P4) łączy się przez wbudowany USB-Serial/JTAG. esptool wybiera właściwy reset („usb-reset”) tylko,
        # gdy rozpozna VID/PID portu – a stałego węzła /dev/stacja/ttyACMn pyserial nie rozpoznaje, więc esptool brał
        # zwykły reset DTR/RTS i chip nie wchodził w tryb pobierania („Wrong boot mode 0x20c”, 16.11). Dlatego wprost:
        r = subprocess.run(ESPTOOL + ["--chip", "esp32p4", "-p", port, "--before", PRZED, "--no-stub",
                                      "write-flash", "0x10000", p],
                           capture_output=True, text=True, timeout=600)
        out = r.stdout + r.stderr
        kod = r.returncode
    except Exception as e:
        out, kod = str(e), -1
    STAN["zadanie"] = None
    # nagranie startuje dopiero teraz: otwarcie portu przed esptool resetowało ekran, a port trzymany w czasie resetu
    # sprawiał, że ekran wracał pod innym numerem (ttyACM1) i esptool nie znajdował ttyACM0
    nagrywaj_start(v)
    sprawdzone = "Hash of data verified" in out
    ok = kod == 0 and (sprawdzone or "Hard resetting" in out)
    if not ok:
        with open(os.path.join(KAT, "wgrywanie-blad-%s.txt" % time.strftime("%Y%m%d-%H%M%S")), "w", encoding="utf-8") as f:
            f.write(out)
    wpis_historii(co="wgranie", wersja=v, suma=s[:12], port=port, wynik="ok" if ok else "blad", sprawdzone=sprawdzone,
                  sekund=round(time.time() - t0), ratunek=ratunek)
    komunikat(("WGRANE: ekran %s%s. Dziennik nagrywa się dalej." % (v, " (zapis sprawdzony)" if sprawdzone else "")) if ok
              else "WGRANIE NIE WYSZŁO – zapis błędu w katalogu stacji; użyj „Ratuj ekran”.")
    return ok


def w_tle(f, *a):
    if not BLOKADA.acquire(blocking=False):
        komunikat("Trwa inne zadanie – poczekaj.")
        return False

    def run():
        try:
            f(*a)
        except Exception as e:
            traceback.print_exc()
            komunikat("Błąd: %s" % e)
        finally:
            BLOKADA.release()
    threading.Thread(target=run, daemon=True).start()
    return True


# ---------------------------------------------------------------- dzienniki

RE_WERSJA = re.compile(r"NT1100 Ekran (\d+(?:\.\d+)+)")
RE_PAMIEC = re.compile(r"pamiec (\d+) s: ram \d+ KB blok \d+ KB min (\d+) KB, psram \d+ KB, klatki (\d+)")
RE_START = re.compile(r"^ESP-ROM:", re.M)  # jeden start = jeden baner ROM (linia rst:0x to jego część)
RE_AWARIA = re.compile(r"Guru Meditation|abort\(\)|task_wdt|assert failed")


def podsumowanie(p):
    """Wersja, czas, restarty (starty po pierwszym), awarie, klatki/min (z linii „pamiec … klatki N” co 10 s), RAM min."""
    with open(p, "rb") as f:
        t = f.read().decode("utf-8", "replace")
    wer = RE_WERSJA.findall(t)
    pam = RE_PAMIEC.findall(t)
    starty = len(RE_START.findall(t))
    # pierwsze 10 s po starcie to niepełny odcinek (ekran dopiero rysuje pierwszą klatkę) – nie liczy się do klatek/min
    kl = [int(k) * 6 for sek, _, k in pam if int(k) > 0 and int(sek) > 10]
    minuty = None
    m = re.search(r"# Stacja: nagranie (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", t)
    st = os.stat(p)
    if m:
        try:
            minuty = max(0, round((st.st_mtime - time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))) / 60))
        except (ValueError, OverflowError):
            pass
    return {"plik": os.path.basename(p), "kb": round(st.st_size / 1024, 1), "wersja": wer[-1] if wer else None,
            "starty": starty, "restarty": max(0, starty - 1), "awarie": len(RE_AWARIA.findall(t)), "minut": minuty,
            "klatki_min": [min(kl), max(kl)] if kl else None, "ram_min_kb": min(int(x) for _, x, _ in pam) if pam else None,
            "kiedy": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}


def dzienniki(n=30):
    out = []
    for p in sorted(glob.glob(os.path.join(DZIENNIKI, "demo-*.txt")), key=os.path.getmtime, reverse=True)[:n]:
        try:
            out.append(podsumowanie(p))
        except OSError:
            pass
    return out


SZUM = ("wydajnosc: etapy", "wydajnosc: tekst", "uklad:", "poziomo:", "w-tle:", "funkcje-290", "telefon-id: co minute: adres")
MAX_ZNAKOW = 9000  # tekst „Pokaż Claude” mieści się w jednej wiadomości czatu


def blad_wgrania():
    """Końcówka zapisu esptool z ostatniego wgrania, jeśli nie wyszło (do pokazania i skopiowania)."""
    ost = next((h for h in historia(50) if h.get("co") == "wgranie"), None)
    if not ost or ost.get("wynik") != "blad":
        return None
    pl = sorted(glob.glob(os.path.join(KAT, "wgrywanie-blad-*.txt")), key=os.path.getmtime)
    if not pl:
        return None
    with open(pl[-1], encoding="utf-8", errors="replace", newline="") as f:
        lin = [x.split("\r")[-1] for x in f.read().split("\n") if x.strip()]  # postęp esptool nadpisuje linię przez \r
    return "Wgranie %s nie wyszło (%s, port %s). Ostatnie linie esptool:\n%s" % (
        ost.get("wersja"), ost.get("ts", "?"), ost.get("port", "?"), "\n".join(lin[-25:]))


def dla_claude(nazwa, linii=80):
    """Krótki tekst do wklejenia w czacie: podsumowanie + błędy + ostatnie linie."""
    p = os.path.join(DZIENNIKI, nazwa)
    if nazwa.startswith("demo-karta-"):   # odczyt z karty: najpierw awarie (ogon), potem końcówka reszty
        with open(p, "rb") as f:
            t = f.read().decode("utf-8", "replace")
        czesci = re.split(r"(?m)^(?==== plik )", t)
        awarie = next((c for c in czesci if c.startswith("=== plik awarie.txt")), "")
        reszta = "".join(c for c in czesci if c.startswith("=== plik ") and c is not awarie)
        a = awarie[:1] + awarie[1:][-5000:] if len(awarie) > 5000 else awarie
        return (a + "\n" + reszta[-(MAX_ZNAKOW - len(a) - 2):])[-MAX_ZNAKOW:]
    s = podsumowanie(p)
    with open(p, "rb") as f:
        lin = f.read().decode("utf-8", "replace").splitlines()
    bledy = [x for x in lin if RE_AWARIA.search(x) or RE_START.search(x) or "BLAD" in x or "błąd" in x.lower()][:40]
    gl = ("Dziennik demo %s: wersja %s, %s min, restarty %d, awarie %d, klatki/min %s, RAM min %s KB."
          % (s["kiedy"], s["wersja"] or "?", s["minut"] if s["minut"] is not None else "?", s["restarty"], s["awarie"],
             "%d–%d" % tuple(s["klatki_min"]) if s["klatki_min"] else "?", s["ram_min_kb"] if s["ram_min_kb"] is not None else "?"))
    kon = [x for x in lin if not x.startswith(SZUM)][-linii:]
    t = "\n".join([gl, "", "Starty i błędy:"] + (bledy[:15] or ["(brak)"]) + ["", "Ostatnie linie (bez powtarzalnych statystyk):"])
    zostalo = MAX_ZNAKOW - len(t)
    ogon = []
    for x in reversed(kon):
        zostalo -= len(x) + 1
        if zostalo < 0:
            break
        ogon.append(x)
    return t + "\n" + "\n".join(reversed(ogon))


# ---------------------------------------------------------------- stan dla strony

def aktualizacja():
    """Kiedy aktualizator ostatnio sprawdzał repozytorium i czy przycisk „Zaktualizuj teraz” ma kto obsłużyć
    (jednostka stacja-aktualizacja.path pojawia się po instalatorze z 1.0.5)."""
    try:
        with open(os.path.join(KAT, "aktualizacja"), encoding="utf-8") as f:
            kiedy = f.read().strip()
    except OSError:
        kiedy = None
    return {"sprawdzono": kiedy, "przycisk": os.path.exists(AKT_JEDNOSTKA),
            "czeka": os.path.exists(os.path.join(KAT, "aktualizuj"))}


def stan():
    lst = budowy()
    dz = dzienniki(10)
    na_ekranie = next((d["wersja"] for d in dz if d["wersja"]), None) or ostatnio_wgrana()
    n = STAN["nagrywa"]
    wgran = sum(1 for h in historia(500) if h.get("co") == "wgranie" and h.get("wynik") == "ok")
    nagr = sum(1 for h in historia(500) if h.get("co") == "nagranie")
    return {"wersja_stacji": WERSJA, "port": znajdz_port(0), "zadanie": STAN["zadanie"], "komunikat": STAN["komunikat"],
            "log": list(reversed(STAN["log"]))[:15], "nagrywa": {"plik": os.path.basename(n.plik), "bajty": n.bajty,
                                                                  "sekund": round(time.time() - n.start_ts)} if n else None,
            "na_ekranie": na_ekranie, "budowy": [{k: v for k, v in b.items() if k != "sciezka"} for b in lst[:8]],
            "najnowsza": ({k: v for k, v in lst[0].items() if k != "sciezka"} if lst else None),
            "dzienniki": dz, "historia": historia(15), "klucz": bool(klucz()), "sprawdzono": STAN["sprawdzono"],
            "blad_budow": STAN["blad_budow"], "blad_wgrania": blad_wgrania(), "fala2": {"wgran": wgran, "nagran": nagr},
            "aktualizacja": aktualizacja()}


# ---------------------------------------------------------------- serwer

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def wyslij(self, kod, tresc, typ="application/json; charset=utf-8"):
        if not isinstance(tresc, bytes):
            tresc = json.dumps(tresc, ensure_ascii=False).encode() if "json" in typ else str(tresc).encode()
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(tresc)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(tresc)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(WWW, "index.html"), "rb") as f:
                return self.wyslij(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/stan":
            return self.wyslij(200, stan())
        m = re.match(r"^/(d|claude)/(demo-[\w.\-]+\.txt)$", path)
        if m and os.path.exists(os.path.join(DZIENNIKI, m.group(2))):
            if m.group(1) == "d":
                with open(os.path.join(DZIENNIKI, m.group(2)), "rb") as f:
                    return self.wyslij(200, f.read(), "text/plain; charset=utf-8")
            return self.wyslij(200, dla_claude(m.group(2)), "text/plain; charset=utf-8")
        return self.wyslij(404, {"blad": "nie ma"})

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        try:
            j = json.loads(self.rfile.read(min(n, 65536)) or b"{}") if n else {}
        except ValueError:
            j = {}
        if path == "/api/wgraj":
            w = j.get("wersja")
            if w and not re.fullmatch(r"\d+(?:\.\d+)+", str(w)):
                return self.wyslij(400, {"blad": "zła wersja"})
            return self.wyslij(200, {"ok": w_tle(wgraj, w or None, False)})
        if path == "/api/ratuj":
            return self.wyslij(200, {"ok": w_tle(wgraj, None, True)})
        if path == "/api/nagrywaj":
            nagrywaj_start()
            return self.wyslij(200, {"ok": True})
        if path == "/api/karta":
            return self.wyslij(200, {"ok": w_tle(pobierz_karte)})
        if path == "/api/stop":
            nagrywaj_stop()
            return self.wyslij(200, {"ok": True})
        if path == "/api/aktualizuj":
            # znacznik dla systemd (stacja-aktualizacja.path); aktualizator czeka, aż nic się nie wgrywa
            with open(os.path.join(KAT, "aktualizuj"), "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M"))
            komunikat("Sprawdzam aktualizację Stacji – jeśli jest nowa wersja, strona odświeży się sama za chwilę.")
            return self.wyslij(200, {"ok": True})
        if path == "/api/sprawdz":
            return self.wyslij(200, {"ok": w_tle(sprawdz_budowy)})
        return self.wyslij(404, {"blad": "nie ma"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-www", type=int, default=int(os.environ.get("STACJA_PORT_WWW", "8990")))
    a = ap.parse_args()
    for d in (KAT, BUDOWY, DZIENNIKI):
        os.makedirs(d, exist_ok=True)
    komunikat("Stacja uruchomiona.")
    if os.environ.get("STACJA_PETLA", "1") == "1":
        threading.Thread(target=petla_budow, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", a.port_www), H).serve_forever()


if __name__ == "__main__":
    main()
