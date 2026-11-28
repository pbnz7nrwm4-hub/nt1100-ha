"""Stacja jako serwer aplikacji Apex (Android, tablet w nawigacji): wersje APK i aktualizacje, konfiguracja
z kluczem TomTom, odbiór dziennika z tabletu. Tylko biblioteka standardowa; wpina się w serwer Stacji (stacja.py).

Kontrakt aplikacji (nagłówek X-Klucz = klucz aplikacji, brak/zły = 401):
  GET  /api/nav/apex/app/manifest.json  -> {"versionCode","versionName","bytes","sha256"} (404 gdy brak wersji)
  GET  /api/nav/apex/app/apex.apk       -> plik, Range (206/416), Content-Length, Accept-Ranges
  GET  /api/nav/apex/config             -> {"tomtomKey": str}
  POST /api/nav/apex/log                -> zapis dziennika (tekst lub zip, do 5 MB)
  POST /api/nav/apex/route.ntr          -> 501 (liczenie tras online – później)
GUI (strona /apex, za PIN-em; sesja w nagłówku X-Sesja): /api/apex/...  Dostęp tylko z sieci prywatnej (LAN).
Klucze (TomTom, aplikacji) i PIN leżą tylko w katalogu danych Stacji (plik 0600), nigdy w repo ani w logach.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import struct
import threading
import time
import zipfile
from urllib.parse import parse_qs, urlsplit

PAKIET = "pl.nt1100"
MAX_APK = 300 << 20
MAX_LOG = 5 << 20
MAX_DZIENNIKOW = 200
SESJA_S = 12 * 3600
PODGLAD_B = 200 * 1024

A = None  # jedyna instancja (otwiera ją main Stacji albo test)


class BladApex(Exception):
    def __init__(self, tekst, kod=400):
        super().__init__(tekst)
        self.kod = kod


# ---------------------------------------------------------------- odczyt AndroidManifest.xml z APK (binarny XML)

def _napis(dane, pool, i):
    """Łańcuch nr i z puli ciągów (UTF-8 lub UTF-16)."""
    start, n, flagi, off0 = pool
    if i < 0 or i >= n:
        return None
    off = struct.unpack_from("<I", dane, start + 28 + 4 * i)[0] + off0
    if flagi & 0x100:
        p = off
        d = dane[p]
        p += 2 if d & 0x80 else 1
        b = dane[p]
        if b & 0x80:
            b = ((b & 0x7F) << 8) | dane[p + 1]
            p += 2
        else:
            p += 1
        return dane[p:p + b].decode("utf-8", "replace")
    d = struct.unpack_from("<H", dane, off)[0]
    if d & 0x8000:
        d = ((d & 0x7FFF) << 16) | struct.unpack_from("<H", dane, off + 2)[0]
        off += 4
    else:
        off += 2
    return dane[off:off + 2 * d].decode("utf-16-le", "replace")


def czytaj_manifest(dane):
    """Z binarnego AndroidManifest.xml: {"pakiet","versionCode","versionName"} (brakujące = None)."""
    if len(dane) < 16 or struct.unpack_from("<H", dane, 0)[0] != 0x0003:
        raise ValueError("to nie jest binarny AndroidManifest.xml")
    pool = None
    p = struct.unpack_from("<H", dane, 2)[0]
    while p + 8 <= len(dane):
        typ, hdr, rozm = struct.unpack_from("<HHI", dane, p)
        if rozm < 8 or p + rozm > len(dane):
            break
        if typ == 0x0001:
            n, _, flagi, s0 = struct.unpack_from("<IIII", dane, p + 8)
            pool = (p, n, flagi, p + s0)
        elif typ == 0x0102 and pool:
            nazwa = struct.unpack_from("<I", dane, p + 20)[0]
            atr_od, atr_rozm, atr_n = struct.unpack_from("<HHH", dane, p + 24)
            if _napis(dane, pool, nazwa) != "manifest":
                raise ValueError("pierwszy element to nie <manifest>")
            out = {"pakiet": None, "versionCode": None, "versionName": None}
            for k in range(atr_n):
                a = p + 16 + atr_od + k * (atr_rozm or 20)
                _, nm, raw, _, _, typ_w, dat = struct.unpack_from("<IIIHBBI", dane, a)
                nm = _napis(dane, pool, nm)
                if nm in ("package", "versionName"):
                    idx = raw if raw != 0xFFFFFFFF else (dat if typ_w == 3 else None)
                    out["pakiet" if nm == "package" else "versionName"] = _napis(dane, pool, idx) if idx is not None else None
                elif nm == "versionCode" and typ_w in (0x10, 0x11):
                    out["versionCode"] = dat
            return out
        p += rozm
    raise ValueError("w manifeście nie ma elementu <manifest>")


def czytaj_apk(sciezka):
    """Odczyt pakietu i wersji z pliku APK. Błąd (ValueError) = to nie jest czytelny APK."""
    if not zipfile.is_zipfile(sciezka):
        raise ValueError("to nie jest plik APK (nie jest archiwum zip)")
    with zipfile.ZipFile(sciezka) as z:
        try:
            i = z.getinfo("AndroidManifest.xml")
        except KeyError:
            raise ValueError("w pliku nie ma AndroidManifest.xml – to nie jest APK")
        if i.file_size > 4 << 20:
            raise ValueError("AndroidManifest.xml podejrzanie duży")
        return czytaj_manifest(z.read(i))


# ---------------------------------------------------------------- magazyn

def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _bezpieczna(s, dl=40):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s or "")[:dl] or "nieznana"


def _teraz():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _zapisz_json(p, d, tajny=False):
    tmp = p + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if tajny else 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, p)


def _wczytaj_json(p, domyslne):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return domyslne


class Apex:
    def __init__(self, katalog):
        self.kat = os.path.join(katalog, "apex")
        self.wersje = os.path.join(self.kat, "wersje")
        self.dz = os.path.join(self.kat, "dzienniki")
        self.tmp = os.path.join(self.kat, "tmp")
        for d in (self.kat, self.wersje, self.dz, self.tmp):
            os.makedirs(d, mode=0o750, exist_ok=True)
        try:
            os.chmod(self.kat, 0o750)
        except OSError:
            pass
        self.blokada = threading.Lock()
        self.sesje = {}        # token -> wygasa
        self.proby = {}        # ip -> (liczba błędów, do kiedy zablokowane)
        self.kontakt = _wczytaj_json(os.path.join(self.kat, "kontakt.json"), None)

    # ---- ustawienia (sekrety)
    def ust(self):
        return _wczytaj_json(os.path.join(self.kat, "ustawienia.json"), {})

    def zapisz_ust(self, u):
        _zapisz_json(os.path.join(self.kat, "ustawienia.json"), u, tajny=True)

    def klucz_app(self):
        return self.ust().get("kluczApp") or ""

    # ---- PIN i sesje
    @staticmethod
    def _hash_pin(pin, sol):
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(sol), 200_000).hex()

    def pin_ustawiony(self):
        return bool(self.ust().get("pin"))

    def ustaw_pin(self, pin):
        if not re.fullmatch(r"\d{4,12}", pin or ""):
            raise BladApex("PIN to 4–12 cyfr.")
        sol = secrets.token_hex(16)
        u = self.ust()
        u["pin"] = {"sol": sol, "hash": self._hash_pin(pin, sol)}
        self.zapisz_ust(u)

    def zaloguj(self, pin, ip):
        b, do = self.proby.get(ip, (0, 0))
        if do > time.time():
            raise BladApex("Za dużo błędnych prób – poczekaj %d s." % (do - time.time() + 1), 429)
        p = self.ust().get("pin")
        if not p or not hmac.compare_digest(self._hash_pin(str(pin or ""), p["sol"]), p["hash"]):
            b += 1
            self.proby[ip] = (b, time.time() + min(300, 5 * 2 ** (b - 4)) if b >= 4 else 0)
            raise BladApex("Zły PIN.", 401)
        self.proby.pop(ip, None)
        t = secrets.token_urlsafe(24)
        teraz = time.time()
        self.sesje = {k: v for k, v in self.sesje.items() if v > teraz}
        self.sesje[t] = teraz + SESJA_S
        return t

    def sesja_ok(self, h):
        t = h.headers.get("X-Sesja") or ""
        return bool(t) and self.sesje.get(t, 0) > time.time()

    # ---- wersje
    def lista(self):
        out = []
        for d in os.listdir(self.wersje):
            m = _wczytaj_json(os.path.join(self.wersje, d, "meta.json"), None)
            if m and os.path.exists(os.path.join(self.wersje, d, "apex.apk")):
                out.append(m)
        out.sort(key=lambda m: m["versionCode"], reverse=True)
        return out

    def biezaca(self):
        lst = self.lista()
        if not lst:
            return None
        try:
            with open(os.path.join(self.kat, "biezaca"), encoding="utf-8") as f:
                vc = int(f.read().strip())
            for m in lst:
                if m["versionCode"] == vc:
                    return m
        except (OSError, ValueError):
            pass
        return lst[0]

    def _ustaw_biezaca(self, vc):
        with open(os.path.join(self.kat, "biezaca"), "w", encoding="utf-8") as f:
            f.write(str(int(vc)))

    def przyjmij(self, h, vc_form, vn_form, wymus):
        """Strumieniowy odbiór pliku APK z ciała żądania, walidacja, zapis. Zwraca meta wersji."""
        n = int(h.headers.get("Content-Length") or 0)
        if n <= 0:
            raise BladApex("Pusty plik.")
        if n > MAX_APK:
            raise BladApex("Plik za duży (limit %d MB)." % (MAX_APK >> 20), 413)
        tmp = os.path.join(self.tmp, "wgrywany-%s.apk" % secrets.token_hex(4))
        sha = hashlib.sha256()
        try:
            with open(tmp, "wb") as f:
                zostalo = n
                while zostalo:
                    b = h.rfile.read(min(1 << 20, zostalo))
                    if not b:
                        raise BladApex("Wgrywanie przerwane.")
                    f.write(b)
                    sha.update(b)
                    zostalo -= len(b)
            reczne = False
            try:
                m = czytaj_apk(tmp)
            except ValueError as e:
                if not (vc_form and vn_form) or not zipfile.is_zipfile(tmp):
                    raise BladApex("%s. Jeśli to na pewno APK, wpisz versionCode i versionName w formularzu." % e)
                m = {"pakiet": None, "versionCode": None, "versionName": None}
                reczne = True
            vc = m["versionCode"] if m["versionCode"] is not None else vc_form
            vn = m["versionName"] or vn_form
            if vc is None or not vn:
                raise BladApex("Nie umiem odczytać wersji z pliku – wpisz versionCode i versionName.")
            if m["pakiet"] is not None and m["pakiet"] != PAKIET:
                raise BladApex("Inny pakiet (%s) – oczekuję %s. Plik nie jest aplikacją Apex." % (m["pakiet"], PAKIET))
            if reczne and not wymus:
                raise BladApex("Wersja z formularza, bez sprawdzenia pakietu – potwierdź „wymuś”.")
            with self.blokada:
                lst = self.lista()
                naj = lst[0]["versionCode"] if lst else None
                if naj is not None and vc <= naj and not wymus:
                    raise BladApex("versionCode %d nie jest wyższy od najnowszego wgranego (%d) – aplikacja nie zaktualizuje się "
                                   "do niższej wersji. Zmień wersję w budowie albo wymuś świadomie." % (vc, naj), 409)
                d = os.path.join(self.wersje, str(vc))
                os.makedirs(d, mode=0o750, exist_ok=True)
                os.replace(tmp, os.path.join(d, "apex.apk"))
                meta = {"versionCode": vc, "versionName": vn, "bytes": n, "sha256": sha.hexdigest(),
                        "pakiet": m["pakiet"] or PAKIET, "dodano": _teraz(), "reczne": reczne}
                _zapisz_json(os.path.join(d, "meta.json"), meta)
                self._ustaw_biezaca(vc)
            return meta
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def usun(self, vc, wymus):
        with self.blokada:
            lst = self.lista()
            m = next((x for x in lst if x["versionCode"] == vc), None)
            if not m:
                raise BladApex("Nie ma takiej wersji.", 404)
            biez = self.biezaca()
            if len(lst) == 1 and not wymus:
                raise BladApex("To jedyna wgrana wersja – po usunięciu tablet nie dostanie aktualizacji. Potwierdź „wymuś”.", 409)
            if biez and biez["versionCode"] == vc and not wymus:
                raise BladApex("To bieząca wersja (tablet ją pobiera). Najpierw ustaw inną jako biezącą albo potwierdź „wymuś”.", 409)
            shutil.rmtree(os.path.join(self.wersje, str(vc)))
            if biez and biez["versionCode"] == vc:
                try:
                    os.remove(os.path.join(self.kat, "biezaca"))
                except OSError:
                    pass

    def ustaw_biezaca(self, vc):
        with self.blokada:
            if not any(x["versionCode"] == vc for x in self.lista()):
                raise BladApex("Nie ma takiej wersji.", 404)
            self._ustaw_biezaca(vc)

    # ---- dzienniki z tabletu
    def zapisz_dziennik(self, h, ip):
        n = int(h.headers.get("Content-Length") or 0)
        if n <= 0:
            raise BladApex("Pusty dziennik.")
        if n > MAX_LOG:
            h.close_connection = True
            raise BladApex("Dziennik za duży (limit 5 MB).", 413)
        dane = h.rfile.read(n)
        ua = h.headers.get("User-Agent") or ""
        m = re.match(r"Apex/(\S+)", ua)
        wer = _bezpieczna(m.group(1) if m else None, 20)
        rozsz = "zip" if dane[:2] == b"PK" else "txt"
        nazwa = "apex-%s-v%s.%s" % (time.strftime("%Y%m%d-%H%M%S"), wer, rozsz)
        p = os.path.join(self.dz, nazwa)
        i = 1
        while os.path.exists(p):
            i += 1
            p = os.path.join(self.dz, nazwa.replace("." + rozsz, "-%d.%s" % (i, rozsz)))
        with open(p, "wb") as f:
            f.write(dane)
        pliki = sorted(os.listdir(self.dz))
        for stary in pliki[:-MAX_DZIENNIKOW]:
            try:
                os.remove(os.path.join(self.dz, stary))
            except OSError:
                pass
        return os.path.basename(p)

    def dzienniki(self):
        out = []
        for nazwa in sorted(os.listdir(self.dz), reverse=True):
            p = os.path.join(self.dz, nazwa)
            if os.path.isfile(p):
                out.append({"plik": nazwa, "bajty": os.path.getsize(p),
                            "kiedy": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p)))})
        return out

    # ---- kontakt tabletu
    def odnotuj_kontakt(self, h, ip):
        m = re.match(r"Apex/(\S+)", h.headers.get("User-Agent") or "")
        self.kontakt = {"ts": _teraz(), "ip": ip, "wersja": m.group(1)[:30] if m else None,
                        "sciezka": urlsplit(h.path).path[:60]}
        _zapisz_json(os.path.join(self.kat, "kontakt.json"), self.kontakt)


def otworz(katalog):
    global A
    A = Apex(katalog)
    return A


# ---------------------------------------------------------------- HTTP

def _json(h, kod, d):
    t = json.dumps(d, ensure_ascii=False).encode()
    h.send_response(kod)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(t)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(t)


def _ip(h):
    return h.client_address[0]


def _lan(h):
    """Tylko sieć prywatna; ślad przekazania przez serwer pośredni (tunel, proxy) = odmowa."""
    if any(h.headers.get(x) for x in ("X-Forwarded-For", "Cf-Connecting-Ip", "Forwarded", "X-Real-Ip")):
        return False
    try:
        a = ipaddress.ip_address(_ip(h).split("%")[0])
    except ValueError:
        return False
    return a.is_private or a.is_loopback


def _plik(h, sciezka, typ, meta_bajty, nazwa=None):
    """Plik z obsługą Range: 200 / 206 / 416."""
    rozm = meta_bajty
    od, do, kod = 0, rozm - 1, 200
    r = h.headers.get("Range")
    if r:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", r.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                od = int(m.group(1))
                do = int(m.group(2)) if m.group(2) else rozm - 1
            else:
                dl = int(m.group(2))
                od, do = max(0, rozm - dl), rozm - 1
            if od >= rozm or od > do:
                h.send_response(416)
                h.send_header("Content-Range", "bytes */%d" % rozm)
                h.send_header("Content-Length", "0")
                h.end_headers()
                return
            do = min(do, rozm - 1)
            kod = 206
    dl = do - od + 1
    h.send_response(kod)
    h.send_header("Content-Type", typ)
    h.send_header("Content-Length", str(dl))
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Cache-Control", "no-store")
    if kod == 206:
        h.send_header("Content-Range", "bytes %d-%d/%d" % (od, do, rozm))
    if nazwa:
        h.send_header("Content-Disposition", 'attachment; filename="%s"' % nazwa)
    h.end_headers()
    try:
        with open(sciezka, "rb") as f:
            f.seek(od)
            zostalo = dl
            while zostalo:
                b = f.read(min(256 << 10, zostalo))
                if not b:
                    break
                h.wfile.write(b)
                zostalo -= len(b)
    except (BrokenPipeError, ConnectionResetError):
        pass


def obsluz(h, metoda):
    """Wywoływane przez serwer Stacji dla ścieżek /api/nav/apex/… i /api/apex/…; zwraca True, gdy obsłużono."""
    u = urlsplit(h.path)
    path = u.path
    app = path.startswith("/api/nav/apex/")
    if not (app or path.startswith("/api/apex/")):
        return False
    if A is None:
        _json(h, 503, {"blad": "Apex niegotowy"})
        return True
    if not _lan(h):
        _json(h, 403, {"blad": "tylko sieć domowa"})
        return True
    try:
        (_app if app else _gui)(h, metoda, path, parse_qs(u.query))
    except BladApex as e:
        _json(h, e.kod, {"ok": False, "blad": str(e)})
    except (BrokenPipeError, ConnectionResetError):
        pass
    return True


def _app(h, metoda, path, q):
    k = A.klucz_app()
    podany = h.headers.get("X-Klucz") or ""
    if not k or not hmac.compare_digest(podany.encode(), k.encode()):
        return _json(h, 401, {"blad": "zły albo brak klucza"})
    A.odnotuj_kontakt(h, _ip(h))
    r = path[len("/api/nav/apex"):]
    if metoda == "GET" and r == "/app/manifest.json":
        m = A.biezaca()
        if not m:
            return _json(h, 404, {"blad": "brak wgranej wersji"})
        return _json(h, 200, {x: m[x] for x in ("versionCode", "versionName", "bytes", "sha256")})
    if metoda == "GET" and r == "/app/apex.apk":
        m = A.biezaca()
        if not m:
            return _json(h, 404, {"blad": "brak wgranej wersji"})
        return _plik(h, os.path.join(A.wersje, str(m["versionCode"]), "apex.apk"),
                     "application/vnd.android.package-archive", m["bytes"])
    if metoda == "GET" and r == "/config":
        return _json(h, 200, {"tomtomKey": A.ust().get("tomtomKey") or ""})
    if metoda == "POST" and r == "/log":
        return _json(h, 200, {"ok": True, "plik": A.zapisz_dziennik(h, _ip(h))})
    if metoda == "POST" and r == "/route.ntr":
        return _json(h, 501, {"blad": "liczenie tras online jeszcze niedostępne"})
    return _json(h, 404, {"blad": "nie ma"})


def _cialo(h, limit=65536):
    n = int(h.headers.get("Content-Length") or 0)
    try:
        return json.loads(h.rfile.read(min(n, limit)) or b"{}") if n else {}
    except ValueError:
        return {}


def _gui(h, metoda, path, q):
    r = path[len("/api/apex"):]
    ip = _ip(h)
    # bez sesji: stan minimalny, logowanie, pierwsze ustawienie PIN-u
    if metoda == "GET" and r == "/stan" and not A.sesja_ok(h):
        return _json(h, 200, {"zalogowany": False, "pin_ustawiony": A.pin_ustawiony()})
    if metoda == "POST" and r == "/login":
        return _json(h, 200, {"ok": True, "sesja": A.zaloguj(str(_cialo(h).get("pin") or ""), ip)})
    if metoda == "POST" and r == "/pin" and not A.pin_ustawiony():
        pin = str(_cialo(h).get("pin") or "")
        A.ustaw_pin(pin)
        return _json(h, 200, {"ok": True, "sesja": A.zaloguj(pin, ip)})
    if not A.sesja_ok(h):
        return _json(h, 401, {"blad": "zaloguj się PIN-em"})
    if metoda == "GET" and r == "/stan":
        u = A.ust()
        b = A.biezaca()
        return _json(h, 200, {"zalogowany": True, "pin_ustawiony": True, "wersje": A.lista(),
                              "biezaca": b["versionCode"] if b else None, "tomtom_ustawiony": bool(u.get("tomtomKey")),
                              "klucz_app_ustawiony": bool(u.get("kluczApp")), "kontakt": A.kontakt,
                              "dzienniki": A.dzienniki()})
    if metoda == "GET" and r == "/sekrety":
        u = A.ust()
        return _json(h, 200, {"tomtomKey": u.get("tomtomKey") or "", "kluczApp": u.get("kluczApp") or ""})
    if metoda == "POST" and r == "/pin":
        d = _cialo(h)
        A.ustaw_pin(str(d.get("pin") or ""))
        return _json(h, 200, {"ok": True})
    if metoda == "POST" and r == "/wgraj":
        def liczba(k):
            try:
                return int(q.get(k, [""])[0])
            except ValueError:
                return None
        meta = A.przyjmij(h, liczba("vc"), (q.get("vn", [""])[0] or "").strip()[:40], q.get("wymus", ["0"])[0] == "1")
        return _json(h, 200, {"ok": True, "wersja": meta})
    if metoda == "POST" and r == "/biezaca":
        A.ustaw_biezaca(int(_cialo(h).get("versionCode", -1)))
        return _json(h, 200, {"ok": True})
    if metoda == "POST" and r == "/usun":
        d = _cialo(h)
        if d.get("potwierdz") is not True:
            raise BladApex("Brak potwierdzenia usunięcia.")
        A.usun(int(d.get("versionCode", -1)), d.get("wymus") is True)
        return _json(h, 200, {"ok": True})
    if metoda == "POST" and r == "/ustawienia":
        d = _cialo(h)
        u = A.ust()
        if "tomtomKey" in d:
            t = str(d["tomtomKey"]).strip()
            if len(t) > 200 or re.search(r"\s", t):
                raise BladApex("Klucz TomTom wygląda źle (spacje albo za długi).")
            u["tomtomKey"] = t
        if "kluczApp" in d:
            k = str(d["kluczApp"]).strip()
            if k == "generuj":
                k = secrets.token_urlsafe(24)
            if len(k) < 12 or len(k) > 200 or re.search(r"\s", k):
                raise BladApex("Klucz aplikacji: min. 12 znaków, bez spacji.")
            u["kluczApp"] = k
        A.zapisz_ust(u)
        return _json(h, 200, {"ok": True})
    m = re.fullmatch(r"/dziennik/(apex-[\w.\-]+\.(?:txt|zip))", r)
    if metoda == "GET" and m:
        p = os.path.join(A.dz, m.group(1))
        if not os.path.isfile(p):
            return _json(h, 404, {"blad": "nie ma"})
        if q.get("podglad") and p.endswith(".txt"):
            with open(p, "rb") as f:
                dane = f.read()
            t = dane[-PODGLAD_B:].decode("utf-8", "replace")
            if len(dane) > PODGLAD_B:
                t = "… (pokazuję końcówkę, %d KB od końca)\n" % (PODGLAD_B // 1024) + t
            b = t.encode()
            h.send_response(200)
            h.send_header("Content-Type", "text/plain; charset=utf-8")
            h.send_header("Content-Length", str(len(b)))
            h.end_headers()
            h.wfile.write(b)
            return
        return _plik(h, p, "application/octet-stream", os.path.getsize(p), m.group(1))
    return _json(h, 404, {"blad": "nie ma"})
