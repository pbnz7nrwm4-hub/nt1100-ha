"""Testy dodatku Pojazdy (bez Home Assistant i bez sieci). Dane w testach są wymyślone."""
import importlib
import json
import os
import re
import subprocess
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

    def test_kwh100_z_licznika(self):
        pts = [("2026-11-01 08:00", 1000.0), ("2026-11-20 08:00", 1300.0)]
        lad = [{"poczatek": "2026-11-05T10:00", "kwh": 30.0}, {"poczatek": "2026-11-10T10:00", "kwh": 15.0, "wykluczone": 1},
               {"poczatek": "2026-11-12T10:00", "kwh": 30.0, "zrodlo": "ekran_auta"}, {"poczatek": "2026-11-15T10:00", "kwh": 30.0}]
        r = ob.kwh100_z_licznika(lad, pts, "2026-11-01")
        self.assertEqual(r["kwh"], 60.0)
        self.assertEqual(r["kwh100"], 20.0)
        self.assertIsNone(ob.kwh100_z_licznika(lad, pts[:1], "2026-11-01"))

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

    def test_polisa_raty_i_stan(self):
        r = ob.rozloz_raty("2026-09-01", 680, 2)
        self.assertEqual([(x["termin"], x["kwota"]) for x in r], [("2026-09-01", 340.0), ("2027-03-01", 340.0)])
        r4 = ob.rozloz_raty("2026-01-31", 1000, 3)
        self.assertEqual([x["termin"] for x in r4], ["2026-01-31", "2026-05-31", "2026-09-30"])
        self.assertAlmostEqual(sum(x["kwota"] for x in r4), 1000)
        p = {"zakres": "OC", "od": "2026-09-01", "do": "2027-08-31"}
        raty = [{"nr": 1, "termin": "2026-09-01", "kwota": 340, "zaplacono": "2026-08-29"},
                {"nr": 2, "termin": "2027-01-31", "kwota": 340, "zaplacono": None}]
        s = ob.stan_polisy(p, raty, date(2026, 11, 14))
        self.assertEqual((s["waznosc"], s["zaplaconych"], s["do_zaplaty"], s["nastepna"]["dni"]), ("wazna", 1, 340, 78))
        self.assertFalse(s["pilne"])
        self.assertFalse(s["wznowi_sie"])  # niezapłacona rata -> OC nie wznowi się samo
        s = ob.stan_polisy(p, raty, date(2027, 1, 10))
        self.assertEqual((s["opis"], s["poziom"], s["pilne"]), ("rata za 21 dni", "warn", True))
        s = ob.stan_polisy(p, raty, date(2027, 2, 3))
        self.assertEqual((s["opis"], s["poziom"]), ("rata po terminie 3 dni", "bad"))
        raty[1]["zaplacono"] = "2027-01-20"
        s = ob.stan_polisy(p, raty, date(2027, 2, 3))
        self.assertEqual((s["opis"], s["wznowi_sie"], s["wypowiedz_do"]), ("opłacona", True, "2027-08-30"))
        s = ob.stan_polisy(p, raty, date(2027, 8, 20))
        self.assertEqual((s["opis"], s["poziom"], s["pilne"]), ("koniec za 11 dni", "ok", False))
        s = ob.stan_polisy(dict(p, wypowiedziana=1), raty, date(2027, 8, 20))
        self.assertEqual((s["poziom"], s["pilne"], s["wznowi_sie"]), ("warn", True, False))
        self.assertFalse(ob.stan_polisy(dict(p, zakres="AC"), raty, date(2027, 2, 3))["wznowi_sie"])
        self.assertEqual(ob.stan_polisy(p, raty, date(2027, 9, 2))["waznosc"], "wygasla")
        # progi przypomnień: 14/7/1/0 przed, potem co 3 dni; koniec 30/14/1/0
        self.assertEqual([ob.powiadomienie_raty(d) for d in (20, 14, 8, 7, 1, 0, -1, -3, -4, -7)],
                         [None, "d14", "d14", "d7", "d1", "d0", "po0", "po0", "po1", "po2"])
        self.assertEqual([ob.powiadomienie_konca(d) for d in (31, 30, 14, 2, 1, 0, -1)],
                         [None, "k30", "k14", "k14", "k1", "k0", None])

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

    def test_rzadki_licznik_nie_rozciaga_sesji(self):
        # jeden przyrost zgłoszony po 3 h ciszy: początek ma być tuż przed raportem, nie sprzed godzin
        t = datetime(2026, 11, 8, 14, 9, tzinfo=U)
        h = [{"state": "100.0", "last_changed": (t - timedelta(hours=3)).isoformat()},
             {"state": "100.12", "last_changed": t.isoformat()}]
        s = ld.sesje(ld.seria(h), t + timedelta(minutes=ld.KONIEC_PO_MIN + 1), min_kwh=0)
        self.assertEqual(len(s), 1)
        self.assertGreaterEqual(s[0]["start"], t - timedelta(minutes=ld.PRZERWA_MIN))
        # okno historii przesunięte do przodu nie zmienia początku sesji
        h2 = [{"state": "100.0", "last_changed": (t - timedelta(minutes=25)).isoformat()}, h[1]]
        s2 = ld.sesje(ld.seria(h2), t + timedelta(hours=1), min_kwh=0)
        self.assertEqual(s2[0]["start"], s[0]["start"])

    def test_sesja_nie_konczy_sie_przed_mozliwym_przedluzeniem(self):
        start = datetime(2026, 11, 5, 21, 0, tzinfo=U)
        s = ld.sesje(ld.seria(self._licznik(start, 30, 2.0)), start + timedelta(minutes=30 + 18))
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

    def test_scalanie_dubli(self):
        sv = srv
        pid = sv.DB.lista("pojazdy")[0]["id"]
        for p, k, kwh in [("2026-11-09 06:05", "2026-11-09 07:20", 0.7), ("2026-11-09 06:55", "2026-11-09 07:20", 0.7),
                          ("2026-11-09 07:05", "2026-11-09 07:20", 0.3), ("2026-11-09 20:00", "2026-11-10 03:25", 8.5)]:
            sv.DB.dodaj("ladowania", {"pojazd_id": pid, "poczatek": p, "koniec": k, "kwh": kwh, "miejsce": "dom",
                                      "zrodlo": "auto", "uid": "t:" + p})
        self.assertEqual(sv.scal_ladowania(True)["do_usuniecia"], 2)
        sv.scal_ladowania(False)
        z = [x for x in sv.DB.lista("ladowania", pojazd_id=pid) if x["poczatek"].startswith("2026-11-09 0")]
        self.assertEqual([x["poczatek"] for x in z], ["2026-11-09 06:05"])
        self.assertEqual(sv.scal_ladowania(True)["do_usuniecia"], 0)
        for x in sv.DB.lista("ladowania", pojazd_id=pid):
            sv.DB.usun("ladowania", x["id"])

    def test_telegram_tankowanie(self):
        pr = self.req("api/telegram/propozycja", {"pojazd": "nt1100", "litry": "14,32", "kwota": "88,64", "przebieg": 12340})
        self.assertTrue(pr["ok"])
        self.assertAlmostEqual(pr["tankowanie"]["cena_l"], 6.19, places=2)
        self.assertEqual(pr["tankowanie"]["zrodlo"], "telegram")
        self.assertIn("NT1100: 14,32 l", pr["tekst"])
        # propozycja nic nie zapisuje
        poj = [p for p in self.req("api/pojazdy") if p["klucz"] == "nt1100"][0]["id"]
        przed = len([x for x in self.req("api/historia?pojazd=%d" % poj) if x.get("typ") == "tankowanie"])
        self.req("api/telegram/propozycja", {"pojazd": "nt1100", "litry": 10, "cena_l": 6})
        po = len([x for x in self.req("api/historia?pojazd=%d" % poj) if x.get("typ") == "tankowanie"])
        self.assertEqual(przed, po)
        # brak pojazdu / litrów
        self.assertEqual(self.req("api/telegram/propozycja", {"litry": 10, "cena_l": 6})["powod"], "pojazd")
        self.assertEqual(self.req("api/telegram/propozycja", {"pojazd": "nt1100"})["powod"], "litry")
        # litry ponad bak i niezgodna kwota
        uw = self.req("api/telegram/propozycja", {"pojazd": "nt1100", "litry": 30, "cena_l": 6, "kwota": 500})["ostrzezenia"]
        self.assertTrue(any("bak" in x for x in uw) and any("niezgodna" in x for x in uw))
        # zapis raz, drugi klik = duplikat
        z1 = self.req("api/telegram/zapisz", {"pojazd": "nt1100", "litry": 14.32, "kwota": 88.64, "przebieg": 12340, "uid": "m1"})
        z2 = self.req("api/telegram/zapisz", {"pojazd": "nt1100", "litry": 14.32, "kwota": 88.64, "przebieg": 12340, "uid": "m1"})
        self.assertIn("id", z1)
        self.assertTrue(z2.get("duplikat"))
        po2 = len([x for x in self.req("api/historia?pojazd=%d" % poj) if x.get("typ") == "tankowanie"])
        self.assertEqual(po2, po + 1)

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

    def test_polisy(self):
        nt = [p for p in self.req("api/pojazdy") if p["klucz"] == "nt1100"][0]["id"]
        tid = self.req("api/terminy", {"pojazd_id": nt, "nazwa": "2 rata polisy", "kategoria": "Ubezpieczenie",
                                       "nastepny_data": "2027-01-31"})["id"]
        # nowa polisa z terminu: raty z formularza, pierwsza zapłacona -> koszt, termin znika
        r = self.req("api/polisy", {"pojazd_id": nt, "zakres": "OC", "od": "2026-09-01", "do": "2027-08-31",
                                    "skladka": "680", "z_terminu": tid,
                                    "raty": [{"termin": "2026-09-01", "kwota": 340, "zaplacono": "2026-08-29"},
                                             {"termin": "2027-01-31", "kwota": "340"}]})
        pid = r["id"]
        self.assertFalse(any(t["id"] == tid for t in self.req("api/terminy")))
        pol = self.req("api/polisy/%d" % pid)
        self.assertEqual((pol["stan"]["zaplaconych"], pol["stan"]["liczba_rat"], pol["stan"]["do_zaplaty"]), (1, 2, 340))
        kos = lambda: [x for x in self.req("api/historia?pojazd=%d" % nt) if x.get("zrodlo") == "polisa"]
        self.assertEqual([(x["kwota"], x["data"][:10], x["kategoria"]) for x in kos()], [(340, "2026-08-29", "Ubezpieczenie")])
        self.assertIn("rata 1 z 2", kos()[0]["tytul"])
        # zapłata 2 raty -> drugi koszt; cofnięcie -> koszt znika
        r2 = pol["raty"][1]["id"]
        self.req("api/raty/%d/zaplac" % r2, {"data": "2027-01-20"})
        self.assertEqual(len(kos()), 2)
        self.assertTrue(self.req("api/polisy/%d" % pid)["stan"]["oplacona"])
        self.req("api/raty/%d/zaplac" % r2, {"cofnij": True})
        self.assertEqual(len(kos()), 1)
        # edycja bez rat zostawia raty i koszty; wypowiedzenie
        self.req("api/polisy/%d" % pid, {"wypowiedziana": 1, "ubezpieczyciel": "Test"})
        p2 = self.req("api/polisy/%d" % pid)
        self.assertEqual((len(p2["raty"]), p2["wypowiedziana"], len(kos())), (2, 1, 1))
        # Start, czujnik
        st = self.req("api/start")
        karta = [c for c in st["pojazdy"] if c["id"] == nt][0]
        self.assertEqual(karta["polisy"][0]["zaplaconych"], 1)
        cz = {c[0]: c for c in srv.czujniki()}
        self.assertIn("sensor.pojazdy_nt1100_polisa", cz)
        self.assertEqual(cz["sensor.pojazdy_nt1100_polisa"][2]["polisy"][0]["raty"], "1/2")
        # odnowienie: nowa polisa od dnia po końcu, stara ukryta z bieżących
        n = self.req("api/polisy/%d/odnow" % pid, {})["id"]
        nowa = self.req("api/polisy/%d" % n)
        self.assertEqual((nowa["od"], nowa["do"], len(nowa["raty"]), nowa["raty"][1]["termin"]),
                         ("2027-09-01", "2028-08-31", 2, "2028-03-01"))
        self.assertEqual([x["id"] for x in self.req("api/polisy")], [n])
        self.assertEqual(len(self.req("api/polisy?wszystkie=1")), 2)
        # błędne daty
        with self.assertRaises(urllib.error.HTTPError):
            self.req("api/polisy", {"pojazd_id": nt, "od": "2027-01-01", "do": "2026-01-01"})
        # usunięcie polisy usuwa jej raty i koszty
        self.req("api/polisy/%d/usun" % pid, {})
        self.req("api/polisy/%d/usun" % n, {})
        self.assertEqual(kos(), [])
        self.assertEqual(srv.DB.lista("raty"), [])

    def test_powiadomienia_polis(self):
        nt = [p for p in self.req("api/pojazdy") if p["klucz"] == "nt1100"][0]["id"]
        dzis = srv.teraz_lok().date()
        r = self.req("api/polisy", {"pojazd_id": nt, "zakres": "OC+AC", "od": (dzis - timedelta(days=300)).isoformat(),
                                    "do": (dzis + timedelta(days=10)).isoformat(),
                                    "raty": [{"termin": (dzis - timedelta(days=300)).isoformat(), "kwota": 500, "zaplacono": "2026-01-01"},
                                             {"termin": (dzis - timedelta(days=2)).isoformat(), "kwota": 512}]})
        wyslane = []
        stare = srv.powiadom
        srv.powiadom = lambda t, tr, tag: wyslane.append((t, tr))
        try:
            srv.powiadomienia_polis()
            srv.powiadomienia_polis()  # drugi raz nic nowego
        finally:
            srv.powiadom = stare
        self.assertEqual(len(wyslane), 2)
        self.assertIn("po terminie", wyslane[0][0])
        self.assertIn("AC może zostać rozwiązane", wyslane[0][1])
        self.assertIn("kończy się za 10 dni", wyslane[1][0])
        self.assertIn("sama się nie wznowi", wyslane[1][1])
        self.req("api/polisy/%d/usun" % r["id"], {})

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



class Kontener(unittest.TestCase):
    """1.8.0: aplikacja samodzielna (kontener) + dodatek-pośrednik w HA – dwa prawdziwe procesy."""

    def _start(self, env):
        e = dict(os.environ, PJ_PORT="0", PJ_PETLA="0", SUPERVISOR_TOKEN="", **env)
        for k in ("PJ_HA_URL", "PJ_KLUCZ", "PJ_LAN", "PJ_APLIKACJA", "PJ_HA_TOKEN"):
            if k not in env:
                e.pop(k, None)
        p = subprocess.Popen([sys.executable, "-u", os.path.join(POJ, "server.py")], env=e, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
        linia = p.stdout.readline()
        port = int(re.search(r"porcie (\d+)", linia).group(1))
        threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()
        return "http://127.0.0.1:%d/" % port, linia

    def _req(self, url, body=None, headers=None):
        r = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                   method="POST" if body is not None else "GET",
                                   headers=dict({"Content-Type": "application/json"}, **(headers or {})))
        with urllib.request.urlopen(r, timeout=10) as f:
            b = f.read()
            return json.loads(b) if "json" in f.headers.get("Content-Type", "") else b

    def test_przenosiny_i_posrednik(self):
        import baza as bz
        kat = tempfile.mkdtemp(prefix="pojazdy-kontener-")
        a_dane, b_dane = os.path.join(kat, "app"), os.path.join(kat, "dodatek")
        os.makedirs(a_dane)
        os.makedirs(b_dane)
        # dodatek ma już dane (jak u użytkownika przed przenosinami)
        stara = bz.Baza(os.path.join(b_dane, "pojazdy.db"))
        nt = [p for p in stara.lista("pojazdy") if p["klucz"] == "nt1100"][0]["id"]
        stara.dodaj("tankowania", {"pojazd_id": nt, "data": "2026-11-01 10:00", "przebieg": 1000, "litry": 15, "cena_l": 6, "kwota": 90})
        stara.ustaw("telegram_chat", "123")
        stara.db.close()
        app, linia = self._start({"PJ_DATA": a_dane, "PJ_SHARE": a_dane, "PJ_HA_URL": "http://127.0.0.1:9", "PJ_KLUCZ": "sekret"})
        self.assertIn("aplikacja samodzielna", linia)
        # bez klucza nic; z kluczem pusta aplikacja
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._req(app + "api/pojazdy")
        self.assertEqual(e.exception.code, 403)
        self.assertTrue(self._req(app + "api/przenosiny", headers={"X-Pojazdy-Klucz": "sekret"})["pusta"])
        with open(os.path.join(b_dane, "options.json"), "w") as f:
            json.dump({"adres_aplikacji": app.rstrip("/"), "klucz_aplikacji": "sekret", "token_ha": "tok-123"}, f)
        dod, linia = self._start({"PJ_DATA": b_dane, "PJ_SHARE": b_dane, "PJ_PEERS": "127.0.0.1"})
        self.assertIn("pośrednik", linia)
        # dodatek sam przenosi bazę i token; panel przez dodatek pokazuje dane z aplikacji
        for _ in range(50):
            st = self._req(app + "api/przenosiny", headers={"X-Pojazdy-Klucz": "sekret"})
            if not st["pusta"] and st["token"]:
                break
            threading.Event().wait(0.2)
        self.assertFalse(st["pusta"])
        self.assertTrue(st["token"])
        with open(os.path.join(a_dane, "ha_token")) as f:
            self.assertEqual(f.read(), "tok-123")
        self.assertEqual(os.stat(os.path.join(a_dane, "ha_token")).st_mode & 0o777, 0o600)
        self.assertIn(b"Pojazdy", self._req(dod))
        h = self._req(dod + "api/historia?pojazd=%d" % nt)
        self.assertEqual([x["litry"] for x in h if x["typ"] == "tankowanie"], [15])
        self.assertEqual(self._req(dod + "api/ustawienia")["telegram_chat"], "123")
        # zapis przez pośrednika trafia do aplikacji, nie do starej bazy dodatku
        self._req(dod + "api/koszty", {"pojazd_id": nt, "kategoria": "Serwis", "tytul": "Olej", "kwota": 300, "data": "2026-11-10"})
        h2 = self._req(app + "api/historia?pojazd=%d" % nt, headers={"X-Pojazdy-Klucz": "sekret"})
        self.assertTrue(any(x["typ"] == "koszt" and x["kwota"] == 300 for x in h2))
        stara = bz.Baza(os.path.join(b_dane, "pojazdy.db"))
        self.assertEqual(stara.lista("koszty"), [])
        stara.db.close()
        # aplikacja z danymi nie da się nadpisać
        r = urllib.request.Request(app + "api/przenosiny", data=b"SQLite format 3\x00", method="POST",
                                   headers={"X-Pojazdy-Klucz": "sekret"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(r, timeout=10)
        self.assertEqual(e.exception.code, 409)

    def test_lan_i_adres_ha(self):
        kat = tempfile.mkdtemp(prefix="pojazdy-lan-")
        app, _ = self._start({"PJ_DATA": kat, "PJ_SHARE": kat, "PJ_HA_URL": "http://127.0.0.1:9", "PJ_KLUCZ": "sekret", "PJ_LAN": "1"})
        self.assertEqual(len(self._req(app + "api/pojazdy")), 2)  # panel w sieci domowej bez klucza
        with self.assertRaises(urllib.error.HTTPError) as e:  # przenosiny zawsze z kluczem
            self._req(app + "api/przenosiny")
        self.assertEqual(e.exception.code, 403)
        # w dodatku adresy HA idą przez Supervisora (bez zmian)
        self.assertEqual(srv.ha_adres("/core/api/states/x"), "http://supervisor/core/api/states/x")

    def test_posrednik_bez_aplikacji(self):
        kat = tempfile.mkdtemp(prefix="pojazdy-brak-")
        with open(os.path.join(kat, "options.json"), "w") as f:
            json.dump({"adres_aplikacji": "http://127.0.0.1:9", "klucz_aplikacji": "x"}, f)
        dod, _ = self._start({"PJ_DATA": kat, "PJ_SHARE": kat, "PJ_PEERS": "127.0.0.1"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._req(dod + "api/start")
        self.assertEqual(e.exception.code, 502)
        self.assertIn("nie odpowiada", json.loads(e.exception.read())["blad"])


if __name__ == "__main__":
    unittest.main()
