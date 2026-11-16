"""Zadania dzieci: pełny przebieg przez HTTP z atrapą Ollamy (AI) i atrapą Home Assistanta (powiadomienia)."""
import datetime as dt
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
T = tempfile.mkdtemp(prefix="zadania-test-")
POWIADOMIENIA = []
AI = {"pytania": []}
JPG = b"\xff\xd8\xff\xe0" + b"0" * 2000


class Atrapa(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        odp = json.dumps([{"domain": "light", "services": {"turn_on": {}}},
                          {"domain": "notify", "services": {"mobile_app_mama": {}, "persistent_notification": {},
                                                            "mobile_app_a": {}}}]).encode()
        self.send_response(200 if self.path == "/api/services" else 404)
        self.send_header("Content-Length", str(len(odp)))
        self.end_headers()
        self.wfile.write(odp)

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/api/services/notify/"):
            assert self.headers["Authorization"] == "Bearer tok"
            POWIADOMIENIA.append((self.path.rsplit("/", 1)[1], d))
            odp = b"[]"
        else:
            oai = self.path.endswith("/chat/completions")
            if oai:   # API zgodne z OpenAI → ten sam słownik co Ollama
                AI["klucz"] = self.headers.get("Authorization")
                m = d["messages"][0]["content"]
                if isinstance(m, list):
                    d = {"prompt": m[0]["text"], "images": [x["image_url"]["url"] for x in m[1:]]}
                else:
                    d = {"prompt": m}
            AI["pytania"].append(d)
            if "dziennika" in d["prompt"]:
                r = {"zadania": [{"przedmiot": "Matematyka", "tytul": "Zad. 3 i 4 str. 52", "opis": "zeszyt ćwiczeń",
                                  "termin": "2026-11-18", "rodzaj": "zadanie"},
                                 {"przedmiot": "Historia", "tytul": "Sprawdzian rozdz. 2", "termin": "zly", "rodzaj": "sprawdzian"},
                                 {"tytul": ""}]}
            elif "Pomagasz rodzicowi" in d["prompt"]:
                r = {"tytul": "Posprzątać biurko", "opis": "Pusty blat do 18:00.", "brakuje": ["termin", "co znaczy porządek"],
                     "kroki": ["Książki", "Kable"], "punkty": "12", "weryfikacja": "zdjecie", "dlaczego": "efekt widać",
                     "minuty": 0, "uwaga": "Pasuje do wieku."}
            elif "Przepisz wiernie" in d["prompt"]:
                r = {"tresc": "Ułamek to część całości. Licznik jest nad kreską, mianownik pod kreską.", "czytelne": True}
            elif "Ułóż" in d["prompt"] and "korepetytorem" in d["prompt"]:
                r = {"pytania": [{"p": "Co to jest licznik?", "odp": "Liczba nad kreską ułamkową."},
                                 {"p": "Co to jest mianownik?", "odp": "Liczba pod kreską."}, {"p": ""}]}
            elif "Sprawdź odpowiedź ucznia" in d["prompt"]:
                r = {"ocena": "dobrze" if "nad" in d["prompt"].split("Odpowiedź ucznia:")[1].split("Fragment materiału")[0] else "zle", "komentarz": "Komentarz."}
            elif "Pytanie ucznia:" in d["prompt"]:
                r = {"odpowiedz": "Mianownik mówi, na ile części dzielimy.", "z_materialu": "mianownik" in d["prompt"].split("Pytanie ucznia:")[1]}
            elif "pomocnikiem dziecka" in d["prompt"]:
                r = {"pierwszy_krok": "Zdejmij wszystko z blatu na łóżko", "wskazowki": ["Najpierw książki", "Potem kable", "a", "b"],
                     "minuty": "15", "otucha": "Dasz radę."}
            elif d.get("images"):
                r = {"werdykt": "raczej zrobione", "punkty": [{"ok": True, "tekst": "Pusty blat"},
                                                              {"ok": False, "tekst": "Kabel z lewej"}],
                     "dla_dziecka": "Prawie idealnie!"}
            else:
                r = {"kroki": ["Książki na półkę", "Kable zwinąć", "Wytrzeć blat"]}
            t = json.dumps(r, ensure_ascii=False)
            odp = json.dumps({"choices": [{"message": {"content": "```json\n" + t + "\n```"}}]} if oai
                             else {"response": t}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(odp)))
        self.end_headers()
        self.wfile.write(odp)


atr = ThreadingHTTPServer(("127.0.0.1", 0), Atrapa)
threading.Thread(target=atr.serve_forever, daemon=True).start()
ADR_ATR = "http://127.0.0.1:%d" % atr.server_address[1]
with open(os.path.join(T, "ha_token"), "w") as f:
    f.write("tok")
os.environ.update({"ZD_KATALOG": T, "ZD_HA_URL": ADR_ATR, "ZD_HA_TOKEN": os.path.join(T, "ha_token"),
                   "ZD_AI_URL": ADR_ATR, "ZD_ADRES": "http://dom:8092", "ZD_LOSOWE": "0"})
sys.path.insert(0, os.path.join(HERE, "..", "zadania"))
import zadania as Z  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), Z.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d" % srv.server_address[1]


def zapytaj(ses, sciezka, dane=None, typ="application/json", nag=None):
    h = {"X-Zadania-Sesja": ses} if ses else {}
    h.update(nag or {})
    body = None
    if dane is not None:
        body = dane if isinstance(dane, bytes) else json.dumps(dane).encode()
        h["Content-Type"] = typ
    req = urllib.request.Request(URL + sciezka, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, (json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def czekaj(f, s=5):
    k = time.time() + s
    while time.time() < k:
        if f():
            return True
        time.sleep(0.05)
    return False


class TestZadania(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Z.db()
        with Z.BLOKADA:
            a = Z.ex("INSERT INTO osoby(imie,rola,admin,kod) VALUES('Admin','dorosly',1,'kodadmin00')")
            cls.adm = Z.nowa_sesja(a)
        cls.kody = {}

        def dodaj(**kw):
            _, r = zapytaj(cls.adm, "/api/osoba", kw)
            cls.kody[r["id"]] = r["link"].rsplit("/", 1)[1]
            with Z.BLOKADA:
                return r["id"], Z.nowa_sesja(r["id"]), r["link"]
        cls.a_id, cls.a, _ = dodaj(imie="Dziecko A", rola="dziecko", powiadom="notify.mobile_app_a")
        cls.b_id, cls.b, _ = dodaj(imie="Dziecko B", rola="dziecko")
        cls.m_id, cls.m, _ = dodaj(imie="Mama", rola="dorosly", powiadom="mobile_app_mama")
        cls.i_id, cls.i, _ = dodaj(imie="Inny rodzic", rola="dorosly")
        cls.d_id, cls.d, ln = dodaj(imie="Dziadek", rola="dorosly")
        assert ln.startswith("http://dom:8092/k/")
        # Mama: A zleca+zatwierdza; Inny rodzic: B; Dziadek: A tylko podgląd; Admin: A zatwierdza (bez zlecania)
        for dor, dz, zl, za in ((cls.m_id, cls.a_id, 1, 1), (cls.i_id, cls.b_id, 1, 1), (cls.d_id, cls.a_id, 0, 0),
                                (1, cls.a_id, 0, 1)):
            s, _ = zapytaj(cls.adm, "/api/opieka", {"dorosly_id": dor, "dziecko_id": dz, "zleca": zl, "zatwierdza": za})
            assert s == 200

    def test_1_logowanie_linkiem(self):
        req = urllib.request.Request(URL + "/k/" + self.kody[self.b_id])

        class Bez(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            urllib.request.build_opener(Bez).open(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            tok = e.headers["Set-Cookie"].split("zd=")[1].split(";")[0]
            self.assertEqual(zapytaj(tok, "/api/stan")[1]["ja"]["imie"], "Dziecko B")
        self.assertEqual(zapytaj(None, "/api/stan")[0], 401)
        self.assertEqual(zapytaj("zlykodzlykod", "/api/stan")[0], 401)
        s, r = zapytaj(None, "/")
        self.assertEqual(s, 200)
        self.assertIn(b"Zadania", r)

    def test_2_role(self):
        _, st = zapytaj(self.m, "/api/stan")
        self.assertEqual([d["imie"] for d in st["dzieci"]], ["Dziecko A"])
        _, st = zapytaj(self.i, "/api/stan")
        self.assertEqual([d["imie"] for d in st["dzieci"]], ["Dziecko B"])
        self.assertNotIn("osoby", st)
        # Inny rodzic nie zleca dziecku A, dziadek tylko podgląda
        self.assertEqual(zapytaj(self.i, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "x"})[0], 403)
        self.assertEqual(zapytaj(self.d, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "x"})[0], 403)
        _, st = zapytaj(self.d, "/api/stan")
        self.assertEqual(st["dzieci"][0]["prawa"], {"zleca": False, "zatwierdza": False})
        # dziecko nie zleca, nie zarządza osobami
        self.assertEqual(zapytaj(self.a, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "x"})[0], 403)
        self.assertEqual(zapytaj(self.m, "/api/osoba", {"imie": "x", "rola": "dziecko"})[0], 403)

    def test_3_pelny_przebieg_ze_zdjeciem(self):
        POWIADOMIENIA.clear()
        termin = (dt.datetime.now() + dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        s, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Posprzątać biurko",
                                                "opis": "Pusty blat", "termin": termin, "punkty": 20, "ai_kroki": True})
        self.assertEqual(s, 200, r)
        zid = r["zadanie_id"]
        self.assertTrue(czekaj(lambda: POWIADOMIENIA))
        self.assertEqual(POWIADOMIENIA[0][0], "mobile_app_a")
        self.assertEqual(POWIADOMIENIA[0][1]["data"]["url"], "http://dom:8092/#z%d" % zid)
        # AI rozpisuje kroki
        self.assertTrue(czekaj(lambda: len(Z.q1("SELECT kroki FROM zadania WHERE id=?", zid)["kroki"]) > 5))
        _, st = zapytaj(self.a, "/api/stan")
        z = [x for x in st["zadania"] if x["id"] == zid][0]
        self.assertEqual(len(z["kroki"]), 3)
        self.assertNotIn("wymaga_zdjecia", z)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/kroki" % zid, {"i": 0, "z": True})[0], 200)
        # B nie widzi zadania A
        self.assertEqual(zapytaj(self.b, "/api/zadanie/%d/kroki" % zid, {"i": 0, "z": True})[0], 403)
        # bez zdjęcia nie wyśle
        s, r = zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})
        self.assertEqual((s, r.get("potrzebne_zdjecie")), (409, True))
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/zdjecie/po" % zid, b"nie zdjecie", "image/jpeg")[0], 415)
        s, r = zapytaj(self.a, "/api/zadanie/%d/zdjecie/po" % zid, JPG, "image/jpeg")
        self.assertEqual(s, 200)
        pid = r["id"]
        self.assertTrue(czekaj(lambda: Z.q1("SELECT ocena_stan FROM zadania WHERE id=?", zid)["ocena_stan"] == "gotowa"))
        _, st = zapytaj(self.m, "/api/stan")
        z = [x for x in st["zadania"] if x["id"] == zid][0]
        self.assertEqual(z["ocena"]["werdykt"], "raczej_zrobione")
        self.assertEqual(len(z["ocena"]["punkty"]), 2)
        self.assertIn("images", AI["pytania"][-1])
        self.assertIn("Pusty blat", AI["pytania"][-1]["prompt"])
        # zdjęcie widzą: dziecko, mama, dziadek; nie widzi inny rodzic
        self.assertEqual(zapytaj(self.d, "/api/zdjecie/%d" % pid)[0], 200)
        self.assertEqual(zapytaj(self.i, "/api/zdjecie/%d" % pid)[0], 404)
        POWIADOMIENIA.clear()
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {"komentarz": "kabel od lampki"})[0], 200)
        self.assertTrue(czekaj(lambda: POWIADOMIENIA))
        self.assertEqual(POWIADOMIENIA[0][0], "mobile_app_mama")   # admin bez usługi powiadomień – tylko mama
        # dziadek (podgląd) nie zatwierdzi
        self.assertEqual(zapytaj(self.d, "/api/zadanie/%d/decyzja" % zid, {"decyzja": "zatwierdz"})[0], 403)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/zdjecie/po" % zid, JPG, "image/jpeg")[0], 409)
        s, r = zapytaj(self.m, "/api/zadanie/%d/decyzja" % zid, {"decyzja": "zatwierdz", "slowo": "Super!"})
        self.assertEqual((s, r["punkty"]), (200, 20))
        self.assertEqual(zapytaj(self.m, "/api/zadanie/%d/decyzja" % zid, {"decyzja": "zatwierdz"})[0], 409)
        self.assertEqual(Z.saldo(self.a_id), 20)
        self.assertEqual(zapytaj(self.m, "/api/zadanie/%d/usun" % zid, {})[0], 409)

    def test_4_poprawka_i_czesciowo(self):
        _, r = zapytaj(self.i, "/api/zadanie", {"dziecko_id": self.b_id, "tytul": "Zeszyt angielski", "weryfikacja": "zeszyt",
                                                "punkty": 15, "kroki": ["Ćwiczenie 3"]})
        zid = r["zadanie_id"]
        zapytaj(self.b, "/api/zadanie/%d/zdjecie/po" % zid, JPG, "image/jpeg")
        self.assertEqual(zapytaj(self.b, "/api/zadanie/%d/wyslij" % zid, {})[0], 200)
        zapytaj(self.i, "/api/zadanie/%d/decyzja" % zid, {"decyzja": "poprawka", "slowo": "Brakuje ćw. 4"})
        self.assertEqual(Z.q1("SELECT stan FROM zadania WHERE id=?", zid)["stan"], "do_poprawki")
        self.assertEqual(zapytaj(self.b, "/api/zadanie/%d/wyslij" % zid, {})[0], 200)
        _, r = zapytaj(self.i, "/api/zadanie/%d/decyzja" % zid, {"decyzja": "czesciowo"})
        self.assertEqual(r["punkty"], 7)
        self.assertEqual(Z.saldo(self.b_id), 7)

    def test_5_zaufanie_losowe_i_minutnik(self):
        _, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Pościel", "weryfikacja": "zaufanie",
                                                "punkty": 2, "kroki": ["x"]})
        zid = r["zadanie_id"]
        with Z.BLOKADA:
            Z.ex("UPDATE zadania SET wymaga_zdjecia=1 WHERE id=?", zid)
        s, r = zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})
        self.assertEqual((s, r.get("losowe")), (409, True))
        with Z.BLOKADA:
            Z.ex("UPDATE zadania SET wymaga_zdjecia=0 WHERE id=?", zid)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})[0], 200)
        _, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Czytanie", "weryfikacja": "minutnik",
                                                "minuty": 20, "kroki": ["x"]})
        zid = r["zadanie_id"]
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})[0], 409)
        zapytaj(self.a, "/api/zadanie/%d/start" % zid, {})
        s, r = zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})
        self.assertEqual(s, 409)
        self.assertIn("zostalo", r)
        start = Z.iso(Z.teraz() - dt.timedelta(minutes=21))
        with Z.BLOKADA:
            Z.ex("UPDATE zadania SET start=? WHERE id=?", start, zid)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})[0], 200)

    def test_6_powtarzane_i_pula(self):
        _, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Zęby", "pora": "rano", "dni": "1234567",
                                                "godzina": "08:00", "weryfikacja": "zaufanie", "punkty": 1, "kroki": ["x"]})
        self.assertTrue(r["szablon_id"] and r["zadanie_id"])
        self.assertEqual(Z.wygeneruj(), [])          # drugi raz nie dubluje
        jutro = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        self.assertEqual(len(Z.wygeneruj(jutro)), 1)
        _, st = zapytaj(self.a, "/api/stan")
        self.assertFalse([z for z in st["zadania"] if z["dzien"] == jutro])   # jutrzejszych jeszcze nie widać
        zapytaj(self.m, "/api/szablon/%d/wylacz" % r["szablon_id"], {})
        self.assertEqual(Z.wygeneruj((dt.date.today() + dt.timedelta(days=2)).isoformat()), [])
        _, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Odkurzyć auto", "pula": True,
                                                "punkty": 30, "kroki": ["x"]})
        zid = r["zadanie_id"]
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wyslij" % zid, {})[0], 409)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wez" % zid, {})[0], 200)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/wez" % zid, {})[0], 409)
        self.assertEqual(Z.q1("SELECT dzien FROM zadania WHERE id=?", zid)["dzien"], Z.dzis())

    def test_7_nagrody_i_wymiana(self):
        with Z.BLOKADA:
            Z.ex("INSERT INTO punkty(dziecko_id,ile,powod,ts) VALUES(?,?,?,?)", self.a_id, 100, "test", Z.iso(Z.teraz()))
        s0 = Z.saldo(self.a_id)
        _, r = zapytaj(self.m, "/api/nagroda", {"dziecko_id": self.a_id, "nazwa": "Bajka", "koszt": 30})
        nid = r["id"]
        self.assertEqual(zapytaj(self.i, "/api/nagroda", {"dziecko_id": self.a_id, "nazwa": "x", "koszt": 1})[0], 403)
        _, r = zapytaj(self.a, "/api/nagroda", {"nazwa": "Rower", "koszt": 5000, "cel": True})
        self.assertEqual(Z.q1("SELECT stan FROM nagrody WHERE id=?", r["id"])["stan"], "propozycja")
        zapytaj(self.m, "/api/nagroda/%d/decyzja" % r["id"], {"decyzja": "tak", "koszt": 1000})
        self.assertEqual(Z.q1("SELECT koszt, stan FROM nagrody WHERE id=?", r["id"]), {"koszt": 1000, "stan": "aktywna"})
        self.assertEqual(zapytaj(self.a, "/api/wymiana", {"nagroda_id": r["id"]})[0], 409)   # za mało punktów
        _, w = zapytaj(self.a, "/api/wymiana", {"nagroda_id": nid})
        _, st = zapytaj(self.a, "/api/stan")
        self.assertEqual(st["dzieci"][0]["zarezerwowane"], 30)
        self.assertEqual(zapytaj(self.d, "/api/wymiana/%d/decyzja" % w["id"], {"decyzja": "tak"})[0], 403)
        zapytaj(self.m, "/api/wymiana/%d/decyzja" % w["id"], {"decyzja": "tak"})
        self.assertEqual(Z.saldo(self.a_id), s0 - 30)
        self.assertEqual(zapytaj(self.m, "/api/wymiana/%d/decyzja" % w["id"], {"decyzja": "tak"})[0], 409)

    def test_8_seria_i_przypomnienie(self):
        nowe = Z.ex("INSERT INTO osoby(imie,rola,kod,powiadom) VALUES('C','dziecko','kodc000000','mobile_app_c')")
        d = dt.date.today()
        for i, stan in ((1, "zatwierdzone"), (2, "wyslane"), (4, "zatwierdzone"), (9, "do_zrobienia")):
            Z.ex("INSERT INTO zadania(dziecko_id,tytul,dzien,stan) VALUES(?,?,?,?)", nowe, "t",
                 (d - dt.timedelta(days=i)).isoformat(), stan)
        self.assertEqual(Z.seria(nowe), 3)   # dzień 3 bez zadań nie przerywa; dzień 9 dalej niż 3 puste dni
        POWIADOMIENIA.clear()
        Z.ex("INSERT INTO zadania(dziecko_id,tytul,dzien,stan,termin) VALUES(?,?,?,?,?)", nowe, "Pies", d.isoformat(),
             "do_zrobienia", Z.iso(Z.teraz() + dt.timedelta(minutes=30)))
        self.assertEqual(Z.przypomnienia(), 1)
        self.assertEqual(Z.przypomnienia(), 0)
        self.assertTrue(czekaj(lambda: POWIADOMIENIA))

    def test_9_osoby_i_nowy_link(self):
        zapytaj(self.adm, "/api/osoba/%d" % self.d_id, {"nowy_kod": True})
        self.assertEqual(zapytaj(self.d, "/api/stan")[0], 401)      # nowy link kasuje stare sesje
        with Z.BLOKADA:
            type(self).d = Z.nowa_sesja(self.d_id)
        self.assertEqual(zapytaj(self.d, "/api/stan")[0], 200)
        self.assertEqual(zapytaj(self.adm, "/api/osoba/1", {"usun": True})[0], 409)
        self.assertEqual(zapytaj(self.adm, "/api/opieka", {"dorosly_id": self.a_id, "dziecko_id": self.b_id})[0], 400)
        _, st = zapytaj(self.adm, "/api/stan")
        self.assertTrue(st["ja"]["admin"])
        self.assertIn("osoby", st)
        self.assertTrue(st["ha"])
        self.assertTrue(st["klucz_dodatku"])

    def test_a_pin(self):
        oid = Z.ex("INSERT INTO osoby(imie,rola,kod) VALUES('P','dziecko','kodp0000000')")
        Z.ex("INSERT INTO opieka(dorosly_id,dziecko_id,zleca,zatwierdza) VALUES(?,?,1,1)", self.m_id, oid)
        ses = Z.nowa_sesja(oid)
        _, st = zapytaj(ses, "/api/stan")
        self.assertFalse(st["ja"]["ma_pin"])
        self.assertEqual(zapytaj(ses, "/api/pin", {"pin": "12"})[0], 400)
        self.assertEqual(zapytaj(ses, "/api/pin", {"pin": "4321"})[0], 200)
        self.assertEqual(zapytaj(ses, "/api/pin", {"pin": "1111", "stary": "0000"})[0], 403)   # zmiana wymaga starego
        Z.ex("UPDATE osoby SET pin_bledy=0 WHERE id=?", oid)

        class Bez(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        with self.assertRaises(urllib.error.HTTPError) as e:    # link przy PIN-ie tylko podpowiada imię
            urllib.request.build_opener(Bez).open(URL + "/k/kodp0000000")
        self.assertIn("#zaloguj-%d" % oid, e.exception.headers["Location"])
        self.assertIsNone(e.exception.headers.get("Set-Cookie"))
        _, lg = zapytaj(None, "/api/logowanie")
        self.assertIn({"id": oid, "imie": "P", "ma_pin": True}, lg["osoby"])
        self.assertNotIn("kod", json.dumps(lg))
        r = urllib.request.urlopen(urllib.request.Request(URL + "/api/zaloguj", json.dumps({"osoba_id": oid, "pin": "4321"}).encode(),
                                                          {"Content-Type": "application/json"}))
        tok = r.headers["Set-Cookie"].split("zd=")[1].split(";")[0]
        self.assertEqual(zapytaj(None, "/api/stan", nag={"Cookie": "zd=" + tok})[0], 200)
        for _ in range(4):
            self.assertEqual(zapytaj(None, "/api/zaloguj", {"osoba_id": oid, "pin": "0000"})[0], 403)
        _, r = zapytaj(None, "/api/zaloguj", {"osoba_id": oid, "pin": "0000"})
        self.assertIn("zablokowane", r["blad"])
        self.assertEqual(zapytaj(None, "/api/zaloguj", {"osoba_id": oid, "pin": "4321"})[0], 429)
        self.assertEqual(zapytaj(self.i, "/api/osoba/%d/pin_reset" % oid, {})[0], 403)
        s, r = zapytaj(self.m, "/api/osoba/%d/pin_reset" % oid, {})
        self.assertEqual(s, 200)
        self.assertTrue(r["link"].endswith("/k/kodp0000000"))
        self.assertEqual(zapytaj(None, "/api/stan", nag={"Cookie": "zd=" + tok})[0], 401)   # sesje skasowane
        s, r = zapytaj(None, "/api/zaloguj", {"osoba_id": oid, "pin": "4321"})
        self.assertEqual((s, r.get("bez_pinu")), (409, True))

    def test_b_dodatek_ha(self):
        klucz = Z.klucz_dodatku(utworz=True)
        nag = {"X-Zadania-Klucz": klucz, "X-Zadania-HA-User": "ha-uzytkownik-1", "X-Zadania-HA-Nazwa": "Zosia HA",
               "X-Zadania-Panel": "/hassio/ingress/abc_zadania"}
        s, r = zapytaj(None, "/api/stan", nag=nag)
        self.assertEqual((s, r.get("logowanie")), (401, True))
        _, lg = zapytaj(None, "/api/logowanie", nag=nag)
        self.assertEqual((lg["przez_ha"], lg["konto_ha"]), (True, "Zosia HA"))
        self.assertFalse(zapytaj(None, "/api/logowanie", nag=dict(nag, **{"X-Zadania-Klucz": "zly"}))[1]["przez_ha"])
        _, st = zapytaj(self.adm, "/api/stan")
        self.assertIn("ha-uzytkownik-1", [k["id"] for k in st["ha_konta"]])
        self.assertEqual(zapytaj(self.adm, "/api/osoba/%d" % self.a_id, {"ha_user": "nieznane"})[0], 400)
        self.assertEqual(zapytaj(self.adm, "/api/osoba/%d" % self.a_id, {"ha_user": "ha-uzytkownik-1"})[0], 200)
        s, st = zapytaj(None, "/api/stan", nag=nag)
        self.assertEqual((s, st["ja"]["imie"], st["ja"]["przez_ha"]), (200, "Dziecko A", True))
        self.assertEqual(Z.ust("panel_ha"), "/hassio/ingress/abc_zadania")
        Z.ustaw_pin(self.a_id, "9999")
        self.assertEqual(zapytaj(None, "/api/pin", {"pin": "1234"}, nag=nag)[0], 200)   # w HA bez starego PIN-u
        POWIADOMIENIA.clear()
        Z.powiadom(Z.osoba(self.a_id), "t", "m")
        self.assertTrue(czekaj(lambda: POWIADOMIENIA))
        self.assertEqual(POWIADOMIENIA[0][1]["data"]["url"], "/hassio/ingress/abc_zadania")
        self.assertEqual(zapytaj(None, "/api/dodatek/token", {"token": "tok2"}, nag={"X-Zadania-Klucz": "zly"})[0], 403)
        self.assertEqual(zapytaj(None, "/api/dodatek/token", {"token": "tok2"}, nag={"X-Zadania-Klucz": klucz})[0], 200)
        with open(os.path.join(T, "ha_token")) as f:
            self.assertEqual(f.read(), "tok2")
        self.assertEqual(zapytaj(None, "/api/wyloguj", {}, nag=nag)[0], 200)
        self.assertEqual(zapytaj(None, "/api/stan", nag=nag)[0], 401)

    def test_c_zrzut_doprecyzuj_katalog(self):
        s, r = zapytaj(self.m, "/api/zrzut", JPG, "image/jpeg")
        self.assertEqual(s, 200, r)
        self.assertEqual(len(r["zadania"]), 2)
        self.assertEqual(r["zadania"][0]["tytul"], "Matematyka: Zad. 3 i 4 str. 52")
        self.assertEqual((r["zadania"][0]["termin"], r["zadania"][1]["termin"]), ("2026-11-18", ""))
        self.assertEqual(r["zadania"][1]["weryfikacja"], "minutnik")
        self.assertEqual(zapytaj(self.a, "/api/zrzut", JPG, "image/jpeg")[0], 403)
        self.assertEqual(zapytaj(self.m, "/api/zrzut", b"tekst", "image/jpeg")[0], 415)
        Z.ex("UPDATE osoby SET rok_ur=? WHERE id=?", dt.date.today().year - 13, self.a_id)
        s, r = zapytaj(self.m, "/api/doprecyzuj", {"dziecko_id": self.a_id, "tytul": "biurko"})
        self.assertEqual((s, r["punkty"], r["weryfikacja"], r["dlaczego"]), (200, 12, "zdjecie", "efekt widać"))
        self.assertIn("13 lat", AI["pytania"][-1]["prompt"])
        self.assertEqual(zapytaj(self.i, "/api/doprecyzuj", {"dziecko_id": self.a_id, "tytul": "x"})[0], 403)
        _, st = zapytaj(self.m, "/api/stan")
        self.assertEqual(st["dzieci"][0]["wiek"], 13)
        with open(os.path.join(HERE, "..", "zadania", "www", "katalog.json"), encoding="utf-8") as f:
            kat = json.load(f)
        self.assertGreaterEqual(len(kat), 45)
        for k in kat:
            self.assertIn(k["od"], (6, 10, 13))
            self.assertIn(k["weryfikacja"], Z.WERYFIKACJE)
            self.assertIn(k["pora"], Z.PORY)
            self.assertTrue(k["minuty"] or k["weryfikacja"] != "minutnik")
        self.assertEqual(zapytaj(None, "/katalog.json")[0], 200)

    def test_d_podsumowanie(self):
        s, r = zapytaj(None, "/api/podsumowanie")
        self.assertEqual(s, 200)
        self.assertIn("Dziecko A", [d["imie"] for d in r["dzieci"]])
        self.assertTrue({"punkty", "seria", "dzis", "dzis_zrobione", "tydzien_punkty"} <= set(r["dzieci"][0]))
        self.assertNotIn("kod", json.dumps(r))
        self.assertEqual(zapytaj(None, "/api/podsumowanie", nag={"X-Zadania-Klucz": "x"})[0], 401)   # nie przez dodatek

    def test_e_ai_openai(self):
        """llama-swap na Macu: …/v1/chat/completions, klucz z pliku, obraz jako data:, odpowiedź w ```json."""
        kl = os.path.join(T, "ai_klucz")
        with open(kl, "w") as f:
            f.write("sekret\n")
        stare = (Z.AI_URL, Z.AI_KLUCZ)
        Z.AI_URL, Z.AI_KLUCZ = ADR_ATR + "/v1", kl
        try:
            o = Z.ai_zapytaj("Oceń zadanie", ["QUJD"])
            self.assertEqual(o["dla_dziecka"], "Prawie idealnie!")
            self.assertEqual(AI["klucz"], "Bearer sekret")
            self.assertTrue(AI["pytania"][-1]["images"][0].startswith("data:image/jpeg;base64,QUJD"))
            self.assertEqual(Z.ai_zapytaj("Rozpisz")["kroki"][0], "Książki na półkę")
        finally:
            Z.AI_URL, Z.AI_KLUCZ = stare

    def test_f_wersja_1_3(self):
        """Kroki AI tylko na życzenie, lista telefonów z HA, historia punktów dla dziecka, podsumowanie tygodnia."""
        with open(os.path.join(T, "ha_token"), "w") as f:   # test dodatku podmienił token
            f.write("tok")
        Z._NOTIFY["ts"] = 0.0
        n = len(AI["pytania"])
        s, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Bez kroków", "weryfikacja": "zaufanie"})
        self.assertEqual(s, 200, r)
        time.sleep(0.4)
        self.assertEqual(Z.q1("SELECT kroki FROM zadania WHERE id=?", r["zadanie_id"])["kroki"], "[]")
        self.assertEqual(len(AI["pytania"]), n)
        _, st = zapytaj(self.adm, "/api/stan")
        self.assertEqual(st["telefony"], ["mobile_app_a", "mobile_app_mama"])
        _, sd = zapytaj(self.a, "/api/stan")
        self.assertIn("punkty", sd)
        self.assertNotIn("telefony", sd)
        self.assertTrue(all(p["dziecko_id"] == self.a_id for p in sd["punkty"]))
        POWIADOMIENIA.clear()
        self.assertEqual(Z.podsumowanie_tygodnia(), 0 if not (Z.teraz().isoweekday() == 7 and Z.teraz().hour >= 18) else 1)
        self.assertEqual(Z.podsumowanie_tygodnia(wymus=True), 1)      # tylko Mama ma telefon i zatwierdza
        self.assertTrue(czekaj(lambda: POWIADOMIENIA))
        usl, d = POWIADOMIENIA[-1]
        self.assertEqual(usl, "mobile_app_mama")
        self.assertRegex(d["message"], r"Dziecko A: \d+ z \d+ zadań, \+\d+ pkt")

    def test_g_pomoc_i_proby(self):
        """„Pomóż mi zacząć” (limit 3, tylko dziecko) i licznik zdjęć „po” dla rodzica."""
        s, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Biurko 2", "weryfikacja": "zdjecie"})
        zid = r["zadanie_id"]
        self.assertEqual(zapytaj(self.b, "/api/zadanie/%d/pomoc" % zid, {})[0], 403)
        self.assertEqual(zapytaj(self.m, "/api/zadanie/%d/pomoc" % zid, {})[0], 403)
        s, r = zapytaj(self.a, "/api/zadanie/%d/pomoc" % zid, {})
        self.assertEqual(s, 200, r)
        self.assertEqual((r["pierwszy_krok"], len(r["wskazowki"]), r["minuty"], r["ile"]),
                         ("Zdejmij wszystko z blatu na łóżko", 3, 15, 1))
        self.assertIn("NIE rozwiązuj", AI["pytania"][-1]["prompt"])
        zapytaj(self.a, "/api/zadanie/%d/pomoc" % zid, {})
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/pomoc" % zid, {})[1]["ile"], 3)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/pomoc" % zid, {})[0], 409)
        for _ in range(2):
            self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/zdjecie/po" % zid, JPG, "image/jpeg")[0], 200)
        _, st = zapytaj(self.m, "/api/stan")
        z = [x for x in st["zadania"] if x["id"] == zid][0]
        self.assertEqual((z["proby"], z["pomoc"]["ile"]), (2, 3))

    def test_h_wersja_1_5(self):
        """Nie dam rady → jutro; własne zgłoszenie z punktami od rodzica; ponaglenie po 2 h; kieszonkowe; przypomnienia."""
        with open(os.path.join(T, "ha_token"), "w") as f:
            f.write("tok")
        termin = (Z.teraz() + dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
        _, r = zapytaj(self.m, "/api/zadanie", {"dziecko_id": self.a_id, "tytul": "Odkurzyć", "weryfikacja": "zaufanie",
                                                 "termin": termin})
        zid = r["zadanie_id"]
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/niedamrady" % zid, {"powod": ""})[0], 400)
        self.assertEqual(zapytaj(self.b, "/api/zadanie/%d/niedamrady" % zid, {"powod": "x"})[0], 403)
        POWIADOMIENIA.clear()
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/niedamrady" % zid, {"powod": "Mam trening do 20"})[0], 200)
        self.assertEqual(zapytaj(self.a, "/api/zadanie/%d/niedamrady" % zid, {"powod": "znowu"})[0], 409)
        self.assertTrue(czekaj(lambda: any("trening" in d["message"] for _, d in POWIADOMIENIA)))
        self.assertEqual(zapytaj(self.d, "/api/zadanie/%d/prosba" % zid, {"decyzja": "jutro"})[0], 403)   # dziadek tylko podgląd
        self.assertEqual(zapytaj(self.m, "/api/zadanie/%d/prosba" % zid, {"decyzja": "jutro"})[0], 200)
        z = Z.q1("SELECT * FROM zadania WHERE id=?", zid)
        jutro = (Z.teraz().date() + dt.timedelta(days=1)).isoformat()
        self.assertEqual((z["prosba"], z["dzien"], z["termin"][:16]), ("", jutro, jutro + "T" + z["termin"][11:16]))
        # własne zgłoszenie
        self.assertEqual(zapytaj(self.m, "/api/zgloszenie", {"tytul": "x"})[0], 403)
        s, r = zapytaj(self.a, "/api/zgloszenie", {"tytul": "Umyłam okno"})
        self.assertEqual(s, 200, r)
        przed = Z.saldo(self.a_id)
        s, r = zapytaj(self.m, "/api/zadanie/%d/decyzja" % r["zadanie_id"], {"decyzja": "zatwierdz", "punkty": 7})
        self.assertEqual((s, r["punkty"], Z.saldo(self.a_id) - przed), (200, 7, 7))
        zapytaj(self.a, "/api/zgloszenie", {"tytul": "2"})
        _, r3 = zapytaj(self.a, "/api/zgloszenie", {"tytul": "3"})
        self.assertEqual(zapytaj(self.a, "/api/zgloszenie", {"tytul": "4"})[0], 409)
        # ponaglenie: zgłoszenie nr 3 „wysłane” 3 h temu
        with Z.BLOKADA:
            Z.ex("UPDATE zadania SET ponaglono=1 WHERE stan='wyslane'")
            Z.ex("UPDATE zadania SET ponaglono=0, wyslane=? WHERE id=?", Z.iso(Z.teraz() - dt.timedelta(hours=3)), r3["zadanie_id"])
        POWIADOMIENIA.clear()
        ile = Z.ponaglenia()
        if 7 <= Z.teraz().hour < 22:
            self.assertEqual(ile, 1)
            self.assertTrue(czekaj(lambda: any("od ponad 2 godzin" in d["message"] for _, d in POWIADOMIENIA)))
            self.assertEqual(Z.ponaglenia(), 0)
        else:
            self.assertEqual(ile, 0)
        # kieszonkowe
        self.assertEqual(zapytaj(self.m, "/api/osoba/%d" % self.a_id, {"grosze": 10})[0], 403)
        self.assertEqual(zapytaj(self.adm, "/api/osoba/%d" % self.a_id, {"grosze": 10})[0], 200)
        _, st = zapytaj(self.a, "/api/stan")
        self.assertEqual(st["dzieci"][0]["grosze"], 10)
        # własne przypomnienia dziecka
        self.assertEqual(zapytaj(self.a, "/api/przypomnienie", {"tekst": "Kartkówka", "kiedy": ""})[0], 400)
        za_chwile = (Z.teraz() + dt.timedelta(days=2)).strftime("%Y-%m-%dT07:00")
        s, r = zapytaj(self.a, "/api/przypomnienie", {"tekst": "Kartkówka z matematyki", "kiedy": za_chwile})
        self.assertEqual(s, 200, r)
        _, st = zapytaj(self.a, "/api/stan")
        self.assertEqual([p["tekst"] for p in st["przypomnienia"]], ["Kartkówka z matematyki"])
        _, sm = zapytaj(self.m, "/api/stan")
        self.assertEqual(len(sm["przypomnienia"]), 1)                       # mama widzi przypomnienia swojego dziecka
        _, si = zapytaj(self.i, "/api/stan")
        self.assertEqual(si["przypomnienia"], [])                           # inny rodzic nie
        self.assertEqual(zapytaj(self.b, "/api/przypomnienie/%d/usun" % r["id"], {})[0], 404)
        self.assertEqual(Z.wyslij_przypomnienia(), 0)
        with Z.BLOKADA:
            Z.ex("UPDATE notatki SET kiedy=? WHERE id=?", Z.iso(Z.teraz() - dt.timedelta(minutes=1)), r["id"])
        POWIADOMIENIA.clear()
        self.assertEqual(Z.wyslij_przypomnienia(), 1)
        self.assertTrue(czekaj(lambda: any(d["message"] == "Kartkówka z matematyki" for _, d in POWIADOMIENIA)))
        self.assertEqual(Z.wyslij_przypomnienia(), 0)

    def test_i_nauka(self):
        """Uczę się: materiał ze zdjęcia, przepytywanie z oceną, wytłumacz z oznaczeniem „poza materiałem”, podgląd rodzica."""
        self.assertEqual(zapytaj(self.m, "/api/nauka", {"temat": "Ułamki", "tryb": "przepytaj"})[0], 403)
        self.assertEqual(zapytaj(self.a, "/api/nauka", {"temat": "Ułamki", "tryb": "zly"})[0], 400)
        s, r = zapytaj(self.a, "/api/nauka", {"temat": "Ułamki", "tryb": "przepytaj"})
        self.assertEqual(s, 200, r)
        nid = r["id"]
        self.assertEqual(zapytaj(self.b, "/api/nauka/%d/pytania" % nid, {})[0], 404)
        s, r = zapytaj(self.a, "/api/nauka/%d/strona" % nid, JPG, "image/jpeg")
        self.assertEqual((s, r["strony"]), (200, 1), r)
        s, r = zapytaj(self.a, "/api/nauka/%d/pytania" % nid, {})
        self.assertEqual((s, r["ile"], r["pytania"][0]["poza"], r["pytania"][0]["wzor"]), (200, 2, False, ""), r)
        self.assertIn("WYŁĄCZNIE z poniższego materiału", AI["pytania"][-1]["prompt"])
        self.assertIn("Licznik jest nad kreską", AI["pytania"][-1]["prompt"])
        self.assertEqual(zapytaj(self.a, "/api/nauka/%d/strona" % nid, JPG, "image/jpeg")[0], 409)
        s, r = zapytaj(self.a, "/api/nauka/%d/odpowiedz" % nid, {"i": 0, "tekst": "to ta liczba nad kreską"})
        self.assertEqual((r["pytania"][0]["ocena"], r["pytania"][0]["wzor"], r["koniec"]), ("dobrze", "Liczba nad kreską ułamkową.", None))
        self.assertEqual(zapytaj(self.a, "/api/nauka/%d/odpowiedz" % nid, {"i": 0, "tekst": "x"})[0], 409)
        s, r = zapytaj(self.a, "/api/nauka/%d/odpowiedz" % nid, {"i": 1, "tekst": "nie wiem"})
        self.assertEqual((r["dobrze"], r["odpowiedzi"], bool(r["koniec"])), (1, 2, True))
        # wytłumacz: bez materiału zawsze „poza”; z materiałem zależnie od odpowiedzi modelu
        _, r = zapytaj(self.a, "/api/nauka", {"temat": "Ułamki", "tryb": "wytlumacz", "material": "Mianownik jest pod kreską."})
        w = r["id"]
        self.assertEqual(zapytaj(self.a, "/api/nauka/%d/pytania" % w, {})[0], 409)
        _, r = zapytaj(self.a, "/api/nauka/%d/pytanie" % w, {"tekst": "co robi mianownik?"})
        self.assertEqual(r["rozmowa"][-1]["poza"], False)
        _, r = zapytaj(self.a, "/api/nauka/%d/pytanie" % w, {"tekst": "a kto wymyślił ułamki?"})
        self.assertEqual((r["rozmowa"][-1]["poza"], r["poza"]), (True, 1))
        _, r = zapytaj(self.a, "/api/nauka", {"temat": "Bez materiału", "tryb": "test"})
        _, r = zapytaj(self.a, "/api/nauka/%d/pytania" % r["id"], {})
        self.assertTrue(all(p["poza"] for p in r["pytania"]))
        # rodzic widzi wynik, nie treść
        _, sm = zapytaj(self.m, "/api/stan")
        n = [x for x in sm["nauka"] if x["id"] == nid][0]
        self.assertEqual((n["dobrze"], n["ile"], "pytania" in n), (1, 2, False))
        _, si = zapytaj(self.i, "/api/stan")
        self.assertEqual(si["nauka"], [])

    def test_bez_ai(self):
        o = Z.normalizuj_ocene({"werdykt": "coś dziwnego", "punkty": [{"ok": 1, "tekst": "a"}, "zły"]})
        self.assertEqual(o["werdykt"], "niepewne")
        self.assertEqual(o["punkty"], [{"ok": True, "tekst": "a"}])
        self.assertEqual(Z.termin_ok("2026-11-16"), "2026-11-16T20:00:00")
        self.assertRaises(Z.Blad, Z.termin_ok, "jutro")


if __name__ == "__main__":
    unittest.main()
