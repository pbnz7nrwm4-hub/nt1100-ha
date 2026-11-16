#!/usr/bin/env python3
"""Zadania dzieci – aplikacja w sieci domowej (kontener „aplikacje”).

Rodzic zleca zadanie (termin, oczekiwania, punkty, sposób potwierdzenia), dziecko potwierdza (zwykle zdjęciem),
lokalne AI (opcjonalnie, serwer Ollama w domu) podpowiada ocenę, rodzic zatwierdza. Punkty, nagrody, duży cel,
zadania powtarzane (rutyny), pula zadań do wzięcia, role opiekunów osobno dla każdego dziecka.
Dane i zdjęcia zostają w domu (katalog danych). Kod bez imion i adresów – wszystko wpisuje się w aplikacji.
Tylko biblioteka standardowa.

Uruchom:  python3 zadania.py                      (serwer, port z ZD_PORT, domyślnie 8092)
          python3 zadania.py --nowy-admin "Imię"  (pierwszy dorosły z prawami administratora; wypisuje link)
          python3 zadania.py --link "Imię"        (przypomina link osoby)
          python3 zadania.py --pin-reset "Imię"   (kasuje PIN osoby i wypisuje jej link – gdy ktoś zapomni)

Logowanie: osobisty link przy pierwszym wejściu, potem imię + PIN (sesja w ciasteczku).
Spoza domu: panel w aplikacji Home Assistant przez dodatek-pośrednik (katalog zadania-dodatek): dodatek przekazuje
żądania z kluczem (ZD_KLUCZ_PLIK) i identyfikatorem użytkownika HA; konto HA łączy się z osobą raz, PIN-em.
"""
import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WERSJA = "1.7.0"
KAT = os.path.expanduser(os.environ.get("ZD_KATALOG", "/var/lib/zadania"))
BAZA = os.path.join(KAT, "zadania.db")
ZDJ = os.path.join(KAT, "zdjecia")
PORT = int(os.environ.get("ZD_PORT", "8092"))
ADRES = os.environ.get("ZD_ADRES", "").rstrip("/")          # adres strony w linkach (np. http://<ip>:8092)
HA_URL = os.environ.get("ZD_HA_URL", "").rstrip("/")
HA_TOKEN_PLIK = os.environ.get("ZD_HA_TOKEN", "/etc/zadania/ha_token")
AI_URL = os.environ.get("ZD_AI_URL", "").rstrip("/")         # Ollama (http://<mac>:11434) albo zgodny z OpenAI (…/v1)
AI_KLUCZ = os.environ.get("ZD_AI_KLUCZ", "/etc/zadania/ai_klucz")  # plik z kluczem API (tylko dla …/v1)
AI_MODEL = os.environ.get("ZD_AI_MODEL", "gemma3:12b")
AI_TIMEOUT = int(os.environ.get("ZD_AI_TIMEOUT", "240"))
LOSOWE = float(os.environ.get("ZD_LOSOWE", "0.2"))           # odsetek zadań „na zaufanie” z losowym zdjęciem
ZDJ_DNI = int(os.environ.get("ZD_ZDJECIA_DNI", "90"))         # po ilu dniach kasować zdjęcia zakończonych zadań
KLUCZ_PLIK = os.environ.get("ZD_KLUCZ_PLIK", "/etc/zadania/klucz_dodatku")
AKT_JEDNOSTKA = os.environ.get("ZD_AKT_JEDNOSTKA", "/etc/systemd/system/zadania-aktualizacja.path")
PODGLAD_MIN = 120       # po tylu minutach „Zobacz jako dziecko” wyłącza się samo
MAX_ZDJ = 8 * 1024 * 1024
PIN_PROB = 5            # tyle błędnych PIN-ów pod rząd …
PIN_BLOKADA_MIN = 15    # … blokuje logowanie tej osoby na tyle minut
SESJA_DNI = 365
WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")

WERYFIKACJE = ("zdjecie", "zeszyt", "minutnik", "zaufanie")
PORY = ("", "rano", "popoludnie", "wieczor")
KONCOWE = ("zatwierdzone", "czesciowo")
BLOKADA = threading.RLock()

SCHEMAT = """
CREATE TABLE IF NOT EXISTS osoby(id INTEGER PRIMARY KEY, imie TEXT NOT NULL, rola TEXT NOT NULL,
  admin INTEGER DEFAULT 0, kod TEXT UNIQUE NOT NULL, powiadom TEXT DEFAULT '', aktywna INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS opieka(dorosly_id INTEGER, dziecko_id INTEGER, zleca INTEGER DEFAULT 1,
  zatwierdza INTEGER DEFAULT 1, PRIMARY KEY(dorosly_id, dziecko_id));
CREATE TABLE IF NOT EXISTS szablony(id INTEGER PRIMARY KEY, dziecko_id INTEGER, tytul TEXT, opis TEXT, kroki TEXT,
  punkty INTEGER, weryfikacja TEXT, minuty INTEGER, pora TEXT, dni TEXT, godzina TEXT, zleca_id INTEGER,
  aktywny INTEGER DEFAULT 1, utworzone TEXT);
CREATE TABLE IF NOT EXISTS zadania(id INTEGER PRIMARY KEY, dziecko_id INTEGER, tytul TEXT, opis TEXT DEFAULT '',
  kroki TEXT DEFAULT '[]', termin TEXT, punkty INTEGER DEFAULT 0, weryfikacja TEXT, minuty INTEGER DEFAULT 0,
  pora TEXT DEFAULT '', pula INTEGER DEFAULT 0, zleca_id INTEGER, szablon_id INTEGER, dzien TEXT,
  stan TEXT DEFAULT 'do_zrobienia', start TEXT, wyslane TEXT, komentarz TEXT DEFAULT '', wymaga_zdjecia INTEGER DEFAULT 0,
  ocena TEXT DEFAULT '', ocena_stan TEXT DEFAULT '', slowo TEXT DEFAULT '', zatwierdzil_id INTEGER, zatwierdzone TEXT,
  przyznane INTEGER DEFAULT 0, przypomniano INTEGER DEFAULT 0, utworzone TEXT);
CREATE TABLE IF NOT EXISTS zdjecia(id INTEGER PRIMARY KEY, zadanie_id INTEGER, rodzaj TEXT, plik TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS punkty(id INTEGER PRIMARY KEY, dziecko_id INTEGER, ile INTEGER, powod TEXT,
  zadanie_id INTEGER, wymiana_id INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS nagrody(id INTEGER PRIMARY KEY, dziecko_id INTEGER, nazwa TEXT, koszt INTEGER,
  cel INTEGER DEFAULT 0, stan TEXT DEFAULT 'aktywna', zaproponowal_id INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS wymiany(id INTEGER PRIMARY KEY, nagroda_id INTEGER, dziecko_id INTEGER, koszt INTEGER,
  stan TEXT DEFAULT 'czeka', ts TEXT, decyzja_id INTEGER, decyzja_ts TEXT);
CREATE INDEX IF NOT EXISTS zad_dz ON zadania(dziecko_id, dzien);
CREATE TABLE IF NOT EXISTS sesje(token TEXT PRIMARY KEY, osoba_id INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS ustawienia(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS ha_konta(id TEXT PRIMARY KEY, nazwa TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS nauka(id INTEGER PRIMARY KEY, dziecko_id INTEGER, temat TEXT, tryb TEXT, material TEXT DEFAULT '',
  strony INTEGER DEFAULT 0, dane TEXT DEFAULT '{}', start TEXT, ruch TEXT, koniec TEXT);
CREATE TABLE IF NOT EXISTS notatki(id INTEGER PRIMARY KEY, osoba_id INTEGER, tekst TEXT, kiedy TEXT, wyslane INTEGER DEFAULT 0, ts TEXT);
"""
KOLUMNY = (("osoby", "pin_hash", "TEXT DEFAULT ''"), ("osoby", "pin_sol", "TEXT DEFAULT ''"),
           ("osoby", "ha_user", "TEXT DEFAULT ''"), ("osoby", "pin_bledy", "INTEGER DEFAULT 0"),
           ("osoby", "pin_blokada", "TEXT DEFAULT ''"), ("osoby", "rok_ur", "INTEGER DEFAULT 0"),
           ("zadania", "pomoc", "TEXT DEFAULT ''"), ("zadania", "proby", "INTEGER DEFAULT 0"),
           ("zadania", "ponaglono", "INTEGER DEFAULT 0"), ("zadania", "prosba", "TEXT DEFAULT ''"),
           ("zadania", "wlasne", "INTEGER DEFAULT 0"), ("osoby", "grosze", "INTEGER DEFAULT 0"), ("osoby", "podglad", "TEXT DEFAULT ''"))


class Blad(Exception):
    def __init__(self, kod, tekst, **dod):
        super().__init__(tekst)
        self.kod, self.tekst, self.dod = kod, tekst, dod


# ---------- czas ----------
def teraz():
    return dt.datetime.now().replace(microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def dzis():
    return teraz().date().isoformat()


def termin_ok(s):
    if not s:
        return None
    s = s.strip().replace(" ", "T")
    for f in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            t = dt.datetime.strptime(s, f)
            return iso(t if f != "%Y-%m-%d" else t.replace(hour=20))
        except ValueError:
            pass
    raise Blad(400, "Nie rozumiem terminu: " + s)


# ---------- baza ----------
def baza():
    os.makedirs(KAT, exist_ok=True)
    c = sqlite3.connect(BAZA, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


DB = None


def db():
    global DB
    if DB is None:
        DB = baza()
        DB.executescript(SCHEMAT)
        for tab, kol, typ in KOLUMNY:
            if kol not in [r[1] for r in DB.execute("PRAGMA table_info(%s)" % tab)]:
                DB.execute("ALTER TABLE %s ADD COLUMN %s %s" % (tab, kol, typ))
        konfig_zastosuj()
    return DB


def konfig_zastosuj():
    """Ustawienia zapisane w aplikacji (ekran „Ustawienia”) mają pierwszeństwo przed plikiem instalatora."""
    global AI_URL, AI_MODEL, HA_URL
    u = {w["k"]: w["v"] for w in DB.execute("SELECT k, v FROM ustawienia WHERE k IN ('cfg_ai_url','cfg_ai_model','cfg_ha_url')")}
    if "cfg_ai_url" in u:
        AI_URL = u["cfg_ai_url"]
    if u.get("cfg_ai_model"):
        AI_MODEL = u["cfg_ai_model"]
    if "cfg_ha_url" in u:
        HA_URL = u["cfg_ha_url"]


def q(sql, *a):
    return [dict(r) for r in db().execute(sql, a).fetchall()]


def q1(sql, *a):
    r = db().execute(sql, a).fetchone()
    return dict(r) if r else None


def ex(sql, *a):
    return db().execute(sql, a).lastrowid


def nowy_kod():
    return secrets.token_urlsafe(12)


def link(osoba):
    return "%s/k/%s" % (ADRES or "", osoba["kod"])


def ust(k, dom=""):
    r = q1("SELECT v FROM ustawienia WHERE k=?", k)
    return r["v"] if r else dom


def ustaw(k, v):
    ex("INSERT INTO ustawienia(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, v)


# ---------- PIN, sesje, dodatek HA ----------
def klucz_dodatku(utworz=False):
    """Klucz, którym dodatek HA podpisuje żądania. Administrator widzi go w aplikacji (Osoby) i wkleja w opcje dodatku."""
    try:
        with open(KLUCZ_PLIK, encoding="utf-8") as f:
            k = f.read().strip()
            if k:
                return k
    except OSError:
        pass
    k = ust("klucz_dodatku")
    if not k and utworz:
        k = secrets.token_urlsafe(24)
        ustaw("klucz_dodatku", k)
    return k


def skrot_pin(pin, sol):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), sol.encode(), 120000).hex()


def pin_poprawny_format(pin):
    if not re.match(r"^\d{4,6}$", str(pin or "")):
        raise Blad(400, "PIN to 4–6 cyfr.")
    return str(pin)


def ustaw_pin(oid, pin):
    sol = secrets.token_hex(8)
    ex("UPDATE osoby SET pin_hash=?, pin_sol=?, pin_bledy=0, pin_blokada='' WHERE id=?", skrot_pin(pin, sol), sol, oid)


def sprawdz_pin(o, pin):
    """Sprawdza PIN z blokadą po PIN_PROB błędach. Rzuca Blad, gdy zły albo zablokowany."""
    if not o or not o["aktywna"]:
        raise Blad(404, "Nie ma takiej osoby.")
    if not o["pin_hash"]:
        raise Blad(409, "Ta osoba nie ma jeszcze PIN-u. Otwórz jej osobisty link.", bez_pinu=True)
    if o["pin_blokada"] and o["pin_blokada"] > iso(teraz()):
        raise Blad(429, "Za dużo prób. Spróbuj o %s." % o["pin_blokada"][11:16])
    if hmac.compare_digest(skrot_pin(str(pin or ""), o["pin_sol"]), o["pin_hash"]):
        ex("UPDATE osoby SET pin_bledy=0, pin_blokada='' WHERE id=?", o["id"])
        return True
    bl = o["pin_bledy"] + 1
    blok = iso(teraz() + dt.timedelta(minutes=PIN_BLOKADA_MIN)) if bl >= PIN_PROB else ""
    ex("UPDATE osoby SET pin_bledy=?, pin_blokada=? WHERE id=?", 0 if blok else bl, blok, o["id"])
    raise Blad(403, "Zły PIN." + (" Logowanie zablokowane na %d min." % PIN_BLOKADA_MIN if blok else
                                  " Zostało prób: %d." % (PIN_PROB - bl)))


def nowa_sesja(oid):
    tok = secrets.token_urlsafe(24)
    ex("INSERT INTO sesje(token,osoba_id,ts) VALUES(?,?,?)", tok, oid, iso(teraz()))
    return tok


def usun_sesje(oid):
    ex("DELETE FROM sesje WHERE osoba_id=?", oid)


def ciastko(tok, wiek=SESJA_DNI * 86400):
    return ("Set-Cookie", "zd=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax" % (tok, wiek))


# ---------- prawa ----------
def opieka(ja, dziecko_id):
    """Prawa osoby wobec dziecka: dict(zleca, zatwierdza, widzi)."""
    if ja["rola"] == "dziecko":
        return {"widzi": ja["id"] == dziecko_id, "zleca": False, "zatwierdza": False, "dziecko": ja["id"] == dziecko_id}
    if ja["admin"]:
        r = q1("SELECT * FROM opieka WHERE dorosly_id=? AND dziecko_id=?", ja["id"], dziecko_id) or {}
        return {"widzi": True, "zleca": True, "zatwierdza": True, "dziecko": False, "opiekun": bool(r)}
    r = q1("SELECT * FROM opieka WHERE dorosly_id=? AND dziecko_id=?", ja["id"], dziecko_id)
    if not r:
        return {"widzi": False, "zleca": False, "zatwierdza": False, "dziecko": False}
    return {"widzi": True, "zleca": bool(r["zleca"]), "zatwierdza": bool(r["zatwierdza"]), "dziecko": False, "opiekun": True}


def wymagaj(ja, dziecko_id, prawo):
    if not opieka(ja, dziecko_id).get(prawo):
        raise Blad(403, "Brak uprawnień do tego dziecka.")


def moje_dzieci(ja):
    if ja["rola"] == "dziecko":
        return q("SELECT * FROM osoby WHERE id=?", ja["id"])
    if ja["admin"]:
        return q("SELECT * FROM osoby WHERE rola='dziecko' AND aktywna=1 ORDER BY imie")
    return q("SELECT o.* FROM osoby o JOIN opieka p ON p.dziecko_id=o.id WHERE p.dorosly_id=? AND o.aktywna=1 ORDER BY o.imie",
             ja["id"])


# ---------- punkty ----------
def saldo(dziecko_id):
    r = q1("SELECT COALESCE(SUM(ile),0) s FROM punkty WHERE dziecko_id=?", dziecko_id)
    return r["s"]


def zarezerwowane(dziecko_id):
    r = q1("SELECT COALESCE(SUM(koszt),0) s FROM wymiany WHERE dziecko_id=? AND stan='czeka'", dziecko_id)
    return r["s"]


def tydzien(dziecko_id):
    od = iso(teraz() - dt.timedelta(days=7))
    r = q1("SELECT COALESCE(SUM(ile),0) s FROM punkty WHERE dziecko_id=? AND ile>0 AND ts>=?", dziecko_id, od)
    return r["s"]


def seria(dziecko_id):
    """Ile dni z rzędu wszystkie zadania dnia były wysłane lub zatwierdzone. Dziś liczy się, gdy już skończone;
    dni bez zadań (do 3 pod rząd) serii nie przerywają, ale jej nie wydłużają."""
    od = (teraz().date() - dt.timedelta(days=90)).isoformat()
    dni = {}
    for z in q("SELECT dzien, stan FROM zadania WHERE dziecko_id=? AND dzien>=? AND pula=0", dziecko_id, od):
        d = dni.setdefault(z["dzien"], [0, 0])
        d[0] += 1
        d[1] += z["stan"] in KONCOWE or z["stan"] == "wyslane"
    d = teraz().date()
    k = d.isoformat()
    if not (k in dni and dni[k][0] == dni[k][1]):
        d -= dt.timedelta(days=1)
    n = pusto = 0
    while pusto <= 3:
        k = d.isoformat()
        if k in dni:
            if dni[k][0] != dni[k][1]:
                break
            n += 1
            pusto = 0
        else:
            pusto += 1
        d -= dt.timedelta(days=1)
    return n


# ---------- powiadomienia (Home Assistant) ----------
def ha_token():
    """Token HA: plik z instalatora albo przekazany przez dodatek (opcja „token_ha”) i zapisany w katalogu danych."""
    for p in (os.path.join(KAT, "ha_token"), HA_TOKEN_PLIK):   # najpierw wpisany w aplikacji albo przez dodatek
        try:
            with open(p, encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    return t
        except OSError:
            pass
    return ""


_NOTIFY = {"ts": 0.0, "lista": []}


def ha_telefony():
    """Usługi notify.mobile_app_* z Home Assistanta (lista do wyboru w Osobach); pamięć 5 min, błąd = pusta lista."""
    if time.time() - _NOTIFY["ts"] < 300:
        return _NOTIFY["lista"]
    lista = []
    tok = ha_token()
    if HA_URL and tok:
        try:
            req = urllib.request.Request(HA_URL + "/api/services", headers={"Authorization": "Bearer " + tok})
            for d in json.loads(urllib.request.urlopen(req, timeout=5).read().decode()):
                if d.get("domain") == "notify":
                    lista = sorted(k for k in (d.get("services") or {}) if k.startswith("mobile_app_"))
        except Exception as e:  # noqa: BLE001
            print("lista telefonów z HA nieudana:", e, file=sys.stderr)
    _NOTIFY["ts"], _NOTIFY["lista"] = time.time(), lista
    return lista


def powiadom(osoba, tytul, tresc, sciezka="/"):
    """Wysyła powiadomienie przez usługę notify w HA (np. mobile_app_telefon). Bez HA – tylko zapis w dzienniku."""
    usl = (osoba or {}).get("powiadom") or ""
    if not (HA_URL and usl):
        return False
    tok = ha_token()
    if not tok:
        return False
    usl = usl.replace("notify.", "")
    panel = ust("panel_ha")
    url = panel if (panel and osoba.get("ha_user")) else ((ADRES + sciezka) if ADRES else "")
    dane = {"title": tytul, "message": tresc}
    if url:
        dane["data"] = {"url": url, "clickAction": url}

    def wyslij():
        try:
            req = urllib.request.Request(HA_URL + "/api/services/notify/" + usl, data=json.dumps(dane).encode(),
                                         headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:  # noqa: BLE001 – powiadomienie nie może zatrzymać aplikacji
            print("powiadomienie nieudane:", usl, e, file=sys.stderr)
    threading.Thread(target=wyslij, daemon=True).start()
    return True


def zatwierdzajacy(dziecko_id):
    ids = [r["dorosly_id"] for r in q("SELECT dorosly_id FROM opieka WHERE dziecko_id=? AND zatwierdza=1", dziecko_id)]
    if not ids:
        ids = [r["id"] for r in q("SELECT id FROM osoby WHERE admin=1 AND aktywna=1")]
    return [o for o in (osoba(i) for i in ids) if o]


def osoba(i):
    return q1("SELECT * FROM osoby WHERE id=?", i)


# ---------- AI (Ollama albo API zgodne z OpenAI) ----------
def ai_wlaczone():
    return bool(AI_URL)


def ai_klucz():
    for p in (os.path.join(KAT, "ai_klucz"), AI_KLUCZ):   # najpierw wpisany w aplikacji
        try:
            with open(p, encoding="utf-8") as f:
                k = f.read().strip()
                if k:
                    return k
        except OSError:
            pass
    return ""


def ai_json(tekst):
    """Odpowiedź modelu → słownik; znosi ```json … ``` i tekst wokół obiektu."""
    t = (tekst or "").strip()
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            raise
        return json.loads(t[i:j + 1])


def ai_zapytaj(prompt, obrazy=(), format_json=True):
    if AI_URL.endswith("/v1"):   # llama-swap / llama.cpp / LM Studio (API zgodne z OpenAI)
        tresc = [{"type": "text", "text": prompt}]
        tresc += [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + o}} for o in obrazy]
        dane = {"model": AI_MODEL, "temperature": 0.2, "max_tokens": 1500,
                "messages": [{"role": "user", "content": tresc if obrazy else prompt}]}
        if format_json:
            dane["response_format"] = {"type": "json_object"}
        h = {"Content-Type": "application/json"}
        k = ai_klucz()
        if k:
            h["Authorization"] = "Bearer " + k
        req = urllib.request.Request(AI_URL + "/chat/completions", data=json.dumps(dane).encode(), headers=h)
        odp = json.loads(urllib.request.urlopen(req, timeout=AI_TIMEOUT).read().decode())
        tekst = ((odp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    else:                         # Ollama
        dane = {"model": AI_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
        if format_json:
            dane["format"] = "json"
        if obrazy:
            dane["images"] = list(obrazy)
        req = urllib.request.Request(AI_URL + "/api/generate", data=json.dumps(dane).encode(),
                                     headers={"Content-Type": "application/json"})
        odp = json.loads(urllib.request.urlopen(req, timeout=AI_TIMEOUT).read().decode())
        tekst = odp.get("response", "")
    return ai_json(tekst) if format_json else tekst


WERDYKTY = ("zrobione", "raczej_zrobione", "niepewne", "nie_zrobione")


def prompt_oceny(z, ile_przed):
    kroki = "; ".join(k.get("t", "") for k in json.loads(z["kroki"] or "[]"))
    if z["weryfikacja"] == "zeszyt":
        co = ("Na zdjęciu jest zeszyt albo kartka z pracą domową dziecka. Odczytaj, co jest napisane, "
              "i oceń, czy praca jest zrobiona zgodnie z poleceniem.")
    else:
        co = ("Ostatnie zdjęcie pokazuje efekt po wykonaniu zadania." +
              (" Wcześniejsze zdjęcie pokazuje stan przed." if ile_przed else ""))
    return (
        "Jesteś życzliwym pomocnikiem rodzica. Oceniasz, czy dziecko wykonało zadanie domowe. " + co + "\n"
        "Zadanie: " + z["tytul"] + "\n"
        "Czego oczekuje rodzic: " + (z["opis"] or "(brak opisu)") + "\n"
        "Kroki: " + (kroki or "(brak)") + "\n"
        "Komentarz dziecka: " + (z["komentarz"] or "(brak)") + "\n"
        "Odpowiedz wyłącznie JSON po polsku: {\"werdykt\": \"zrobione|raczej_zrobione|niepewne|nie_zrobione\", "
        "\"punkty\": [{\"ok\": true, \"tekst\": \"krótko, co widać\"}], "
        "\"dla_dziecka\": \"jedno ciepłe zdanie, co poprawić albo pochwała\"}. "
        "Oceniaj tylko to, co widać. Gdy czegoś nie widać, napisz to i daj werdykt niepewne."
    )


def normalizuj_ocene(o):
    if not isinstance(o, dict):
        raise ValueError("odpowiedź AI nie jest obiektem")
    w = str(o.get("werdykt", "niepewne")).strip().lower().replace(" ", "_")
    if w not in WERDYKTY:
        w = "niepewne"
    pk = []
    for p in (o.get("punkty") or [])[:6]:
        if isinstance(p, dict) and p.get("tekst"):
            pk.append({"ok": bool(p.get("ok")), "tekst": str(p["tekst"])[:200]})
    return {"werdykt": w, "punkty": pk, "dla_dziecka": str(o.get("dla_dziecka", ""))[:300], "model": AI_MODEL,
            "ts": iso(teraz())}


def ocen(zadanie_id):
    """Ocena zdjęć zadania w tle. Wynik w zadania.ocena (JSON), stan w ocena_stan."""
    with BLOKADA:
        z = q1("SELECT * FROM zadania WHERE id=?", zadanie_id)
        zd = q("SELECT * FROM zdjecia WHERE zadanie_id=? ORDER BY id", zadanie_id)
    if not z or not zd:
        return
    przed = [p for p in zd if p["rodzaj"] == "przed"][-1:]
    po = [p for p in zd if p["rodzaj"] != "przed"][-2:]
    obrazy = []
    for p in przed + po:
        try:
            with open(os.path.join(ZDJ, p["plik"]), "rb") as f:
                obrazy.append(base64.b64encode(f.read()).decode())
        except OSError:
            pass
    try:
        wynik = normalizuj_ocene(ai_zapytaj(prompt_oceny(z, len(przed)), obrazy))
        stan, tekst = "gotowa", json.dumps(wynik, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        stan, tekst = "blad", json.dumps({"blad": str(e)[:200]}, ensure_ascii=False)
    with BLOKADA:
        ex("UPDATE zadania SET ocena=?, ocena_stan=? WHERE id=?", tekst, stan, zadanie_id)


def rozpisz_kroki(zadanie_id):
    with BLOKADA:
        z = q1("SELECT * FROM zadania WHERE id=?", zadanie_id)
    if not z or json.loads(z["kroki"] or "[]"):
        return
    try:
        o = ai_zapytaj("Rozpisz zadanie domowe dla dziecka na 2–5 krótkich kroków (po polsku, po kilka słów, "
                       "tryb rozkazujący, życzliwie). Zadanie: " + z["tytul"] + ". Oczekiwania rodzica: " +
                       (z["opis"] or "brak") + '. Odpowiedz JSON: {"kroki": ["…", "…"]}')
        kroki = [{"t": str(k)[:80], "z": False} for k in (o.get("kroki") or [])[:5] if str(k).strip()]
    except Exception as e:  # noqa: BLE001
        print("kroki AI nieudane:", e, file=sys.stderr)
        return
    if kroki:
        with BLOKADA:
            ex("UPDATE zadania SET kroki=? WHERE id=? AND kroki='[]'", json.dumps(kroki, ensure_ascii=False), zadanie_id)


def w_tle(f, *a):
    if ai_wlaczone():
        threading.Thread(target=f, args=a, daemon=True).start()


# ---------- zadania powtarzane ----------
def wygeneruj(dzien=None):
    d = dt.date.fromisoformat(dzien or dzis())
    nr = str(d.isoweekday())
    nowe = []
    with BLOKADA:
        for s in q("SELECT * FROM szablony WHERE aktywny=1"):
            if nr not in (s["dni"] or ""):
                continue
            if q1("SELECT id FROM zadania WHERE szablon_id=? AND dzien=?", s["id"], d.isoformat()):
                continue
            if s["utworzone"] and s["utworzone"][:10] > d.isoformat():
                continue
            termin = d.isoformat() + "T" + (s["godzina"] or "20:00") + ":00"
            nowe.append(dodaj_zadanie(dict(s, termin=termin, dzien=d.isoformat(), szablon_id=s["id"])))
    return nowe


def dodaj_zadanie(z):
    kroki = z.get("kroki") or "[]"
    if isinstance(kroki, list):
        kroki = json.dumps([{"t": str(k.get("t", k) if isinstance(k, dict) else k)[:80], "z": False}
                            for k in kroki if str(k).strip()], ensure_ascii=False)
    wymaga = 1 if (z.get("weryfikacja") == "zaufanie" and random.random() < LOSOWE) else 0
    zid = ex("INSERT INTO zadania(dziecko_id,tytul,opis,kroki,termin,punkty,weryfikacja,minuty,pora,pula,zleca_id,"
             "szablon_id,dzien,wymaga_zdjecia,utworzone) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             z["dziecko_id"], z["tytul"], z.get("opis", ""), kroki, z.get("termin"), int(z.get("punkty") or 0),
             z.get("weryfikacja", "zdjecie"), int(z.get("minuty") or 0), z.get("pora", ""), int(z.get("pula") or 0),
             z.get("zleca_id"), z.get("szablon_id"), z.get("dzien"), wymaga, iso(teraz()))
    if kroki == "[]" and z.get("ai_kroki"):   # tylko na życzenie zlecającego (1.3)
        w_tle(rozpisz_kroki, zid)
    return zid


# ---------- widok ----------
def zadanie_dla(z, ja):
    z = dict(z)
    z["kroki"] = json.loads(z["kroki"] or "[]")
    z["zdjecia"] = [{"id": p["id"], "rodzaj": p["rodzaj"]} for p in
                    q("SELECT id, rodzaj FROM zdjecia WHERE zadanie_id=? ORDER BY id", z["id"])]
    try:
        z["ocena"] = json.loads(z["ocena"]) if z["ocena"] else None
    except ValueError:
        z["ocena"] = None
    try:
        z["pomoc"] = json.loads(z["pomoc"]) if z.get("pomoc") else None
    except ValueError:
        z["pomoc"] = None
    if ja["rola"] == "dziecko":
        z.pop("wymaga_zdjecia", None)   # losowe sprawdzenie – dziecko dowiaduje się przy wysyłaniu
    zl = osoba(z["zleca_id"]) if z.get("zleca_id") else None
    z["zleca"] = zl["imie"] if zl else ""
    za = osoba(z["zatwierdzil_id"]) if z.get("zatwierdzil_id") else None
    z["zatwierdzil"] = za["imie"] if za else ""
    z["po_terminie"] = bool(z["termin"] and z["stan"] in ("do_zrobienia", "do_poprawki") and z["termin"] < iso(teraz()))
    return z


def stan_dla(ja):
    wygeneruj()
    d = dzis()
    od7 = (teraz().date() - dt.timedelta(days=7)).isoformat()
    dzieci = []
    for c in moje_dzieci(ja):
        pr = opieka(ja, c["id"])
        dzieci.append({"id": c["id"], "imie": c["imie"], "saldo": saldo(c["id"]), "zarezerwowane": zarezerwowane(c["id"]),
                       "wiek": (teraz().year - c["rok_ur"]) if c["rok_ur"] else None, "grosze": c["grosze"] or 0,
                       "tydzien": tydzien(c["id"]), "seria": seria(c["id"]),
                       "prawa": {"zleca": pr["zleca"], "zatwierdza": pr["zatwierdza"]}})
    ids = [c["id"] for c in dzieci] or [-1]
    zn = ",".join("?" * len(ids))
    zad = q("SELECT * FROM zadania WHERE dziecko_id IN (" + zn + ") AND ("
            "pula=1 OR dzien=? OR stan IN ('do_zrobienia','do_poprawki','wyslane') OR (dzien>=? AND dzien<=?)) "
            "ORDER BY COALESCE(termin,'9999'), id", *ids, d, od7, d)
    zad = [z for z in zad if z["pula"] or not (z["dzien"] and z["dzien"] > d)]
    nagr = q("SELECT * FROM nagrody WHERE dziecko_id IN (" + zn + ") AND stan IN ('aktywna','propozycja') ORDER BY cel DESC, koszt",
             *ids)
    wym = q("SELECT w.*, n.nazwa FROM wymiany w JOIN nagrody n ON n.id=w.nagroda_id WHERE w.dziecko_id IN (" + zn + ") "
            "AND (w.stan='czeka' OR w.ts>=?) ORDER BY w.id DESC", *ids, od7)
    wynik = {"wersja": WERSJA, "teraz": iso(teraz()), "dzis": d, "ai": ai_wlaczone(),
             "ja": {"id": ja["id"], "imie": ja["imie"], "rola": ja["rola"], "admin": bool(ja["admin"]),
                    "ma_pin": bool(ja["pin_hash"]) or bool(ja.get("_podglad")), "przez_ha": bool(ja.get("_przez_ha")),
                    "podglad": bool(ja.get("_podglad"))},
             "dzieci": dzieci, "zadania": [zadanie_dla(z, ja) for z in zad], "nagrody": nagr, "wymiany": wym}
    wynik["punkty"] = q("SELECT * FROM punkty WHERE dziecko_id IN (" + zn + ") ORDER BY id DESC LIMIT 60", *ids)
    wynik["przypomnienia"] = q("SELECT id, osoba_id, tekst, kiedy, wyslane FROM notatki WHERE osoba_id IN (" + zn + ") AND kiedy>=? "
                               "ORDER BY kiedy", *ids, d)
    wynik["nauka"] = [nauka_dla(n, ja) for n in q("SELECT * FROM nauka WHERE dziecko_id IN (" + zn + ") AND start>=? ORDER BY id DESC LIMIT 30",
                                                 *ids, od7)]
    if ja["rola"] != "dziecko":
        wynik["szablony"] = q("SELECT * FROM szablony WHERE aktywny=1 AND dziecko_id IN (" + zn + ") ORDER BY dziecko_id, pora, tytul",
                              *ids)
    if ja["admin"]:
        wynik["osoby"] = [{"id": o["id"], "imie": o["imie"], "rola": o["rola"], "admin": o["admin"], "powiadom": o["powiadom"],
                           "rok_ur": o["rok_ur"] or None, "ha_user": o["ha_user"], "grosze": o["grosze"] or 0,
                           "link": link(o), "ma_pin": bool(o["pin_hash"]), "ha": bool(o["ha_user"])}
                          for o in q("SELECT * FROM osoby WHERE aktywna=1 ORDER BY rola DESC, imie")]
        wynik["klucz_dodatku"] = klucz_dodatku(utworz=True)
        wynik["ha_konta"] = q("SELECT * FROM ha_konta ORDER BY nazwa")
        wynik["adres"] = ADRES
        wynik["opieka"] = q("SELECT * FROM opieka")
        wynik["ha"] = bool(HA_URL and ha_token())
        wynik["telefony"] = ha_telefony()
        wynik["ustawienia"] = {"ai_url": AI_URL, "ai_model": AI_MODEL, "ai_klucz": bool(ai_klucz()), "ha_url": HA_URL,
                               "ha_token": bool(ha_token()), "aktualizacja": aktualizacja_stan()}
    return wynik


def podsumowanie():
    """Liczby dla tablicy w domu (strona Aplikacje na Wyse): bez zdjęć, opisów i kodów."""
    wygeneruj()
    d = dzis()
    od7 = iso(teraz() - dt.timedelta(days=7))
    dzieci = []
    for c in q("SELECT * FROM osoby WHERE rola='dziecko' AND aktywna=1 ORDER BY imie"):
        z = q("SELECT stan FROM zadania WHERE dziecko_id=? AND dzien=? AND pula=0", c["id"], d)
        dzieci.append({"imie": c["imie"], "punkty": saldo(c["id"]) - zarezerwowane(c["id"]), "seria": seria(c["id"]),
                       "dzis": len(z), "dzis_zrobione": sum(1 for x in z if x["stan"] in KONCOWE or x["stan"] == "wyslane"),
                       "tydzien_punkty": tydzien(c["id"])})
    return {"wersja": WERSJA, "dzieci": dzieci,
            "do_zatwierdzenia": q1("SELECT COUNT(*) n FROM zadania WHERE stan='wyslane'")["n"]
            + q1("SELECT COUNT(*) n FROM wymiany WHERE stan='czeka'")["n"],
            "tydzien_zatwierdzone": q1("SELECT COUNT(*) n FROM zadania WHERE stan IN ('zatwierdzone','czesciowo') AND zatwierdzone>=?",
                                       od7)["n"],
            "po_terminie": q1("SELECT COUNT(*) n FROM zadania WHERE stan IN ('do_zrobienia','do_poprawki') AND pula=0 "
                              "AND termin IS NOT NULL AND termin<?", iso(teraz()))["n"]}


# ---------- akcje ----------
def tekst(v, n=200):
    return str(v or "").strip()[:n]


def a_zadanie(ja, b):
    dz = int(b.get("dziecko_id") or 0)
    wymagaj(ja, dz, "zleca")
    tyt = tekst(b.get("tytul"), 120)
    if not tyt:
        raise Blad(400, "Wpisz, co trzeba zrobić.")
    wer = b.get("weryfikacja") or "zdjecie"
    if wer not in WERYFIKACJE:
        raise Blad(400, "Nieznany sposób potwierdzenia.")
    pora = b.get("pora") or ""
    if pora not in PORY:
        raise Blad(400, "Nieznana pora dnia.")
    kroki = [k for k in (b.get("kroki") or []) if str(k).strip()][:8]
    z = {"dziecko_id": dz, "tytul": tyt, "opis": tekst(b.get("opis"), 600), "kroki": kroki,
         "punkty": max(0, min(1000, int(b.get("punkty") or 0))), "weryfikacja": wer,
         "minuty": max(0, min(240, int(b.get("minuty") or 0))), "pora": pora, "zleca_id": ja["id"],
         "ai_kroki": bool(b.get("ai_kroki"))}
    dni = "".join(sorted(set(re.sub(r"[^1-7]", "", str(b.get("dni") or "")))))
    with BLOKADA:
        if dni:
            godz = tekst(b.get("godzina"), 5) or "20:00"
            if not re.match(r"^\d\d:\d\d$", godz):
                raise Blad(400, "Godzina w formacie GG:MM.")
            sid = ex("INSERT INTO szablony(dziecko_id,tytul,opis,kroki,punkty,weryfikacja,minuty,pora,dni,godzina,zleca_id,utworzone)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", dz, z["tytul"], z["opis"],
                     json.dumps([{"t": tekst(k, 80), "z": False} for k in kroki], ensure_ascii=False),
                     z["punkty"], wer, z["minuty"], pora, dni, godz, ja["id"], iso(teraz()))
            nowe = wygeneruj()
            zid = nowe[0] if nowe else None
            res = {"szablon_id": sid, "zadanie_id": zid}
        else:
            z["pula"] = 1 if b.get("pula") else 0
            z["termin"] = termin_ok(b.get("termin"))
            z["dzien"] = None if z["pula"] else (z["termin"][:10] if z["termin"] else dzis())
            zid = dodaj_zadanie(z)
            res = {"zadanie_id": zid}
    if zid and not z.get("pula"):
        powiadom(osoba(dz), "Nowe zadanie", "%s zleca: %s" % (ja["imie"], tyt), "/#z%d" % zid)
    return res


def zadanie_moje(ja, zid, prawo):
    z = q1("SELECT * FROM zadania WHERE id=?", zid)
    if not z:
        raise Blad(404, "Nie ma takiego zadania.")
    wymagaj(ja, z["dziecko_id"], prawo)
    return z


def a_kroki(ja, zid, b):
    with BLOKADA:
        z = zadanie_moje(ja, zid, "widzi")
        kroki = json.loads(z["kroki"] or "[]")
        i = int(b.get("i", -1))
        if not 0 <= i < len(kroki):
            raise Blad(400, "Nie ma takiego kroku.")
        kroki[i]["z"] = bool(b.get("z"))
        ex("UPDATE zadania SET kroki=? WHERE id=?", json.dumps(kroki, ensure_ascii=False), zid)
    return {"ok": True}


def a_wez(ja, zid):
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if not z["pula"]:
            raise Blad(409, "To zadanie już ktoś wziął.")
        termin = z["termin"] or (dzis() + "T20:00:00")
        ex("UPDATE zadania SET pula=0, dzien=?, termin=? WHERE id=?", dzis(), termin, zid)
    return {"ok": True}


def a_start(ja, zid):
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if not z["start"]:
            ex("UPDATE zadania SET start=? WHERE id=?", iso(teraz()), zid)
    return {"ok": True}


def a_zdjecie(ja, zid, rodzaj, dane):
    if rodzaj not in ("przed", "po"):
        raise Blad(400, "Rodzaj zdjęcia: przed albo po.")
    if not dane or len(dane) > MAX_ZDJ:
        raise Blad(413, "Zdjęcie puste albo za duże.")
    if dane[:3] == b"\xff\xd8\xff":
        roz = "jpg"
    elif dane[:8] == b"\x89PNG\r\n\x1a\n":
        roz = "png"
    else:
        raise Blad(415, "To nie wygląda na zdjęcie (JPEG albo PNG).")
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if z["stan"] in KONCOWE or z["stan"] == "wyslane":
            raise Blad(409, "Zadanie już wysłane.")
        os.makedirs(ZDJ, exist_ok=True)
        plik = "%d_%s_%s.%s" % (zid, rodzaj, secrets.token_hex(4), roz)
        with open(os.path.join(ZDJ, plik), "wb") as f:
            f.write(dane)
        pid = ex("INSERT INTO zdjecia(zadanie_id,rodzaj,plik,ts) VALUES(?,?,?,?)", zid, rodzaj, plik, iso(teraz()))
        if rodzaj == "po":
            ex("UPDATE zadania SET proby=proby+1 WHERE id=?", zid)   # ile razy dziecko robiło zdjęcie „po” (wysiłek)
        if rodzaj == "po" and ai_wlaczone():
            ex("UPDATE zadania SET ocena_stan='czeka' WHERE id=?", zid)
    if rodzaj == "po":
        w_tle(ocen, zid)
    return {"id": pid}


def a_usun_zdjecie(ja, pid):
    with BLOKADA:
        p = q1("SELECT * FROM zdjecia WHERE id=?", pid)
        if not p:
            raise Blad(404, "Nie ma takiego zdjęcia.")
        z = zadanie_moje(ja, p["zadanie_id"], "dziecko")
        if z["stan"] in KONCOWE or z["stan"] == "wyslane":
            raise Blad(409, "Zadanie już wysłane.")
        ex("DELETE FROM zdjecia WHERE id=?", pid)
        try:
            os.remove(os.path.join(ZDJ, p["plik"]))
        except OSError:
            pass
    return {"ok": True}


def a_wyslij(ja, zid, b):
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if z["stan"] not in ("do_zrobienia", "do_poprawki"):
            raise Blad(409, "To zadanie jest już wysłane.")
        if z["pula"]:
            raise Blad(409, "Najpierw weź zadanie z puli.")
        po = q("SELECT id FROM zdjecia WHERE zadanie_id=? AND rodzaj='po'", zid)
        w = z["weryfikacja"]
        if w in ("zdjecie", "zeszyt") and not po:
            raise Blad(409, "Dodaj zdjęcie.", potrzebne_zdjecie=True)
        if w == "zaufanie" and z["wymaga_zdjecia"] and not po:
            raise Blad(409, "Dziś losowe sprawdzenie – zrób jedno zdjęcie.", potrzebne_zdjecie=True, losowe=True)
        if w == "minutnik" and z["minuty"]:
            if not z["start"]:
                raise Blad(409, "Najpierw włącz minutnik.")
            minelo = (teraz() - dt.datetime.fromisoformat(z["start"])).total_seconds() / 60
            if minelo < z["minuty"]:
                raise Blad(409, "Jeszcze %d min." % (z["minuty"] - int(minelo)), zostalo=int(z["minuty"] - minelo))
        ex("UPDATE zadania SET stan='wyslane', wyslane=?, komentarz=? WHERE id=?", iso(teraz()), tekst(b.get("komentarz"), 300), zid)
        dz = osoba(z["dziecko_id"])
    for o in zatwierdzajacy(z["dziecko_id"]):
        powiadom(o, "Do zatwierdzenia", "%s: %s" % (dz["imie"], z["tytul"]), "/#z%d" % zid)
    return {"ok": True}


def a_decyzja(ja, zid, b):
    dec = b.get("decyzja")
    if dec not in ("zatwierdz", "czesciowo", "poprawka"):
        raise Blad(400, "Decyzja: zatwierdz, czesciowo albo poprawka.")
    with BLOKADA:
        z = zadanie_moje(ja, zid, "zatwierdza")
        if z["stan"] != "wyslane":
            raise Blad(409, "To zadanie nie czeka na zatwierdzenie.")
        slowo = tekst(b.get("slowo"), 300)
        if dec == "poprawka":
            ex("UPDATE zadania SET stan='do_poprawki', slowo=?, zatwierdzil_id=? WHERE id=?", slowo, ja["id"], zid)
            pk = 0
        else:
            pk = z["punkty"] if dec == "zatwierdz" else z["punkty"] // 2
            if "punkty" in b and b["punkty"] not in (None, ""):
                pk = max(0, min(1000, int(b["punkty"])))
            stan = "zatwierdzone" if dec == "zatwierdz" else "czesciowo"
            ex("UPDATE zadania SET stan=?, slowo=?, zatwierdzil_id=?, zatwierdzone=?, przyznane=? WHERE id=?",
               stan, slowo, ja["id"], iso(teraz()), pk, zid)
            if pk:
                ex("INSERT INTO punkty(dziecko_id,ile,powod,zadanie_id,ts) VALUES(?,?,?,?,?)",
                   z["dziecko_id"], pk, z["tytul"], zid, iso(teraz()))
    msg = {"zatwierdz": "Zatwierdzone, +%d pkt" % pk, "czesciowo": "Częściowo, +%d pkt" % pk,
           "poprawka": "Do poprawki"}[dec]
    powiadom(osoba(z["dziecko_id"]), z["tytul"], msg + (" – " + slowo if slowo else ""), "/#z%d" % zid)
    return {"ok": True, "punkty": pk}


def a_usun_zadanie(ja, zid):
    with BLOKADA:
        z = zadanie_moje(ja, zid, "zleca")
        if z["stan"] in KONCOWE:
            raise Blad(409, "Zatwierdzonego zadania nie usuwam (punkty już przyznane).")
        for p in q("SELECT plik FROM zdjecia WHERE zadanie_id=?", zid):
            try:
                os.remove(os.path.join(ZDJ, p["plik"]))
            except OSError:
                pass
        ex("DELETE FROM zdjecia WHERE zadanie_id=?", zid)
        ex("DELETE FROM zadania WHERE id=?", zid)
    return {"ok": True}


def a_szablon_wylacz(ja, sid):
    with BLOKADA:
        s = q1("SELECT * FROM szablony WHERE id=?", sid)
        if not s:
            raise Blad(404, "Nie ma takiego powtarzania.")
        wymagaj(ja, s["dziecko_id"], "zleca")
        ex("UPDATE szablony SET aktywny=0 WHERE id=?", sid)
    return {"ok": True}


def a_nagroda(ja, b):
    dz = int(b.get("dziecko_id") or (ja["id"] if ja["rola"] == "dziecko" else 0))
    naz = tekst(b.get("nazwa"), 100)
    koszt = int(b.get("koszt") or 0)
    if not naz or koszt <= 0:
        raise Blad(400, "Podaj nazwę i koszt w punktach.")
    with BLOKADA:
        if ja["rola"] == "dziecko":
            wymagaj(ja, dz, "dziecko")
            nid = ex("INSERT INTO nagrody(dziecko_id,nazwa,koszt,cel,stan,zaproponowal_id,ts) VALUES(?,?,?,?,?,?,?)",
                     dz, naz, koszt, 1 if b.get("cel") else 0, "propozycja", ja["id"], iso(teraz()))
        else:
            wymagaj(ja, dz, "zleca")
            nid = ex("INSERT INTO nagrody(dziecko_id,nazwa,koszt,cel,stan,zaproponowal_id,ts) VALUES(?,?,?,?,?,?,?)",
                     dz, naz, koszt, 1 if b.get("cel") else 0, "aktywna", ja["id"], iso(teraz()))
    if ja["rola"] == "dziecko":
        for o in zatwierdzajacy(dz):
            powiadom(o, "Propozycja nagrody", "%s proponuje: %s (%d pkt)" % (ja["imie"], naz, koszt), "/#nagrody")
    return {"id": nid}


def a_nagroda_decyzja(ja, nid, b):
    with BLOKADA:
        n = q1("SELECT * FROM nagrody WHERE id=?", nid)
        if not n:
            raise Blad(404, "Nie ma takiej nagrody.")
        wymagaj(ja, n["dziecko_id"], "zatwierdza")
        if b.get("decyzja") == "usun":
            ex("UPDATE nagrody SET stan='usunieta' WHERE id=?", nid)
        elif n["stan"] != "propozycja":
            raise Blad(409, "Ta nagroda nie czeka na decyzję.")
        else:
            koszt = int(b.get("koszt") or n["koszt"])
            ex("UPDATE nagrody SET stan=?, koszt=? WHERE id=?", "aktywna" if b.get("decyzja") == "tak" else "odrzucona",
               koszt, nid)
    return {"ok": True}


def a_wymiana(ja, b):
    nid = int(b.get("nagroda_id") or 0)
    with BLOKADA:
        n = q1("SELECT * FROM nagrody WHERE id=? AND stan='aktywna'", nid)
        if not n:
            raise Blad(404, "Nie ma takiej nagrody.")
        wymagaj(ja, n["dziecko_id"], "dziecko")
        wolne = saldo(n["dziecko_id"]) - zarezerwowane(n["dziecko_id"])
        if wolne < n["koszt"]:
            raise Blad(409, "Brakuje %d pkt." % (n["koszt"] - wolne))
        wid = ex("INSERT INTO wymiany(nagroda_id,dziecko_id,koszt,ts) VALUES(?,?,?,?)", nid, n["dziecko_id"], n["koszt"],
                 iso(teraz()))
    for o in zatwierdzajacy(n["dziecko_id"]):
        powiadom(o, "Wymiana punktów", "%s chce: %s (%d pkt)" % (ja["imie"], n["nazwa"], n["koszt"]), "/#nagrody")
    return {"id": wid}


def a_wymiana_decyzja(ja, wid, b):
    with BLOKADA:
        w = q1("SELECT w.*, n.nazwa FROM wymiany w JOIN nagrody n ON n.id=w.nagroda_id WHERE w.id=?", wid)
        if not w:
            raise Blad(404, "Nie ma takiej wymiany.")
        wymagaj(ja, w["dziecko_id"], "zatwierdza")
        if w["stan"] != "czeka":
            raise Blad(409, "Ta wymiana jest już rozstrzygnięta.")
        tak = b.get("decyzja") == "tak"
        ex("UPDATE wymiany SET stan=?, decyzja_id=?, decyzja_ts=? WHERE id=?", "zatwierdzona" if tak else "odrzucona",
           ja["id"], iso(teraz()), wid)
        if tak:
            ex("INSERT INTO punkty(dziecko_id,ile,powod,wymiana_id,ts) VALUES(?,?,?,?,?)", w["dziecko_id"], -w["koszt"],
               "Nagroda: " + w["nazwa"], wid, iso(teraz()))
    powiadom(osoba(w["dziecko_id"]), "Nagroda", ("Masz: " if tak else "Jeszcze nie: ") + w["nazwa"], "/#nagrody")
    return {"ok": True}


def a_punkty(ja, b):
    """Ręczna korekta punktów (premia albo odjęcie) – tylko zatwierdzający."""
    dz = int(b.get("dziecko_id") or 0)
    wymagaj(ja, dz, "zatwierdza")
    ile = int(b.get("ile") or 0)
    if not ile:
        raise Blad(400, "Podaj liczbę punktów.")
    with BLOKADA:
        ex("INSERT INTO punkty(dziecko_id,ile,powod,ts) VALUES(?,?,?,?)", dz, ile, tekst(b.get("powod"), 100) or "Premia", iso(teraz()))
    return {"ok": True}


def tylko_admin(ja):
    if not ja["admin"]:
        raise Blad(403, "Tylko administrator.")


# ---------- ustawienia w aplikacji (zamiast poleceń w konsoli) ----------
def zapisz_tajne(nazwa, wartosc):
    """Klucz albo token do pliku w katalogu danych (poza bazą, żeby nie trafiał do nocnych kopii bazy)."""
    sc = os.path.join(KAT, nazwa)
    if not wartosc:
        try:
            os.remove(sc)
        except OSError:
            pass
        return
    fd = os.open(sc, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(wartosc)
    os.chmod(sc, 0o600)


def adres_ok(v, co):
    v = str(v or "").strip().rstrip("/")[:200]
    if v and not re.match(r"^https?://[A-Za-z0-9._\-\[\]:]+(/[A-Za-z0-9._~/\-]*)?$", v):
        raise Blad(400, "Adres %s ma zaczynać się od http:// i nie mieć spacji." % co)
    return v


def aktualizacja_stan():
    info = ""
    try:
        with open(os.path.join(KAT, "aktualizacja"), encoding="utf-8") as f:
            info = f.read().strip()[:40]
    except OSError:
        pass
    return {"przycisk": os.path.exists(AKT_JEDNOSTKA), "sprawdzono": info}


def sprawdz_polaczenia():
    """Próba połączenia z AI i Home Assistantem – to samo, co robiło polecenie zadania-ai."""
    w = {"ai": {"ok": False, "tekst": "AI jest wyłączone (brak adresu)."}, "ha": {"ok": False, "tekst": "Brak adresu Home Assistanta."}}
    if AI_URL:
        try:
            h, k = {}, ai_klucz()
            if k:
                h["Authorization"] = "Bearer " + k
            req = urllib.request.Request(AI_URL + ("/models" if AI_URL.endswith("/v1") else "/api/tags"), headers=h)
            odp = urllib.request.urlopen(req, timeout=10).read().decode()
            if AI_MODEL in odp:
                w["ai"] = {"ok": True, "tekst": "AI odpowiada, model %s jest dostępny." % AI_MODEL}
            else:
                w["ai"]["tekst"] = "Serwer AI odpowiada, ale nie ma modelu %s. Sprawdź nazwę." % AI_MODEL
        except urllib.error.HTTPError as e:
            w["ai"]["tekst"] = "Serwer AI odmówił (kod %d). Sprawdź klucz." % e.code
        except Exception:  # noqa: BLE001
            w["ai"]["tekst"] = "Serwer AI nie odpowiada. Sprawdź adres i czy komputer z AI jest włączony."
    if HA_URL:
        tok = ha_token()
        if not tok:
            w["ha"]["tekst"] = "Brak tokenu Home Assistanta."
        else:
            try:
                req = urllib.request.Request(HA_URL + "/api/", headers={"Authorization": "Bearer " + tok})
                urllib.request.urlopen(req, timeout=10).read()
                w["ha"] = {"ok": True, "tekst": "Home Assistant odpowiada, powiadomienia będą działać."}
            except urllib.error.HTTPError as e:
                w["ha"]["tekst"] = "Home Assistant odrzucił token." if e.code in (401, 403) else "Home Assistant zwrócił błąd %d." % e.code
            except Exception:  # noqa: BLE001
                w["ha"]["tekst"] = "Home Assistant nie odpowiada pod tym adresem."
    return w


def a_ustawienia(ja, b):
    global AI_URL, AI_MODEL, HA_URL
    tylko_admin(ja)
    with BLOKADA:
        if "ai_url" in b:
            ustaw("cfg_ai_url", adres_ok(b["ai_url"], "AI"))
        if "ai_model" in b:
            m = str(b["ai_model"] or "").strip()[:80]
            if not re.match(r"^[A-Za-z0-9._:/\-]*$", m):
                raise Blad(400, "Nazwa modelu ma niedozwolone znaki.")
            if m:
                ustaw("cfg_ai_model", m)
        if "ha_url" in b:
            ustaw("cfg_ha_url", adres_ok(b["ha_url"], "Home Assistanta"))
        for pole, plik in (("ai_klucz", "ai_klucz"), ("ha_token", "ha_token")):
            v = str(b.get(pole) or "").strip()[:600]
            if v:
                zapisz_tajne(plik, v)
            elif b.get(pole + "_usun"):
                zapisz_tajne(plik, "")
        konfig_zastosuj()
        _NOTIFY["ts"] = 0.0
    return dict(sprawdz_polaczenia(), ok=True)


def a_ustawienia_test(ja):
    tylko_admin(ja)
    return dict(sprawdz_polaczenia(), ok=True)


def a_aktualizuj(ja):
    """Prośba o aktualizację teraz: plik-znacznik, na który czeka usługa systemowa (uprawnienia roota ma tylko ona)."""
    tylko_admin(ja)
    if not os.path.exists(AKT_JEDNOSTKA):
        raise Blad(409, "Ta instalacja aktualizuje się sama co godzinę. Przycisk zadziała po jednorazowym odświeżeniu instalacji.")
    with open(os.path.join(KAT, "aktualizuj"), "w", encoding="utf-8") as f:
        f.write(iso(teraz()))
    return {"ok": True, "wersja": WERSJA}


def a_podglad(ja, b):
    """Administrator ogląda i klika aplikację jako wybrane dziecko (do prób). Działania są prawdziwe."""
    tylko_admin(ja)
    with BLOKADA:
        c = osoba(int(b.get("dziecko_id") or 0))
        if c["rola"] != "dziecko":
            raise Blad(400, "Podgląd działa tylko dla dziecka.")
        ex("UPDATE osoby SET podglad=? WHERE id=?", "%d|%s" % (c["id"], iso(teraz() + dt.timedelta(minutes=PODGLAD_MIN))), ja["id"])
    return {"ok": True}


def a_podglad_koniec(ja):
    with BLOKADA:
        ex("UPDATE osoby SET podglad='' WHERE id=?", ja["id"])
    return {"ok": True}


def w_podgladzie(o):
    """Osoba, jako którą działa administrator w trybie podglądu, albo on sam."""
    if not (o and o["admin"] and o.get("podglad")):
        return o
    cid, _, do = o["podglad"].partition("|")
    c = q1("SELECT * FROM osoby WHERE id=? AND aktywna=1 AND rola='dziecko'", int(cid or 0)) if do > iso(teraz()) else None
    if not c:
        ex("UPDATE osoby SET podglad='' WHERE id=?", o["id"])
        return o
    c["_podglad"] = o["id"]
    c["_przez_ha"] = o.get("_przez_ha", False)
    return c


def a_osoba(ja, b):
    tylko_admin(ja)
    imie = tekst(b.get("imie"), 40)
    rola = b.get("rola")
    if not imie or rola not in ("dziecko", "dorosly"):
        raise Blad(400, "Podaj imię i rolę (dziecko albo dorosły).")
    with BLOKADA:
        oid = ex("INSERT INTO osoby(imie,rola,admin,kod,powiadom) VALUES(?,?,?,?,?)", imie, rola,
                 1 if (rola == "dorosly" and b.get("admin")) else 0, nowy_kod(), tekst(b.get("powiadom"), 80))
    return {"id": oid, "link": link(osoba(oid))}


def a_osoba_zmien(ja, oid, b):
    tylko_admin(ja)
    with BLOKADA:
        o = osoba(oid)
        if not o:
            raise Blad(404, "Nie ma takiej osoby.")
        if "imie" in b and tekst(b["imie"], 40):
            ex("UPDATE osoby SET imie=? WHERE id=?", tekst(b["imie"], 40), oid)
        if "powiadom" in b:
            ex("UPDATE osoby SET powiadom=? WHERE id=?", tekst(b["powiadom"], 80), oid)
        if "ha_user" in b:
            hu = tekst(b["ha_user"], 64)
            if hu and not q1("SELECT id FROM ha_konta WHERE id=?", hu):
                raise Blad(400, "Nie znam takiego konta HA – niech ta osoba raz otworzy Zadania w aplikacji HA.")
            if hu:
                ex("UPDATE osoby SET ha_user='' WHERE ha_user=?", hu)
            ex("UPDATE osoby SET ha_user=? WHERE id=?", hu, oid)
        if "rok_ur" in b:
            r = int(b["rok_ur"] or 0)
            if r and not 1990 <= r <= teraz().year:
                raise Blad(400, "Rok urodzenia, np. 2013.")
            ex("UPDATE osoby SET rok_ur=? WHERE id=?", r, oid)
        if "grosze" in b:   # kieszonkowe: ile groszy za 1 punkt (0 = wyłączone)
            ex("UPDATE osoby SET grosze=? WHERE id=?", max(0, min(1000, int(b["grosze"] or 0))), oid)
        if b.get("nowy_kod"):
            ex("UPDATE osoby SET kod=? WHERE id=?", nowy_kod(), oid)
            usun_sesje(oid)
        if "admin" in b and o["rola"] == "dorosly":
            if not b["admin"] and oid == ja["id"]:
                raise Blad(409, "Nie odbieraj sobie praw administratora.")
            ex("UPDATE osoby SET admin=? WHERE id=?", 1 if b["admin"] else 0, oid)
        if b.get("usun"):
            if oid == ja["id"]:
                raise Blad(409, "Nie usuwaj siebie.")
            ex("UPDATE osoby SET aktywna=0, kod=?, ha_user='' WHERE id=?", "x" + nowy_kod(), oid)
            usun_sesje(oid)
            ex("DELETE FROM opieka WHERE dorosly_id=? OR dziecko_id=?", oid, oid)
        o = osoba(oid)
    return {"ok": True, "link": link(o)}


def a_zrzut(ja, dane):
    """Zrzut ekranu (np. dziennik elektroniczny) albo zdjęcie kartki -> propozycje zadań od AI. Nic nie zapisuje:
    rodzic wybiera, które zlecić."""
    if ja["rola"] == "dziecko" or not [d for d in moje_dzieci(ja) if opieka(ja, d["id"])["zleca"]]:
        raise Blad(403, "Zadania ze zrzutu dodaje rodzic, który zleca.")
    if not ai_wlaczone():
        raise Blad(409, "AI nie jest jeszcze podłączone – ten przycisk zadziała po podłączeniu modelu z komputera w domu.")
    if not dane or len(dane) > MAX_ZDJ or not (dane[:3] == b"\xff\xd8\xff" or dane[:8] == b"\x89PNG\r\n\x1a\n"):
        raise Blad(415, "Potrzebny obraz JPEG albo PNG.")
    prompt = ("To zrzut ekranu z dziennika elektronicznego szkoły (np. zadania domowe, sprawdziany, kartkówki) albo zdjęcie "
              "kartki z zadaniami. Dzisiaj jest " + dzis() + ". Wypisz wszystkie zadania do zrobienia przez ucznia. "
              "Odpowiedz wyłącznie JSON: {\"zadania\": [{\"przedmiot\": \"…\", \"tytul\": \"krótko, co zrobić\", "
              "\"opis\": \"szczegóły z ekranu\", \"termin\": \"RRRR-MM-DD albo null\", \"rodzaj\": \"zadanie|sprawdzian|kartkowka|inne\"}]}. "
              "Nie zmyślaj: tylko to, co widać na obrazie.")
    try:
        o = ai_zapytaj(prompt, [base64.b64encode(dane).decode()])
    except Exception as e:  # noqa: BLE001
        raise Blad(502, "AI nie odpowiedziało: %s" % str(e)[:120])
    wynik = []
    for z in (o.get("zadania") if isinstance(o, dict) else None) or []:
        if not isinstance(z, dict) or not str(z.get("tytul") or "").strip():
            continue
        t = str(z.get("termin") or "")
        t = t if re.match(r"^\d{4}-\d\d-\d\d$", t) else ""
        rodz = str(z.get("rodzaj") or "zadanie")
        prz = tekst(z.get("przedmiot"), 40)
        wynik.append({"tytul": ((prz + ": ") if prz else "") + tekst(z.get("tytul"), 90), "opis": tekst(z.get("opis"), 400),
                      "termin": t, "rodzaj": rodz, "weryfikacja": "zeszyt" if rodz == "zadanie" else "minutnik",
                      "minuty": 0 if rodz == "zadanie" else 30, "punkty": 10 if rodz == "zadanie" else 15})
    return {"zadania": wynik[:15]}


def a_doprecyzuj(ja, b):
    """AI czyta polecenie rodzica (z wiekiem dziecka) i proponuje poprawki. Nic nie zapisuje."""
    dz = int(b.get("dziecko_id") or 0)
    wymagaj(ja, dz, "zleca")
    if not ai_wlaczone():
        raise Blad(409, "AI nie jest jeszcze podłączone – ten przycisk zadziała po podłączeniu modelu z komputera w domu.")
    tyt = tekst(b.get("tytul"), 120)
    if not tyt:
        raise Blad(400, "Wpisz najpierw, co trzeba zrobić.")
    c = osoba(dz)
    wiek = (teraz().year - c["rok_ur"]) if c and c["rok_ur"] else None
    prompt = ("Pomagasz rodzicowi napisać jasne zadanie domowe dla dziecka" + (" w wieku %d lat" % wiek if wiek else "") + ". "
              "Zadanie: " + tyt + ". Opis rodzica: " + (tekst(b.get("opis"), 600) or "(brak)") + ". "
              "Oceń, czego brakuje, żeby dziecko wiedziało dokładnie, co ma zrobić i kiedy jest zrobione, i zaproponuj lepszą wersję. "
              "Dopasuj do wieku. Odpowiedz wyłącznie JSON po polsku: {\"tytul\": \"krótki\", \"opis\": \"czego oczekujemy, konkretnie\", "
              "\"brakuje\": [\"czego nie było w poleceniu\"], \"kroki\": [\"2–5 krótkich kroków\"], \"punkty\": liczba 1–30, "
              "\"weryfikacja\": \"zdjecie|zeszyt|minutnik|zaufanie\" (jak dziecko najlepiej pokaże, że zrobione), "
              "\"dlaczego\": \"jedno zdanie, czemu ta forma potwierdzenia\", \"minuty\": liczba albo 0, "
              "\"uwaga\": \"jedno zdanie, np. czy zadanie pasuje do wieku\"}")
    try:
        o = ai_zapytaj(prompt)
    except Exception as e:  # noqa: BLE001
        raise Blad(502, "AI nie odpowiedziało: %s" % str(e)[:120])
    if not isinstance(o, dict):
        raise Blad(502, "AI odpowiedziało nie na temat.")
    wer = o.get("weryfikacja") if o.get("weryfikacja") in WERYFIKACJE else "zdjecie"
    try:
        pk = max(0, min(100, int(o.get("punkty") or 0)))
        mn = max(0, min(240, int(o.get("minuty") or 0)))
    except (TypeError, ValueError):
        pk, mn = 0, 0
    return {"tytul": tekst(o.get("tytul"), 120) or tyt, "opis": tekst(o.get("opis"), 600),
            "brakuje": [tekst(x, 160) for x in (o.get("brakuje") or [])[:6] if str(x).strip()],
            "kroki": [tekst(x, 80) for x in (o.get("kroki") or [])[:6] if str(x).strip()],
            "punkty": pk, "weryfikacja": wer, "minuty": mn, "uwaga": tekst(o.get("uwaga"), 200),
            "dlaczego": tekst(o.get("dlaczego"), 200)}


def a_nie_dam_rady(ja, zid, b):
    """Dziecko prosi o przesunięcie zadania i podaje powód; decyduje rodzic."""
    powod = tekst(b.get("powod"), 200)
    if not powod:
        raise Blad(400, "Napisz krótko, dlaczego.")
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if z["stan"] not in ("do_zrobienia", "do_poprawki") or z["pula"]:
            raise Blad(409, "Tego zadania nie da się już przesunąć.")
        if z["prosba"]:
            raise Blad(409, "Prośba już wysłana. Poczekaj na odpowiedź.")
        ex("UPDATE zadania SET prosba=? WHERE id=?", powod, zid)
        dz = osoba(z["dziecko_id"])
    for o in zatwierdzajacy(z["dziecko_id"]):
        powiadom(o, "Prośba o przesunięcie", "%s: %s – %s" % (dz["imie"], z["tytul"], powod), "/#z%d" % zid)
    return {"ok": True}


def a_prosba(ja, zid, b):
    """Rodzic odpowiada na „nie dam rady”: jutro (termin i dzień +1) albo zostaje."""
    dec = b.get("decyzja")
    if dec not in ("jutro", "zostaje"):
        raise Blad(400, "Decyzja: jutro albo zostaje.")
    with BLOKADA:
        z = zadanie_moje(ja, zid, "zatwierdza")
        if not z["prosba"]:
            raise Blad(409, "Nie ma prośby do rozpatrzenia.")
        if dec == "jutro":
            jutro = teraz().date() + dt.timedelta(days=1)
            godz = z["termin"][11:16] if z["termin"] else "18:00"
            ex("UPDATE zadania SET prosba='', termin=?, dzien=?, przypomniano=0 WHERE id=?",
               "%sT%s" % (jutro.isoformat(), godz), jutro.isoformat(), zid)
        else:
            ex("UPDATE zadania SET prosba='' WHERE id=?", zid)
    powiadom(osoba(z["dziecko_id"]), z["tytul"], "Przesunięte na jutro." if dec == "jutro" else "Zostaje na dziś. Dasz radę!",
             "/#z%d" % zid)
    return {"ok": True}


def a_zgloszenie(ja, b):
    """Dziecko zgłasza coś, co zrobiło samo z siebie; punkty przyznaje rodzic przy zatwierdzaniu."""
    if ja["rola"] != "dziecko":
        raise Blad(403, "To zgłasza dziecko.")
    tyt = tekst(b.get("tytul"), 120)
    if not tyt:
        raise Blad(400, "Napisz, co zrobiłaś albo zrobiłeś.")
    with BLOKADA:
        if q1("SELECT COUNT(*) AS n FROM zadania WHERE dziecko_id=? AND wlasne=1 AND dzien=?", ja["id"], dzis())["n"] >= 3:
            raise Blad(409, "Dziś już 3 zgłoszenia. Resztę jutro.")
        zid = dodaj_zadanie({"dziecko_id": ja["id"], "tytul": tyt, "opis": tekst(b.get("opis"), 300), "punkty": 0,
                             "weryfikacja": "zaufanie", "zleca_id": ja["id"], "dzien": dzis()})
        ex("UPDATE zadania SET stan='wyslane', wyslane=?, wlasne=1, wymaga_zdjecia=0 WHERE id=?", iso(teraz()), zid)
    for o in zatwierdzajacy(ja["id"]):
        powiadom(o, "Zrobione z własnej inicjatywy", "%s: %s" % (ja["imie"], tyt), "/#z%d" % zid)
    return {"zadanie_id": zid}


def a_przypomnienie(ja, b):
    """Własne przypomnienie (np. kartkówka w czwartek): powiadomienie o podanej porze, widać je też na ekranie „Dziś”."""
    t = tekst(b.get("tekst"), 160)
    if not t:
        raise Blad(400, "Napisz, o czym przypomnieć.")
    kiedy = termin_ok(b.get("kiedy"))
    if not kiedy:
        raise Blad(400, "Wybierz dzień i godzinę.")
    with BLOKADA:
        if q1("SELECT COUNT(*) AS n FROM notatki WHERE osoba_id=? AND wyslane=0", ja["id"])["n"] >= 30:
            raise Blad(409, "Masz już 30 przypomnień. Usuń stare.")
        nid = ex("INSERT INTO notatki(osoba_id,tekst,kiedy,ts) VALUES(?,?,?,?)", ja["id"], t, kiedy, iso(teraz()))
    return {"id": nid}


def a_przypomnienie_usun(ja, nid):
    with BLOKADA:
        n = q1("SELECT * FROM notatki WHERE id=?", nid)
        if not n or n["osoba_id"] != ja["id"]:
            raise Blad(404, "Nie ma takiego przypomnienia.")
        ex("DELETE FROM notatki WHERE id=?", nid)
    return {"ok": True}


def wyslij_przypomnienia():
    with BLOKADA:
        lista = q("SELECT * FROM notatki WHERE wyslane=0 AND kiedy<=?", iso(teraz()))
        for n in lista:
            ex("UPDATE notatki SET wyslane=1 WHERE id=?", n["id"])
    for n in lista:
        powiadom(osoba(n["osoba_id"]), "Przypomnienie", n["tekst"], "/")
    return len(lista)


def ponaglenia():
    """Zadanie czeka na zatwierdzenie ponad 2 h → jedno przypomnienie dla zatwierdzających (tylko 7–22)."""
    t = teraz()
    if not 7 <= t.hour < 22:
        return 0
    with BLOKADA:
        lista = q("SELECT * FROM zadania WHERE stan='wyslane' AND ponaglono=0 AND wyslane<=?", iso(t - dt.timedelta(hours=2)))
        for z in lista:
            ex("UPDATE zadania SET ponaglono=1 WHERE id=?", z["id"])
    for z in lista:
        dz = osoba(z["dziecko_id"])
        for o in zatwierdzajacy(z["dziecko_id"]):
            powiadom(o, "Czeka na Twoją decyzję", "%s: %s (od ponad 2 godzin)" % (dz["imie"] if dz else "", z["tytul"]),
                     "/#z%d" % z["id"])
    return len(lista)


# ---------- nauka z AI (1.6): przepytaj mnie, wytłumacz, test ----------
TRYBY_NAUKI = {"przepytaj": 5, "test": 10, "wytlumacz": 0}
MAT_MAX = 6000      # znaków materiału (kontekst modelu 16k)
POZA = "To nie wynika z Twoich materiałów – sprawdź w podręczniku albo zapytaj nauczyciela."


def nauka_dla(n, ja):
    """Sesja nauki do pokazania: dziecko dostaje pytania bez wzorcowych odpowiedzi, rodzic sam wynik."""
    d = json.loads(n["dane"] or "{}")
    pyt = d.get("pytania") or []
    odp = [p for p in pyt if p.get("ocena")]
    koniec = n["koniec"] or n["ruch"] or n["start"]
    minuty = max(0, int((dt.datetime.fromisoformat(koniec) - dt.datetime.fromisoformat(n["start"])).total_seconds() // 60))
    w = {"id": n["id"], "dziecko_id": n["dziecko_id"], "temat": n["temat"], "tryb": n["tryb"], "start": n["start"],
         "koniec": n["koniec"], "strony": n["strony"], "ma_material": bool(n["material"]), "minuty": minuty,
         "ile": len(pyt), "odpowiedzi": len(odp), "dobrze": sum(1 for p in odp if p["ocena"] == "dobrze"),
         "czesciowo": sum(1 for p in odp if p["ocena"] == "czesciowo"),
         "poza": sum(1 for p in pyt if p.get("poza")) + sum(1 for r in d.get("rozmowa") or [] if r.get("poza")),
         "pytan_dziecka": len(d.get("rozmowa") or [])}
    if ja["rola"] == "dziecko":
        w["pytania"] = [{"p": p["p"], "poza": bool(p.get("poza")), "moja": p.get("moja", ""), "ocena": p.get("ocena", ""),
                         "komentarz": p.get("komentarz", ""), "wzor": p.get("odp", "") if p.get("ocena") else ""} for p in pyt]
        w["rozmowa"] = d.get("rozmowa") or []
    return w


def nauka_moja(ja, nid):
    n = q1("SELECT * FROM nauka WHERE id=?", nid)
    if not n or ja["rola"] != "dziecko" or n["dziecko_id"] != ja["id"]:
        raise Blad(404, "Nie ma takiej nauki.")
    return n


def ai_nauka(prompt, obrazy=()):
    if not ai_wlaczone():
        raise Blad(409, "Komputer w domu jest teraz wyłączony. Spróbuj później.")
    try:
        o = ai_zapytaj(prompt, obrazy)
    except Exception as e:  # noqa: BLE001
        raise Blad(502, "Komputer w domu nie odpowiedział. Spróbuj za chwilę. (%s)" % str(e)[:80])
    if not isinstance(o, dict):
        raise Blad(502, "Nie udało się. Spróbuj jeszcze raz.")
    return o


def wiek_tekst(c):
    return (" w wieku %d lat" % (teraz().year - c["rok_ur"])) if c and c["rok_ur"] else ""


def a_nauka(ja, b):
    """Start nauki: temat, forma i ewentualnie wpisany materiał. Zdjęcia stron dochodzą osobno."""
    if ja["rola"] != "dziecko":
        raise Blad(403, "Naukę zaczyna dziecko.")
    temat = tekst(b.get("temat"), 120)
    tryb = b.get("tryb")
    if not temat:
        raise Blad(400, "Napisz, czego się uczysz.")
    if tryb not in TRYBY_NAUKI:
        raise Blad(400, "Wybierz formę: przepytaj, test albo wytłumacz.")
    with BLOKADA:
        nid = ex("INSERT INTO nauka(dziecko_id,temat,tryb,material,start,ruch) VALUES(?,?,?,?,?,?)", ja["id"], temat, tryb,
                 tekst(b.get("material"), MAT_MAX), iso(teraz()), iso(teraz()))
    return {"id": nid}


def a_nauka_strona(ja, nid, dane):
    """Zdjęcie notatek albo strony podręcznika → model przepisuje treść (najwyżej 3 strony na naukę)."""
    if not dane or len(dane) > MAX_ZDJ or dane[:3] != b"\xff\xd8\xff":
        raise Blad(415, "To nie wygląda na zdjęcie.")
    with BLOKADA:
        n = nauka_moja(ja, nid)
        if n["strony"] >= 3:
            raise Blad(409, "Najwyżej 3 strony na jedną naukę.")
        if json.loads(n["dane"] or "{}").get("pytania"):
            raise Blad(409, "Pytania są już ułożone. Zacznij nową naukę z nowym materiałem.")
    o = ai_nauka("Na zdjęciu jest strona podręcznika albo notatki ucznia. Przepisz wiernie całą treść po polsku (tekst, wzory, "
                 "podpisy), niczego nie dodawaj od siebie i niczego nie streszczaj. Odpowiedz wyłącznie JSON: "
                 "{\"tresc\": \"przepisana treść\", \"czytelne\": true albo false}", [base64.b64encode(dane).decode()])
    tresc = str(o.get("tresc") or "").strip()
    if len(tresc) < 20:
        raise Blad(422, "Nie umiem odczytać tej strony. Zrób zdjęcie z bliska, przy dobrym świetle.")
    with BLOKADA:
        n = nauka_moja(ja, nid)
        mat = (n["material"] + "\n\n" + tresc).strip()[:MAT_MAX]
        ex("UPDATE nauka SET material=?, strony=strony+1, ruch=? WHERE id=?", mat, iso(teraz()), nid)
    return {"strony": n["strony"] + 1, "znakow": len(mat), "czytelne": bool(o.get("czytelne", True))}


def a_nauka_pytania(ja, nid):
    """Model układa pytania z materiału; bez materiału – z własnej wiedzy, każde oznaczone „poza materiałem”."""
    with BLOKADA:
        n = nauka_moja(ja, nid)
        d = json.loads(n["dane"] or "{}")
        ile = TRYBY_NAUKI[n["tryb"]]
        if not ile:
            raise Blad(409, "W tej formie to Ty zadajesz pytania.")
        if d.get("pytania"):
            return nauka_dla(n, ja)
        c = osoba(ja["id"])
    if n["material"]:
        zrodlo = ("Układaj pytania WYŁĄCZNIE z poniższego materiału ucznia. Jeśli materiału jest za mało na %d pytań, ułóż mniej. "
                  "MATERIAŁ:\n%s\nKONIEC MATERIAŁU. " % (ile, n["material"]))
    else:
        zrodlo = "Uczeń nie dał materiału, więc układasz pytania z własnej wiedzy o temacie (poziom szkoły podstawowej). "
    o = ai_nauka("Jesteś cierpliwym korepetytorem ucznia" + wiek_tekst(c) + ". Temat: " + n["temat"] + ". " + zrodlo
                 + "Ułóż %d krótkich pytań sprawdzających zrozumienie (nie tylko daty i definicje), od łatwiejszych do trudniejszych. "
                 "Odpowiedz wyłącznie JSON po polsku: {\"pytania\": [{\"p\": \"pytanie\", \"odp\": \"wzorcowa krótka odpowiedź\"}]}" % ile)
    pyt = [{"p": tekst(x.get("p"), 300), "odp": tekst(x.get("odp"), 500), "poza": not n["material"]}
           for x in (o.get("pytania") or [])[:ile] if isinstance(x, dict) and str(x.get("p") or "").strip()]
    if not pyt:
        raise Blad(502, "Nie udało się ułożyć pytań. Spróbuj jeszcze raz.")
    with BLOKADA:
        d["pytania"] = pyt
        ex("UPDATE nauka SET dane=?, ruch=? WHERE id=?", json.dumps(d, ensure_ascii=False), iso(teraz()), nid)
        return nauka_dla(q1("SELECT * FROM nauka WHERE id=?", nid), ja)


def a_nauka_odpowiedz(ja, nid, b):
    """Dziecko odpowiada na pytanie; model porównuje z odpowiedzią wzorcową i materiałem."""
    moja = tekst(b.get("tekst"), 600)
    if not moja:
        raise Blad(400, "Napisz odpowiedź (albo „nie wiem”).")
    with BLOKADA:
        n = nauka_moja(ja, nid)
        d = json.loads(n["dane"] or "{}")
        pyt = d.get("pytania") or []
        i = int(b.get("i") or 0)
        if not 0 <= i < len(pyt):
            raise Blad(404, "Nie ma takiego pytania.")
        if pyt[i].get("ocena"):
            raise Blad(409, "Na to pytanie już odpowiedziałaś/eś.")
        c = osoba(ja["id"])
    o = ai_nauka("Jesteś życzliwym korepetytorem ucznia" + wiek_tekst(c) + ". Sprawdź odpowiedź ucznia. Pytanie: " + pyt[i]["p"]
                 + " Odpowiedź wzorcowa: " + pyt[i]["odp"] + " Odpowiedź ucznia: " + moja + " "
                 + ("Fragment materiału ucznia:\n" + n["material"][:3000] + "\n" if n["material"] else "")
                 + "Oceniaj sens, nie dosłowne brzmienie ani literówki. Odpowiedz wyłącznie JSON po polsku: "
                 "{\"ocena\": \"dobrze|czesciowo|zle\", \"komentarz\": \"1–2 zdania: co dobrze, czego zabrakło, bez wyśmiewania\"}")
    ocena = o.get("ocena") if o.get("ocena") in ("dobrze", "czesciowo", "zle") else "czesciowo"
    with BLOKADA:
        n = nauka_moja(ja, nid)
        d = json.loads(n["dane"] or "{}")
        d["pytania"][i].update({"moja": moja, "ocena": ocena, "komentarz": tekst(o.get("komentarz"), 400)})
        gotowe = all(p.get("ocena") for p in d["pytania"])
        ex("UPDATE nauka SET dane=?, ruch=?, koniec=? WHERE id=?", json.dumps(d, ensure_ascii=False), iso(teraz()),
           iso(teraz()) if gotowe else None, nid)
        return nauka_dla(q1("SELECT * FROM nauka WHERE id=?", nid), ja)


def a_nauka_pytanie(ja, nid, b):
    """„Wytłumacz”: dziecko pyta; model odpowiada z materiału, a gdy tam tego nie ma – z własnej wiedzy z wyraźnym oznaczeniem."""
    pyt = tekst(b.get("tekst"), 400)
    if not pyt:
        raise Blad(400, "Napisz, czego nie rozumiesz.")
    with BLOKADA:
        n = nauka_moja(ja, nid)
        d = json.loads(n["dane"] or "{}")
        if len(d.get("rozmowa") or []) >= 15:
            raise Blad(409, "To już 15 pytań w tej nauce. Zacznij nową.")
        c = osoba(ja["id"])
    o = ai_nauka("Jesteś cierpliwym korepetytorem ucznia" + wiek_tekst(c) + ". Temat: " + n["temat"] + ". "
                 + ("MATERIAŁ UCZNIA:\n" + n["material"] + "\nKONIEC MATERIAŁU. Najpierw szukaj odpowiedzi w materiale. "
                    if n["material"] else "Uczeń nie dał materiału. ")
                 + "Pytanie ucznia: " + pyt + " Wytłumacz prostymi słowami, krok po kroku, z jednym przykładem. Jeśli to zadanie "
                 "do rozwiązania, pokaż sposób na PODOBNYM przykładzie, nie podawaj gotowego wyniku. Odpowiedz wyłącznie JSON po polsku: "
                 "{\"odpowiedz\": \"wyjaśnienie, najwyżej 6 zdań\", \"z_materialu\": true jeśli odpowiedź wynika z materiału ucznia, inaczej false}")
    odp = tekst(o.get("odpowiedz"), 1500)
    if not odp:
        raise Blad(502, "Nie udało się. Zapytaj inaczej.")
    poza = not (n["material"] and o.get("z_materialu") is True)
    with BLOKADA:
        n = nauka_moja(ja, nid)
        d = json.loads(n["dane"] or "{}")
        d.setdefault("rozmowa", []).append({"p": pyt, "o": odp, "poza": poza})
        ex("UPDATE nauka SET dane=?, ruch=? WHERE id=?", json.dumps(d, ensure_ascii=False), iso(teraz()), nid)
        return nauka_dla(q1("SELECT * FROM nauka WHERE id=?", nid), ja)


def a_nauka_koniec(ja, nid):
    with BLOKADA:
        nauka_moja(ja, nid)
        ex("UPDATE nauka SET koniec=COALESCE(koniec,?) WHERE id=?", iso(teraz()), nid)
    return {"ok": True}


def a_pomoc(ja, zid):
    """„Pomóż mi zacząć”: AI podpowiada dziecku pierwszy krok. Nie robi zadania za dziecko. Najwyżej 3 razy na zadanie."""
    with BLOKADA:
        z = zadanie_moje(ja, zid, "dziecko")
        if z["stan"] not in ("do_zrobienia", "do_poprawki"):
            raise Blad(409, "To zadanie jest już wysłane.")
        stara = json.loads(z["pomoc"]) if z["pomoc"] else {}
        ile = int(stara.get("ile") or 0)
        if ile >= 3:
            raise Blad(409, "Podpowiedź była już 3 razy. Zapytaj rodzica.")
        c = osoba(z["dziecko_id"])
    if not ai_wlaczone():
        raise Blad(409, "Komputer w domu jest teraz wyłączony. Zapytaj rodzica.")
    wiek = (teraz().year - c["rok_ur"]) if c and c["rok_ur"] else None
    kroki = "; ".join(k.get("t", "") for k in json.loads(z["kroki"] or "[]"))
    prompt = ("Jesteś życzliwym pomocnikiem dziecka" + (" w wieku %d lat" % wiek if wiek else "") + ". Dziecko ma zadanie i nie wie, "
              "jak się za nie zabrać. NIE rozwiązuj zadania i nie podawaj odpowiedzi do pracy domowej. Pomóż tylko zacząć. "
              "Zadanie: " + z["tytul"] + ". Czego oczekuje rodzic: " + (z["opis"] or "(brak opisu)") + ". "
              "Kroki od rodzica: " + (kroki or "(brak)") + ". "
              + ("Rodzic odesłał do poprawki z uwagą: " + z["slowo"] + ". " if z["stan"] == "do_poprawki" and z["slowo"] else "")
              + "Odpowiedz wyłącznie JSON po polsku, prostymi słowami, bez zdrobnień dla nastolatka: "
              "{\"pierwszy_krok\": \"jedna mała rzecz na 2 minuty, od której zacząć\", "
              "\"wskazowki\": [\"najwyżej 3 krótkie wskazówki\"], \"minuty\": ile minut zajmie całość (liczba), "
              "\"otucha\": \"jedno krótkie zdanie zachęty\"}")
    try:
        o = ai_zapytaj(prompt)
    except Exception as e:  # noqa: BLE001
        raise Blad(502, "Komputer w domu nie odpowiedział. Spróbuj za chwilę. (%s)" % str(e)[:80])
    if not isinstance(o, dict) or not str(o.get("pierwszy_krok") or "").strip():
        raise Blad(502, "Nie udało się przygotować podpowiedzi. Spróbuj jeszcze raz.")
    try:
        mn = max(0, min(240, int(o.get("minuty") or 0)))
    except (TypeError, ValueError):
        mn = 0
    pomoc = {"pierwszy_krok": tekst(o.get("pierwszy_krok"), 200),
             "wskazowki": [tekst(x, 160) for x in (o.get("wskazowki") or [])[:3] if str(x).strip()],
             "minuty": mn, "otucha": tekst(o.get("otucha"), 160), "ile": ile + 1, "ts": iso(teraz())}
    with BLOKADA:
        ex("UPDATE zadania SET pomoc=? WHERE id=?", json.dumps(pomoc, ensure_ascii=False), zid)
    return pomoc


def a_pin(ja, b):
    if ja.get("_podglad"):
        raise Blad(403, "W podglądzie nie zmienia się PIN-u dziecka.")
    pin = pin_poprawny_format(b.get("pin"))
    with BLOKADA:
        o = osoba(ja["id"])
        if o["pin_hash"] and not ja.get("_przez_ha"):   # w aplikacji HA tożsamość potwierdza logowanie HA
            sprawdz_pin(o, b.get("stary"))
        ustaw_pin(ja["id"], pin)
    return {"ok": True}


def a_pin_reset(ja, oid):
    """Kasuje PIN: administrator każdemu, zatwierdzający – swojemu dziecku. Osoba ustawia nowy przy wejściu z linku
    (albo z aplikacji HA, gdy konto już połączone)."""
    with BLOKADA:
        o = osoba(oid)
        if not o or not o["aktywna"]:
            raise Blad(404, "Nie ma takiej osoby.")
        if not ja["admin"] and not (o["rola"] == "dziecko" and opieka(ja, oid)["zatwierdza"]):
            raise Blad(403, "PIN skasuje administrator albo opiekun dziecka.")
        ex("UPDATE osoby SET pin_hash='', pin_sol='', pin_bledy=0, pin_blokada='' WHERE id=?", oid)
        usun_sesje(oid)
    return {"ok": True, "link": link(o)}


def a_opieka(ja, b):
    tylko_admin(ja)
    dor, dz = int(b.get("dorosly_id") or 0), int(b.get("dziecko_id") or 0)
    od, odz = osoba(dor), osoba(dz)
    if not (od and odz and od["rola"] == "dorosly" and odz["rola"] == "dziecko"):
        raise Blad(400, "Opiekun to dorosły, podopieczny to dziecko.")
    with BLOKADA:
        if b.get("usun"):
            ex("DELETE FROM opieka WHERE dorosly_id=? AND dziecko_id=?", dor, dz)
        else:
            ex("INSERT INTO opieka(dorosly_id,dziecko_id,zleca,zatwierdza) VALUES(?,?,?,?) "
               "ON CONFLICT(dorosly_id,dziecko_id) DO UPDATE SET zleca=excluded.zleca, zatwierdza=excluded.zatwierdza",
               dor, dz, 1 if b.get("zleca") else 0, 1 if b.get("zatwierdza") else 0)
    return {"ok": True}


# ---------- prace w tle ----------
def przypomnienia():
    """Godzinę przed terminem – przypomnienie dziecku (raz)."""
    za_godz = iso(teraz() + dt.timedelta(hours=1))
    with BLOKADA:
        lista = q("SELECT * FROM zadania WHERE stan IN ('do_zrobienia','do_poprawki') AND pula=0 AND przypomniano=0 "
                  "AND termin IS NOT NULL AND termin<=? AND termin>?", za_godz, iso(teraz()))
        for z in lista:
            ex("UPDATE zadania SET przypomniano=1 WHERE id=?", z["id"])
    for z in lista:
        powiadom(osoba(z["dziecko_id"]), "Za godzinę termin", z["tytul"], "/#z%d" % z["id"])
    return len(lista)


def podsumowanie_tygodnia(wymus=False):
    """Niedziela od 18:00, raz w tygodniu: każdy zatwierdzający dostaje jedno powiadomienie o swoich dzieciach."""
    t = teraz()
    znak = "%d-%02d" % t.isocalendar()[:2]
    if not wymus and not (t.isoweekday() == 7 and t.hour >= 18 and ust("tydzien_wyslany") != znak):
        return 0
    od = (t.date() - dt.timedelta(days=6)).isoformat()
    ile = 0
    with BLOKADA:
        ustaw("tydzien_wyslany", znak)
        dorosli = q("SELECT * FROM osoby WHERE rola='dorosly' AND aktywna=1")
        paczki = []
        for o in dorosli:
            linie = []
            for c in moje_dzieci(o):
                if not opieka(o, c["id"])["zatwierdza"]:
                    continue
                r = q1("SELECT COUNT(*) AS n, SUM(stan IN ('zatwierdzone','czesciowo')) AS ok FROM zadania "
                       "WHERE dziecko_id=? AND pula=0 AND dzien>=? AND dzien<=?", c["id"], od, t.date().isoformat())
                pk = q1("SELECT COALESCE(SUM(ile),0) AS s FROM punkty WHERE dziecko_id=? AND ile>0 AND ts>=?", c["id"], od)["s"]
                linie.append("%s: %d z %d zadań, +%d pkt" % (c["imie"], r["ok"] or 0, r["n"] or 0, pk))
            if linie:
                paczki.append((o, "; ".join(linie)))
    for o, tresc in paczki:
        ile += 1 if powiadom(o, "Zadania – podsumowanie tygodnia", tresc, "/#dzieci") else 0
    return ile


def sprzataj_zdjecia():
    granica = (teraz().date() - dt.timedelta(days=ZDJ_DNI)).isoformat()
    with BLOKADA:
        stare = q("SELECT p.* FROM zdjecia p JOIN zadania z ON z.id=p.zadanie_id WHERE z.stan IN ('zatwierdzone','czesciowo') "
                  "AND z.dzien<?", granica)
        for p in stare:
            try:
                os.remove(os.path.join(ZDJ, p["plik"]))
            except OSError:
                pass
            ex("DELETE FROM zdjecia WHERE id=?", p["id"])
    return len(stare)


def petla_tla():
    while True:
        try:
            wygeneruj()
            przypomnienia()
            wyslij_przypomnienia()
            ponaglenia()
            podsumowanie_tygodnia()
            if teraz().hour == 3:
                sprzataj_zdjecia()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(300)


# ---------- HTTP ----------
TRASY_POST = [
    (r"^/api/ustawienia$", lambda ja, m, b, raw: a_ustawienia(ja, b)),
    (r"^/api/ustawienia/test$", lambda ja, m, b, raw: a_ustawienia_test(ja)),
    (r"^/api/aktualizuj$", lambda ja, m, b, raw: a_aktualizuj(ja)),
    (r"^/api/podglad$", lambda ja, m, b, raw: a_podglad(ja, b)),
    (r"^/api/podglad/koniec$", lambda ja, m, b, raw: a_podglad_koniec(ja)),
    (r"^/api/zadanie$", lambda ja, m, b, raw: a_zadanie(ja, b)),
    (r"^/api/zadanie/(\d+)/kroki$", lambda ja, m, b, raw: a_kroki(ja, int(m[1]), b)),
    (r"^/api/zadanie/(\d+)/niedamrady$", lambda ja, m, b, raw: a_nie_dam_rady(ja, int(m[1]), b)),
    (r"^/api/zadanie/(\d+)/prosba$", lambda ja, m, b, raw: a_prosba(ja, int(m[1]), b)),
    (r"^/api/nauka$", lambda ja, m, b, raw: a_nauka(ja, b)),
    (r"^/api/nauka/(\d+)/strona$", lambda ja, m, b, raw: a_nauka_strona(ja, int(m[1]), raw)),
    (r"^/api/nauka/(\d+)/pytania$", lambda ja, m, b, raw: a_nauka_pytania(ja, int(m[1]))),
    (r"^/api/nauka/(\d+)/odpowiedz$", lambda ja, m, b, raw: a_nauka_odpowiedz(ja, int(m[1]), b)),
    (r"^/api/nauka/(\d+)/pytanie$", lambda ja, m, b, raw: a_nauka_pytanie(ja, int(m[1]), b)),
    (r"^/api/nauka/(\d+)/koniec$", lambda ja, m, b, raw: a_nauka_koniec(ja, int(m[1]))),
    (r"^/api/zgloszenie$", lambda ja, m, b, raw: a_zgloszenie(ja, b)),
    (r"^/api/przypomnienie$", lambda ja, m, b, raw: a_przypomnienie(ja, b)),
    (r"^/api/przypomnienie/(\d+)/usun$", lambda ja, m, b, raw: a_przypomnienie_usun(ja, int(m[1]))),
    (r"^/api/zadanie/(\d+)/pomoc$", lambda ja, m, b, raw: a_pomoc(ja, int(m[1]))),
    (r"^/api/zadanie/(\d+)/wez$", lambda ja, m, b, raw: a_wez(ja, int(m[1]))),
    (r"^/api/zadanie/(\d+)/start$", lambda ja, m, b, raw: a_start(ja, int(m[1]))),
    (r"^/api/zadanie/(\d+)/zdjecie/(przed|po)$", lambda ja, m, b, raw: a_zdjecie(ja, int(m[1]), m[2], raw)),
    (r"^/api/zadanie/(\d+)/wyslij$", lambda ja, m, b, raw: a_wyslij(ja, int(m[1]), b)),
    (r"^/api/zadanie/(\d+)/decyzja$", lambda ja, m, b, raw: a_decyzja(ja, int(m[1]), b)),
    (r"^/api/zadanie/(\d+)/usun$", lambda ja, m, b, raw: a_usun_zadanie(ja, int(m[1]))),
    (r"^/api/zdjecie/(\d+)/usun$", lambda ja, m, b, raw: a_usun_zdjecie(ja, int(m[1]))),
    (r"^/api/szablon/(\d+)/wylacz$", lambda ja, m, b, raw: a_szablon_wylacz(ja, int(m[1]))),
    (r"^/api/nagroda$", lambda ja, m, b, raw: a_nagroda(ja, b)),
    (r"^/api/nagroda/(\d+)/decyzja$", lambda ja, m, b, raw: a_nagroda_decyzja(ja, int(m[1]), b)),
    (r"^/api/wymiana$", lambda ja, m, b, raw: a_wymiana(ja, b)),
    (r"^/api/wymiana/(\d+)/decyzja$", lambda ja, m, b, raw: a_wymiana_decyzja(ja, int(m[1]), b)),
    (r"^/api/punkty$", lambda ja, m, b, raw: a_punkty(ja, b)),
    (r"^/api/osoba$", lambda ja, m, b, raw: a_osoba(ja, b)),
    (r"^/api/osoba/(\d+)$", lambda ja, m, b, raw: a_osoba_zmien(ja, int(m[1]), b)),
    (r"^/api/opieka$", lambda ja, m, b, raw: a_opieka(ja, b)),
    (r"^/api/pin$", lambda ja, m, b, raw: a_pin(ja, b)),
    (r"^/api/zrzut$", lambda ja, m, b, raw: a_zrzut(ja, raw)),
    (r"^/api/doprecyzuj$", lambda ja, m, b, raw: a_doprecyzuj(ja, b)),
    (r"^/api/osoba/(\d+)/pin_reset$", lambda ja, m, b, raw: a_pin_reset(ja, int(m[1]))),
]
TYPY = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css",
        ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json", ".webmanifest": "application/manifest+json"}


class H(BaseHTTPRequestHandler):
    server_version = "Zadania/" + WERSJA

    def log_message(self, f, *a):
        if os.environ.get("ZD_LOG"):
            super().log_message(f, *a)

    def wyslij(self, kod, cialo, typ="application/json; charset=utf-8", naglowki=()):
        if isinstance(cialo, (dict, list)):
            cialo = json.dumps(cialo, ensure_ascii=False).encode()
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(cialo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in naglowki:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cialo)

    def dodatek_ha(self):
        """Identyfikator użytkownika HA, gdy żądanie przyszło przez dodatek-pośrednik z dobrym kluczem."""
        k, klucz = self.headers.get("X-Zadania-Klucz") or "", klucz_dodatku()
        if not (klucz and k and hmac.compare_digest(k.encode(), klucz.encode())):
            return ""
        panel = self.headers.get("X-Zadania-Panel") or ""
        if panel.startswith("/") and panel != ust("panel_ha"):
            with BLOKADA:
                ustaw("panel_ha", panel)
        return (self.headers.get("X-Zadania-HA-User") or "").strip()[:64]

    def sesja(self):
        tok = self.headers.get("X-Zadania-Sesja") or ""
        for cz in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = cz.strip().partition("=")
            if k == "zd" and not tok:
                tok = v
        return tok

    def kto(self, prawdziwy=False):
        with BLOKADA:
            o = self.kto_naprawde()
            return o if prawdziwy else w_podgladzie(o)

    def kto_naprawde(self):
        ha = self.dodatek_ha()
        with BLOKADA:
            if ha:
                naz = (self.headers.get("X-Zadania-HA-Nazwa") or "").strip()[:60]
                ex("INSERT INTO ha_konta(id,nazwa,ts) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET nazwa=excluded.nazwa, ts=excluded.ts",
                   ha, naz or ha[:8], iso(teraz()))
                o = q1("SELECT * FROM osoby WHERE ha_user=? AND aktywna=1", ha)
                if o:
                    o["_przez_ha"] = True
                    return o
                return None
            tok = self.sesja()
            if not tok:
                return None
            s = q1("SELECT * FROM sesje WHERE token=?", tok)
            if not s or s["ts"] < iso(teraz() - dt.timedelta(days=SESJA_DNI)):
                return None
            return q1("SELECT * FROM osoby WHERE id=? AND aktywna=1", s["osoba_id"])

    def logowanie(self, sc, b):
        """Bez sesji: lista osób, logowanie PIN-em, wylogowanie. W dodatku HA logowanie łączy konto HA z osobą."""
        ha = self.dodatek_ha()
        if sc == "/api/zaloguj":
            with BLOKADA:
                o = osoba(int(b.get("osoba_id") or 0))
                sprawdz_pin(o, b.get("pin"))
                if ha:
                    ex("UPDATE osoby SET ha_user='' WHERE ha_user=?", ha)
                    ex("UPDATE osoby SET ha_user=? WHERE id=?", ha, o["id"])
                    return self.wyslij(200, {"ok": True})
                tok = nowa_sesja(o["id"])
            return self.wyslij(200, {"ok": True}, naglowki=[ciastko(tok)])
        if sc == "/api/wyloguj":
            with BLOKADA:
                if ha:
                    ex("UPDATE osoby SET ha_user='' WHERE ha_user=?", ha)
                else:
                    ex("DELETE FROM sesje WHERE token=?", self.sesja())
            return self.wyslij(200, {"ok": True}, naglowki=[ciastko("", 0)])
        return None

    def do_GET(self):
        sc = self.path.split("?")[0]
        try:
            m = re.match(r"^/k/([A-Za-z0-9_-]{8,40})$", sc)
            if m:
                with BLOKADA:
                    o = q1("SELECT * FROM osoby WHERE kod=? AND aktywna=1", m[1])
                    if not o:
                        return self.wyslij(404, "Nieznany link. Poproś o nowy.".encode(), "text/plain; charset=utf-8")
                    if o["pin_hash"]:   # PIN już jest – link tylko podpowiada imię, wejście PIN-em
                        return self.wyslij(302, b"", naglowki=[("Location", "../#zaloguj-%d" % o["id"])])
                    tok = nowa_sesja(o["id"])
                return self.wyslij(302, b"", naglowki=[("Location", "../"), ciastko(tok)])
            if sc == "/api/zdrowie":
                return self.wyslij(200, {"ok": True, "wersja": WERSJA})
            if sc == "/api/podsumowanie" and not self.headers.get("X-Zadania-Klucz"):   # tylko bezpośrednio w domu
                with BLOKADA:
                    return self.wyslij(200, podsumowanie())
            if sc == "/api/logowanie":
                ha = self.dodatek_ha()
                with BLOKADA:
                    konto = q1("SELECT nazwa FROM ha_konta WHERE id=?", ha) if ha else None
                    return self.wyslij(200, {"przez_ha": bool(ha), "konto_ha": konto["nazwa"] if konto else "", "osoby": [
                        {"id": o["id"], "imie": o["imie"], "ma_pin": bool(o["pin_hash"])}
                        for o in q("SELECT * FROM osoby WHERE aktywna=1 ORDER BY rola DESC, imie")]})
            if sc.startswith("/api/"):
                ja = self.kto()
                if not ja:
                    return self.wyslij(401, {"blad": "Zaloguj się.", "logowanie": True})
                if sc == "/api/stan":
                    with BLOKADA:
                        return self.wyslij(200, stan_dla(ja))
                m = re.match(r"^/api/zdjecie/(\d+)$", sc)
                if m:
                    with BLOKADA:
                        p = q1("SELECT * FROM zdjecia WHERE id=?", int(m[1]))
                        z = p and q1("SELECT * FROM zadania WHERE id=?", p["zadanie_id"])
                        if not (p and z and opieka(ja, z["dziecko_id"])["widzi"]):
                            return self.wyslij(404, {"blad": "Brak zdjęcia."})
                    with open(os.path.join(ZDJ, p["plik"]), "rb") as f:
                        d = f.read()
                    return self.wyslij(200, d, "image/png" if p["plik"].endswith(".png") else "image/jpeg")
                return self.wyslij(404, {"blad": "Nie ma takiego adresu."})
            plik = "index.html" if sc in ("/", "") else sc.lstrip("/")
            pelna = os.path.realpath(os.path.join(WWW, plik))
            if not pelna.startswith(os.path.realpath(WWW) + os.sep) or not os.path.isfile(pelna):
                return self.wyslij(404, b"Nie ma.", "text/plain; charset=utf-8")
            with open(pelna, "rb") as f:
                return self.wyslij(200, f.read(), TYPY.get(os.path.splitext(pelna)[1], "application/octet-stream"))
        except Blad as e:
            return self.wyslij(e.kod, dict({"blad": e.tekst}, **e.dod))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self.wyslij(500, {"blad": str(e)})

    def do_POST(self):
        sc = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_ZDJ + 1024:
                raise Blad(413, "Za duże.")
            raw = self.rfile.read(n) if n else b""
            if sc == "/api/dodatek/token":
                if not self.dodatek_ha() and not (self.headers.get("X-Zadania-Klucz") and hmac.compare_digest(
                        (self.headers.get("X-Zadania-Klucz") or "").encode(), (klucz_dodatku() or "-").encode())):
                    raise Blad(403, "Zły klucz dodatku.")
                tok = (json.loads(raw.decode() or "{}").get("token") or "").strip()
                if tok:
                    os.makedirs(KAT, exist_ok=True)
                    fd = os.open(os.path.join(KAT, "ha_token"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(tok)
                return self.wyslij(200, {"ok": True, "ha": bool(HA_URL)})
            if sc in ("/api/zaloguj", "/api/wyloguj"):
                b = json.loads(raw.decode() or "{}") if raw else {}
                return self.logowanie(sc, b)
            ja = self.kto(prawdziwy=sc.startswith("/api/podglad"))
            if not ja:
                raise Blad(401, "Zaloguj się.", logowanie=True)
            for wzor, f in TRASY_POST:
                m = re.match(wzor, sc)
                if m:
                    b = {}
                    if raw and "json" in (self.headers.get("Content-Type") or ""):
                        b = json.loads(raw.decode() or "{}")
                    try:
                        return self.wyslij(200, f(ja, m, b, raw))
                    except (ValueError, TypeError) as e:
                        raise Blad(400, "Złe dane: %s" % e)
            raise Blad(404, "Nie ma takiego adresu.")
        except Blad as e:
            return self.wyslij(e.kod, dict({"blad": e.tekst}, **e.dod))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self.wyslij(500, {"blad": str(e)})


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--nowy-admin")
    a.add_argument("--link")
    a.add_argument("--pin-reset")
    a.add_argument("--port", type=int, default=PORT)
    a = a.parse_args()
    if a.nowy_admin:
        with BLOKADA:
            oid = ex("INSERT INTO osoby(imie,rola,admin,kod) VALUES(?,?,?,?)", a.nowy_admin.strip()[:40], "dorosly", 1, nowy_kod())
        print("Administrator dodany. Twój link (otwórz na telefonie, nie wklejaj nigdzie):", link(osoba(oid)))
        return
    if a.pin_reset:
        o = q1("SELECT * FROM osoby WHERE imie=? AND aktywna=1", a.pin_reset.strip())
        if not o:
            print("Nie ma takiej osoby.")
            return
        with BLOKADA:
            ex("UPDATE osoby SET pin_hash='', pin_sol='', pin_bledy=0, pin_blokada='' WHERE id=?", o["id"])
            usun_sesje(o["id"])
        print("PIN skasowany. Otwórz link i ustaw nowy PIN:", link(o))
        return
    if a.link:
        o = q1("SELECT * FROM osoby WHERE imie=? AND aktywna=1", a.link.strip())
        print(link(o) if o else "Nie ma takiej osoby.")
        return
    db()
    threading.Thread(target=petla_tla, daemon=True).start()
    print("Zadania %s na porcie %d (AI: %s, HA: %s)" % (WERSJA, a.port, AI_URL or "wyłączone", "tak" if HA_URL else "nie"),
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
