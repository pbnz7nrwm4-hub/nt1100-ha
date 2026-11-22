"""Paczki mapy: wybór (pakiety.py), ciekawe miejsca (miejsca.py), kontrola zgodności i miejsca przy trasie w dodatku."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIL = os.path.join(HERE, "..", "silnik-tras")
sys.path.insert(0, SIL)
sys.path.insert(0, os.path.join(HERE, "..", "nt1100_jazdy"))
import miejsca  # noqa: E402
import pakiety  # noqa: E402
import kontrola_zgodnosci  # noqa: E402


def f(tags, lon=19.0, lat=50.0):
    return {"properties": tags, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


class Pakiety(unittest.TestCase):
    def test_smieci_wracaja_do_domyslnych(self):
        p = pakiety.popraw({"poi": ["jedzenie", "; rm -rf /"], "budynki": "tak", "miejsca": True, "miejsca_grupy": ["x"]})
        self.assertEqual(p["poi"], ["jedzenie"])
        self.assertFalse(p["budynki"])
        self.assertTrue(p["miejsca"])
        self.assertEqual(p["miejsca_grupy"], list(pakiety.MIEJSCA_GRUPY))

    def test_env_i_brak_pliku(self):
        e = pakiety.env(pakiety.popraw({"poi": ["jedzenie"]}))
        self.assertNotIn("jedzenie", e["MAPA_POI_BEZ"])
        self.assertIn("parkingi", e["MAPA_POI_BEZ"])
        out = subprocess.run([sys.executable, os.path.join(SIL, "pakiety.py"), "env", "/nie/ma"], capture_output=True, text=True)
        self.assertEqual(out.stdout, "")   # bez pliku nie nadpisujemy obszar.env

    def test_build_map_pomija_grupy(self):
        kod = "import build_map as b; print(sorted({k for _, k in b.POI_TAGS}))"
        pelna = subprocess.run([sys.executable, "-c", kod], cwd=SIL, capture_output=True, text=True).stdout
        bez = subprocess.run([sys.executable, "-c", kod], cwd=SIL, capture_output=True, text=True,
                             env=dict(os.environ, MAPA_POI_BEZ="jedzenie,parkingi")).stdout
        self.assertIn("11", pelna)
        self.assertNotIn("11", bez)
        self.assertNotIn("19", bez)
        self.assertIn("10", bez)   # stacje zawsze


class Miejsca(unittest.TestCase):
    def test_wybor(self):
        ms, inny = miejsca.wybierz([
            f({"historic": "castle", "wikipedia": "pl:Zamek_w_Pszczynie", "name": "Zamek"}),
            f({"historic": "castle", "wikipedia": "de:Schloss"}),
            f({"amenity": "fuel", "wikipedia": "pl:Stacja"}),
            f({"tourism": "museum", "wikipedia": "pl:Muzeum X"}),
        ], {"zamki"})
        self.assertEqual([m["t"] for m in ms], ["Zamek w Pszczynie"])
        self.assertEqual(inny, 1)

    def test_opisy_cache_i_blad_sieci(self):
        ms = [{"t": "A"}, {"t": "B"}]
        wolane = []

        def pob(t):
            wolane.append(list(t))
            return {x: ("Zdanie pierwsze. " + "x" * 500, "https://upload.wikimedia.org/%s.jpg" % x) for x in t}
        miejsca.opisy(ms, {"A": {"o": "z pamięci", "z": "https://a/a.jpg"}}, pob, pauza=0)
        self.assertEqual(wolane, [["B"]])
        self.assertEqual((ms[0]["o"], ms[0]["z"]), ("z pamięci", "https://a/a.jpg"))
        self.assertLessEqual(len(ms[1]["o"]), miejsca.OPIS_MAX)
        self.assertTrue(ms[1]["z"].endswith("B.jpg"))
        # stary cache (sam napis, bez zdjęcia) jest pobierany jeszcze raz
        wolane.clear()
        ms3 = [{"t": "A"}]
        miejsca.opisy(ms3, {"A": "stary opis"}, pob, pauza=0)
        self.assertEqual(wolane, [["A"]])
        self.assertTrue(ms3[0]["z"])

        def pada(t):
            raise OSError("brak sieci")
        ms2 = miejsca.opisy([{"t": "C"}], {}, pada, pauza=0, log=lambda *_: None)
        self.assertEqual(ms2[0]["o"], "")


class Zgodnosc(unittest.TestCase):
    def test_flagi_i_czesci(self):
        with tempfile.TemporaryDirectory() as d:
            dane = b"NTT1\x01\x03xx"
            with open(os.path.join(d, "c_1_2.ntt"), "wb") as fh:
                fh.write(dane)
            with open(os.path.join(d, "manifest.json"), "w") as fh:
                json.dump({"format": 1, "wersja": 8, "files": [["c_1_2.ntt", len(dane), zlib.crc32(dane)]], "graph": {"x": 1}}, fh)
            ok = kontrola_zgodnosci.kontrola(d, {"ntt_format": 1, "flagi_znane": 3, "czesci": "c,g,a,n,h"})
            self.assertTrue(ok["ok"], ok)
            zle = kontrola_zgodnosci.kontrola(d, {"ntt_format": 1, "flagi_znane": 1, "czesci": "c"})
            self.assertFalse(zle["ok"])
            self.assertEqual(len(zle["powody"]), 2)


class PrzyTrasie(unittest.TestCase):
    def test_ciekawe_along(self):
        import nav
        with tempfile.TemporaryDirectory() as d:
            n = nav.Nav(os.path.join(d, "s"), d, lambda: {})
            n._ciekawe = (9e18, None)
            self.assertIsNone(n.ciekawe_along({"pts": [[50, 19], [50, 19.2]]}))
            blisko = {"n": "Zamek", "g": "zamki", "lat": 50.01, "lon": 19.1, "t": "Zamek X", "o": "Opis."}
            daleko = {"n": "Daleko", "g": "muzea", "lat": 50.3, "lon": 19.1, "t": "Daleko", "o": ""}
            n._ciekawe = (9e18, {(500, 191): [blisko], (503, 191): [daleko]})
            pts = [[50.0, 19.0 + i * 0.01] for i in range(21)]
            out = n.ciekawe_along({"pts": pts}, 5000.0)
            self.assertEqual([p["name"] for p in out], ["Zamek"])
            self.assertEqual(out[0]["kind"], 90)
            self.assertTrue(out[0]["wiki"].endswith("/Zamek_X"))
            self.assertLess(out[0]["off_m"], 1500)


if __name__ == "__main__":
    unittest.main()
