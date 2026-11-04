"""Tests of the navigation part of the add-on (no Home Assistant, no internet).

Run: python3 -m unittest discover -s tests
"""
import importlib.util
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
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
        code, body, _ = self.req(self.pu + "/api/nav/gpx?name=Z+Kurvigera", (GPX % seg).encode(),
                                 {"Content-Type": "application/gpx+xml"}, "POST")
        self.assertEqual(code, 200, body)
        j = json.loads(body)
        rid = j["id"]
        r = j["route"]
        self.assertEqual(r["name"], "Z Kurvigera")
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
        body = FakeGraphHopper.calls[1]
        self.assertEqual(body["profile"], "motocykl")
        self.assertEqual(body["points"][0], [19.9, 50.0])
        self.assertTrue(any("curvature" in json.dumps(p) for p in body["custom_model"]["priority"]))
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


if __name__ == "__main__":
    unittest.main()
