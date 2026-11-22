"""Stacja ekranu bez ekranu i bez GitHuba: port = pty, esptool = atrapa, repozytorium budów = lokalny serwer."""
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
T = tempfile.mkdtemp(prefix="stacja-test-")
M, SL = os.openpty()
os.symlink(os.ttyname(SL), os.path.join(T, "ttyACM0"))
ATR = os.path.join(T, "esptool_atrapa.py")
with open(ATR, "w") as f:
    f.write("import sys,time; open(sys.argv[0]+'.arg','w').write(' '.join(sys.argv[1:])); time.sleep(0.5); print('Writing...'); print('Hash of data verified.'); print('Hard resetting via RTS pin...')\n")
with open(os.path.join(T, "klucz"), "w") as f:
    f.write("testowy")
BIN = {"2.15.0": b"A" * 3000, "2.16.0": b"B" * 3000}
GH = {"wersja": "2.15.0", "zla_suma": False}


class Repo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        assert self.headers["Authorization"] == "Bearer testowy"
        v = GH["wersja"]
        nazwa = "nt1100-ekran5-%s-app-0x10000.bin" % v
        suma = "0" * 64 if GH["zla_suma"] else hashlib.sha256(BIN[v]).hexdigest()
        p = self.path.split("?")[0]
        if p.endswith("/contents/"):
            d = json.dumps([{"name": n, "type": "file"} for n in ("SHA256SUMS", "WYNIK.txt", nazwa)]).encode()
        elif p.endswith("/SHA256SUMS"):
            d = ("%s  %s\n" % (suma, nazwa)).encode()
        elif p.endswith("/WYNIK.txt"):
            d = ("wersja %s\ncommit 645ba723147a10f12edfc494b4df02359ecdb696\nwynik ok\nczas 2026-11-13T23:22:24+00:00\n" % v).encode()
        elif p.endswith("/" + nazwa):
            d = BIN[v]
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(d)


GHS = ThreadingHTTPServer(("127.0.0.1", 0), Repo)
threading.Thread(target=GHS.serve_forever, daemon=True).start()
os.environ.update(STACJA_KATALOG=os.path.join(T, "st"), STACJA_ESPTOOL="%s %s" % (sys.executable, ATR),
                  STACJA_PORT=os.path.join(T, "ttyACM*"), STACJA_KLUCZ=os.path.join(T, "klucz"),
                  STACJA_API="http://127.0.0.1:%d" % GHS.server_port)
sys.path.insert(0, os.path.join(HERE, "..", "stacja"))
import stacja as S  # noqa: E402


def czekaj(war, s=10):
    for _ in range(int(s / 0.1)):
        if war():
            return True
        time.sleep(0.1)
    return False


class Stacja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d/" % cls.srv.server_port

    def post(self, p, b=None):
        r = urllib.request.Request(self.url + p, data=json.dumps(b or {}).encode(), method="POST",
                                   headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(r).read())

    def test_calosc(self):
        # 1. pobranie budowy z repozytorium (suma zgodna), druga wersja, zła suma odrzucona
        self.assertEqual(S.sprawdz_budowy(), "2.15.0")
        self.assertIsNone(S.sprawdz_budowy())  # już jest
        GH.update(wersja="2.16.0", zla_suma=True)
        self.assertIsNone(S.sprawdz_budowy())
        self.assertIn("inną sumę", S.STAN["blad_budow"])
        GH["zla_suma"] = False
        self.assertEqual(S.sprawdz_budowy(), "2.16.0")
        self.assertEqual([b["wersja"] for b in S.budowy()], ["2.16.0", "2.15.0"])
        self.assertEqual(S.budowy()[0]["commit"], "645ba72")
        # 2. strona i stan
        self.assertIn("Stacja ekranu", urllib.request.urlopen(self.url).read().decode())
        st = json.loads(urllib.request.urlopen(self.url + "api/stan").read())
        self.assertFalse(st["aktualizacja"]["przycisk"])  # brak jednostki .path w teście
        self.assertTrue(self.post("api/aktualizuj")["ok"])
        self.assertTrue(os.path.exists(os.path.join(T, "st", "aktualizuj")))
        self.assertTrue(json.loads(urllib.request.urlopen(self.url + "api/stan").read())["aktualizacja"]["czeka"])
        os.remove(os.path.join(T, "st", "aktualizuj"))
        self.assertEqual(st["najnowsza"]["wersja"], "2.16.0")
        self.assertTrue(st["port"])
        # 3. wgranie poprzedniej wersji z nagrywaniem od startu
        self.post("api/wgraj", {"wersja": "2.15.0"})
        self.assertTrue(czekaj(lambda: S.ostatnio_wgrana() == "2.15.0"))
        arg = open(ATR + ".arg").read()
        self.assertIn("--before usb-reset", arg)
        self.assertIn("write-flash 0x10000", arg)
        self.assertIsNotNone(S.STAN["nagrywa"])
        time.sleep(0.8)
        # jeden start = baner ROM z linią rst:0x (tak wygląda na prawdziwym ekranie); pierwsze 10 s nie liczy się do klatek
        os.write(M, b"ESP-ROM:esp32p4-eco2-20240710\nrst:0x7 (HP_SYS_HP_WDT_RESET),boot:0x20c (SPI_FAST_FLASH_BOOT)\n"
                    b"NT1100 Ekran 2.15.0, PSRAM 32768 KB, karta ok\n"
                    b"pamiec 10 s: ram 200 KB blok 100 KB min 115 KB, psram 30000 KB, klatki 6, demo 50.0 km/h\n"
                    b"pamiec 20 s: ram 190 KB blok 90 KB min 111 KB, psram 30000 KB, klatki 100, demo 50.0 km/h\n"
                    b"pamiec 30 s: ram 190 KB blok 90 KB min 112 KB, psram 30000 KB, klatki 120, demo 50.0 km/h\n")
        time.sleep(0.8)
        self.post("api/stop")
        dz = S.dzienniki()
        self.assertEqual(dz[0]["wersja"], "2.15.0")
        self.assertEqual(dz[0]["restarty"], 0)
        self.assertEqual(dz[0]["klatki_min"], [600, 720])
        self.assertEqual(dz[0]["ram_min_kb"], 111)
        t = urllib.request.urlopen(self.url + "claude/" + dz[0]["plik"]).read().decode()
        self.assertIn("wersja 2.15.0", t)
        self.assertIn("klatki/min 600–720", t)
        # 4. zła wersja i ścieżka spoza dzienników
        with self.assertRaises(urllib.error.HTTPError):
            self.post("api/wgraj", {"wersja": "../x"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.url + "d/..%2Fhistoria.jsonl")
        self.assertEqual(e.exception.code, 404)
        # 5. plik podmieniony w archiwum = odmowa
        p = S.budowy()[0]["sciezka"]
        with open(p, "ab") as f:
            f.write(b"x")
        self.assertFalse(S.wgraj())
        self.assertIn("NIE zgadza", S.STAN["komunikat"])
        # 6. nieudane wgranie: końcówka esptool do pokazania i skopiowania
        S.wpis_historii(co="wgranie", wersja="2.16.0", port="/dev/ttyACM0", wynik="blad")
        with open(os.path.join(S.KAT, "wgrywanie-blad-20991231-000000.txt"), "w") as f:
            f.write("esptool v5\nWriting at 0x10000 (1 %)\rWriting at 0x20000 (2 %)\nA fatal error occurred: Packet content transfer stopped\n")
        b = S.stan()["blad_wgrania"]
        self.assertIn("Packet content transfer stopped", b)
        self.assertIn("Writing at 0x20000", b)
        self.assertNotIn("0x10000 (1", b)
        # 7. dziennik z karty: polecenie DZIENNIK na porcie, odpowiedź w pliku „demo-karta-…”
        def ekran():
            got = b""
            while b"DZIENNIK" not in got:
                got += os.read(M, 64)
            os.write(M, b"szum\n=== KARTA POCZATEK ===\n=== plik awarie.txt (5 B, od 0) ===\npc 4001 ra 4002\n=== plik funkcje.txt (3 B, od 0) ===\nabc\n=== KARTA KONIEC ===\n")
        th = threading.Thread(target=ekran, daemon=True)
        th.start()
        S.STAN["komunikat"] = ""
        self.assertTrue(S.pobierz_karte())
        th.join(2)
        nk = sorted(f for f in os.listdir(S.DZIENNIKI) if f.startswith("demo-karta-"))
        self.assertTrue(nk)
        tk = S.dla_claude(nk[-1])
        self.assertIn("pc 4001 ra 4002", tk)
        self.assertIn("abc", tk)
        # „Pokaż Claude” mieści się w jednej wiadomości
        self.assertLess(len(S.dla_claude(dz[0]["plik"])), 9500)


if __name__ == "__main__":
    unittest.main()
