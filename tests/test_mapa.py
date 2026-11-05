"""Mapa na ekran: tło (woda, rzeki, miejscowości) i sumy kontrolne w manifeście."""
import binascii
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
import ntt  # noqa: E402

_spec = importlib.util.spec_from_file_location("build_map", os.path.join(HERE, "..", "silnik-tras", "build_map.py"))
build_map = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_map)

OSM = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
 <node id="1" version="1" lat="50.010" lon="19.910"/>
 <node id="2" version="1" lat="50.010" lon="19.990"/>
 <node id="11" version="1" lat="50.020" lon="19.920"/>
 <node id="12" version="1" lat="50.020" lon="19.940"/>
 <node id="13" version="1" lat="50.032" lon="19.940"/>
 <node id="14" version="1" lat="50.032" lon="19.920"/>
 <node id="21" version="1" lat="50.024" lon="19.926"/>
 <node id="22" version="1" lat="50.024" lon="19.934"/>
 <node id="23" version="1" lat="50.028" lon="19.934"/>
 <node id="24" version="1" lat="50.028" lon="19.926"/>
 <node id="31" version="1" lat="50.050" lon="19.850"/>
 <node id="32" version="1" lat="50.051" lon="19.900"/>
 <node id="33" version="1" lat="50.050" lon="19.950"/>
 <node id="41" version="1" lat="50.001" lon="19.991"/>
 <node id="42" version="1" lat="50.001" lon="19.993"/>
 <node id="43" version="1" lat="50.002" lon="19.993"/>
 <node id="44" version="1" lat="50.002" lon="19.991"/>
 <node id="50" version="1" lat="50.040" lon="19.940"><tag k="place" v="town"/><tag k="name" v="Testowo"/><tag k="population" v="12000"/></node>
 <node id="51" version="1" lat="50.060" lon="19.960"><tag k="place" v="hamlet"/><tag k="name" v="Przysiółek"/></node>
 <node id="61" version="1" lat="50.060" lon="19.910"/>
 <node id="62" version="1" lat="50.060" lon="19.930"/>
 <node id="63" version="1" lat="50.075" lon="19.930"/>
 <node id="64" version="1" lat="50.075" lon="19.910"/>
 <node id="65" version="1" lat="50.065" lon="19.915"/>
 <node id="66" version="1" lat="50.065" lon="19.925"/>
 <node id="67" version="1" lat="50.070" lon="19.925"/>
 <node id="68" version="1" lat="50.070" lon="19.915"/>
 <node id="71" version="1" lat="50.080" lon="19.950"/>
 <node id="72" version="1" lat="50.080" lon="19.951"/>
 <node id="73" version="1" lat="50.081" lon="19.951"/>
 <node id="74" version="1" lat="50.081" lon="19.950"/>
 <node id="81" version="1" lat="50.085" lon="19.960"/>
 <node id="82" version="1" lat="50.085" lon="19.975"/>
 <node id="83" version="1" lat="50.095" lon="19.975"/>
 <node id="84" version="1" lat="50.095" lon="19.960"/>
 <node id="85" version="1" lat="50.050" lon="20.020"/>
 <node id="86" version="1" lat="50.050" lon="20.040"/>
 <node id="87" version="1" lat="50.060" lon="20.040"/>
 <node id="88" version="1" lat="50.060" lon="20.020"/>
 <way id="100" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/><tag k="name" v="Główna"/></way>
 <way id="101" version="1"><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="14"/><nd ref="11"/></way>
 <way id="102" version="1"><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="24"/><nd ref="21"/></way>
 <way id="103" version="1"><nd ref="31"/><nd ref="32"/><nd ref="33"/><tag k="waterway" v="river"/><tag k="name" v="Rzeka"/></way>
 <way id="104" version="1"><nd ref="41"/><nd ref="42"/><nd ref="43"/><nd ref="44"/><nd ref="41"/><tag k="natural" v="water"/></way>
 <way id="110" version="1"><nd ref="61"/><nd ref="62"/><nd ref="63"/><nd ref="64"/><nd ref="61"/></way>
 <way id="111" version="1"><nd ref="65"/><nd ref="66"/><nd ref="67"/><nd ref="68"/><nd ref="65"/></way>
 <way id="112" version="1"><nd ref="71"/><nd ref="72"/><nd ref="73"/><nd ref="74"/><nd ref="71"/><tag k="natural" v="wood"/></way>
 <way id="113" version="1"><nd ref="81"/><nd ref="82"/><nd ref="83"/><nd ref="84"/><nd ref="81"/><tag k="landuse" v="residential"/></way>
 <way id="114" version="1"><nd ref="85"/><nd ref="86"/><nd ref="87"/><nd ref="88"/><nd ref="85"/><tag k="landuse" v="farmland"/></way>
 <relation id="200" version="1"><member type="way" ref="101" role="outer"/><member type="way" ref="102" role="inner"/>
  <tag k="type" v="multipolygon"/><tag k="natural" v="water"/><tag k="name" v="Jezioro"/></relation>
 <relation id="210" version="1"><member type="way" ref="110" role="outer"/><member type="way" ref="111" role="inner"/>
  <tag k="type" v="multipolygon"/><tag k="landuse" v="forest"/></relation>
</osm>
"""


@unittest.skipUnless(shutil.which("osmium"), "brak programu osmium (osmium-tool)")
class BuildMapBackgroundTest(unittest.TestCase):
    def test_water_rivers_places_and_crc(self):
        d = tempfile.mkdtemp(prefix="nt1100-mapa-")
        try:
            with open(os.path.join(d, "t.osm"), "w") as f:
                f.write(OSM)
            subprocess.run(["osmium", "cat", os.path.join(d, "t.osm"), "-o", os.path.join(d, "t.osm.pbf")], check=True)
            out = os.path.join(d, "mapa")
            m = build_map.build(os.path.join(d, "t.osm.pbf"), out)
            files = {f[0]: f for f in m["files"]}
            self.assertIn("c_500_199.ntt", files)
            for name, size, crc in m["files"]:
                b = open(os.path.join(out, name), "rb").read()
                self.assertEqual((len(b), binascii.crc32(b)), (size, crc))
            # old readers still read roads
            ways, points = ntt.read_cell(os.path.join(out, "c_500_199.ntt"))
            self.assertEqual([w.name for w in ways], ["Główna"])
            bg = ntt.read_background(os.path.join(out, "c_500_199.ntt"))
            kinds = sorted((k, n) for k, n, _ in bg["waters"])
            self.assertEqual(kinds, [(1, "Jezioro"), (2, "")])          # lake + island; small pond dropped
            self.assertEqual(len(bg["rivers"]), 1)
            self.assertEqual(bg["rivers"][0][:2], (1, "Rzeka"))
            self.assertEqual([(p[2], p[4]) for p in bg["places"]], [(2, "Testowo")])   # hamlet skipped
            self.assertGreater(bg["places"][0][3], 150)
            # the river piece west of 19.9 lands in the neighbouring cell (no roads there)
            self.assertIn("c_500_198.ntt", files)
            bg2 = ntt.read_background(os.path.join(out, "c_500_198.ntt"))
            self.assertEqual(len(bg2["rivers"]), 1)
            # the first byte of flags tells new readers about the extra parts (1 = background, 2 = terrain)
            self.assertEqual(open(os.path.join(out, "c_500_199.ntt"), "rb").read()[5], 3)
            # terrain (map style B): forest with a clearing, homes; tiny wood and farmland left out
            ter = sorted((k, len(p)) for k, p in bg["terrain"])
            self.assertEqual([k for k, _ in ter], [1, 4, 1 | 0x80])
            forest = [p for k, p in bg["terrain"] if k == 1][0]
            self.assertAlmostEqual(min(q[0] for q in forest), 50.06, places=5)
            self.assertAlmostEqual(max(q[1] for q in forest), 19.93, places=5)
            # roads-only cell east of 20.0: no farmland, so no terrain flag
            self.assertNotIn("c_500_200.ntt", files)
            self.assertEqual(m["wersja"], build_map.MAP_VERSION)
            self.assertEqual(subprocess.run([sys.executable, os.path.join(HERE, "..", "silnik-tras", "build_map.py"),
                                             "--wersja"], capture_output=True, text=True).stdout.strip(),
                             str(build_map.MAP_VERSION))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class EmptySeaTest(unittest.TestCase):
    def test_empty_water_polygons_zip(self):
        import struct
        import zipfile
        spec = importlib.util.spec_from_file_location("pusta_woda", os.path.join(HERE, "..", "silnik-tras", "pusta_woda.py"))
        pw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pw)
        d = tempfile.mkdtemp(prefix="nt1100-woda-")
        try:
            out = os.path.join(d, "w.zip")
            pw.main(out)
            with zipfile.ZipFile(out) as z:
                names = sorted(n.rsplit(".", 1)[1] for n in z.namelist())
                shp = z.read("water-polygons-split-3857/water_polygons.shp")
                dbf = z.read("water-polygons-split-3857/water_polygons.dbf")
            self.assertEqual(names, ["dbf", "prj", "shp", "shx"])
            self.assertEqual(len(shp), 100)
            self.assertEqual(struct.unpack(">i", shp[:4])[0], 9994)
            self.assertEqual(struct.unpack(">i", shp[24:28])[0] * 2, len(shp))
            self.assertEqual(struct.unpack("<i", shp[32:36])[0], 5)
            self.assertEqual(struct.unpack("<I", dbf[4:8])[0], 0)            # no records
            self.assertEqual(struct.unpack("<H", dbf[8:10])[0], len(dbf) - 1)  # header length (+ EOF byte)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ClipTest(unittest.TestCase):
    def test_clip_and_simplify(self):
        ring = [(49.95, 19.95), (49.95, 20.05), (50.05, 20.05), (50.05, 19.95)]
        part = build_map.clip_ring(ring, 50.0, 20.0, 50.1, 20.1)
        self.assertEqual(sorted(part), sorted([(50.0, 20.0), (50.0, 20.05), (50.05, 20.05), (50.05, 20.0)]))
        line = [(50.0, 19.9 + i * 0.001) for i in range(50)]
        self.assertEqual(len(build_map.simplify(line, 0.0001)), 2)


if __name__ == "__main__":
    unittest.main()
