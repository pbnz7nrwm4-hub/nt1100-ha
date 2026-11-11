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
        if body.get("algorithm") == "alternative_route":
            # 1.5.46: a second, longer way (east first, then north)
            a = line(50.0, 19.9, 90, 1000)
            b = line(a[-1][0], a[-1][1], 0, 1200)[1:]
            p2 = a + b
            out["paths"].append({"points": {"coordinates": [[p[1], p[0]] for p in p2]}, "distance": 2200.0, "time": 150000,
                                 "details": {"time": [[0, len(p2) - 1, 150000]]}, "instructions": []})
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

    def test_curviness_skips_junction_turns(self):
        # skręt w prawo na skrzyżowaniu (z silnika tras) nie podnosi krętości trasy
        pts = nav.densify(l_shape(), 30)
        cum = nav.cum_dist(pts)
        full = nav.curviness(pts, cum)
        j = min(range(len(cum)), key=lambda i: abs(cum[i] - 1000))
        no_junction = nav.curviness(pts, cum, turns=[{"idx": j, "type": nav.T_RIGHT}])
        self.assertLess(no_junction["deg_km"], full["deg_km"])
        self.assertEqual(no_junction["level"], "prosta")
        # łagodne „lekko w prawo” zostaje policzone
        slight = nav.curviness(pts, cum, turns=[{"idx": j, "type": nav.T_SLIGHT_R}])
        self.assertEqual(slight["deg_km"], full["deg_km"])

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

    def test_gpx_bmw_round_trip(self):
        # 1.5.41: the layout of BMW Motorrad Connected (Adrian's file Poprad - Bierun, 8.11): trk = road,
        # rte = named stops, cnrd:routeOptions -> variant and avoidances
        pts = l_shape()
        route = {"name": "Próbna", "pts": pts, "variant": "kreto", "avoid": ["platne", "gruntowe"],
                 "waypoints": [{"idx": len(pts) // 2, "name": "Huty"}]}
        x = nav.to_gpx_bmw(route)
        self.assertIn('creator="BMW Motorrad Connected"', x)
        self.assertIn('windingness="medium"', x)
        self.assertIn('tollRoads="forbid" dirtRoads="forbid"', x)
        self.assertIn('motorways="allow"', x)
        g = nav.parse_gpx(x.encode())
        self.assertEqual(len(g["pts"]), len(pts))
        self.assertEqual(g["variant"], "kreto")
        self.assertEqual(g["avoid"], ["platne", "gruntowe"])
        self.assertEqual([w["name"] for w in g["wpts"]], ["Huty"])

    def test_gpx_bmw_stabilized(self):
        # 1.5.46 (Kurviger „route stabilization”, Adrian 9.11 „pod BMW”): shaping points 300 m after turns onto
        # another road, at most one per 8 km, long straight stretches every 16 km; read back they are not stops
        pts = []
        lat, lon = 50.0, 19.9
        turns = []
        for k in range(12):                          # 12 legs of 5 km, alternating north / east
            seg = line(lat, lon, 0 if k % 2 == 0 else 90, 5000, 25.0)
            if pts:
                turns.append({"idx": len(pts) - 1, "type": nav.T_RIGHT if k % 2 else nav.T_LEFT, "text": "Droga %d" % k})
                seg = seg[1:]
            pts += seg
            lat, lon = pts[-1]
        route = {"name": "Długa", "pts": pts, "cum": nav.cum_dist(pts), "variant": "kreto", "turns": turns,
                 "waypoints": [{"idx": len(pts) - 1, "name": "cel", "kind": 2}]}
        sp = nav.stabilize_points(route)
        self.assertTrue(4 <= len(sp) <= 8, sp)
        cum = route["cum"]
        gaps = [cum[b[0]] - cum[a[0]] for a, b in zip(sp, sp[1:])]
        self.assertTrue(all(g >= 8000 for g in gaps), gaps)
        x = nav.to_gpx_bmw(route)
        self.assertEqual(x.count("<type>shaping</type>"), len(sp))
        self.assertEqual(nav.parse_gpx(x.encode())["wpts"], [])   # shaping points are not stops

    def test_closures_kept_without_delay(self):
        # 1.5.46 (a10): a road closure (TomTom iconCategory 8) stays even with no delay, first on the list
        pts = nav.densify(l_shape(), 30)
        cum = nav.cum_dist(pts)
        n = nav.Nav(os.path.join(TMP, "cl"), TMP, lambda: {"tomtom_key": "k"})
        old = nav.http_json
        nav.http_json = lambda *a, **k: {"incidents": [
            {"geometry": {"type": "LineString", "coordinates": [[19.95, 50.2], [pts[40][1], pts[40][0]]]},
             "properties": {"iconCategory": 8, "magnitudeOfDelay": 4, "delay": 0, "events": [{"description": "zamknięta"}]}},
            {"geometry": {"type": "Point", "coordinates": [pts[10][1], pts[10][0]]},
             "properties": {"iconCategory": 6, "magnitudeOfDelay": 1, "delay": 20}}]}
        try:
            out = n.incidents_along(pts, cum, 0, 50000)
        finally:
            nav.http_json = old
        self.assertEqual(out["closed"], 1)
        self.assertEqual(len(out["incidents"]), 1)
        self.assertTrue(out["incidents"][0]["closed"])
        self.assertEqual(out["incidents"][0]["idx"], 40)

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


    def test_pack_ntr_leg_variants(self):
        """1.5.32: „Mój plan” – wariant trasy w nagłówku, wariant odcinka przy przystanku, na którym się kończy."""
        pts = nav.densify(l_shape(), 30)
        route = {"id": 2, "version": 1, "name": "plan", "variant": "mix", "pts": pts, "cum": nav.cum_dist(pts), "turns": [],
                 "waypoints": [{"idx": 10, "name": "A", "kind": 1, "leg": "kreto"},
                               {"idx": len(pts) - 1, "name": "cel", "kind": 2, "leg": "szybko"}]}
        b = nav.pack_ntr(route)
        self.assertEqual(struct.unpack_from("<4sBB", b, 0)[2], nav.VARIANT_CODE["mix"])
        w2 = struct.unpack_from("<IBBH32s", b, len(b) - 40)
        w1 = struct.unpack_from("<IBBH32s", b, len(b) - 80)
        self.assertEqual((w1[0], w1[2]), (10, nav.VARIANT_CODE["kreto"]))
        self.assertEqual((w2[1], w2[2]), (2, nav.VARIANT_CODE["szybko"]))
        route["variant"] = None
        for w in route["waypoints"]:
            w.pop("leg")
        b = nav.pack_ntr(route)  # zwykła trasa: pola jak dawniej (zera)
        self.assertEqual(struct.unpack_from("<4sBB", b, 0)[2], 0)
        self.assertEqual(struct.unpack_from("<IBBH32s", b, len(b) - 40)[2], 0)

    def test_pack_ntr_utf8_cut(self):
        """Długie polskie nazwy obcięte bez przecinania litery (ekran rysował krzaczek)."""
        self.assertEqual(nav.utf8_cut("ąąą", 5), "ąą".encode())
        self.assertEqual(nav.utf8_cut("abc", 5), b"abc")
        self.assertEqual(nav.utf8_cut(None, 5), b"")
        pts = nav.densify(l_shape(), 30)
        name = "Przełęcz Salmopolska → Szczyrk → Żywiec"  # 44 bajty+
        route = {"id": 1, "version": 1, "name": name, "pts": pts, "cum": nav.cum_dist(pts),
                 "turns": [{"idx": 3, "type": nav.T_RIGHT, "exit": 0, "text": "ulica Źródlana–Łąkowa–Ściegiennego"}],
                 "waypoints": [{"idx": len(pts) - 1, "name": "Schronisko na Hali Łabowskiej ąę", "kind": 2}]}
        b = nav.pack_ntr(route)
        head = struct.calcsize("<4sBBHIIIHHHHH40s")
        raw = struct.unpack_from("<4sBBHIIIHHHHH40s", b, 0)[-1].rstrip(b"\0")
        self.assertTrue(name.startswith(raw.decode("utf-8")))  # poprawny UTF-8, bez ucinania litery
        t = struct.unpack_from("<IBBH32s", b, head + 14 * len(pts))[-1].rstrip(b"\0")
        t.decode("utf-8")
        w = struct.unpack_from("<IBBH32s", b, len(b) - 40)[-1].rstrip(b"\0")
        w.decode("utf-8")

    def test_gpx_name_and_many_waypoints_fast(self):
        """Nazwa trasy z trk, nie z punktów; duży plik z wieloma nazwami liczy się szybko."""
        pts = line(50.0, 19.9, 0, 40000, 2.0)
        wpts = "".join('<wpt lat="%.6f" lon="19.9"><name>p%d</name></wpt>' % (50.0 + i * 1e-4, i) for i in range(2000))
        seg = "".join('<trkpt lat="%.6f" lon="%.6f"><name>pkt</name></trkpt>' % p for p in pts)
        data = ('<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">%s'
                '<trk><name>Długa</name><trkseg>%s</trkseg></trk></gpx>' % (wpts, seg)).encode()
        t = time.time()
        g = nav.parse_gpx(data)
        self.assertLess(time.time() - t, 5)
        self.assertEqual(g["name"], "Długa")
        self.assertEqual(len(g["pts"]), len(pts))

    def test_route_at_needs_history(self):
        """Jazda sprzed zaplanowania trasy nie dostaje „zgodności” z bieżącą trasą."""
        d = tempfile.mkdtemp(prefix="nt1100-ra-")
        try:
            n = nav.Nav(os.path.join(d, "s"), d, lambda: {})
            self.assertIsNone(n.route_at(time.time()))
            n.save_state(current_history=[{"t": 1000, "rid": 4}, {"t": 2000, "rid": 5}])
            self.assertIsNone(n.route_at(999))
            self.assertEqual(n.route_at(1500), 4)
            self.assertEqual(n.route_at(5000), 5)
        finally:
            shutil.rmtree(d, ignore_errors=True)


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

    def test_02b_screen_own_key(self):
        # 1.5.35: ekran ma osobny klucz; po „tylko klucz ekranu” klucz skrzynki nie wpuszcza ekranu, ale skrzynkę tak
        code, body, _ = self.req(self.pu + "/api/settings")
        sk = json.loads(body)["screen_key"]
        self.assertTrue(sk and sk != KEY)
        self.assertEqual(self.req(self.iu + "/api/nav/ping?klucz=" + sk)[0], 200)
        self.assertEqual(self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": sk})[0], 200)
        self.assertEqual(self.req(self.iu + "/api/ping", headers={"X-Klucz": sk})[0], 401)  # skrzynka tylko swoim
        try:
            self.assertEqual(self.jpost(self.pu + "/api/settings", {"screen_key_only": True})[0], 200)
            self.assertEqual(self.req(self.iu + "/api/nav/ping?klucz=" + KEY)[0], 401)
            self.assertEqual(self.req(self.iu + "/api/ping", headers={"X-Klucz": KEY})[0], 200)
            code, j = self.jpost(self.pu + "/api/screen_key/new", {})
            self.assertEqual(code, 200)
            self.assertNotEqual(j["screen_key"], sk)
            self.assertEqual(self.req(self.iu + "/api/nav/ping?klucz=" + sk)[0], 401)
            self.assertEqual(self.req(self.iu + "/api/nav/ping?klucz=" + j["screen_key"])[0], 200)
        finally:
            self.jpost(self.pu + "/api/settings", {"screen_key_only": False})

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
        # 1.5.46: „Inna trasa” z ekranu przez dodatek – porównanie, nowa trasa zapisana, ale nie bieżąca
        self.assertEqual(last.get("timeout_ms"), nav.GH_TIMEOUT_MS)   # e5: bezpiecznik zapytania
        code, a = self.jpost(self.iu + "/api/nav/alt", {"id": rid, "lat": 50.0, "lon": 19.9, "heading": 0, "mode": "inaczej"},
                             {"X-Klucz": KEY})
        self.assertEqual(code, 200, a)
        self.assertTrue(a["ok"], a)
        self.assertEqual(FakeGraphHopper.calls[-1]["algorithm"], "alternative_route")
        self.assertEqual((a["new_km"], a["new_min"]), (2.2, 2))
        self.assertNotEqual(a["id"], rid)
        code, body, _ = self.req(self.pu + "/api/nav/routes")
        self.assertEqual(json.loads(body)["current"], rid)          # not current until the rider takes it
        code, a2 = self.jpost(self.iu + "/api/nav/alt", {"id": rid, "lat": 50.0, "lon": 19.9, "mode": "szybciej"},
                              {"X-Klucz": KEY})
        self.assertTrue(a2["ok"], a2)
        self.assertEqual(a2["variant"], "szybko")
        self.assertNotIn("algorithm", FakeGraphHopper.calls[-1])
        code, a3 = self.jpost(self.iu + "/api/nav/alt", {"id": rid, "lat": 50.0, "lon": 19.9, "mode": "zle"},
                              {"X-Klucz": KEY})
        self.assertFalse(a3["ok"])
        # 1.5.50 (e2): wszystkie inne drogi naraz – te same co obecna odpadają, zostaje alternatywa silnika z kształtem
        code, al = self.jpost(self.iu + "/api/nav/alts", {"id": rid, "lat": 50.0, "lon": 19.9, "heading": 0}, {"X-Klucz": KEY})
        self.assertEqual(code, 200, al)
        self.assertTrue(al["ok"], al)
        self.assertEqual((al["n"], al["a0_mode"], al["a0_km"], al["a0_min"]), (1, "inaczej", 2.2, 2))
        self.assertNotEqual(al["a0_id"], rid)
        shape = [tuple(float(x) for x in q.split(",")) for q in al["a0_shape"].split(";")]
        self.assertTrue(2 <= len(shape) <= 40, len(shape))
        self.assertAlmostEqual(shape[0][0], 50.0, places=3)
        self.assertTrue(al["now_shape"].count(";") >= 1)
        self.assertNotIn("a1_id", al)
        code, body, _ = self.req(self.pu + "/api/nav/routes")
        self.assertEqual(json.loads(body)["current"], rid)
        # „objazd 1 km”: odcinek do ominięcia idzie do silnika jako obszar, a następne planowanie już go nie ma
        code, s = self.jpost(self.iu + "/api/nav/reroute", {"id": rid, "lat": 50.0, "lon": 19.9, "heading": 0, "avoid_km": 1},
                             {"X-Klucz": KEY})
        self.assertEqual(code, 200, s)
        feats = (FakeGraphHopper.calls[-1]["custom_model"].get("areas") or {}).get("features") or []
        self.assertIn("objazd", [f["id"] for f in feats])
        self.jpost(self.pu + "/api/nav/plan", {"points": [{"lat": 50.0, "lon": 19.9}, {"lat": 50.009, "lon": 19.914}],
                                               "variants": ["szybko"], "weather": False})
        self.assertNotIn("areas", FakeGraphHopper.calls[-1]["custom_model"])
        self.assertFalse(hasattr(srv.navapi.NAV, "_avoid_segment"))
        # bez klucza treść nie jest czytana; za duża treść = 413
        import http.client
        port = int(self.iu.rsplit(":", 1)[1])
        for key, want in (("zly", 401), (KEY, 413)):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.putrequest("POST", "/api/nav/log")
            c.putheader("X-Klucz", key)
            c.putheader("Content-Length", "2000000")  # zapowiedziana treść, wysłane tylko 10 B
            c.endheaders(b"x" * 10)
            r = c.getresponse()
            self.assertEqual(r.status, want)
            self.assertEqual(r.getheader("Connection"), "close")
            c.close()
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
        # the only 90° turn of the L-shaped test route is a junction from the engine -> not a bend (1.5.28)
        self.assertEqual(j["routes"][0]["curvy"]["level"], "prosta")
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

    def test_06b_screen_goto_destination_avoid_and_search(self):
        """Ekran 5" przez hotspot: cel wybrany na ekranie (adres z karty) z jego wariantem i omijaniem."""
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu, "home": {"lat": 50.0, "lon": 19.9, "name": "Dom"}})
        FakeGraphHopper.calls = []
        code, j = self.jpost(self.iu + "/api/nav/goto", {"dest_lat": 50.009, "dest_lon": 19.914, "dest_name": "Polna 3",
                                                         "variant": "szybko", "avoid": ["autostrady", "zle"]},
                             {"X-Klucz": KEY})
        self.assertEqual(code, 200, j)
        self.assertEqual((j["place"]["name"], j["route"]["variant"]), ("Polna 3", "szybko"))
        prio = json.dumps(FakeGraphHopper.calls[0]["custom_model"]["priority"])
        self.assertIn("MOTORWAY", prio)
        self.assertNotIn("toll", prio)                    # omijanie tylko to, co wybrał ekran
        nv = srv.navapi.NAV
        old = nv.search
        nv.search = lambda q, lat=None, lon=None, limit=8: [
            {"name": "Stacja", "label": "Stacja, Miasto", "lat": 50.1, "lon": 19.2}]
        try:
            self.jpost(self.pu + "/api/nav/fav", {"fav": [{"name": "Praca", "lat": 50.2, "lon": 19.3}]})
            code, body, _ = self.req(self.iu + "/api/nav/search?q=praca", headers={"X-Klucz": KEY})
            res = json.loads(body)["results"]
            self.assertEqual([r["name"] for r in res], ["Praca", "Stacja"])
            code, body, _ = self.req(self.iu + "/api/nav/search?q=s", headers={"X-Klucz": KEY})
            self.assertEqual(json.loads(body)["results"], [])
            code, body, _ = self.req(self.iu + "/api/nav/search?q=praca")
            self.assertEqual(code, 401)
        finally:
            nv.search = old
            self.jpost(self.pu + "/api/nav/fav", {"fav": []})

    def test_07b_screen_backup_and_logs(self):
        # 1.5.46 (a12): what only the screen has goes to the add-on: home saved on the screen, ride ratings, card logs
        code, j = self.jpost(self.iu + "/api/nav/kopia", {"home": {"lat": 50.1, "lon": 19.2, "name": "Dom"},
                                                         "ratings": [{"t": 1700000000, "score": 4, "name": "Pętla", "km": 80}]},
                             {"X-Klucz": KEY})
        self.assertEqual((code, j["ratings"], j["home"]), (200, 1, True))
        code, j = self.jpost(self.iu + "/api/nav/kopia", {"ratings": [{"t": 1700000000, "score": 4, "name": "Pętla"}]},
                             {"X-Klucz": KEY})
        self.assertEqual((j["ratings"], j["home"]), (1, True))        # no duplicate, home kept
        nv = srv.navapi.NAV
        for part in (b"linia 1\n", b"linia 2\n"):
            code, body, _ = self.req(self.iu + "/api/nav/dziennik?plik=funkcje.txt&klucz=" + KEY, part, {}, "POST")
            self.assertEqual(code, 200, body)
        with open(os.path.join(nv.dir, "dziennik-ekranu", "funkcje.txt"), "rb") as f:
            self.assertEqual(f.read(), b"linia 1\nlinia 2\n")
        code, _, _ = self.req(self.iu + "/api/nav/dziennik?plik=..%2Fx&klucz=" + KEY, b"x", {}, "POST")
        self.assertEqual(code, 400)

    def test_07c_weather_here_in_ping(self):
        # 1.5.46 (ekran 2.7.0, pkt 16): the weather where the screen is, for the empty panel; the ping never waits for
        # Open-Meteo (first ping: fetched in the background, the next one carries it)
        hourly = {"time": [time.strftime("%Y-%m-%dT%H:00", time.gmtime(time.time() + h * 3600)) for h in range(-2, 30)]}
        for k in ("temperature_2m", "precipitation_probability", "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m"):
            hourly[k] = [7] * len(hourly["time"])
        seen = []

        def fake(url, timeout=0):
            seen.append(url)
            return {"hourly": hourly}
        orig, orig_on = nav.http_json, srv.WEATHER_ON
        nav.http_json, srv.WEATHER_ON = fake, True
        nav.WX_CACHE.clear()
        try:
            u = self.iu + "/api/nav/ping?klucz=" + KEY + "&k=ekran5&lat=50.11&lon=19.21"
            code, body, _ = self.req(u)
            self.assertEqual(code, 200)
            self.assertNotIn("wx_here", json.loads(body))
            for _ in range(50):
                if seen and (round(50.11, 1), round(19.21, 1)) in nav.WX_CACHE:
                    break
                time.sleep(0.05)
            j = json.loads(self.req(u)[1])
            self.assertEqual(len(j["wx_here"]), 5)
            self.assertEqual((j["wx_here"][0]["temp"], j["wx_here"][0]["rain_prob"]), (7, 7))
            self.assertEqual(len(seen), 1)
            self.assertNotIn("wx_here", json.loads(self.req(self.iu + "/api/nav/ping?klucz=" + KEY + "&lat=50.11&lon=19.21")[1]))
        finally:
            nav.http_json, srv.WEATHER_ON = orig, orig_on
            nav.WX_CACHE.clear()

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
        # pasek „w trasie” na stronie: prędkość i odległość od domu (jest tylko z ustawionym domem)
        self.assertEqual(j["pos"]["speed"], 0)
        home = nv.settings()["home"]
        if home:
            self.assertGreaterEqual(j["pos"]["home_m"], 0)
        else:
            self.assertNotIn("home_m", j["pos"])
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
        self.assertNotIn("Bieru", json.dumps(r, ensure_ascii=False))  # bez nazw miejscowości z okolicy domu
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
            # 1.5.45: the screen sends what its card has, the add-on says what to fetch and remove
            raw0 = open(os.path.join(nv.map_dir, "c_500_199.ntt"), "rb").read()
            card = "built 2026-10-02\npos 50.05 19.95\nc_500_199.ntt %d %d\nc_520_210.ntt 5 7\nc_999_999.ntt 3 0\n" % (
                len(raw0), binascii.crc32(raw0))

            def diff(text):
                code, body, _ = self.req(self.iu + "/api/nav/mapa/roznice?klucz=" + KEY, text.encode(), {}, "POST")
                self.assertEqual(code, 200)
                return body.decode().splitlines()
            lines = diff(card)
            self.assertEqual(lines[:5], ["built 2026-11-02", "stan ok", "gz 1", "pobierz 1 %d" % len(raw), "usun 1"])
            self.assertEqual(lines[5:], ["+ c_520_210.ntt %d %d" % (len(raw), binascii.crc32(raw)), "- c_999_999.ntt"])
            # crc 0 (unknown, e.g. after a copy from the computer): the size decides
            lines = diff("built 2026-11-02\nc_500_199.ntt %d 0\nc_520_210.ntt %d %d\n" % (len(raw0), len(raw), binascii.crc32(raw)))
            self.assertEqual(lines[1:5], ["stan ok", "gz 1", "pobierz 0 0", "usun 0"])
            # empty card: everything, nearest to the screen first (Kraków area: c_500_199 before c_520_210)
            lines = diff("built -\npos 50.05 19.95\n")
            self.assertEqual([x.split()[1] for x in lines[5:]], ["c_500_199.ntt", "c_520_210.ntt"])
            # never back: the card has a newer map than the add-on - nothing to do, the add-on fetches its own
            calls = []
            old = srv.navapi.NAV.map_sync
            srv.navapi.NAV.map_sync = lambda *a, **k: calls.append(1)
            srv.navapi.SYNC_LAST["t"] = 0
            try:
                lines = diff("built 2026-11-09\nc_500_199.ntt 1 1\n")
                self.assertEqual(lines[:5], ["built 2026-11-02", "stan nowsza", "gz 0", "pobierz 0 0", "usun 0"])
                for _ in range(50):
                    if calls:
                        break
                    time.sleep(0.05)
                self.assertEqual(calls, [1])
                diff("built 2026-11-09\n")          # at most once an hour
                time.sleep(0.2)
                self.assertEqual(calls, [1])
            finally:
                srv.navapi.NAV.map_sync = old
            code, _, _ = self.req(self.iu + "/api/nav/mapa/roznice", b"built -\n", {}, "POST")
            self.assertEqual(code, 401)
            # ZIP for the SD card: prepared in the background, then downloadable
            for _ in range(100):
                code, body, h = self.req(self.pu + "/api/nav/mapa.zip")
                if code == 200:
                    break
                self.assertEqual(code, 202)
                time.sleep(0.1)
            self.assertEqual(code, 200)
            z = zipfile.ZipFile(io.BytesIO(body))
            self.assertEqual(sorted(z.namelist()), ["m6/c/500/c_500_199.ntt", "m6/c/520/c_520_210.ntt", "m6/manifest.json"])
            self.assertEqual(z.read("m6/c/520/c_520_210.ntt"), raw)
            code, body, _ = self.req(self.pu + "/api/nav/routes")
            self.assertTrue(json.loads(body)["zip"]["ready"])
        finally:
            ms.shutdown()
            self.jpost(self.pu + "/api/nav/settings", {"map_url": "", "home": None})


    def test_11b_offline_graph_sync_and_route(self):
        """Graf tras (mapa 3): pobierany z kontenera, w manifeście ekranu, w ZIP; trasa offline."""
        import gzip
        import zipfile
        nv = srv.navapi.NAV
        root = tempfile.mkdtemp(dir=TMP)
        out = os.path.join(root, "mapa")
        os.makedirs(out)
        a, m, b = (50.05, 19.95), (50.05, 20.0), (50.05, 20.05)
        c = build_map.Cell((500, 199))
        c2 = build_map.Cell((500, 200))
        for cell in (c, c2):
            cell.add_way(7, 4, 0, 0, 0, "Prosta", "", [a, m, b], [(0, 11), (1, 12), (2, 13)])
        files = []
        for cell in (c, c2):
            n, crc = cell.write(os.path.join(out, ntt.cell_name(cell.key)))
            files.append([ntt.cell_name(cell.key), n, crc])
        tmp = os.path.join(root, "kraw.bin")
        with open(tmp, "wb") as f:
            build_map.graph_edges(f, 7, 4, 0, {}, 0, 0, [a, m, b], [(0, 11), (1, 12), (2, 13)])
        graph = build_map.build_graph(tmp, [], out)
        idx = struct.pack("<4sBBI", b"NTAI", 1, 0, 0)
        with open(os.path.join(out, "a_index.nta"), "wb") as f:
            f.write(idx)
        poi = struct.pack("<4sBBI", b"NTAP", 1, 0, 1)
        for x in (b"orlen bierun", "Orlen".encode(), "Bieruń".encode()):
            poi += bytes([len(x)]) + x
        poi += struct.pack("<Bii", 10, 50090000, 19090000)
        with open(os.path.join(out, "a_poi.nta"), "wb") as f:
            f.write(poi)
        addr = {"format": 1, "bytes": len(idx) + len(poi), "cells": [["a_index.nta", len(idx), binascii.crc32(idx)],
                                                                     ["a_poi.nta", len(poi), binascii.crc32(poi)]]}
        with open(os.path.join(out, "manifest.json"), "w") as f:
            json.dump({"format": 1, "wersja": 5, "built": "2026-11-06", "bytes": sum(x[1] for x in files),
                       "files": files, "graph": graph, "addr": addr}, f)
        ms = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(MS.H, directory=root))
        threading.Thread(target=ms.serve_forever, daemon=True).start()
        try:
            self.jpost(self.pu + "/api/nav/settings", {"map_url": "http://127.0.0.1:%d" % ms.server_address[1]})
            code, j = self.jpost(self.pu + "/api/nav/map/sync", {"force": True})
            self.assertTrue(j["ok"], j)
            self.assertEqual(j["files"], 6)                       # 2 kwadraty mapy + 2 grafu + spisy adresów i miejsc
            self.assertTrue(os.path.exists(os.path.join(nv.map_dir, "g_500_199.ntg")))
            code, body, _ = self.req(self.iu + "/api/nav/mapa/manifest.json?klucz=" + KEY)
            mf = json.loads(body)
            self.assertEqual(sorted(f[0] for f in mf["files"]), ["c_500_199.ntt", "c_500_200.ntt"])
            self.assertEqual(sorted(f[0] for f in mf["graph"]["cells"]), ["g_500_199.ntg", "g_500_200.ntg"])
            self.assertEqual([f[0] for f in mf["addr"]["cells"]], ["a_index.nta", "a_poi.nta"])
            code, body, _ = self.req(self.iu + "/api/nav/mapa/a_poi.nta.gz?klucz=" + KEY)
            self.assertEqual((code, gzip.decompress(body)), (200, poi))
            code, body, _ = self.req(self.pu + "/api/nav/miejsca?q=Orlen%20Bieru%C5%84&lat=50.1&lon=19.1")
            r = json.loads(body)["results"]
            self.assertEqual([(x["name"], x["city"], x["kind"]) for x in r], [("Orlen", "Bieruń", "stacja")])
            self.assertLess(r[0]["km"], 2)
            code, body, _ = self.req(self.iu + "/api/nav/mapa/a_index.nta.gz?klucz=" + KEY)
            self.assertEqual((code, gzip.decompress(body)), (200, idx))
            code, body, _ = self.req(self.pu + "/api/nav/adres?miasto=Bierun")
            self.assertEqual(json.loads(body), {"ok": False, "towns": []})
            raw = open(os.path.join(nv.map_dir, "g_500_199.ntg"), "rb").read()
            code, body, _ = self.req(self.iu + "/api/nav/mapa/g_500_199.ntg.gz?klucz=" + KEY)
            self.assertEqual((code, gzip.decompress(body)), (200, raw))
            code, body, _ = self.req(self.iu + "/api/nav/mapa/g_500_199.ntg?klucz=" + KEY)
            self.assertEqual((code, body), (200, raw))
            # trasa offline jak na ekranie
            code, body, _ = self.req(self.pu + "/api/nav/offline?from=50.05,19.951&to=50.05,20.049&variant=szybko")
            j = json.loads(body)
            self.assertTrue(j["ok"], j)
            self.assertAlmostEqual(j["km"], 7.15, delta=0.2)
            self.assertEqual(len(j["pts"]), 3)
            code, body, _ = self.req(self.pu + "/api/nav/offline?from=x")
            self.assertEqual(code, 400)
            # ekran 5" dostaje ustawienia do liczenia offline
            code, body, _ = self.req(self.iu + "/api/nav/ping?k=ekran5", headers={"X-Klucz": KEY})
            off = json.loads(body)["offline"]
            self.assertIn("kreto", off["curvy"])
            self.assertIsInstance(off["avoid"], list)
            code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
            self.assertNotIn("offline", json.loads(body))
            # ZIP na kartę z grafem
            for _ in range(100):
                code, body, h = self.req(self.pu + "/api/nav/mapa.zip")
                if code == 200:
                    break
                time.sleep(0.1)
            names = zipfile.ZipFile(io.BytesIO(body)).namelist()
            self.assertIn("m6/g/500/g_500_200.ntg", names)
            self.assertIn("m6/a_index.nta", names)
        finally:
            ms.shutdown()
            self.jpost(self.pu + "/api/nav/settings", {"map_url": ""})

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

    def test_13_avoid_gravel_and_favourites(self):
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu})
        pts = [{"lat": 50.0, "lon": 19.9, "name": "A"}, {"lat": 50.02, "lon": 19.95, "name": "B"}]
        rules = {}
        for av in (["gruntowe"], ["szutrowe"], ["gruntowe", "szutrowe"]):
            FakeGraphHopper.calls = []
            code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["szybko"], "avoid": av,
                                                             "weather": False})
            self.assertEqual(code, 200, j)
            rules[tuple(av)] = json.dumps(FakeGraphHopper.calls[0]["custom_model"]["priority"])
        self.assertIn("TRACK", rules[("gruntowe",)])
        self.assertNotIn("GRAVEL", rules[("gruntowe",)])
        self.assertIn("FINE_GRAVEL", rules[("szutrowe",)])
        self.assertNotIn("TRACK", rules[("szutrowe",)])
        self.assertTrue("TRACK" in rules[("gruntowe", "szutrowe")] and "GRAVEL" in rules[("gruntowe", "szutrowe")])
        # ulubione: zapis, walidacja, cel skrótu po samej nazwie
        code, j = self.jpost(self.pu + "/api/nav/fav", {"fav": [{"lat": 50.009, "lon": 19.914, "name": "Praca"},
                                                                {"lat": 50.005, "lon": 19.9, "name": "Szkoła"}]})
        self.assertEqual(code, 200, j)
        self.assertEqual([f["name"] for f in j["fav"]], ["Praca", "Szkoła"])
        code, j = self.jpost(self.pu + "/api/nav/fav", {"fav": [{"lat": 1, "lon": 2, "name": "a"}, {"lat": 3, "lon": 4, "name": "A"}]})
        self.assertEqual(code, 400)
        code, j = self.jpost(self.pu + "/api/nav/fav", {"fav": [{"lat": "x", "lon": 2, "name": "a"}]})
        self.assertEqual(code, 400)
        code, body, _ = self.req(self.pu + "/api/nav/settings")
        self.assertEqual(len(json.loads(body)["fav"]), 2)
        self.jpost(self.pu + "/api/nav/home", {"home": {"lat": 50.0, "lon": 19.9}})
        code, j = self.jpost(self.pu + "/api/nav/goto", {"text": "praca"})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["place"]["name"], "Praca")

    def test_14_car_mode(self):
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu, "default_variant": "kreto"})
        self.jpost(self.pu + "/api/nav/home", {"home": {"lat": 50.0, "lon": 19.9}})
        code, j = self.jpost(self.pu + "/api/nav/settings", {"vehicle": "rower"})
        self.assertEqual(code, 400)
        code, s = self.jpost(self.pu + "/api/nav/settings", {"vehicle": "auto"})
        self.assertEqual((s["vehicle"], s["go_variant"], s["default_variant"]), ("auto", "szybko", "kreto"))
        FakeGraphHopper.calls = []
        code, j = self.jpost(self.pu + "/api/nav/goto", {"text": "50.009, 19.914"})
        self.assertEqual(code, 200, j)
        self.assertFalse(any("curvature" in json.dumps(c["custom_model"]) for c in FakeGraphHopper.calls))
        code, body, _ = self.req(self.iu + "/api/nav/ping?klucz=" + KEY)
        st = json.loads(body)["settings"]
        self.assertEqual((st["vehicle"], st["lean_popup_deg"]), ("auto", 90))
        code, s = self.jpost(self.pu + "/api/nav/settings", {"vehicle": "moto"})
        self.assertEqual(s["go_variant"], "kreto")
        code, body, _ = self.req(self.iu + "/api/nav/ping?klucz=" + KEY)
        self.assertNotEqual(json.loads(body)["settings"]["lean_popup_deg"], 90)

    def test_15_car_drive_traffic_detour(self):
        api = srv.navapi
        self.jpost(self.pu + "/api/nav/settings", {"engine_url": self.ghu, "vehicle": "auto"})
        pts = [{"lat": 50.0, "lon": 19.9, "name": "Dom"}, {"lat": 50.009, "lon": 19.914, "name": "Praca"}]
        code, j = self.jpost(self.pu + "/api/nav/plan", {"points": pts, "variants": ["szybko"], "weather": False})
        self.assertEqual(code, 200, j)
        code, s = self.jpost(self.pu + "/api/nav/send", {"token": j["token"], "variant": "szybko", "current": False})
        rid = s["id"]
        route = api.NAV.route(rid)
        start, dest = route["pts"][1], route["pts"][-1]
        pos = {"p": start}
        sent = []
        mid = len(route["pts"]) // 2
        orig = (api.phone_position, api.NAV.traffic, srv.send_notification, srv.options)
        api.phone_position = lambda: {"lat": pos["p"][0], "lon": pos["p"][1], "age_s": 30, "entity": "device_tracker.x"}
        api.NAV.traffic = lambda r, lat, lon: ({"delay_s": 900, "incidents": [{"idx": mid, "km": 0.4, "delay_s": 900, "len_m": 150, "text": "roboty"}]}
                                               if r == rid else {"delay_s": 0, "incidents": []})
        srv.send_notification = lambda title, msg, tag="", url=None, link_text="": sent.append((title, msg, url))
        srv.options = lambda: {"klucz": KEY, "adres_spoza_domu": self.iu}
        try:
            code, d = self.jpost(self.pu + "/api/nav/drive", {"id": rid})
            self.assertEqual(code, 200, d)
            self.assertIn("/api/nav/trasa.gpx?id=%d" % rid, d["link"])
            self.assertEqual(api.drive_check(), "objazd")
            self.assertEqual(len(sent), 1)
            self.assertIn("Korek 15 min", sent[0][0])
            alt_id = api.drive()["alert"]["alt"]
            self.assertIn("id=%d" % alt_id, sent[0][2])
            # link z powiadomienia działa bez klucza, zły podpis nie
            code, body, hd = self.req(sent[0][2])
            self.assertEqual(code, 200)
            self.assertIn(b"<trkpt", body)
            self.assertIn(b'creator="OsmAndRouter"', body)
            import xml.etree.ElementTree as ET
            ET.fromstring(body)
            code, _, _ = self.req(sent[0][2][:-3] + "abc")
            self.assertEqual(code, 404)
            # ten sam korek nie wraca co kilka minut
            self.assertEqual(api.drive_check(), "zgloszony")
            self.assertEqual(len(sent), 1)
            # przy celu sprawdzanie samo się kończy
            pos["p"] = dest
            self.assertEqual(api.drive_check(), "na miejscu")
            self.assertIsNone(api.drive())
            code, d = self.jpost(self.pu + "/api/nav/drive", {"id": rid})
            code, d = self.jpost(self.pu + "/api/nav/drive", {"stop": True})
            self.assertIsNone(d["drive"])
        finally:
            api.phone_position, api.NAV.traffic, srv.send_notification, srv.options = orig
            self.jpost(self.pu + "/api/nav/settings", {"vehicle": "moto"})

    def test_16_gpx_for_osmand_has_turns(self):
        pts = [(50.0 + i * 0.001, 19.9) for i in range(10)]
        route = {"name": "A & B", "pts": pts, "times": list(range(0, 100, 10)), "waypoints": [],
                 "turns": [{"idx": 3, "type": nav.T_RIGHT, "exit": 0, "text": "Wschodnia"},
                           {"idx": 6, "type": nav.T_ROUNDABOUT, "exit": 2, "text": ""},
                           {"idx": 9, "type": nav.T_FINISH, "exit": 0, "text": ""}]}
        import xml.etree.ElementTree as ET
        g = ET.fromstring(nav.to_gpx(route, osmand=True))
        ns = {"g": "http://www.topografix.com/GPX/1/1", "o": "https://osmand.net"}
        self.assertEqual(g.get("creator"), "OsmAndRouter")
        rp = g.findall("g:rte/g:rtept", ns)
        self.assertEqual([x.findtext("g:extensions/o:offset", namespaces=ns) for x in rp], ["0", "3", "6", "9"])
        self.assertEqual([x.findtext("g:extensions/o:turn", namespaces=ns) for x in rp], [None, "TR", "RNDB2", None])
        self.assertEqual(rp[1].findtext("g:desc", namespaces=ns), "Skręć w prawo – Wschodnia")
        self.assertEqual(rp[1].findtext("g:extensions/o:time", namespaces=ns), "30")
        self.assertEqual(len(g.findall("g:trk/g:trkseg/g:trkpt", ns)), 10)
        g2 = ET.fromstring(nav.to_gpx_osmand(route, start=1000))
        self.assertEqual(g2.findall("g:trk/g:trkseg/g:trkpt", ns)[9].findtext("g:time", namespaces=ns), "1970-01-01T00:18:10Z")
        self.assertNotIn("rte", nav.to_gpx(route))

    def test_17_engine_down_message(self):
        n = srv.navapi.NAV
        import urllib.error
        e = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        orig = n.build_status
        try:
            n.build_status = lambda: {"pracuje": True, "etap": "mapa do przeglądarki (trasy nie liczą się)"}
            self.assertIn("przebudowy", n.engine_error(e))
            n.build_status = lambda: None
            self.assertIn("systemctl start nt1100-trasy", n.engine_error(e))
            self.assertEqual(n.engine_error(ValueError("zły punkt")), "zły punkt")
        finally:
            n.build_status = orig

    def test_18_screen5_home_routes_firmware(self):
        """Ekran 5": dom z bramą i garażem w pingu, przycisk jak pilot, wybór trasy, własna paczka."""
        calls, states = [], {"cover.brama": "closed", "cover.garaz": "opening"}

        def fake_ha(method, path, body=None, timeout=10):
            calls.append((method, path, body))
            if method == "GET" and path.startswith("/core/api/states/"):
                return {"state": states.get(path.rsplit("/", 1)[1], "unknown")}
            return []
        orig = srv.ha_call
        srv.ha_call = fake_ha
        try:
            code, j = self.jpost(self.pu + "/api/nav/settings", {"gate_entity": "light.zle"})
            self.assertEqual(code, 400)
            code, j = self.jpost(self.pu + "/api/nav/settings", {"gate_entity": "cover.brama", "garage_entity": "cover.garaz",
                                                                 "home": {"lat": 50.0, "lon": 19.9, "name": "Dom"}})
            self.assertEqual(code, 200, j)
            # two routes: both offered, the current first
            pts = l_shape()
            seg = "".join('<trkpt lat="%.6f" lon="%.6f"></trkpt>' % p for p in pts)
            ids = []
            for name in ("Pierwsza", "Druga"):
                code, body, _ = self.req(self.pu + "/api/nav/gpx?name=" + name, (GPX % seg).encode(),
                                         {"Content-Type": "application/gpx+xml"}, "POST")
                ids.append(json.loads(body)["id"])
            code, body, _ = self.req(self.iu + "/api/nav/ping?k=ekran5", headers={"X-Klucz": KEY})
            j = json.loads(body)
            self.assertEqual(j["home"]["gate"], {"state": "zamknięta", "open": False})
            self.assertEqual(j["home"]["garage"], {"state": "otwiera się", "open": True})
            self.assertEqual((j["home"]["lat"], j["home"]["lon"]), (50.0, 19.9))
            self.assertEqual(j["routes"][0]["id"], ids[1])
            self.assertIn(ids[0], [r["id"] for r in j["routes"]])
            self.assertLessEqual(len(j["routes"]), 8)
            # the rider picks the older one on the screen
            code, j = self.jpost(self.iu + "/api/nav/use", {"id": ids[0]}, {"X-Klucz": KEY})
            self.assertEqual((code, j["current"]), (200, ids[0]))
            code, body, _ = self.req(self.iu + "/api/nav/ping", headers={"X-Klucz": KEY})
            self.assertEqual(json.loads(body)["route"]["id"], ids[0])
            code, j = self.jpost(self.iu + "/api/nav/use", {"id": 99999}, {"X-Klucz": KEY})
            self.assertEqual(code, 404)
            # gate closed: toggle; garage moving: stop (like the remote)
            calls.clear()
            code, j = self.jpost(self.iu + "/api/nav/dom", {"which": "gate"}, {"X-Klucz": KEY})
            self.assertEqual((code, j["service"]), (200, "cover.toggle"))
            self.assertIn(("POST", "/core/api/services/cover/toggle", {"entity_id": "cover.brama"}), calls)
            code, j = self.jpost(self.iu + "/api/nav/dom", {"which": "garage"}, {"X-Klucz": KEY})
            self.assertEqual(j["service"], "cover.stop_cover")
            code, j = self.jpost(self.iu + "/api/nav/dom", {"which": "okno"}, {"X-Klucz": KEY})
            self.assertEqual(code, 400)
            code, _ = self.jpost(self.iu + "/api/nav/dom", {"which": "gate"})
            self.assertEqual(code, 401)
        finally:
            srv.ha_call = orig
        # 1.5.23: calendar on the ping, fuel prices through Google
        self.check_calendar_and_prices(ids)
        # firmware: each screen gets only its own package
        fw = srv.FIRMWARE
        made = not os.path.isdir(fw)
        os.makedirs(fw, exist_ok=True)
        with open(os.path.join(fw, "ekran5.bin"), "wb") as f:
            f.write(b"x" * 100)
        with open(os.path.join(fw, "ekran5.json"), "w") as f:
            json.dump({"version": "2.0.0"}, f)
        try:
            code, body, _ = self.req(self.iu + "/api/nav/fw?k=ekran5", headers={"X-Klucz": KEY})
            self.assertEqual(json.loads(body), {"version": "2.0.0", "size": 100})
            code, body, _ = self.req(self.iu + "/api/nav/ping?k=ekran5", headers={"X-Klucz": KEY})
            self.assertEqual(json.loads(body)["fw"], "2.0.0")
            code, body, _ = self.req(self.iu + "/api/nav/ping?k=ekran", headers={"X-Klucz": KEY})
            self.assertNotEqual(json.loads(body)["fw"], "2.0.0")
        finally:
            os.remove(os.path.join(fw, "ekran5.bin"))
            os.remove(os.path.join(fw, "ekran5.json"))
            if made:
                shutil.rmtree(fw, ignore_errors=True)

    def check_calendar_and_prices(self, ids):
        navmod = srv.navapi.nav
        now = time.time()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + "+00:00"
        seen = []

        def fake_ha(method, path, body=None, timeout=10):
            seen.append(path)
            if path.startswith("/core/api/calendars/calendar.dom"):
                return [{"start": {"dateTime": iso(now + 7200)}, "end": {"dateTime": iso(now + 9000)}, "summary": "Dentysta"},
                        {"start": {"date": time.strftime("%Y-%m-%d", time.localtime(now + 86400))}, "end": {"date": "x"},
                         "summary": "Urodziny"}]
            return {"state": "closed"}
        orig = srv.ha_call
        srv.ha_call = fake_ha
        try:
            code, j = self.jpost(self.pu + "/api/nav/settings", {"calendar_entity": "light.zle"})
            self.assertEqual(code, 400)
            code, j = self.jpost(self.pu + "/api/nav/settings", {"calendar_entity": "calendar.dom", "google_key": "G-123"})
            self.assertEqual(code, 200, j)
            self.assertIs(j["google_key"], True)
            code, body, _ = self.req(self.iu + "/api/nav/ping?k=ekran5", headers={"X-Klucz": KEY})
            j = json.loads(body)
            self.assertEqual([c["title"] for c in j["calendar"]], ["Dentysta", "Urodziny"])
            self.assertTrue(j["calendar"][0]["when"].startswith(("dziś", "jutro")), j["calendar"][0])
            self.assertEqual(j["calendar"][1]["when"], "jutro")
            # fuel prices: one Google call per station, the second ask comes from the cache
            calls = []

            def fake_http(url, data=None, headers=None, timeout=25):
                calls.append((url, data, headers))
                return {"places": [{"displayName": {"text": "Orlen"}, "fuelOptions": {"fuelPrices": [
                    {"type": "DIESEL", "price": {"units": "6", "nanos": 500000000, "currencyCode": "PLN"}, "updateTime": iso(now - 600)},
                    {"type": "REGULAR_UNLEADED", "price": {"units": "6", "nanos": 190000000, "currencyCode": "PLN"},
                     "updateTime": iso(now - 7200)}]}}]}
            o2 = navmod.http_json
            navmod.http_json = fake_http
            try:
                pl = {"places": [{"lat": 50.1, "lon": 19.9, "name": "A"}, {"lat": 50.2, "lon": 19.8, "name": "B"}, {"lat": "x"}]}
                code, j = self.jpost(self.iu + "/api/nav/fuel_prices", pl, {"X-Klucz": KEY})
                self.assertEqual(code, 200, j)
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0][2]["X-Goog-Api-Key"], "G-123")
                self.assertEqual(j["prices"][0]["text"], "6,19 zł · 2 h temu")
                self.assertEqual(j["prices"][0]["pb95"], 6.19)
                self.assertIsNone(j["prices"][2])
                code, j = self.jpost(self.iu + "/api/nav/fuel_prices", pl, {"X-Klucz": KEY})
                self.assertEqual(len(calls), 2)  # z pamięci
                code, _ = self.jpost(self.iu + "/api/nav/fuel_prices", pl)
                self.assertEqual(code, 401)
                # 1.5.34: to samo z panelu (ingress, bez klucza ekranu), z tej samej pamięci
                code, j = self.jpost(self.pu + "/api/nav/fuel_prices", pl)
                self.assertEqual(code, 200, j)
                self.assertEqual(j["prices"][0]["pb95"], 6.19)
                self.assertEqual(len(calls), 2)
                code, j = self.jpost(self.pu + "/api/nav/fuel_prices", {"places": "x"})
                self.assertEqual(code, 400)
                # licznik zapytań do Google: tylko te, które poszły (2 stacje z kluczem), nie z pamięci
                code, j = self.jpost(self.pu + "/api/nav/settings", {})
                self.assertEqual(code, 200, j)
                self.assertEqual(j["google_usage"]["n"], 2)
                self.assertEqual(j["google_usage"]["warn"], 500)
            finally:
                navmod.http_json = o2
            # 1.5.50: pogoda dla trasy policzonej na ekranie (punkty z czasem przejazdu), prognoza co ok. 30 min jazdy
            def fake_meteo(url, data=None, headers=None, timeout=25):
                n = url.split("latitude=")[1].split("&")[0].count("%2C") + 1
                hours = [time.strftime("%Y-%m-%dT%H:00", time.gmtime(now - 3600 + 3600 * k)) for k in range(30)]
                one = {"hourly": {"time": hours, "temperature_2m": [7 + k for k in range(30)], "precipitation_probability": [60] * 30,
                                  "precipitation": [0.4] * 30, "weather_code": [61] * 30, "wind_speed_10m": [18] * 30,
                                  "wind_gusts_10m": [30] * 30}}
                return [one] * n if n > 1 else one
            navmod.http_json = fake_meteo
            wx_on, srv.WEATHER_ON = srv.WEATHER_ON, True
            try:
                with navmod.WX_LOCK:
                    navmod.WX_CACHE.clear()
                pts = ";".join("%.5f,%.5f,%d" % (49.7 + 0.01 * k, 19.0 + 0.02 * k, 600 * k) for k in range(8))   # 70 min jazdy
                code, j = self.jpost(self.iu + "/api/nav/wx", {"pts": pts}, {"X-Klucz": KEY})
                self.assertEqual(code, 200, j)
                self.assertTrue(j["ok"], j)
                self.assertEqual((j["n"], j["w0_idx"], j["w1_idx"], j["w2_idx"], j["w3_idx"]), (4, 0, 3, 6, 7))
                self.assertEqual((j["w0_rain_prob"], j["w0_code"], j["w0_wind"]), (60, 61, 18))
                code, j = self.jpost(self.iu + "/api/nav/wx", {"pts": "x"}, {"X-Klucz": KEY})
                self.assertEqual(code, 400)
                code, _ = self.jpost(self.iu + "/api/nav/wx", {"pts": pts})
                self.assertEqual(code, 401)
            finally:
                navmod.http_json = o2
                srv.WEATHER_ON = wx_on
            # bez klucza: odpowiedź bez cen, nie błąd
            code, j = self.jpost(self.pu + "/api/nav/settings", {"google_key": ""})
            self.assertEqual(code, 200, j)
            code, j = self.jpost(self.iu + "/api/nav/fuel_prices", {"places": [{"lat": 50.3, "lon": 19.7}]}, {"X-Klucz": KEY})
            self.assertEqual((code, j["ok"], j["prices"]), (200, False, [None]))
        finally:
            srv.ha_call = orig

if __name__ == "__main__":
    unittest.main()
