"""Tests of the navigation part of the add-on (no Home Assistant, no internet).

Run: python3 -m unittest discover -s tests
"""
import binascii
import functools
import io
import importlib.util
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(HERE, "..", "nt1100_jazdy")
SERVER = os.path.join(ADDON, "server.py")
BUILD_MAP = os.path.join(HERE, "..", "silnik-tras", "build_map.py")

TMP = tempfile.mkdtemp(prefix="nt1100-nav-test-")
os.environ.update({
    "NT_SHARE": os.path.join(TMP, "share"), "NT_DATA": os.path.join(TMP, "data"),
    "NT_INGRESS_PEERS": "127.0.0.1", "NT_INGRESS_PORT": "0", "NT_INGEST_PORT": "0", "NT_WEATHER": "0",
    "SUPERVISOR_TOKEN": "", "NT_FIRMWARE": os.path.join(TMP, "fw"),
})
os.environ["no_proxy"] = os.environ.get("no_proxy", "") + ",127.0.0.1,localhost"
os.environ["NO_PROXY"] = os.environ["no_proxy"]
sys.path.insert(0, ADDON)
spec = importlib.util.spec_from_file_location("server", SERVER)
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
import nav  # noqa: E402
import ntt  # noqa: E402

_ms = importlib.util.spec_from_file_location("mapa_serwer", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "silnik-tras", "mapa-serwer.py"))
MS = importlib.util.module_from_spec(_ms)
_ms.loader.exec_module(MS)

spec2 = importlib.util.spec_from_file_location("build_map", BUILD_MAP)
build_map = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(build_map)

KEY = "klucz-testowy"


def line(lat0, lon0, heading, length_m, step_m=20.0):
    """Points along a straight line (lat, lon)."""
    out = []
    n = int(length_m / step_m) + 1
    for i in range(n):
        d = i * step_m
        lat = lat0 + d * math.cos(math.radians(heading)) / 111320.0
        lon = lon0 + d * math.sin(math.radians(heading)) / (111320.0 * math.cos(math.radians(lat0)))
        out.append((lat, lon))
    return out


def l_shape():
    """1 km north then 1 km east: one right turn."""
    a = line(50.0, 19.9, 0, 1000)
    b = line(a[-1][0], a[-1][1], 90, 1000)[1:]
    return a + b


GPX = """<?xml version="1.0"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
<wpt lat="50.0045" lon="19.9"><name>Przełęcz</name></wpt>
<wpt lat="51.0" lon="21.0"><name>daleko</name></wpt>
<trk><name>Testowa</name><trkseg>%s</trkseg></trk></gpx>"""


class FakeGraphHopper(BaseHTTPRequestHandler):
    """Answers /route with the L-shaped path regardless of the request."""
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
        FakeGraphHopper.calls.append(body)
        pts = l_shape()
        n = len(pts)
        out = {"paths": [{
            "points": {"coordinates": [[p[1], p[0]] for p in pts]},
            "distance": 2000.0, "time": 120000,
            "details": {"time": [[0, n - 1, 120000]], "max_speed": [[0, n // 2, 90], [n // 2, n - 1, 50]]},
            "instructions": [{"sign": 0, "interval": [0, 50], "street_name": "Północna"},
                             {"sign": 2, "interval": [50, 100], "street_name": "Wschodnia"},
                             {"sign": 4, "interval": [100, 100], "street_name": ""}],
        }]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GeometryTest(unittest.TestCase):
    def test_turns_from_geometry(self):
        pts = nav.densify(l_shape(), 30)
        cum = nav.cum_dist(pts)
        turns = nav.turns_from_geometry(pts, cum)
        kinds = [t["type"] for t in turns]
        self.assertEqual(kinds, [nav.T_RIGHT])
        self.assertAlmostEqual(cum[turns[0]["idx"]], 1000, delta=20)

    def test_curviness_levels(self):
        pts = nav.densify(l_shape(), 30)
        c = nav.curviness(pts, nav.cum_dist(pts))
        self.assertEqual(c["level"], "lekko kręta")
        wind = []
        lat, lon, head = 50.0, 19.9, 0.0
        for t in range(600):
            head += 6 * math.sin(t / 15.0)
            lat += 15 * math.cos(math.radians(head)) / 111320
            lon += 15 * math.sin(math.radians(head)) / (111320 * math.cos(math.radians(lat)))
            wind.append((lat, lon))
        c = nav.curviness(wind, nav.cum_dist(wind))
        self.assertEqual(c["level"], "bardzo kręta")

    def test_search_without_language(self):
        # Photon odrzuca lang=pl; zapytanie ma iść bez parametru języka.
        seen = []
        orig = nav.http_json
        nav.http_json = lambda url, timeout=0: seen.append(url) or {"features": [{
            "properties": {"name": "Rynek", "city": "Wrocław"},
            "geometry": {"coordinates": [17.03, 51.11]}}]}
        try:
            out = nav.Nav.search(None, "Wrocław Rynek", 50.1, 19.1)
            name = nav.Nav.reverse(None, 51.11, 17.03)
        finally:
            nav.http_json = orig
        self.assertEqual(out[0]["lat"], 51.11)
        self.assertEqual(name, "Rynek")
        self.assertTrue(seen and all("lang=" not in u for u in seen))

    def test_weather_one_request_and_cache(self):
        seen = []
        hourly = {"time": [time.strftime("%Y-%m-%dT%H:00", time.gmtime(time.time() + h * 3600)) for h in range(-2, 30)]}
        for k in ("temperature_2m", "precipitation_probability", "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m"):
            hourly[k] = [1] * len(hourly["time"])

        def fake(url, timeout=0):
            seen.append(url)
            n = len(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["latitude"][0].split(","))
            return [{"hourly": hourly} for _ in range(n)] if n > 1 else {"hourly": hourly}
        orig = nav.http_json
        nav.http_json = fake
        nav.WX_CACHE.clear()
        try:
            pts = line(50.5, 19.0, 0, 120000, 1000.0)
            times = [i * 60 for i in range(len(pts))]  # 2 h jazdy, punkt co 30 min
            wx = nav.Nav.weather_along(None, pts, None, times)
            self.assertEqual(len(seen), 1)
            self.assertEqual(len(wx), 5)
            nav.Nav.weather_along(None, pts, None, times)
            self.assertEqual(len(seen), 1)  # z pamięci
        finally:
            nav.http_json = orig
            nav.WX_CACHE.clear()

    def test_place_links(self):
        p = nav.Nav.parse_place_link("https://www.google.com/maps/place/Zakopane/@49.2992,19.9496,14z/data=xyz")
        self.assertAlmostEqual(p["lat"], 49.2992)
        self.assertEqual(p["name"], "Zakopane")
        p = nav.Nav.parse_place_link("https://maps.apple.com/?ll=50.0614,19.9366&q=Kraków")
        self.assertAlmostEqual(p["lon"], 19.9366)
        p = nav.Nav.parse_place_link("50.06, 19.94")
        self.assertAlmostEqual(p["lat"], 50.06)
        self.assertIsNone(nav.Nav.parse_place_link("Zakopane"))
        self.assertIsNone(nav.Nav.parse_place_link("https://maps.app.goo.gl/abc"))

    def test_gpx_round_trip(self):
        pts = l_shape()
        seg = "".join('<trkpt lat="%.6f" lon="%.6f"></trkpt>' % p for p in pts)
        g = nav.parse_gpx((GPX % seg).encode())
        self.assertEqual(g["name"], "Testowa")
        self.assertEqual(len(g["pts"]), len(pts))
        self.assertEqual(len(g["wpts"]), 2)
        route = {"name": "Testowa", "pts": pts, "cum": nav.cum_dist(pts), "waypoints": [{"idx": 0, "name": "start"}],
                 "turns": []}
        back = nav.parse_gpx(nav.to_gpx(route).encode())
        self.assertEqual(len(back["pts"]), len(pts))

    def test_pack_ntr_header(self):
        pts = nav.densify(l_shape(), 30)
        cum = nav.cum_dist(pts)
        route = {"id": 7, "version": 1234, "name": "Próbna ąę", "pts": pts, "cum": cum, "times": [i * 2 for i in range(len(pts))],
                 "turns": [{"idx": 3, "type": nav.T_RIGHT, "exit": 0, "text": "Wschodnia"}],
                 "limits": [{"idx": 0, "kmh": 90}], "cameras": [{"idx": 5, "type": 1, "limit": 50, "pair": 0}],
                 "weather": [{"idx": 0, "t": 1700000000, "temp": 12.4, "rain_prob": 30, "code": 61, "wind": 20}],
                 "waypoints": [{"idx": len(pts) - 1, "name": "cel", "kind": 2}]}
        b = nav.pack_ntr(route)
        magic, ver, _, nwp, rid, rver, npts, nturn, nlim, ncam, nwx, _, name = struct.unpack_from("<4sBBHIIIHHHHH40s", b, 0)
        self.assertEqual((magic, rid, rver, npts, nturn, nlim, ncam, nwx, nwp), (b"NTR1", 7, 1234, len(pts), 1, 1, 1, 1, 1))
        self.assertEqual(name.rstrip(b"\0").decode(), "Próbna ąę")
        head = struct.calcsize("<4sBBHIIIHHHHH40s")
        self.assertEqual(len(b), head + 14 * len(pts) + 40 + 8 + 8 + 12 + 40)
        lat, lon, c, t = struct.unpack_from("<iiIH", b, head + 14 * 10)
        self.assertEqual(c, int(cum[10]))
        self.assertEqual(t, 2)


class TileTest(unittest.TestCase):
    def test_write_and_read_cell(self):
        cell = build_map.Cell((500, 199))
        pts = l_shape()
        cell.add_way(12345, 4, ntt.F_LIT, 90, 70, "Długa", "DW958", pts, [(0, 1), (len(pts) - 1, 2)])
        cell.add_way(12346, 9, ntt.F_UNPAVED | ntt.F_ONEWAY, 0, 0, "", "", pts[:3], [])
        cell.add_point(900, 50.001, 19.9, ntt.P_CAMERA, 50, "", 0)
        cell.add_point(901, 50.002, 19.9, ntt.P_FUEL, 0, "Orlen", 0)
        d = tempfile.mkdtemp(prefix="nt1100-ntt-")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "c_500_199.ntt")
        cell.write(path)
        ways, points = ntt.read_cell(path)
        self.assertEqual(len(ways), 2)
        w = ways[0]
        self.assertEqual((w.id, w.cls, w.limit, w.limit_back, w.name, w.ref, len(w.pts)), (12345, 4, 90, 70, "Długa", "DW958", len(pts)))
        self.assertAlmostEqual(w.pts[-1][0], pts[-1][0], places=6)
        self.assertEqual(w.junctions, [(0, 1), (len(pts) - 1, 2)])
        self.assertTrue(ways[1].flags & ntt.F_UNPAVED)
        self.assertEqual([p.kind for p in points], [ntt.P_CAMERA, ntt.P_FUEL])
        self.assertEqual(points[1].name, "Orlen")
        m = ntt.Map(d)
        r = m.match_road(50.0005, 19.9, heading=0)
        self.assertIsNotNone(r)
        self.assertEqual(r[0].id, 12345)
        self.assertTrue(r[2])
        r = m.match_road(50.0005, 19.9, heading=180)
        self.assertFalse(r[2])
        near = m.points_near(50.0, 19.9, 500, kinds={ntt.P_CAMERA})
        self.assertEqual(len(near), 1)
        self.assertEqual(near[0][1].limit, 50)


class TileSampleTest(unittest.TestCase):
    def test_bbox_sample_covers_area(self):
        cell = build_map.Cell((500, 199))
        cell.add_way(1, 4, 0, 90, 90, "", "", line(50.0, 19.9, 90, 5000, 50.0), [])
        nid = 1000
        for i in range(30):
            for k in range(30):
                cell.add_point(nid, 50.0 + i * 0.003, 19.9 + k * 0.003, ntt.P_FUEL, 0, "", 0)
                nid += 1
        cell.add_point(5, 50.09, 19.99, ntt.P_CAMERA, 50, "", 0)
        d = tempfile.mkdtemp(prefix="nt1100-ntt-")
        self.addCleanup(shutil.rmtree, d, True)
        cell.write(os.path.join(d, "c_500_199.ntt"))
        m = ntt.Map(d)
        pts = m.points_in_bbox(50.0, 19.9, 50.1, 20.0, None, 100)
        self.assertEqual(len(pts), 100)
        self.assertIn(ntt.P_CAMERA, [p.kind for p in pts])
        self.assertGreater(max(p.lat for p in pts), 50.07)  # nie tylko południe obszaru
        # dopasowanie drogi przez siatkę odcinków, także daleko od początku drogi
        r = m.match_road(50.0001, 19.9 + 4000 / (111320.0 * math.cos(math.radians(50.0))), heading=90)
        self.assertIsNotNone(r)
        self.assertEqual(r[0].id, 1)
        self.assertIsNone(m.match_road(50.01, 19.95, radius_m=30))


class NavServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for d in (srv.RIDES, srv.INCOMING, srv.CACHE, srv.DATA):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(srv.DATA, "options.json"), "w") as f:
            json.dump({"klucz": KEY}, f)
        srv.navapi.init(srv)
        cls.page = srv.serve(0, srv.Page)
        cls.ingest = srv.serve(0, srv.Ingest)
        cls.gh = ThreadingHTTPServer(("127.0.0.1", 0), FakeGraphHopper)
        threading.Thread(target=cls.gh.serve_forever, daemon=True).start()
        cls.pu = "http://127.0.0.1:%d" % cls.page.server_address[1]
        cls.iu = "http://127.0.0.1:%d" % cls.ingest.server_address[1]
        cls.ghu = "http://127.0.0.1:%d" % cls.gh.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.page.shutdown()
        cls.ingest.shutdown()
        cls.gh.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)

    def req(self, url, data=None, headers=None, method=None):
        r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def jpost(self, url, obj, headers=None):
        code, body, _ = self.req(url, json.dumps(obj).encode(), dict({"Content-Type": "application/json"}, **(headers or {})), "POST")
        return code, json.loads(body)

    def test_01_page_lists_and_script(self):
        code, body, _ = self.req(self.pu + "/api/nav/routes")
        self.assertEqual(code, 200)
        j = json.loads(body)
        self.assertEqual(j["routes"], [])
        self.assertFalse(j["map"]["available"])
        self.assertEqual(j["settings"]["default_variant"], "kreto")
        code, body, h = self.req(self.pu + "/nav.js")
        self.assertEqual(code, 200)
        self.assertIn(b"Nawigacja", body)
        code, body, _ = self.req(self.pu + "/")
        self.assertIn(b'src="nav.js"', body)

    def test_02_screen_needs_key(self):
        code, body, _ = self.req(self.iu + "/api/nav/ping")
        self.assertEqual(code, 401)
        code, body, _ = self.req(self.iu + "/api/nav/ping?klucz=zly")
        self.assertEqual(code, 401)
        code, body, _ = self.req(self.iu + "/api/nav/ping?klucz=" + KEY + "&lat=50.1&lon=19.8&v=0.9.1&bat=77")
        self.assertEqual(code, 200)
        j = json.loads(body)
        self.assertTrue(j["ok"])
        self.assertIsNone(j["route"])
        self.assertIn("lean_popup_deg", j["settings"])
        code, body, _ = self.req(self.pu + "/api/nav/screen")
        s = json.loads(body)["screen"]
        self.assertEqual((s["fw"], s["battery"]), ("0.9.1", 77))

    def test_03_gpx_import_to_screen(self):
        pts = l_shape()
        seg = "".join('<trkpt lat="%.6f" lon="%.6f"></trkpt>' % p for p in pts)
        code, body, _ = self.req(self.pu + "/api/nav/gpx?name=Z+Kurvigera+%C5%81%C3%B3d%C5%BA", (GPX % seg).encode(),
                                 {"Content-Type": "application/gpx+xml"}, "POST")
        self.assertEqual(code, 200, body)
        j = json.loads(body)
        rid = j["id"]
        r = j["route"]
        self.assertEqual(r["name"], "Z Kurvigera Łódź")
        self.assertAlmostEqual(r["km"], 2.0, places=1)
        self.assertEqual(r["source"], "gpx")
        self.assertEqual([w["name"] for w in r["waypoints"]], ["Przełęcz", "cel"])
        self.assertTrue(any(t["type"] == nav.T_RIGHT for t in r["turns"]))
        # the screen sees it as current and can download the package
        code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
        j = json.loads(body)
        self.assertEqual(j["route"]["id"], rid)
        code, body, _ = self.req(self.iu + "/api/nav/route.ntr?id=%d" % rid, headers={"X-Klucz": KEY})
        self.assertEqual(code, 200)
        self.assertEqual(body[:4], b"NTR1")
        code, body, _ = self.req(self.iu + "/api/nav/route.json?id=%d" % rid, headers={"X-Klucz": KEY})
        self.assertEqual(json.loads(body)["id"], rid)
        code, body, h = self.req(self.pu + "/api/nav/gpx?id=%d" % rid)
        self.assertEqual(code, 200)
        self.assertIn(b"<trkpt", body)
        # Polish letters in the name: plain filename without them, the real one in filename*
        cd = h.get("Content-Disposition")
        self.assertIn('filename="Z_Kurvigera_Lodz.gpx"', cd)
        self.assertIn("filename*=UTF-8''Z_Kurvigera_%C5%81%C3%B3d%C5%BA.gpx", cd)
        # take it off the screen
        code, j = self.jpost(self.pu + "/api/nav/current", {"id": 0})
        self.assertEqual(code, 200)
        code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
        self.assertIsNone(json.loads(body)["route"])

    def test_04_settings_validation(self):
        code, j = self.jpost(self.pu + "/api/nav/settings", {"engine_url": "ftp://x"})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/settings", {"lean_popup_deg": 90})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/settings", {"avoid": ["rzeki"]})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu, "tomtom_key": "abc", "lean_popup_deg": 25,
                                                             "avoid": ["promy"], "home": {"lat": 50.0, "lon": 19.9, "name": "Dom"}})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["engine_url"], self.ghu)
        self.assertIs(j["tomtom_key"], True)
        self.assertEqual(j["lean_popup_deg"], 25)
        self.assertEqual(j["home"]["name"], "Dom")
        # saved in the add-on state and visible to the screen
        code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
        j = json.loads(body)
        self.assertEqual(j["settings"]["lean_popup_deg"], 25)
        self.assertTrue(j["traffic"])

    def test_05_plan_send_reroute(self):
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu})
        FakeGraphHopper.calls = []
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": [{"lat": 50.0, "lon": 19.9, "name": "Dom"},
                                                                    {"lat": 50.005, "lon": 19.9, "name": "Sklep"},
                                                                    {"lat": 50.009, "lon": 19.914, "name": "Zakopane"}],
                                                         "variants": ["szybko", "kreto"], "avoid": ["gruntowe"], "weather": False})
        self.assertEqual(code, 200, j)
        self.assertEqual(len(j["routes"]), 2)
        self.assertEqual(len(FakeGraphHopper.calls), 2)
        # warianty liczą się równolegle, więc kolejność zapytań do silnika jest dowolna
        curvy = [b for b in FakeGraphHopper.calls if any("curvature" in json.dumps(p) for p in b["custom_model"]["priority"])]
        self.assertEqual(len(curvy), 1)
        body = curvy[0]
        self.assertEqual(body["profile"], "motocykl")
        self.assertEqual(body["points"][0], [19.9, 50.0])
        r = [x for x in j["routes"] if x["variant"] == "kreto"][0]
        self.assertEqual([w["name"] for w in r["waypoints"]], ["Sklep", "Zakopane"])
        self.assertEqual([l["kmh"] for l in r["limits"]][:2], [90, 50])
        self.assertTrue(any(t["text"] == "Wschodnia" and t["type"] == nav.T_RIGHT for t in r["turns"]))
        self.assertEqual(r["min"], 2)
        code, s = self.jpost(self.pu + "/api/nav/send", {"token": j["token"], "variant": "kreto", "name": "Do Zakopanego"})
        self.assertEqual(code, 200, s)
        rid = s["id"]
        code, body, _ = self.req(self.pu + "/api/nav/routes")
        lst = json.loads(body)
        self.assertEqual(lst["current"], rid)
        self.assertEqual(lst["routes"][0]["name"], "Do Zakopanego")
        self.assertEqual(lst["recent"][0]["name"], "Zakopane")
        # the screen asks for a detour from halfway
        code, s = self.jpost(self.iu + "/api/nav/reroute", {"id": rid, "lat": 50.004, "lon": 19.9, "heading": 0, "skip": True},
                             {"X-Klucz": KEY})
        self.assertEqual(code, 200, s)
        self.assertEqual(s["id"], rid)
        last = FakeGraphHopper.calls[-1]
        # start = position, the next waypoint skipped, only the finish remains
        self.assertEqual(len(last["points"]), 2)
        code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
        self.assertEqual(json.loads(body)["route"]["version"], s["version"])
        # expired token
        code, s = self.jpost(self.pu + "/api/nav/send", {"token": "nie-ma", "variant": "kreto"})
        self.assertEqual(code, 410)

    def test_05b_sliders_levels_and_my_plan(self):
        # sliders change the engine request; bad values are refused
        code, j = self.jpost(self.pu + "/api/nav/settings", {"curvy": {"kreto": {"glowne": 150}}})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/settings", {"curvy_levels": [80, 30, 150]})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu,
                                                             "curvy": {"kreto": {"glowne": 0, "zakrety": 100, "dluzej": 100}},
                                                             "curvy_levels": [5, 10, 20]})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["curvy"]["kreto"], {"glowne": 0, "zakrety": 100, "dluzej": 100})
        self.assertEqual(j["curvy"]["lekko"], nav.CURVY_DEFAULT["lekko"])
        FakeGraphHopper.calls = []
        pts = [{"lat": 50.0, "lon": 19.9, "name": "A"}, {"lat": 50.005, "lon": 19.9, "name": "B"},
               {"lat": 50.009, "lon": 19.914, "name": "C"}]
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["kreto"], "weather": False})
        self.assertEqual(code, 200, j)
        cm = FakeGraphHopper.calls[0]["custom_model"]
        pri = {json.dumps(p.get("if") or p.get("else_if")): p["multiply_by"] for p in cm["priority"]}
        self.assertEqual(pri['"road_class == MOTORWAY"'], "1.0")      # glowne 0: motorways not avoided
        self.assertEqual(pri['"curvature > 0.97"'], "0.35")           # zakrety 100: straight roads penalised
        self.assertEqual(cm["distance_influence"], 5)                 # dluzej 100
        # the description follows the thresholds (L-shaped test route: 90° turn over 2 km)
        self.assertEqual(j["routes"][0]["curvy"]["level"], "bardzo kręta")
        # legs: each section with its own variant -> extra "mix" route glued from two engine requests
        FakeGraphHopper.calls = []
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["szybko"], "legs": ["szybko", "bardzo"],
                                                         "weather": False})
        self.assertEqual(code, 200, j)
        self.assertEqual(sorted(r["variant"] for r in j["routes"]), ["mix", "szybko"])
        self.assertEqual(len(FakeGraphHopper.calls), 3)
        mix = [r for r in j["routes"] if r["variant"] == "mix"][0]
        self.assertEqual(mix["legs"], ["szybko", "bardzo"])
        self.assertEqual(len(mix["leg_m"]), 2)
        self.assertTrue(all(m > 0 for m in mix["leg_m"]))  # proportions for the leg bar
        self.assertGreaterEqual(mix["km"], 4.0)  # two 2 km sections (the fake engine returns the same L)
        self.assertEqual([w["name"] for w in mix["waypoints"]][:2], ["B", "C"])
        legs_req = [len(b["points"]) for b in FakeGraphHopper.calls]
        self.assertEqual(sorted(legs_req), [2, 2, 3])
        code, j2 = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "legs": ["szybko"], "weather": False})
        self.assertEqual(code, 400)
        # rerouting a "mix" route keeps the variant of the remaining section
        code, s = self.jpost(self.pu + "/api/nav/send", {"token": j["token"], "variant": "mix", "current": False})
        self.assertEqual(code, 200, s)
        FakeGraphHopper.calls = []
        nav_route = srv.navapi.NAV.route(s["id"])
        mid = nav_route["pts"][len(nav_route["pts"]) * 3 // 4]
        srv.navapi.NAV.reroute(s["id"], mid[0], mid[1])
        self.assertEqual(srv.navapi.NAV.route(s["id"])["variant"], "mix")
        self.jpost(self.pu + "/api/nav/settings", {"curvy": nav.CURVY_DEFAULT, "curvy_levels": None})

    def test_06_goto_from_coordinates(self):
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu, "home": {"lat": 50.0, "lon": 19.9, "name": "Dom"}})
        code, body, _ = self.req(self.iu + "/api/nav/goto?klucz=" + KEY + "&text=" + urllib.parse.quote("50.009, 19.914"))
        self.assertEqual(code, 200, body)
        j = json.loads(body)
        self.assertTrue(j["ok"])
        self.assertEqual(j["route"]["variant"], "kreto")
        code, body, _ = self.req(self.pu + "/api/nav/routes")
        self.assertEqual(json.loads(body)["current"], j["route"]["id"])

    def test_07_screen_log_and_compliance(self):
        pts = l_shape()
        seg = "".join('<trkpt lat="%.6f" lon="%.6f"></trkpt>' % p for p in pts)
        code, body, _ = self.req(self.pu + "/api/nav/gpx?name=Plan", (GPX % seg).encode(), {"Content-Type": "application/gpx+xml"}, "POST")
        rid = json.loads(body)["id"]
        import calendar
        t0 = calendar.timegm((2027, 1, 2, 10, 0, 0))
        code, j = self.jpost(self.iu + "/api/nav/log", {"entries": [{"t": t0 + 60, "what": "offroute", "idx": 10}]}, {"X-Klucz": KEY})
        self.assertEqual((code, j["saved"]), (200, 1))
        # a ride half on the plan, then 330 m north of its eastern leg
        lines = []
        for i, p in enumerate(pts):
            lat = p[0] + (0.003 if i > len(pts) // 2 else 0)
            lines.append("%.6f,%.6f,0,60,300,%d,,,,,," % (lat, p[1], i))
        trk = ("\n".join(lines) + "\n").encode()
        import zlib
        q = "n=3&id=20270102-100000&ext=trk&size=%d&crc=%08x" % (len(trk), zlib.crc32(trk) & 0xFFFFFFFF)
        self.assertEqual(self.req(self.iu + "/api/ingest?" + q, trk, {"X-Klucz": KEY}, "POST")[0], 200)
        s = json.dumps({"ride": "20270102-100000", "start": "2027-01-02T10:00:00Z", "end": "2027-01-02T10:02:00Z",
                        "distance_km": 2.0, "moving_min": 2, "max_speed": 60}).encode()
        q = "n=3&id=20270102-100000&ext=json&size=%d&crc=%08x" % (len(s), zlib.crc32(s) & 0xFFFFFFFF)
        code, body, _ = self.req(self.iu + "/api/ingest?" + q, s, {"X-Klucz": KEY}, "POST")
        self.assertEqual(code, 200, body)
        n = json.loads(body)["n"]
        code, body, _ = self.req(self.pu + "/api/nav/plan?n=%d" % n)
        self.assertEqual(code, 200, body)
        c = json.loads(body)["plan"]
        self.assertEqual(c["route"], rid)
        self.assertTrue(30 <= c["pct"] <= 70, c)
        self.assertTrue(c["deviations"])
        self.assertTrue(c["pts"])
        self.assertEqual(c["events"][0]["what"], "offroute")


    def test_08_nearby_and_stop_at_place(self):
        # mapa w dodatku: stacja 50 m od wschodniego odcinka trasy w kształcie L
        nv = srv.navapi.NAV
        cell = build_map.Cell((500, 199))
        cell.add_point(777, 50.0094, 19.907, ntt.P_FUEL, 0, "Orlen", 0)
        cell.add_point(778, 50.0300, 19.950, ntt.P_FUEL, 0, "Daleko", 0)
        cell.write(os.path.join(nv.map_dir, "c_500_199.ntt"))
        with open(os.path.join(nv.map_dir, "manifest.json"), "w") as f:
            json.dump({"built": "test", "files": [{"name": "c_500_199.ntt", "size": 1}]}, f)
        nv.map.cells.clear()
        nv.map.order.clear()
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu})
        code, body, _ = self.req(self.iu + "/api/nav/goto?klucz=" + KEY + "&text=" + urllib.parse.quote("50.009, 19.914"))
        self.assertEqual(code, 200, body)
        rid = json.loads(body)["route"]["id"]
        # wzdłuż zapisanej trasy
        code, body, _ = self.req(self.pu + "/api/nav/along?id=%d&kinds=10&max=2000" % rid)
        a = json.loads(body)["points"]
        self.assertEqual([p["name"] for p in a], ["Orlen"])
        self.assertLess(a[0]["off_m"], 80)
        self.assertAlmostEqual(a[0]["km"], 1.5, delta=0.1)
        # motocykl na początku trasy: stacja przed nim, po trasie
        self.req(self.iu + "/api/nav/ping?klucz=" + KEY + "&lat=50.0002&lon=19.9")
        code, body, _ = self.req(self.pu + "/api/nav/nearby?kinds=10")
        j = json.loads(body)
        self.assertEqual((j["mode"], j["pos"]["src"]), ("trasa", "ekran"))
        self.assertEqual(j["points"][0]["name"], "Orlen")
        self.assertAlmostEqual(j["points"][0]["dist_km"], 1.5, delta=0.1)
        # „Jedź tam”: postój dodany jako punkt po drodze bieżącej trasy
        code, j = self.jpost(self.pu + "/api/nav/via", {"lat": 50.0094, "lon": 19.907, "name": "Orlen"})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["route"]["id"], rid)
        r = json.loads(self.req(self.pu + "/api/nav/route?id=%d" % rid)[1])
        self.assertIn("Orlen", [w["name"] for w in r["waypoints"]])
        self.assertEqual(json.loads(self.req(self.pu + "/api/nav/routes")[1])["current"], rid)
        # ekran też może poprosić o postój (z kluczem)
        code, j = self.jpost(self.iu + "/api/nav/via?klucz=" + KEY,
                             {"lat": 50.0002, "lon": 19.9, "plat": 50.0094, "plon": 19.907, "name": "Orlen"})
        self.assertEqual(code, 200, j)
        self.assertTrue(j["ok"])
        # POI na mapie: legenda/próbka nie gubi punktów w małym obszarze
        code, body, _ = self.req(self.pu + "/api/nav/poi?bbox=49.99,19.89,50.04,19.96")
        self.assertEqual(len(json.loads(body)["points"]), 2)

    def test_09_demo_route_and_full_points(self):
        code, j = self.jpost(self.pu + "/api/nav/demo", {})
        self.assertEqual(code, 200, j)
        rid = j["id"]
        code, body, _ = self.req(self.pu + "/api/nav/route?id=%d&full=1" % rid)
        r = json.loads(body)
        self.assertEqual(r["source"], "demo")
        self.assertEqual(len(r["pts"]), len(r["cum"]))
        self.assertGreater(r["cum"][-1], 20000)
        self.assertTrue(any(c["type"] == 2 for c in r["cameras"]))
        self.assertEqual([w["kind"] for w in r["waypoints"]], [1, 2])
        self.assertGreater(r["weather"][0]["t"], 1700000000)
        # not put on the screen by itself; the screen can still download it
        lst = json.loads(self.req(self.pu + "/api/nav/routes")[1])
        self.assertNotEqual(lst["current"], rid)
        code, body, _ = self.req(self.iu + "/api/nav/route.ntr?id=%d" % rid, headers={"X-Klucz": KEY})
        self.assertEqual(code, 200)
        self.assertEqual(body[:4], b"NTR1")


    def test_10_vector_map_from_container(self):
        """Styl, czcionki, kafelki PMTiles i wysokości: kontener -> dodatek -> przeglądarka."""
        import gzip
        code, body, h = self.req(self.pu + "/mapa-ciemna.json")
        self.assertEqual(code, 200)
        st = json.loads(body)
        ids = [l["id"] for l in st["layers"]]
        self.assertIn("hillshade", ids)
        self.assertIn("mountain_peak", ids)
        self.assertNotIn("sprite", st)
        fonts = {f for l in st["layers"] for f in (l.get("layout", {}).get("text-font") or [])}
        for f in fonts:
            code, _, _ = self.req(self.pu + "/fonty/" + urllib.parse.quote(f) + "/0-255.pbf")
            self.assertEqual(code, 200, f)
        code, _, _ = self.req(self.pu + "/fonty/..%2F..%2Fserver.py/0-255.pbf")
        self.assertEqual(code, 404)
        # container with one vector tile (z1 x1 y0) and one DEM tile
        root = tempfile.mkdtemp(dir=TMP)
        tile = gzip.compress(b"\x1a\x02xy")
        tid = MS.tile_id(1, 1, 0)

        def v(n):
            out = b""
            while True:
                b, n = n & 0x7F, n >> 7
                out += bytes([b | (0x80 if n else 0)])
                if not n:
                    return out
        d = v(1) + v(tid) + v(1) + v(len(tile)) + v(1)
        hdr = b"PMTiles" + bytes([3]) + struct.pack("<8Q", 127, len(d), 127 + len(d), 0, 127 + len(d), 0,
                                                   127 + len(d), len(tile))
        hdr += struct.pack("<3Q", 1, 1, 1) + bytes([1, 1, 2, 1, 0, 14]) + struct.pack("<4i", 140000000, 489000000, 243000000, 550000000)
        hdr += bytes(127 - len(hdr))
        with open(os.path.join(root, "kafelki.pmtiles"), "wb") as f:
            f.write(hdr + d + tile)
        os.makedirs(os.path.join(root, "dem", "12", "2"))
        with open(os.path.join(root, "dem", "12", "2", "3.png"), "wb") as f:
            f.write(b"\x89PNGdem")
        ms = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(MS.H, directory=root))
        threading.Thread(target=ms.serve_forever, daemon=True).start()
        try:
            code, j = self.jpost(self.pu + "/api/nav/settings", {"map_url": "http://127.0.0.1:%d" % ms.server_address[1]})
            self.assertEqual(code, 200, j)
            srv.navapi._TILES.update(t=0, info=None)
            code, body, _ = self.req(self.pu + "/api/nav/kafelki/info")
            info = json.loads(body)
            self.assertTrue(info["local"])
            self.assertTrue(info["dem"])
            self.assertEqual(info["maxzoom"], 14)
            code, body, h = self.req(self.pu + "/api/nav/kafelki/1/1/0.pbf")
            self.assertEqual((code, body), (200, b"\x1a\x02xy"))   # unpacked for the browser
            self.assertIn("max-age", h.get("Cache-Control", ""))
            code, body, _ = self.req(self.pu + "/api/nav/kafelki/1/0/0.pbf")
            self.assertEqual(code, 204)
            code, body, _ = self.req(self.pu + "/api/nav/dem/12/2/3.png")
            self.assertEqual((code, body), (200, b"\x89PNGdem"))
            code, _, _ = self.req(self.pu + "/api/nav/dem/12/2/4.png")
            self.assertEqual(code, 404)
        finally:
            ms.shutdown()
            self.jpost(self.pu + "/api/nav/settings", {"map_url": ""})
            srv.navapi._TILES.update(t=0, info=None)


    def test_11_screen_map_crc_order_gz_zip(self):
        """Mapa na ekran: tylko zmienione kwadraty, kolejność od domu, gzip i paczka ZIP."""
        import gzip
        import zipfile
        nv = srv.navapi.NAV
        root = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(root, "mapa"))

        def publish(built, cells):
            files = []
            for key, name in cells:
                c = build_map.Cell(key)
                c.add_point(1, key[0] / 10 + 0.05, key[1] / 10 + 0.05, ntt.P_FUEL, 0, name, 0)
                n, crc = c.write(os.path.join(root, "mapa", ntt.cell_name(key)))
                files.append([ntt.cell_name(key), n, crc])
            with open(os.path.join(root, "mapa", "manifest.json"), "w") as f:
                json.dump({"format": 1, "built": built, "bytes": sum(f[1] for f in files), "files": files}, f)
        publish("2026-10-02", [((500, 199), "A"), ((520, 210), "B")])
        ms = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(MS.H, directory=root))
        threading.Thread(target=ms.serve_forever, daemon=True).start()
        try:
            self.jpost(self.pu + "/api/nav/settings", {"map_url": "http://127.0.0.1:%d" % ms.server_address[1]})
            code, j = self.jpost(self.pu + "/api/nav/map/sync", {"force": True})
            self.assertTrue(j["ok"], j)
            publish("2026-11-02", [((500, 199), "A"), ((520, 210), "B2")])
            code, j = self.jpost(self.pu + "/api/nav/map/sync", {})
            self.assertEqual((j["files"], j["kept"]), (1, 1))         # only the changed square is fetched
            # screen manifest: crc for each file, home square first
            self.jpost(self.pu + "/api/nav/settings", {"home": {"lat": 52.05, "lon": 21.05, "name": "Dom"}})
            code, body, _ = self.req(self.iu + "/api/nav/mapa/manifest.json?klucz=" + KEY)
            m = json.loads(body)
            self.assertTrue(m["gz"])
            self.assertEqual([f[0] for f in m["files"]], ["c_520_210.ntt", "c_500_199.ntt"])
            raw = open(os.path.join(nv.map_dir, "c_520_210.ntt"), "rb").read()
            self.assertEqual(m["files"][0][1:], [len(raw), binascii.crc32(raw)])
            code, body, _ = self.req(self.iu + "/api/nav/mapa/c_520_210.ntt.gz?klucz=" + KEY)
            self.assertEqual((code, gzip.decompress(body)), (200, raw))
            code, _, _ = self.req(self.iu + "/api/nav/mapa/manifest.json.gz?klucz=" + KEY)
            self.assertEqual(code, 404)
            # ZIP for the SD card: prepared in the background, then downloadable
            for _ in range(100):
                code, body, h = self.req(self.pu + "/api/nav/mapa.zip")
                if code == 200:
                    break
                self.assertEqual(code, 202)
                time.sleep(0.1)
            self.assertEqual(code, 200)
            z = zipfile.ZipFile(io.BytesIO(body))
            self.assertEqual(sorted(z.namelist()), ["mapa/c_500_199.ntt", "mapa/c_520_210.ntt", "mapa/manifest.json"])
            self.assertEqual(z.read("mapa/c_520_210.ntt"), raw)
            code, body, _ = self.req(self.pu + "/api/nav/routes")
            self.assertTrue(json.loads(body)["zip"]["ready"])
        finally:
            ms.shutdown()
            self.jpost(self.pu + "/api/nav/settings", {"map_url": "", "home": None})


    def test_12_skip_town_and_round_trip_by_time(self):
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu})
        FakeGraphHopper.calls = []
        pts = [{"lat": 50.0, "lon": 19.9, "name": "A"}, {"lat": 50.02, "lon": 19.95, "name": "B"}]
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["szybko"], "weather": False,
                                                         "skip": [{"lat": 50.01, "lon": 19.92, "r": 1500, "name": "Wieś"}]})
        self.assertEqual(code, 200, j)
        cm = FakeGraphHopper.calls[0]["custom_model"]
        self.assertEqual(cm["areas"]["features"][0]["id"], "pomin0")
        ring = cm["areas"]["features"][0]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertAlmostEqual(max(p[1] for p in ring) - 50.01, 1500 / 110540, places=3)
        self.assertEqual(cm["priority"][0], {"if": "in_pomin0", "multiply_by": "0.02"})
        self.assertEqual(j["routes"][0]["skip"][0]["name"], "Wieś")
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "skip": [{"lat": "x", "lon": 1}]})
        self.assertEqual(code, 400)
        # round trip by time: only the start goes to the engine, length is corrected towards the wanted time
        FakeGraphHopper.calls = []
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["kreto"], "round_trip_min": 60,
                                                         "weather": False})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["routes"][0]["name"], "Okrężna 1 h")
        self.assertEqual(j["routes"][0]["round_trip_min"], 60)
        calls = FakeGraphHopper.calls
        self.assertTrue(all(c["algorithm"] == "round_trip" and len(c["points"]) == 1 for c in calls))
        self.assertEqual(calls[0]["round_trip.distance"], 46000)          # 1 h at the curvy average
        self.assertEqual(len(calls), 3)                                    # fake engine always says 2 min
        self.assertGreater(calls[1]["round_trip.distance"], calls[0]["round_trip.distance"])
        self.assertEqual(len({c["round_trip.seed"] for c in calls}), 1)    # same loop shape while correcting
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts[:1], "round_trip_min": 5})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts[:1], "round_trip_min": 60, "round_trip_km": 50})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
