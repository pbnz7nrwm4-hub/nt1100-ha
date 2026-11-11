"""Tests of the add-on server (no Home Assistant, no network).

Run: python3 -m unittest discover -s homeassistant/addon/tests
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "nt1100_jazdy", "server.py")

TMP = tempfile.mkdtemp(prefix="nt1100-test-")
os.environ.update({
    "NT_SHARE": os.path.join(TMP, "share"), "NT_DATA": os.path.join(TMP, "data"),
    "NT_INGRESS_PEERS": "127.0.0.1", "NT_INGRESS_PORT": "0", "NT_INGEST_PORT": "0", "NT_WEATHER": "0",
    "SUPERVISOR_TOKEN": "", "NT_FIRMWARE": os.path.join(TMP, "fw"),
})
spec = importlib.util.spec_from_file_location("server", SERVER)
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

KEY = "test-key-123"


def track(n_points=900, curvy=True):
    """A ride: 1 point per second, a winding road when curvy."""
    import math
    lines = []
    lat, lon, head = 50.0, 19.9, 0.0
    for t in range(n_points):
        if curvy:
            head += 6 * math.sin(t / 15.0)
        speed = 60.0
        step = speed / 3.6
        lat += step * math.cos(math.radians(head)) / 111200
        lon += step * math.sin(math.radians(head)) / (111200 * math.cos(math.radians(lat)))
        lean = 25 * math.sin(t / 15.0) if curvy else 0.0
        lines.append("%.6f,%.6f,%.1f,%.0f,%d,%d,,,,,," % (lat, lon, lean, speed, 300, t))
    return ("\n".join(lines) + "\n").encode()


class ServerTest(unittest.TestCase):
    def test_problems_crash_dry_run(self):
        rep = {"gnss": {"found": True, "fix_pct": 99, "outages": 0}, "crash": {"n": 5, "list": [
            {"s": 750, "type": 1, "g": 6.2, "lean": 70, "speed": 60}, {"s": 900, "type": 3, "g": 0, "lean": -80, "speed": 30}]}}
        out = srv.problems(rep)
        self.assertEqual(len([o for o in out if "upadku" in o]), 3)
        self.assertIn("po 12 min: uderzenie i leżenie", out[0])
        self.assertIn("razem: 5", out[-1])
        self.assertEqual([o for o in srv.problems({"crash": {"n": 0, "list": []}}) if "upadku" in o], [])

    @classmethod
    def setUpClass(cls):
        for d in (srv.RIDES, srv.INCOMING, srv.CACHE, srv.DATA):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(srv.DATA, "options.json"), "w") as f:
            json.dump({"klucz": KEY}, f)
        cls.page = srv.serve(0, srv.Page)
        cls.ingest = srv.serve(0, srv.Ingest)
        cls.pu = "http://127.0.0.1:%d" % cls.page.server_address[1]
        cls.iu = "http://127.0.0.1:%d" % cls.ingest.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.page.shutdown()
        cls.ingest.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)

    def req(self, url, data=None, headers=None, method=None):
        r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def send(self, n, rid, ext, data, key=KEY):
        q = "n=%d&id=%s&ext=%s&size=%d&crc=%08x" % (n, rid, ext, len(data), zlib.crc32(data) & 0xFFFFFFFF)
        return self.req(self.iu + "/api/ingest?" + q, data, {"X-Klucz": key}, "POST")

    def ride(self, n, rid, start="2026-10-04T07:46:40Z", km=15.0, extra=None):
        trk = track()
        self.assertEqual(self.send(n, rid, "trk", trk)[0], 200)
        rep = {"ride": n, "gnss": {"found": True, "fix_pct": 70, "outages": 0}, "imu": {"ok": True},
               "calib": {"ok": True}, "power": {"vbus_drops": 2}, "storage": {"dropped": 0}, "seconds": 900,
               "markers": 1, "battery": 80}
        self.assertEqual(self.send(n, rid, "rep", json.dumps(rep).encode())[0], 200)
        s = {"ride": rid, "start": start, "end": start, "distance_km": km, "moving_min": 15, "max_speed": 60,
             "max_lean_left": 25, "max_lean_right": 25}
        s.update(extra or {})
        code, body, _ = self.send(n, rid, "json", json.dumps(s).encode())
        self.assertEqual(code, 200, body)
        return json.loads(body)["n"]

    def test_wrong_key(self):
        self.assertEqual(self.send(1, "x", "json", b"{}", key="zly")[0], 401)

    def test_bad_crc(self):
        q = "n=5&id=abc&ext=trk&size=3&crc=00000000"
        code, _, _ = self.req(self.iu + "/api/ingest?" + q, b"abc", {"X-Klucz": KEY}, "POST")
        self.assertEqual(code, 422)

    def test_ride_late_files_and_list(self):
        n = self.ride(7, "20261004-074640")
        self.assertTrue(os.path.exists(srv.ride_path(n, "rep")))
        # name changed on the box after sending
        self.assertEqual(self.send(7, "20261004-074640", "nam", b'{"name":"Beskidy","fav":true,"note":""}')[0], 200)
        self.assertEqual(srv.name_info(n)["name"], "Beskidy")
        # raw log copy (in pieces, larger)
        raw = os.urandom(300000)
        code, body, _ = self.send(7, "20261004-074640", "mtl", raw)
        self.assertEqual(code, 200, body)
        with open(srv.ride_path(n, "mtl"), "rb") as f:
            self.assertEqual(f.read(), raw)
        code, body, _ = self.req(self.pu + "/api/rides")
        rides = json.loads(body)["rides"]
        r = [x for x in rides if x["n"] == n][0]
        self.assertEqual(r["name"], "Beskidy")
        self.assertIn("zasilanie zanikało 2×", r["problems"])
        self.assertIn("GPS miał pozycję tylko przez 70% czasu", r["problems"])
        self.assertIsNotNone(r["curvy"]["deg_km"])
        self.assertGreater(r["curvy"]["corners"], 3)
        # name removed on the box: an empty one
        self.assertEqual(self.send(7, "20261004-074640", "nam", b'{"name":"","fav":false,"note":""}')[0], 200)
        self.assertFalse(os.path.exists(srv.ride_path(n, "nam")))
        # raw log download
        code, body, _ = self.req(self.pu + "/dl?f=/rides/%04d.mtl" % n)
        self.assertEqual((code, len(body)), (200, len(raw)))

    def test_signals_file_10hz(self):
        sig = (b"t_ms,unix_ms,rpm,throttle,gear,lean_deg,speed_kmh,long_g,lat_g,sw\n"
               b"0,1793800000000,3100,12.5,3,-4.20,64.0,0.120,-0.050,0\n"
               b"100,1793800000100,3200,15.0,3,-4.60,64.5,0.130,-0.060,0\n")
        self.assertEqual(self.send(21, "20261011-101010", "sig", sig)[0], 200)
        n = self.ride(21, "20261011-101010", start="2026-10-11T10:10:10Z")
        code, body, hdr = self.req(self.pu + "/api/rides/%d/sig" % n)
        self.assertEqual((code, body), (200, sig))
        self.assertIn("text/csv", hdr.get("Content-Type", ""))
        # a ride from older firmware has none
        n2 = self.ride(22, "20261011-111111", start="2026-10-11T11:11:11Z")
        self.assertEqual(self.req(self.pu + "/api/rides/%d/sig" % n2)[0], 404)

    def test_curviness_straight_vs_winding(self):
        def pts(b):
            out = []
            for line in b.decode().splitlines():
                a = line.split(",")
                out.append([float(a[0]), float(a[1]), float(a[2]), float(a[3]), float(a[4]), float(a[5])])
            return out
        straight = srv.curviness(pts(track(curvy=False)))
        winding = srv.curviness(pts(track(curvy=True)))
        self.assertEqual(straight["rating"], "prosta")
        self.assertEqual(straight["corners"], 0)
        self.assertGreater(winding["deg_km"], 80)
        self.assertLessEqual(len(winding["top"]), 5)

    def test_ping_settings_and_service(self):
        code, body, _ = self.req(self.iu + "/api/ping", headers={"X-Klucz": KEY, "X-Wersja": "1.3.0",
                                                                 "X-SD": "30000,12000", "X-Bateria": "77"})
        self.assertEqual(code, 200)
        j = json.loads(body)
        self.assertEqual((j["sd_min_free_pct"], j["hotspot_min_kbit"]), (0, 1000))
        st = srv.state()
        self.assertEqual((st["box_fw"], st["box_sd_free"], st["box_battery"]), ("1.3.0", 12000, 77))
        body = json.dumps({"sd_min_free_pct": 20, "hotspot_min_kbit": 2000, "odo": {"km": 10000, "date": 0},
                           "service": [{"name": "Olej", "interval_km": 6000, "last_km": 9000}]}).encode()
        code, out, _ = self.req(self.pu + "/api/settings", body, {"Content-Type": "application/json"}, "POST")
        self.assertEqual(code, 200, out)
        self.assertEqual(json.loads(self.req(self.iu + "/api/ping", headers={"X-Klucz": KEY})[1])["sd_min_free_pct"], 20)
        self.assertEqual(self.req(self.pu + "/api/settings", b'{"sd_min_free_pct": 90}', {}, "POST")[0], 400)
        odo = srv.odometer()
        self.assertGreaterEqual(odo, 10000)  # rides after the date are added
        sid = srv.settings()["service"][0]["id"]
        code, out, _ = self.req(self.pu + "/api/service/done?id=" + sid, b"", {}, "POST")
        self.assertEqual(code, 200)
        self.assertEqual(srv.service_status()[0]["left_km"], 6000)
        code, out, _ = self.req(self.pu + "/api/status")
        h = json.loads(out)["ha"]
        self.assertEqual(h["box_fw"], "1.3.0")
        self.assertEqual(h["odo"], odo)

    def test_versions(self):
        self.assertEqual(srv.device_version("1.4.2", "1.4.3", None)["status"], "update")
        self.assertEqual(srv.device_version("1.4.10", "1.4.9", None)["status"], "ok")  # numeric, not text order
        self.assertEqual(srv.device_version(None, "1.0.9", None)["status"], "unknown")
        code, out, _ = self.req(self.pu + "/api/versions")
        self.assertEqual(code, 200, out)
        v = json.loads(out)
        self.assertEqual(set(v), {"addon", "box", "screen", "engine"})
        self.assertEqual(v["addon"]["installed"], srv.VERSION)
        self.assertEqual(v["screen"]["latest"], (srv.navapi.screen_firmware_offer("ekran5") or {}).get("version"))
        # 1.5.19: ekran 5" (2.x) porównywany z paczką ekran5, 2,8" (1.x) z paczką ekran
        self.assertEqual(srv.navapi.screen_kind_of("2.0.0"), "ekran5")
        self.assertEqual(srv.navapi.screen_kind_of("1.1.3"), "ekran")
        self.assertEqual(srv.navapi.screen_kind_of(None), "ekran5")
        self.assertEqual(srv.navapi.screen_kind_of("x"), "ekran5")
        # 1.5.35: paczki ekranu 2,8" już nie ma – dodatek nic mu nie proponuje
        self.assertIsNone(srv.navapi.screen_firmware_offer("ekran"))

    def test_records_line(self):
        self.ride(19, "20261001-080000", start="2026-10-01T08:00:00Z", km=20.0)
        self.ride(20, "20261005-080000", start="2026-10-05T08:00:00Z", km=500.0, extra={"max_speed": 210})
        n = srv.late_ride(20, "20261005-080000")
        line = srv.records_line(n, srv.summary(n))
        self.assertIn("najdłuższa jazda", line)
        self.assertIn("najwyższa prędkość (210 km/h)", line)

    def test_weather_points(self):
        pts = [[50, 19, 0, 50, 200, t] for t in range(0, 5400, 10)]
        wp = srv.weather_points(pts)
        self.assertEqual([p[0] for p in wp], [0, 1800, 3600, 5390])

    def test_page_only_from_ingress(self):
        code, _, _ = self.req(self.pu + "/dl?f=/rides/0001.cfg")
        self.assertEqual(code, 400)

    def test_no_part_names(self):
        """Names of the parts inside the box stay out of the published files
        (compared as hashes, so this test does not name them either)."""
        import hashlib
        import re
        banned = {"fdd3269b1beb366d", "92aec3f2f63df47f", "e2952694dec272e5", "80335fa5d5052a29",
                  "7d219bec161177ba", "90bf090e2334db65", "dda2177678726e57", "b38995f3779da856",
                  "e005176a5048ebb9", "75acee422eb4a05b", "7de754d35a3f7148"}
        root = os.path.join(HERE, "..")
        for d, _, names in os.walk(root):
            if "/." in d.replace(os.sep, "/") or "firmware" in d:
                continue
            for name in names:
                if name == "make_page.py" or not name.endswith((".py", ".html", ".md", ".yaml", ".yml", ".txt", ".json")):
                    continue
                text = open(os.path.join(d, name), encoding="utf-8", errors="replace").read().lower()
                for tok in set(re.findall(r"[a-z0-9]+", text)):
                    h = hashlib.sha256(tok.encode()).hexdigest()[:16]
                    self.assertNotIn(h, banned, "%s: nazwa czesci w pliku" % name)


class VersionFallbackTest(unittest.TestCase):
    """1.5.44: the fallback number in server.py must match config.yaml (the footer showed 1.5.41 on 1.5.43)."""

    def test_fallback_matches_config(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nt1100_jazdy")
        with open(os.path.join(root, "config.yaml"), encoding="utf-8") as f:
            cfg = [l.split('"')[1] for l in f if l.startswith("version:")][0]
        with open(os.path.join(root, "server.py"), encoding="utf-8") as f:
            line = [l for l in f if l.startswith("VERSION = ")][0]
        self.assertIn('"%s"' % cfg, line)
        with open(os.path.join(root, "Dockerfile"), encoding="utf-8") as f:
            self.assertIn("NT1100_VERSION=$BUILD_VERSION", f.read())


if __name__ == "__main__":
    unittest.main()
