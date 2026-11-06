"""Testy dodatku Pojazdy (bez Home Assistant i bez sieci). Dane w testach są wymyślone."""
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
POJ = os.path.join(HERE, "..", "pojazdy")
sys.path.insert(0, POJ)
TMP = tempfile.mkdtemp(prefix="pojazdy-test-")
os.environ.update({"PJ_DATA": os.path.join(TMP, "data"), "PJ_SHARE": os.path.join(TMP, "share"),
                   "PJ_PEERS": "127.0.0.1", "PJ_PORT": "0", "PJ_PETLA": "0", "SUPERVISOR_TOKEN": ""})
import obliczenia as ob  # noqa: E402
import ladowania as ld  # noqa: E402
import fuelio  # noqa: E402
import server as srv  # noqa: E402

U = timezone.utc


def tank(d, km, l, c, pelny=1, pom=0, i=None):
    return {"id": i, "data": d, "przebieg": km, "litry": l, "cena_l": c, "kwota": round(l * c, 2), "pelny": pelny,
            "pominiete": pom}


class Obliczenia(unittest.TestCase):
    def test_od_pelnego_do_pelnego(self):
        t = [tank("2026-01-01", 1000, 40, 6, i=1), tank("2026-01-10", 1300, 10, 6, 0, i=2),
             tank("2026-01-20", 1600, 32, 6, i=3)]
        o = ob.odcinki(t)
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]["km"], 600)
        self.assertAlmostEqual(o[0]["l100"], 7.0)  # (10+32)/600
        self.assertEqual(o[0]["tankowanie_id"], 3)

    def test_pominiete_przerywa(self):
        t = [tank("2026-01-01", 1000, 40, 6), tank("2026-01-10", 1500, 30, 6),
             tank("2026-02-10", 3000, 35, 6, pom=1), tank("2026-02-20", 3500, 30, 6)]
        o = ob.odcinki(t)
        self.assertEqual([x["km"] for x in o], [500, 500])

    def test_phev_prad_w_odcinku(self):
        t = [tank("2026-11-01 10:00", 1000, 30, 6), tank("2026-11-20 10:00", 1500, 20, 6)]
        l = [{"poczatek": "2026-11-05 22:00", "kwh": 10, "koszt": 6.4},
             {"poczatek": "2026-11-06 22:00", "kwh": 10, "koszt": 6.4, "wykluczone": 1},
             {"poczatek": "2026-11-25 22:00", "kwh": 10, "koszt": 6.4}]
        o = ob.odcinki(t, l)
        self.assertEqual(o[0]["kwh"], 10)
        self.assertAlmostEqual(o[0]["kwh100"], 2.0)
        self.assertAlmostEqual(o[0]["zl100"], (120 + 6.4) / 500 * 100, places=2)
        s = ob.srednie(o)
        self.assertAlmostEqual(s["l100"], 4.0)

    def test_uzupelnij_i_podejrzana(self):
        self.assertEqual(ob.uzupelnij_tankowanie(10, 6.5, None), (10.0, 6.5, 65.0))
        self.assertEqual(ob.uzupelnij_tankowanie(None, 6.5, 65), (10.0, 6.5, 65.0))
        self.assertEqual(ob.podejrzana_kwota({"litry": 14.96, "cena_l": 7.94, "kwota": 1556.24}), 118.78)
        self.assertIsNone(ob.podejrzana_kwota({"litry": 14.96, "cena_l": 7.94, "kwota": 118.8}))

    def test_terminy(self):
        t = {"co_mies": 12, "ostatnio_data": "2025-11-18"}
        s = ob.stan_terminu(t, date(2026, 11, 6), None)
        self.assertEqual(s["nastepny_data"], "2026-11-18")
        self.assertEqual(s["dni"], 12)
        self.assertTrue(s["pilne"])
        self.assertEqual(ob.opis_terminu(s), "za 12 dni")
        s2 = ob.stan_terminu({"co_km": 12000, "ostatnio_km": 20000}, date(2026, 11, 6), 31540)
        self.assertEqual(s2["km"], 460)
        self.assertEqual(ob.ktore_powiadomienie(s2), "k500")
        self.assertEqual(ob.ktore_powiadomienie(s), "d30")
        self.assertEqual(ob.dodaj_miesiace(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_koszty_miesieczne_i_km(self):
        t = [tank("2026-10-01", 1000, 40, 6), tank("2026-11-01", 1500, 30, 6)]
        m = ob.koszty_miesieczne(t, [{"poczatek": "2026-11-03 10:00", "koszt": 5}], [{"data": "2026-11-04", "kwota": 100}])
        self.assertEqual(m["2026-11"], {"paliwo": 180.0, "prad": 5.0, "inne": 100.0, "razem": 285.0})
        pts = ob.przebiegi(t, [], [{"data": "2026-11-20", "przebieg": 1800}])
        self.assertEqual(ob.km_w_okresie(pts, "2026-11-01", "2026-12-01"), 800)


class Ladowania(unittest.TestCase):
    def test_g13(self):
        self.assertEqual(ld.strefa_g13(datetime(2026, 11, 5, 8)), "przedpoludnie")
        self.assertEqual(ld.strefa_g13(datetime(2026, 11, 5, 17)), "popoludnie")
        self.assertEqual(ld.strefa_g13(datetime(2026, 7, 6, 17)), "pozostale")  # lato: szczyt 19–22
        self.assertEqual(ld.strefa_g13(datetime(2026, 7, 6, 20)), "popoludnie")
        self.assertEqual(ld.strefa_g13(datetime(2026, 11, 11, 8)), "pozostale")  # święto
        self.assertEqual(ld.strefa_g13(datetime(2026, 4, 6, 8)), "pozostale")  # poniedziałek wielkanocny 2026
        self.assertEqual(ld.strefa_g13(datetime(2026, 11, 7, 8)), "pozostale")  # sobota

    def _licznik(self, start, minut, kw, baza=100.0):
        h = [{"state": str(baza), "last_changed": (start - timedelta(hours=2)).isoformat()}]
        for i in range(minut + 1):
            h.append({"state": "%.4f" % (baza + kw * i / 60.0), "last_changed": (start + timedelta(minutes=i)).isoformat()})
        return h

    def test_sesje_i_wycena(self):
        start = datetime(2026, 11, 5, 21, 30, tzinfo=U)  # 22:30 w Polsce (strefa tania)
        h = self._licznik(start, 120, 2.0)
        teraz = start + timedelta(hours=3)
        s = ld.sesje(ld.seria(h), teraz)
        self.assertEqual(len(s), 1)
        self.assertAlmostEqual(s[0]["kwh"], 4.0, places=2)
        self.assertTrue(s[0]["skonczona"])
        self.assertAlmostEqual(sum(s[0]["godziny"].values()), 4.0, places=2)
        # dom w godzinie 21 UTC oddawał (PV), potem pobierał
        def sr(pts):
            return [(datetime(2026, 11, 5, hh, tzinfo=U), v) for hh, v in pts]
        pobrana = sr([(21, 10), (22, 10.5), (23, 13), (24 - 1, 13)])
        pobrana = [(datetime(2026, 11, 5, 21, tzinfo=U), 10), (datetime(2026, 11, 5, 22, tzinfo=U), 10.2),
                   (datetime(2026, 11, 5, 23, tzinfo=U), 12.5), (datetime(2026, 11, 6, 0, tzinfo=U), 15)]
        oddana = [(datetime(2026, 11, 5, 21, tzinfo=U), 5), (datetime(2026, 11, 5, 22, tzinfo=U), 6.0),
                  (datetime(2026, 11, 5, 23, tzinfo=U), 6.0), (datetime(2026, 11, 6, 0, tzinfo=U), 6.0)]
        w = ld.wycen(s[0], {"przedpoludnie": 0.92, "popoludnie": 1.51, "pozostale": 0.64}, pobrana, oddana, [], 0.05)
        # godzina 21 UTC: 1 kWh ładowania, bilans −0,8 -> całość z PV
        self.assertAlmostEqual(w["kwh_pv"], 1.0, places=2)
        self.assertAlmostEqual(w["strefy"]["pozostale"], 3.0, places=2)
        self.assertAlmostEqual(w["koszt"], 3.0 * 0.64, places=2)
        self.assertAlmostEqual(w["koszt_wartosc"], 0.2, places=2)
        bat = [(start - timedelta(minutes=40), 31.0), (start + timedelta(minutes=150), 60.0)]
        s0, s1 = ld.soc(bat, s[0]["start"], s[0]["koniec"])
        row = ld.do_wiersza(s[0], "dom", 1, w, s0, s1, 13.8)
        self.assertEqual(row["poczatek"], "2026-11-05 22:30")
        self.assertAlmostEqual(row["kwh_bateria"], 4.0, places=1)
        self.assertTrue(row["uid"].startswith("auto:dom:20261105T2130"))

    def test_trwajaca_sesja(self):
        start = datetime(2026, 11, 5, 21, 0, tzinfo=U)
        s = ld.sesje(ld.seria(self._licznik(start, 30, 2.0)), start + timedelta(minutes=35))
        self.assertFalse(s[0]["skonczona"])

    def test_przerwa_dzieli(self):
        start = datetime(2026, 11, 5, 10, 0, tzinfo=U)
        h = self._licznik(start, 30, 2.0) + self._licznik(start + timedelta(hours=2), 30, 2.0, baza=101.0)[1:]
        self.assertEqual(len(ld.sesje(ld.seria(h), start + timedelta(hours=5))), 2)


def plik_fuelio():
    """Wymyślona kopia Fuelio: 2 pojazdy, w tym literówka w kwocie."""
    v = '"## Vehicle"\n"Name","Tank1Capacity"\n"%s","%s"\n'
    log = '"## Log"\n"Date","Odo (km)","Fuel (l)","Full","Price","l/100km","City","Missed","FuelType","VolumePrice"\n'
    a = v % ("Honda NT", "20.0") + log + "".join(
        '"%s","%s","%s","1","%s","0","Testowo","0","0","%s"\n' % r for r in [
            ("2026-09-01", "1000.0", "15.0", "105.0", "7.0"), ("2026-09-05", "1300.0", "15.0", "1500.0", "7.0"),
            ("2026-09-10", "1600.0", "16.5", "115.49999999999999", "7.0")]) + \
        '"## CostCategories"\n"CostTypeID","Name","priority","color"\n"1","Serwis","1",""\n' \
        '"## Costs"\n"CostTitle","Date","Odo","CostTypeID","Notes","Cost","RepeatOdo","RepeatMonths","isTemplate","isIncome","RemindDate"\n' \
        '"Olej","2026-09-02","1100.0","1","","250.0","12000","12","0","0","2011-01-01"\n'
    b = v % ("Inny", "40") + log + '"2026-05-01","500.0","30.0","1","180.0","0","","0","110","6.0"\n'
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("vehicle-1-local.csv", a)
        z.writestr("vehicle-2-local.csv", b)
    return buf.getvalue()


class Fuelio(unittest.TestCase):
    def test_czytaj(self):
        p = fuelio.czytaj(plik_fuelio())
        self.assertEqual([x["nazwa"] for x in p], ["Honda NT", "Inny"])
        self.assertEqual(len(p[0]["tankowania"]), 3)
        self.assertEqual(p[0]["podejrzane"][0]["wyliczona"], 105.0)
        self.assertEqual(p[0]["koszty"][0]["kategoria"], "Serwis")
        self.assertEqual(p[0]["terminy"][0]["co_mies"], 12)
        self.assertEqual(p[0]["tankowania"][2]["kwota"], 115.5)  # bez ogona 115.49999999999999

    def test_eksport_wraca(self):
        p = {"nazwa": "Test", "bak_l": 20}
        t = [{"data": "2026-09-01", "przebieg": 1000, "litry": 15, "cena_l": 7, "kwota": 105, "pelny": 1, "stacja": "A"}]
        k = [{"data": "2026-09-02", "kategoria": "Opony", "tytul": "Zimówki", "kwota": 900}]
        back = fuelio.czytaj(fuelio.eksport([(p, t, k)]))
        self.assertEqual(back[0]["nazwa"], "Test")
        self.assertEqual(back[0]["tankowania"][0]["litry"], 15)
        self.assertEqual(back[0]["koszty"][0]["kategoria"], "Opony")


class KorektaBaterii(unittest.TestCase):
    def test_przyrost_i_spadek(self):
        t = [dict(tank("2026-11-01 10:00", 1000, 10, 6), soc=100),
             dict(tank("2026-11-10 10:00", 1400, 10, 6), soc=0)]
        l = [{"poczatek": "2026-11-03 22:00", "kwh": 20.0, "koszt": 10.0}]
        o = ob.odcinki(t, l, "2026-11-01", (13.2, 0.88))
        # bateria spadła o 13,2 kWh -> do zużycia dochodzi 15 kWh z gniazdka
        self.assertAlmostEqual(o[0]["kwh"], 35.0, places=1)
        self.assertTrue(o[0]["skorygowano"])
        self.assertAlmostEqual(o[0]["koszt_pradu"], 10.0 * 35.0 / 20.0, places=1)
        # bez stanu baterii albo bez korekty – jak dotąd
        self.assertAlmostEqual(ob.odcinki(t, l, "2026-11-01")[0]["kwh"], 20.0)
        t2 = [dict(t[0], soc=None), t[1]]
        self.assertNotIn("skorygowano", ob.odcinki(t2, l, "2026-11-01", (13.2, 0.88))[0])
        # przyrost baterii większy niż ładowanie nie daje ujemnego zużycia
        t3 = [dict(t[0], soc=0), dict(t[1], soc=100)]
        self.assertEqual(ob.odcinki(t3, l[:1], "2026-11-01", (13.2, 0.88))[0]["kwh"], 5.0)

    def test_zakres_zuzycia(self):
        # spadek baterii o 13,2 kWh: bez korekty 20 kWh, z korektą 35 kWh -> zakres 20..35 na 400 km
        t = [dict(tank("2026-11-01 10:00", 1000, 10, 6), soc=100),
             dict(tank("2026-11-10 10:00", 1400, 10, 6), soc=0)]
        l = [{"poczatek": "2026-11-03 22:00", "kwh": 20.0, "koszt": 10.0}]
        o = ob.odcinki(t, l, "2026-11-01", (13.2, 0.88))[0]
        self.assertEqual((o["kwh_min"], o["kwh_max"]), (20.0, 35.0))
        sr = ob.srednie([o])
        self.assertAlmostEqual(sr["kwh100_od"], 5.0, places=1)
        self.assertAlmostEqual(sr["kwh100_do"], 8.75, places=1)
        self.assertAlmostEqual(sr["kwh100"], 8.75, places=1)
        # przyrost baterii: korekta zmniejsza, zakres odwrotnie
        t3 = [dict(t[0], soc=0), dict(t[1], soc=50)]
        o3 = ob.odcinki(t3, l, "2026-11-01", (13.2, 0.88))[0]
        self.assertLess(o3["kwh_min"], o3["kwh_max"])
        self.assertEqual(o3["kwh_max"], 20.0)

    def test_pomiar_baterii_na_sucho(self):
        p = {"bateria_kwh": 13.8}
        l = [{"zrodlo": "auto", "kwh": 7.0, "soc_od": 20, "soc_do": 70},
             {"zrodlo": "auto", "kwh": 3.0, "soc_od": 50, "soc_do": 55},       # za mały przyrost – pomijana
             {"zrodlo": "ekran_auta", "kwh": 50.0, "soc_od": 0, "soc_do": 100},  # nie z pomiaru
             {"zrodlo": "auto", "kwh": 7.0, "soc_od": 10, "soc_do": 60, "wykluczone": 1}]
        m = srv.pomiar_baterii(p, l)
        self.assertEqual(m["sesji"], 1)
        self.assertAlmostEqual(m["kwh_na_100"], 14.0, places=1)
        self.assertAlmostEqual(m["ustawienie_kwh_na_100"], 13.8 / srv.SPRAWNOSC_LADOWANIA, places=1)

    def test_baza_ma_kolumne_soc(self):
        import baza
        db = baza.Baza(os.path.join(TMP, "soc.db"))
        r = db.dodaj("tankowania", {"pojazd_id": 1, "data": "2026-11-02 10:00", "przebieg": 1, "litry": 1, "soc": 55.0})
        self.assertEqual(db.jeden("tankowania", r)["soc"], 55.0)
        db.db.close()
        # stara baza bez kolumny dostaje ją przy starcie
        import sqlite3
        st = os.path.join(TMP, "stara.db")
        c = sqlite3.connect(st)
        c.execute("CREATE TABLE tankowania (id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, data TEXT NOT NULL, przebieg REAL,"
                  " litry REAL, cena_l REAL, kwota REAL, pelny INTEGER DEFAULT 1, pominiete INTEGER DEFAULT 0,"
                  " stacja TEXT, notatka TEXT, fuelio_typ TEXT, zrodlo TEXT DEFAULT 'recznie', uid TEXT UNIQUE)")
        c.commit()
        c.close()
        db2 = baza.Baza(st)
        self.assertIn("soc", [x[1] for x in db2.db.execute("PRAGMA table_info(tankowania)")])
        db2.db.close()


class LadowaniaZAuta(unittest.TestCase):
    CSV = b"od,do,kwh_bateria,notatka\n2026-06-01,2026-06-30,150,czerwiec\n2026-07-05,2026-07-05,9.5,\nzle,,x,\n"

    def test_czytaj(self):
        lad = fuelio.czytaj_ladowania(self.CSV)
        self.assertEqual([(x["od"], x["do"], x["kwh_bateria"]) for x in lad],
                         [("2026-06-01", "2026-06-30", 150.0), ("2026-07-05", "2026-07-05", 9.5)])
        self.assertIsNone(fuelio.czytaj_ladowania(plik_fuelio()))

    def test_miesiac_dzielony_na_baki(self):
        t = [{"data": "2026-06-01", "przebieg": 1000, "litry": 10, "pelny": 1},
             {"data": "2026-06-16", "przebieg": 1500, "litry": 10, "pelny": 1},
             {"data": "2026-07-01", "przebieg": 2000, "litry": 10, "pelny": 1}]
        l = [{"poczatek": "2026-06-01 00:00", "koniec": "2026-06-30 23:59", "kwh": 150, "zrodlo": "ekran_auta"}]
        o = ob.odcinki(t, l, "2026-06-01")
        self.assertAlmostEqual(o[0]["kwh"], 75.0, places=1)  # 15 z 30 dni
        self.assertAlmostEqual(o[1]["kwh"], 75.0, places=1)


class Serwer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = srv.uruchom()
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d/" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        r = urllib.request.Request(self.url + path, data=data, method="POST" if data is not None else "GET",
                                   headers=dict({"Content-Type": "application/json"}, **(headers or {})))
        with urllib.request.urlopen(r) as f:
            b = f.read()
            return json.loads(b) if "json" in f.headers.get("Content-Type", "") else b

    def test_przeplyw(self):
        poj = self.req("api/pojazdy")
        self.assertEqual(sorted(p["klucz"] for p in poj), ["eclipse", "nt1100"])
        ecl = [p for p in poj if p["klucz"] == "eclipse"][0]["id"]
        nt = [p for p in poj if p["klucz"] == "nt1100"][0]["id"]
        self.assertIn(b"Pojazdy", self.req(""))
        # import: NT trafia do NT1100, "Inny" pominięty
        pg = self.req("api/import/podglad", raw=plik_fuelio(), headers={"X-Nazwa-Pliku": "kopia.fuelio"})
        self.assertEqual(pg["pojazdy"][0]["pojazd_id"], nt)
        self.assertIsNone(pg["pojazdy"][1]["pojazd_id"])
        w = self.req("api/import/zapisz", {"mapowanie": {"vehicle-1-local.csv": nt}, "popraw": True})
        self.assertEqual((w["tankowan"], w["kosztow"], w["poprawionych"]), (3, 1, 1))
        # drugi raz nic nowego
        self.req("api/import/podglad", raw=plik_fuelio())
        self.assertEqual(self.req("api/import/zapisz", {"mapowanie": {"vehicle-1-local.csv": nt}})["tankowan"], 0)
        # tankowania Eclipse ręcznie + ładowanie ręczne
        self.req("api/tankowania", {"pojazd_id": ecl, "data": "2026-11-01 10:00", "przebieg": 56000, "litry": 30, "cena_l": 6})
        self.req("api/ladowania", {"pojazd_id": ecl, "poczatek": "2026-11-03 22:00", "kwh": 10, "koszt": 6.4, "miejsce": "obce"})
        r = self.req("api/tankowania", {"pojazd_id": ecl, "data": "2026-11-05 10:00", "przebieg": 56500, "kwota": 120, "cena_l": 6})
        self.assertIsNone(r["uwaga"])
        r2 = self.req("api/tankowania", {"pojazd_id": ecl, "data": "2026-11-06 10:00", "przebieg": 56400, "litry": 5, "cena_l": 6})
        self.assertIn("mniejszy", r2["uwaga"])
        self.req("api/tankowania/%d/usun" % r2["id"], {})
        # edycja z pustym polem daty nie zmienia daty wpisu
        self.req("api/tankowania/%d" % r["id"], {"pojazd_id": ecl, "data": "", "przebieg": 56500, "kwota": 120, "cena_l": 6})
        self.assertEqual(self.req("api/tankowania/%d" % r["id"])["data"], "2026-11-05 10:00")
        st = self.req("api/statystyki?pojazd=%d&okres=calosc" % ecl)
        self.assertAlmostEqual(st["srednie"]["l100"], 4.0)
        self.assertAlmostEqual(st["srednie"]["kwh100"], 2.0)
        self.assertIsNotNone(st["benzyna"])
        stn = self.req("api/statystyki?pojazd=%d&okres=calosc" % nt)
        self.assertAlmostEqual(stn["srednie"]["l100"], 5.25)  # (15+16,5)/600
        self.assertEqual(stn["kategorie"], {"Serwis": 250.0})
        start = self.req("api/start")
        self.assertEqual(len(start["pojazdy"]), 2)
        self.assertTrue(any(t["nazwa"] == "Olej" for t in self.req("api/terminy")))
        # termin zrobiony -> koszt w historii
        tid = [t for t in self.req("api/terminy") if t["nazwa"] == "Olej"][0]["id"]
        self.req("api/terminy/%d/zrobione" % tid, {"data": "2026-11-06", "przebieg": 1700, "kwota": "300"})
        t = self.req("api/terminy/%d" % tid)
        self.assertEqual(t["ostatnio_km"], 1700)
        self.assertTrue(any(x["typ"] == "koszt" and x["kwota"] == 300 for x in self.req("api/historia?pojazd=%d" % nt)))
        self.assertEqual(self.req("api/statystyki?pojazd=wszystkie&okres=calosc")["podsumowanie"]["razem"] > 0, True)
        # ładowania z ekranu auta: przesuwają początek liczenia prądu
        pg = self.req("api/import/podglad", raw=LadowaniaZAuta.CSV, headers={"X-Nazwa-Pliku": "auto.csv"})
        self.assertEqual((pg["ladowania"]["ile"], pg["ladowania"]["pojazd_id"]), (2, ecl))
        w = self.req("api/import/zapisz", {"mapowanie": {"ekran": ecl}})
        self.assertEqual((w["ladowan"], w["prad_od"]), (2, "2026-06-01"))
        h = [x for x in self.req("api/historia?pojazd=%d" % ecl) if x.get("zrodlo") == "ekran_auta"]
        self.assertAlmostEqual(sum(x["kwh_bateria"] for x in h), 159.5)
        self.req("api/ustawienia", {"dane_pradu_od": "2026-11-01"})
        z = self.req("api/eksport")
        self.assertEqual(z[:2], b"PK")
        self.assertEqual(len(fuelio.czytaj(z)), 2)
        # kopia nocna
        srv.kopia_nocna()
        self.assertTrue(any(f.endswith(".fuelio") for f in os.listdir(os.path.join(TMP, "share", "kopie"))))
        # czujniki do HA (bez wysyłki)
        ids = [c[0] for c in srv.czujniki()]
        self.assertIn("sensor.pojazdy_eclipse_zuzycie_pradu", ids)
        self.assertIn("sensor.pojazdy_nt1100_terminy", ids)

    def test_soc_z_historii(self):
        ecl = [p for p in self.req("api/pojazdy") if p["klucz"] == "eclipse"][0]["id"]
        i = srv.DB.dodaj("tankowania", {"pojazd_id": ecl, "data": "2026-11-03 18:00", "przebieg": 77000, "litry": 5, "cena_l": 6})
        j = srv.DB.dodaj("tankowania", {"pojazd_id": ecl, "data": "2026-11-04", "przebieg": 77100, "litry": 5, "cena_l": 6})
        stare = srv.ha_historia
        # 18:00 lokalnie = 17:00 UTC (listopad); data bez godziny = 12:00 lokalnie = 11:00 UTC
        srv.ha_historia = lambda e, od, do: {"sensor.eclipse_bateria": [
            {"state": "40", "last_changed": "2026-11-03T16:00:00+00:00"},
            {"state": "unavailable", "last_changed": "2026-11-03T16:30:00+00:00"},
            {"state": "90", "last_changed": "2026-11-04T08:00:00+00:00"}]}
        try:
            srv.uzupelnij_soc()
        finally:
            srv.ha_historia = stare
        self.assertEqual(srv.DB.jeden("tankowania", i)["soc"], 40.0)
        self.assertEqual(srv.DB.jeden("tankowania", j)["soc"], 90.0)
        srv.DB.usun("tankowania", i)
        srv.DB.usun("tankowania", j)

    def test_tylko_przez_ingress(self):
        old = set(srv.PEERS)
        srv.PEERS.clear()
        srv.PEERS.add("10.0.0.9")
        try:
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.req("api/start")
            self.assertEqual(e.exception.code, 403)
        finally:
            srv.PEERS.clear()
            srv.PEERS.update(old)


if __name__ == "__main__":
    unittest.main()
