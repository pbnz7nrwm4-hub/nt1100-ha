"""Składnia skryptów strony dodatku (index.html i nav.js) – błąd w JS wyłącza cały panel.

Wymaga node; bez niego test jest pomijany."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nt1100_jazdy", "www")


@unittest.skipUnless(shutil.which("node"), "brak node")
class StronaTest(unittest.TestCase):
    def check(self, path):
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_nav_js(self):
        self.check(os.path.join(WWW, "nav.js"))

    def test_index_html(self):
        with open(os.path.join(WWW, "index.html"), encoding="utf-8") as f:
            html = f.read()
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        # 1.5.29: cały wyjazd ma te same wykresy i odtwarzanie co jedna jazda
        self.assertIn("function rideCharts(", html)
        self.assertIn("player(D,m,pts,xs,map,trk,CH)", html)
        # 1.5.30: widok mapy przed rysowaniem linii (inaczej Leaflet rzuca błąd i zostaje sam szkic)
        mv = html[html.index("function mapView("):]
        self.assertLess(mv.index("map.fitBounds("), mv.index("map._draw(o.mode"))
        with tempfile.TemporaryDirectory() as d:
            for i, js in enumerate(scripts):
                p = os.path.join(d, "s%d.js" % i)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(js)
                self.check(p)

    def test_moj_plan_w_kolorach_odcinkow(self):
        with open(os.path.join(WWW, "nav.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function legLine(", js)
        self.assertIn("function legCuts(", js)
        self.assertGreaterEqual(js.count("legLine(r,ll)"), 2)  # wynik planowania i zapisana trasa

    def test_wyszukiwarka_i_pinezki(self):
        with open(os.path.join(WWW, "nav.js"), encoding="utf-8") as f:
            js = f.read()
        # pola Start/Cel z wyszukiwarką na cały ekran i pinezki bez ucinanych etykiet
        for s in ("function openSearch(", "function applyPick(", "function pinIcon(", "api/nav/miejsca?q="):
            self.assertIn(s, js)
        self.assertNotIn("permanent:true,direction:'top',offset:[-15,-10]", js)


if __name__ == "__main__":
    unittest.main()
