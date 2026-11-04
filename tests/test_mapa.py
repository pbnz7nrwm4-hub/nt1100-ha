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
 <way id="100" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/><tag k="name" v="Główna"/></way>
 <way id="101" version="1"><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="14"/><nd ref="11"/></way>
 <way id="102" version="1"><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="24"/><nd ref="21"/></way>
 <way id="103" version="1"><nd ref="31"/><nd ref="32"/><nd ref="33"/><tag k="waterway" v="river"/><tag k="name" v="Rzeka"/></way>
 <way id="104" version="1"><nd ref="41"/><nd ref="42"/><nd ref="43"/><nd ref="44"/><nd ref="41"/><tag k="natural" v="water"/></way>
 <relation id="200" version="1"><member type="way" ref="101" role="outer"/><member type="way" ref="102" role="inner"/>
  <tag k="type" v="multipolygon"/><tag k="natural" v="water"/><tag k="name" v="Jezioro"/></relation>
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
            # the first byte of flags tells new readers about the extra part
            self.assertEqual(open(os.path.join(out, "c_500_199.ntt"), "rb").read()[5], 1)
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
