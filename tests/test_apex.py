"""Stacja jako serwer aplikacji Apex: odczyt wersji z APK, klucz aplikacji (401), manifest i Range (206/416),
konfiguracja, dziennik z tabletu, wgrywanie z walidacją za PIN-em, tylko LAN."""
import http.client
import importlib.util
import io
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "stacja"))
import apex  # noqa: E402

# osobna kopia modułu stacja (własny katalog), żeby nie kolidować z test_stacja, który ustawia środowisko przy imporcie
_T = tempfile.mkdtemp(prefix="apex-test-")
os.environ.setdefault("STACJA_KATALOG", _T)
_spec = importlib.util.spec_from_file_location("stacja_dla_apex", os.path.join(HERE, "..", "stacja", "stacja.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def axml(pakiet, vc, vn, utf8):
    """Minimalny binarny AndroidManifest.xml: <manifest package versionCode versionName>."""
    napisy = ["manifest", "package", "versionCode", "versionName", pakiet, vn]

    def jeden(s):
        if utf8:
            b = s.encode()
            return bytes([len(s), len(b)]) + b + b"\0"
        return struct.pack("<H", len(s)) + s.encode("utf-16-le") + b"\0\0"
    dane, offs = b"", []
    for s in napisy:
        offs.append(len(dane))
        dane += jeden(s)
    while len(dane) % 4:
        dane += b"\0"
    start = 28 + 4 * len(napisy)
    pool = struct.pack("<HHIIIIII", 1, 28, start + len(dane), len(napisy), 0, 0x100 if utf8 else 0, start, 0)
    pool += b"".join(struct.pack("<I", o) for o in offs) + dane
    # atrybuty: ns, name, raw, size/res0/type, data
    atr = [(0xFFFFFFFF, 1, 4, 8, 0, 3, 4),          # package = ciąg 4
           (0xFFFFFFFF, 2, 0xFFFFFFFF, 8, 0, 0x10, vc),  # versionCode = int
           (0xFFFFFFFF, 3, 5, 8, 0, 3, 5)]            # versionName = ciąg 5
    el = struct.pack("<HHIII", 0x102, 16, 36 + 20 * len(atr), 1, 0xFFFFFFFF)
    el += struct.pack("<IIHHHHHH", 0xFFFFFFFF, 0, 20, 20, len(atr), 0, 0, 0)
    for a in atr:
        el += struct.pack("<IIIHBBI", *a)
    cialo = pool + el
    return struct.pack("<HHI", 3, 8, 8 + len(cialo)) + cialo


def apk(pakiet="pl.nt1100", vc=2, vn="0.2.0", utf8=True, manifest=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        if manifest:
            z.writestr("AndroidManifest.xml", axml(pakiet, vc, vn, utf8))
        z.writestr("classes.dex", b"dex" * 1000)
    return b.getvalue()


class Apex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kat = tempfile.mkdtemp(prefix="apex-dane-")
        apex.otworz(cls.kat)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_port

    def zadaj(self, metoda, sciezka, dane=None, naglowki=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(naglowki or {})
        if isinstance(dane, (dict, list)):
            dane = json.dumps(dane).encode()
            h.setdefault("Content-Type", "application/json")
        c.request(metoda, sciezka, body=dane, headers=h)
        r = c.getresponse()
        t = r.read()
        c.close()
        return r.status, dict(r.getheaders()), t

    def js(self, *a, **k):
        s, h, t = self.zadaj(*a, **k)
        return s, json.loads(t or b"{}")

    # ---- odczyt wersji z APK
    def test_manifest_utf8_i_utf16(self):
        for u8 in (True, False):
            m = apex.czytaj_manifest(axml("pl.nt1100", 17, "0.3.1-ą", u8))
            self.assertEqual((m["pakiet"], m["versionCode"], m["versionName"]), ("pl.nt1100", 17, "0.3.1-ą"))
        p = os.path.join(self.kat, "t.apk")
        with open(p, "wb") as f:
            f.write(apk(vc=9, vn="1.0"))
        self.assertEqual(apex.czytaj_apk(p)["versionCode"], 9)
        with open(p, "wb") as f:
            f.write(b"to nie zip")
        with self.assertRaises(ValueError):
            apex.czytaj_apk(p)
        with open(p, "wb") as f:
            f.write(apk(manifest=False))
        with self.assertRaises(ValueError):
            apex.czytaj_apk(p)

    # ---- całość
    def test_calosc(self):
        # klucz aplikacji nie ustawiony albo zły = 401 wszędzie
        for sc in ("/api/nav/apex/app/manifest.json", "/api/nav/apex/app/apex.apk", "/api/nav/apex/config"):
            self.assertEqual(self.zadaj("GET", sc)[0], 401)
            self.assertEqual(self.zadaj("GET", sc, naglowki={"X-Klucz": "cokolwiek"})[0], 401)
        self.assertEqual(self.zadaj("POST", "/api/nav/apex/log", b"x")[0], 401)
        # GUI: bez PIN-u tylko stan minimalny; pierwszy PIN daje sesję
        self.assertEqual(self.js("GET", "/api/apex/stan")[1], {"zalogowany": False, "pin_ustawiony": False})
        self.assertEqual(self.zadaj("GET", "/api/apex/sekrety")[0], 401)
        self.assertEqual(self.js("POST", "/api/apex/pin", {"pin": "12"})[0], 400)
        s, j = self.js("POST", "/api/apex/pin", {"pin": "4821"})
        self.assertEqual(s, 200)
        G = {"X-Sesja": j["sesja"]}
        self.assertEqual(self.js("POST", "/api/apex/pin", {"pin": "0000"})[0], 401)  # drugi raz bez sesji nie wolno
        self.assertEqual(self.js("POST", "/api/apex/login", {"pin": "zly"})[0], 401)
        self.assertEqual(self.js("POST", "/api/apex/login", {"pin": "4821"})[0], 200)
        # klucze
        self.assertEqual(self.js("POST", "/api/apex/ustawienia", {"kluczApp": "krotki"}, G)[0], 400)
        self.assertEqual(self.js("POST", "/api/apex/ustawienia", {"kluczApp": "generuj", "tomtomKey": "TT-123"}, G)[0], 200)
        sek = self.js("GET", "/api/apex/sekrety", naglowki=G)[1]
        K = {"X-Klucz": sek["kluczApp"]}
        self.assertGreaterEqual(len(sek["kluczApp"]), 20)
        st = self.js("GET", "/api/apex/stan", naglowki=G)[1]
        self.assertTrue(st["tomtom_ustawiony"] and st["klucz_app_ustawiony"])
        self.assertNotIn("TT-123", json.dumps(st))  # stan nie zdradza kluczy
        self.assertEqual(self.js("GET", "/api/nav/apex/config", naglowki=K)[1], {"tomtomKey": "TT-123"})
        # brak wersji: 404
        self.assertEqual(self.zadaj("GET", "/api/nav/apex/app/manifest.json", naglowki=K)[0], 404)
        # walidacja wgrywania
        W = lambda b, q="": self.js("POST", "/api/apex/wgraj" + q, b, G)  # noqa: E731
        self.assertEqual(W(apk(pakiet="com.inny"))[0], 400)
        self.assertIn("pakiet", W(apk(pakiet="com.inny"))[1]["blad"])
        self.assertEqual(W(b"nie apk")[0], 400)
        self.assertEqual(W(apk(manifest=False))[0], 400)
        s, j = W(apk(vc=5, vn="0.1.0"))
        self.assertEqual((s, j["wersja"]["versionCode"], j["wersja"]["versionName"]), (200, 5, "0.1.0"))
        self.assertEqual(W(apk(vc=5, vn="0.1.0b"))[0], 409)   # równy
        self.assertEqual(W(apk(vc=3, vn="0.0.9"))[0], 409)    # niższy
        self.assertEqual(W(apk(vc=3, vn="0.0.9"), "?wymus=1")[0], 200)  # świadomie
        self.assertEqual(W(apk(vc=6, vn="0.2.0", utf8=False))[0], 200)
        # wersja z formularza, gdy plik nieczytelny (zip bez manifestu) – tylko z „wymuś”
        self.assertEqual(W(apk(manifest=False), "?vc=7&vn=0.3.0")[0], 400)
        self.assertEqual(W(apk(manifest=False), "?vc=7&vn=0.3.0&wymus=1")[0], 200)
        self.assertEqual([x["versionCode"] for x in self.js("GET", "/api/apex/stan", naglowki=G)[1]["wersje"]], [7, 6, 5, 3])
        # bieżąca = ostatnio wgrana; można ustawić inną
        m = self.js("GET", "/api/nav/apex/app/manifest.json", naglowki=K)[1]
        self.assertEqual((m["versionCode"], m["versionName"]), (7, "0.3.0"))
        self.assertEqual(self.js("POST", "/api/apex/biezaca", {"versionCode": 6}, G)[0], 200)
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/manifest.json", naglowki=K)
        m = json.loads(t)
        self.assertEqual(m["versionCode"], 6)
        pelny = apk(vc=6, vn="0.2.0", utf8=False)
        self.assertEqual((m["bytes"], len(m["sha256"])), (len(pelny), 64))
        # plik: 200 z długością, Range 206 / 416
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/apex.apk", naglowki=K)
        self.assertEqual((s, t, h["Accept-Ranges"], int(h["Content-Length"])), (200, pelny, "bytes", len(pelny)))
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/apex.apk", naglowki=dict(K, Range="bytes=10-19"))
        self.assertEqual((s, t, h["Content-Range"]), (206, pelny[10:20], "bytes 10-19/%d" % len(pelny)))
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/apex.apk", naglowki=dict(K, Range="bytes=%d-" % (len(pelny) - 5)))
        self.assertEqual((s, t), (206, pelny[-5:]))
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/apex.apk", naglowki=dict(K, Range="bytes=-7"))
        self.assertEqual((s, t), (206, pelny[-7:]))
        s, h, t = self.zadaj("GET", "/api/nav/apex/app/apex.apk", naglowki=dict(K, Range="bytes=%d-" % len(pelny)))
        self.assertEqual((s, h["Content-Range"]), (416, "bytes */%d" % len(pelny)))
        # usuwanie: z potwierdzeniem; bieżącej i jedynej nie bez „wymuś”
        self.assertEqual(self.js("POST", "/api/apex/usun", {"versionCode": 3}, G)[0], 400)
        self.assertEqual(self.js("POST", "/api/apex/usun", {"versionCode": 6, "potwierdz": True}, G)[0], 409)
        for vc in (3, 5, 7):
            self.assertEqual(self.js("POST", "/api/apex/usun", {"versionCode": vc, "potwierdz": True}, G)[0], 200)
        self.assertEqual(self.js("POST", "/api/apex/usun", {"versionCode": 6, "potwierdz": True}, G)[0], 409)  # jedyna i bieżąca
        self.assertEqual(self.js("POST", "/api/apex/usun", {"versionCode": 6, "potwierdz": True, "wymus": True}, G)[0], 200)
        self.assertEqual(self.zadaj("GET", "/api/nav/apex/app/manifest.json", naglowki=K)[0], 404)
        # dziennik z tabletu: tekst i zip, nazwa z datą i wersją aplikacji; limit 5 MB
        s, j = self.js("POST", "/api/nav/apex/log", b"linia 1\nlinia 2\n", dict(K, **{"User-Agent": "Apex/0.2.0"}))
        self.assertEqual(s, 200)
        self.assertRegex(j["plik"], r"^apex-\d{8}-\d{6}-v0\.2\.0\.txt$")
        s, j2 = self.js("POST", "/api/nav/apex/log", b"PK\x03\x04dane", dict(K, **{"User-Agent": "Apex/../x"}))
        self.assertTrue(j2["plik"].endswith(".zip") and "/" not in j2["plik"])
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/api/nav/apex/log")
        c.putheader("X-Klucz", K["X-Klucz"])
        c.putheader("Content-Length", str((5 << 20) + 1))
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()
        lst = self.js("GET", "/api/apex/stan", naglowki=G)[1]["dzienniki"]
        self.assertEqual(len(lst), 2)
        s, h, t = self.zadaj("GET", "/api/apex/dziennik/%s?podglad=1" % j["plik"], naglowki=G)
        self.assertEqual((s, t), (200, b"linia 1\nlinia 2\n"))
        s, h, t = self.zadaj("GET", "/api/apex/dziennik/" + j2["plik"], naglowki=G)
        self.assertEqual((s, t), (200, b"PK\x03\x04dane"))
        self.assertEqual(self.zadaj("GET", "/api/apex/dziennik/..%2f..%2fustawienia.json", naglowki=G)[0], 404)
        # ostatni kontakt tabletu
        k = self.js("GET", "/api/apex/stan", naglowki=G)[1]["kontakt"]
        self.assertTrue(k["ip"] == "127.0.0.1" and k["ts"])
        # route.ntr: 501; tylko LAN: ślad serwera pośredniego = 403
        self.assertEqual(self.zadaj("POST", "/api/nav/apex/route.ntr", b"{}", K)[0], 501)
        self.assertEqual(self.zadaj("GET", "/api/nav/apex/config", naglowki=dict(K, **{"X-Forwarded-For": "1.2.3.4"}))[0], 403)
        self.assertEqual(self.zadaj("GET", "/api/apex/stan", naglowki={"Cf-Connecting-Ip": "1.2.3.4"})[0], 403)
        # sekrety tylko w pliku 0600 w katalogu danych
        self.assertEqual(oct(os.stat(os.path.join(self.kat, "apex", "ustawienia.json")).st_mode & 0o777), "0o600")
        # strona
        s, h, t = self.zadaj("GET", "/apex")
        self.assertTrue(s == 200 and b"Wgraj APK" in t)

    def test_blokada_pinu(self):
        a = apex.Apex(tempfile.mkdtemp(prefix="apex-pin-"))
        a.ustaw_pin("1234")
        for _ in range(3):
            with self.assertRaises(apex.BladApex):
                a.zaloguj("0000", "10.0.0.5")
        with self.assertRaises(apex.BladApex):
            a.zaloguj("0000", "10.0.0.5")
        with self.assertRaises(apex.BladApex) as e:
            a.zaloguj("1234", "10.0.0.5")   # po 4 błędach nawet dobry PIN czeka
        self.assertEqual(e.exception.kod, 429)
        self.assertTrue(a.zaloguj("1234", "10.0.0.6"))  # inny adres nie jest zablokowany


if __name__ == "__main__":
    unittest.main()
