"""Graf tras na ekran (nawigacja offline): budowa w build_map.py i liczenie w graf.py
tymi samymi regułami co dodatek (warianty, omijanie, jednokierunkowe, zakazy skrętu)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nt1100_jazdy"))
import graf  # noqa: E402
import nav  # noqa: E402
import ntt  # noqa: E402

_spec = importlib.util.spec_from_file_location("build_map", os.path.join(HERE, "..", "silnik-tras", "build_map.py"))
build_map = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_map)

A, B = (50.05, 19.95), (50.05, 20.25)
C, D = (50.15, 19.95), (50.15, 20.02)
E1, J, E2, K = (50.12, 20.10), (50.12, 20.13), (50.12, 20.16), (50.135, 20.13)
BIG = 5000000001  # id węzła ponad 2^32 (w OSM już są)


def osm():
    nodes, ways, rels = {}, [], []
    nid = [1000]

    def node(p, i=None):
        if i is None:
            nid[0] += 1
            i = nid[0]
        nodes[i] = p
        return i

    def way(wid, ids, **tags):
        ways.append((wid, ids, tags))

    a, b = node(A, 1), node(B, 2)
    # autostrada (płatna, jednokierunkowa A -> B)
    way(10, [a, node((50.06, 20.05)), node((50.06, 20.15)), b], highway="motorway", toll="yes")
    # droga wojewódzka prawie prosto
    way(11, [a, node((50.03, 20.10)), b], highway="secondary")
    # kręta droga powiatowa (ok. 27 km)
    zig = [a] + [node((50.05 + (0.01 if i % 2 else -0.01), 19.95 + 0.3 * i / 8)) for i in range(1, 8)] + [b]
    way(12, zig, highway="tertiary")
    # szuter na skróty i dłuższy asfalt
    c, d = node(C, 3), node(D, 4)
    way(20, [c, d], highway="unclassified", surface="gravel")
    way(21, [c, node((50.165, 19.985)), d], highway="unclassified")
    way(22, [c, node((50.13, 19.985)), d], highway="unclassified")
    # zakaz jazdy prosto na skrzyżowaniu J (z drogi 30 w 31), objazd przez K
    e1, j, e2, k = node(E1, 5), node(J, BIG), node(E2, 6), node(K, 7)
    way(30, [e1, j], highway="tertiary")
    way(31, [j, e2], highway="tertiary")
    way(32, [e1, k], highway="residential")
    way(33, [k, e2], highway="residential")
    rels.append((300, [("way", 30, "from"), ("node", j, "via"), ("way", 31, "to")],
                 {"type": "restriction", "restriction": "no_straight_on"}))
    # adresy: miasto z ulicami, dwie wsie o tej samej nazwie daleko od siebie, wieś bez ulic, budynek
    addr = []

    def address(p, **tags):
        addr.append((node(p), tags))
    address((50.050, 19.960), **{"addr:city": "Łąkowo", "addr:street": "Główna", "addr:housenumber": "10",
                                 "addr:postcode": "43-150"})
    address((50.051, 19.961), **{"addr:city": "Łąkowo", "addr:street": "Główna", "addr:housenumber": "2"})
    address((50.052, 19.962), **{"addr:city": "Łąkowo", "addr:street": "Główna", "addr:housenumber": "2a"})
    address((50.053, 19.963), **{"addr:city": "Łąkowo", "addr:street": "Polna", "addr:housenumber": "1"})
    address((50.060, 19.970), **{"addr:city": "Nowa Wieś", "addr:street": "Leśna", "addr:housenumber": "5"})
    address((50.160, 20.270), **{"addr:city": "Nowa Wieś", "addr:street": "Leśna", "addr:housenumber": "5"})
    address((50.161, 20.271), **{"addr:city": "Nowa Wieś", "addr:street": "Leśna", "addr:housenumber": "7"})
    address((50.100, 20.000), **{"addr:place": "Wola", "addr:housenumber": "12"})
    b = [node((50.0540, 19.9640)), node((50.0540, 19.9650)), node((50.0550, 19.9650)), node((50.0550, 19.9640))]
    way(90, b + [b[0]], building="house", **{"addr:city": "Łąkowo", "addr:street": "Polna", "addr:housenumber": "3"})
    # nazwane miejsca: stacje jednej marki (bez nazwy, z miejscowością i bez), hotel jako budynek, bez nazwy
    address((50.0505, 19.9605), amenity="fuel", brand="Orlen")
    address((50.1605, 20.2705), amenity="fuel", name="Orlen", **{"addr:city": "Nowa Wieś"})
    address((50.0700, 19.9800), amenity="restaurant", name="Karczma Pod Lipą")
    address((50.0800, 19.9900), amenity="cafe")
    h = [node((50.0900, 19.9900)), node((50.0900, 19.9910)), node((50.0910, 19.9910)), node((50.0910, 19.9900))]
    way(91, h + [h[0]], building="hotel", tourism="hotel", name="Hotel Łąkowski")
    out = ["<?xml version='1.0' encoding='UTF-8'?>", '<osm version="0.6" generator="test">']
    tagged = dict(addr)
    for i in sorted(nodes):
        tags = "".join('<tag k="%s" v="%s"/>' % kv for kv in tagged.get(i, {}).items())
        out.append(' <node id="%d" version="1" lat="%.6f" lon="%.6f">%s</node>' % (i, nodes[i][0], nodes[i][1], tags))
    for wid, ids, tags in ways:
        out.append(' <way id="%d" version="1">%s%s</way>' % (
            wid, "".join('<nd ref="%d"/>' % i for i in ids),
            "".join('<tag k="%s" v="%s"/>' % kv for kv in tags.items())))
    for rid, members, tags in rels:
        out.append(' <relation id="%d" version="1">%s%s</relation>' % (
            rid, "".join('<member type="%s" ref="%d" role="%s"/>' % m for m in members),
            "".join('<tag k="%s" v="%s"/>' % kv for kv in tags.items())))
    out.append("</osm>")
    return "\n".join(out)


@unittest.skipUnless(shutil.which("osmium"), "brak programu osmium (osmium-tool)")
class GraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="nt1100-graf-")
        src = os.path.join(cls.tmp, "test.osm")
        with open(src, "w") as f:
            f.write(osm())
        pbf = os.path.join(cls.tmp, "test.osm.pbf")
        subprocess.run(["osmium", "cat", src, "-o", pbf, "--overwrite"], check=True)
        cls.out = os.path.join(cls.tmp, "mapa")
        cls.manifest = build_map.build(pbf, cls.out)
        cls.g = graf.Graph(cls.out)
        cls.map = ntt.Map(cls.out)
        cls.curvy = nav.curvy_sliders(None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ways(self, r):
        out = []
        for _, e in r["edges"]:
            if not out or out[-1] != e.way:
                out.append(e.way)
        return out

    def go(self, a, b, variant="szybko", avoid=()):
        r = graf.route(self.g, a, b, variant, avoid, self.curvy)
        self.assertIsNotNone(r)
        return r

    def test_manifest_lists_graph_files(self):
        m = json.load(open(os.path.join(self.out, "manifest.json")))
        self.assertEqual(m["wersja"], 5)
        names = [f[0] for f in m["graph"]["cells"]]
        self.assertTrue(names and all(n.startswith("g_") and n.endswith(".ntg") for n in names))
        self.assertTrue(all(n.endswith(".ntt") for n, _, _ in m["files"]))
        for n, size, crc in m["graph"]["cells"]:
            self.assertEqual(os.path.getsize(os.path.join(self.out, n)), size)
        self.assertEqual(m["graph"]["bytes"], sum(f[1] for f in m["graph"]["cells"]))

    def test_fast_takes_motorway(self):
        r = self.go(A, B)
        self.assertEqual(self.ways(r), [10])
        self.assertAlmostEqual(r["km"], 21.6, delta=0.6)

    def test_avoid_motorway_and_toll(self):
        self.assertEqual(self.ways(self.go(A, B, avoid=["autostrady"])), [11])
        self.assertEqual(self.ways(self.go(A, B, avoid=["platne"])), [11])

    def test_curvy_prefers_bends(self):
        self.assertEqual(self.ways(self.go(A, B, "kreto", ["autostrady"])), [12])
        self.assertEqual(self.ways(self.go(A, B, "bardzo")), [12])

    def test_oneway_motorway_not_backwards(self):
        self.assertEqual(self.ways(self.go(B, A)), [11])

    def test_gravel_only_when_allowed(self):
        self.assertEqual(self.ways(self.go(C, D)), [20])
        self.assertIn(self.ways(self.go(C, D, avoid=["szutrowe"])), ([21], [22]))

    def test_turn_restriction(self):
        self.assertEqual(self.ways(self.go(E1, E2)), [32, 33])
        # w drugą stronę zakaz nie obowiązuje
        self.assertEqual(self.ways(self.go(E2, E1)), [31, 30])

    def test_geometry_from_map_cells(self):
        r = self.go(A, B, "kreto", ["autostrady"])
        pts = graf.geometry(self.g, self.map, r)
        self.assertEqual(len(pts), 9)
        self.assertAlmostEqual(pts[0][0], A[0], places=5)
        self.assertAlmostEqual(pts[-1][1], B[1], places=5)
        back = graf.geometry(self.g, self.map, self.go(B, A))
        self.assertAlmostEqual(back[0][1], B[1], places=5)
        self.assertAlmostEqual(back[1][0], 50.03, places=5)

    def test_rules_match_addon_custom_model(self):
        """Te same suwaki i omijanie co w dodatku: priorytety jak w gh_custom_model."""
        class S:
            def settings(self):
                return {"curvy": nav.curvy_sliders(None)}
        for variant in graf.VARIANTS:
            cm = nav.Nav.gh_custom_model(S(), variant, ["autostrady", "platne"])
            p = graf.params(variant, ["autostrady", "platne"], self.curvy)
            self.assertEqual(p["di"], cm["distance_influence"])
        e = graf.Edge(None, 1000, 60, 4, 0, 0, 100, 250, 1, 0, 1, True)
        self.assertAlmostEqual(graf.priority(e, graf.params("kreto", (), self.curvy)), 1 - 0.65 * 0.8, places=3)  # kręto: zakręty 80 (1.5.28)
        self.assertAlmostEqual(graf.priority(e, graf.params("bardzo", (), self.curvy)), 0.35 * 0.8, places=3)


@unittest.skipUnless(shutil.which("osmium"), "brak programu osmium (osmium-tool)")
class AddressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        GraphTest.setUpClass.__func__(cls)
        import adresy
        cls.a = adresy.Addresses(cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_manifest_and_index(self):
        m = json.load(open(os.path.join(self.out, "manifest.json")))
        names = [f[0] for f in m["addr"]["cells"]]
        self.assertIn("a_index.nta", names)
        self.assertEqual(m["addr"]["bytes"], sum(f[1] for f in m["addr"]["cells"]))
        towns = sorted((t["name"], t["count"]) for t in self.a.index())
        self.assertEqual(towns, [("Nowa Wieś", 1), ("Nowa Wieś", 2), ("Wola", 1), ("Łąkowo", 5)])

    def test_find_without_polish_letters(self):
        r = self.a.find("lakowo", "glowna", "2A")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["name"], "Główna 2a, Łąkowo")
        self.assertAlmostEqual(r["lat"], 50.052, places=5)
        r = self.a.find("Łąk", "Gł")
        self.assertEqual(r["numbers"], ["2", "2a", "10"])
        r = self.a.find("łąkowo")
        self.assertEqual(r["postcode"], "43-150")
        self.assertEqual(r["streets"], ["Główna", "Polna"])

    def test_building_and_village_without_street(self):
        r = self.a.find("Łąkowo", "Polna", "3")
        self.assertAlmostEqual(r["lat"], 50.0545, places=3)
        r = self.a.find("wola", "", "12")
        self.assertEqual((r["ok"], r["name"]), (True, "Wola 12"))

    def test_same_name_far_apart_nearest_first(self):
        r = self.a.find("Nowa Wieś", "Leśna", "7", near=(50.16, 20.27))
        self.assertTrue(r["ok"])
        r = self.a.find("Nowa Wieś", "Leśna", "7", near=(50.06, 19.97))
        self.assertFalse(r["ok"])                       # bliższa Nowa Wieś nie ma numeru 7
        self.assertEqual(r["numbers"], ["5"])

    def test_missing(self):
        self.assertFalse(self.a.find("Xyz")["ok"])
        self.assertFalse(self.a.find("Łąkowo", "Kwiatowa")["ok"])

    def test_places_by_name(self):
        m = json.load(open(os.path.join(self.out, "manifest.json")))
        self.assertIn("a_poi.nta", [f[0] for f in m["addr"]["cells"]])
        self.assertEqual(m["wersja"], 5)
        self.assertEqual(len(self.a.poi_index()), 4)           # kawiarnia bez nazwy pominięta
        r = self.a.places("orlen", near=(50.16, 20.27))
        self.assertEqual([(x["name"], x["city"], x["kind"]) for x in r],
                         [("Orlen", "Nowa Wieś", "stacja"), ("Orlen", "Łąkowo", "stacja")])
        self.assertLess(r[0]["km"], r[1]["km"])
        r = self.a.places("orlen lak")                          # marka + miejscowość, bez ogonków
        self.assertEqual([x["city"] for x in r], ["Łąkowo"])
        r = self.a.places("lakowski")
        self.assertEqual((r[0]["name"], r[0]["kind"]), ("Hotel Łąkowski", "nocleg"))
        self.assertAlmostEqual(r[0]["lat"], 50.0905, places=3)
        self.assertEqual([x["name"] for x in self.a.places("pod lip")], ["Karczma Pod Lipą"])
        self.assertEqual(self.a.places("karczma", kinds={10}), [])
        self.assertEqual(self.a.places(""), [])


if __name__ == "__main__":
    unittest.main()
