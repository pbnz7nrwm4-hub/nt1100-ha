#!/usr/bin/env python3
"""Buduje mapę dla ekranu NT1100 z wycinka OpenStreetMap (plik .osm.pbf).

Wynik: katalog z plikami kwadratów 0,1° × 0,1° (c_<lat10>_<lon10>.ntt) i
manifest.json. Każdy kwadrat ma drogi (klasa, limit prędkości, nazwa,
skrzyżowania) oraz punkty (fotoradary, odcinkowe pomiary, stacje, POI).
Ten sam format czyta dodatek Home Assistant (nav.py) i ekran.

użycie: build_map.py WEJSCIE.osm.pbf KATALOG_WYJSCIOWY [--bbox S,W,N,E]

Potrzebny jest program `osmium` (pakiet osmium-tool) i `sort` z coreutils.
Pamięć: ok. 1–2 GB dla Polski; czas: kilka–kilkanaście minut.

Format kwadratu (little-endian):
  "NTT1" u8 wersja=1 u8 0 i16 lat10 i16 lon10 u32 n_dróg u32 n_punktów
  u32 n_napisów u32 bajty_napisów
  napisy: u32 offset[n_napisów], potem bajty UTF-8 zakończone 0
  drogi: u32 id_osm u8 klasa u8 flagi u8 limit_kmh u8 limit_tył(0=ten sam)
         u16 nazwa(0xFFFF brak) u16 ref u16 n_pkt u16 n_skrzyż
         i32 lat1e6 i32 lon1e6 (pierwszy), potem varint zygzak (dlat, dlon)
         skrzyżowania: u16 indeks_pkt u32 id_węzła
  punkty: u32 id_osm i32 lat1e6 i32 lon1e6 u8 rodzaj u8 limit u16 nazwa u16 para
"""
import collections
import json
import math
import os
import struct
import subprocess
import sys
import time

FORMAT = 1
CELL = 10  # kwadraty 0,1 stopnia

CLASSES = {
    "motorway": 1, "trunk": 2, "primary": 3, "secondary": 4, "tertiary": 5,
    "unclassified": 6, "residential": 7, "service": 8, "track": 9, "living_street": 10,
    "motorway_link": 11, "trunk_link": 12, "primary_link": 13, "secondary_link": 14, "tertiary_link": 15,
}
ROAD_FILTER = ",".join(CLASSES)
# Drogi serwisowe tylko jako dojazdy do stacji itp.; drogi gruntowe zostają
# (ekran je pokazuje i omija przy liczeniu trasy).
SKIP_SERVICE = {"parking_aisle", "driveway", "emergency_access"}

F_ONEWAY, F_UNPAVED, F_TOLL, F_ROUNDABOUT, F_FERRY, F_TUNNEL, F_BRIDGE, F_LIT = 1, 2, 4, 8, 16, 32, 64, 128

UNPAVED = {"unpaved", "gravel", "dirt", "ground", "grass", "sand", "mud", "fine_gravel", "compacted",
           "earth", "cobblestone", "sett", "pebblestone", "woodchips", "rock", "unhewn_cobblestone"}

# Rodzaje punktów.
P_CAMERA, P_SECTION_START, P_SECTION_END = 1, 2, 3
P_FUEL, P_RESTAURANT, P_CAFE, P_VIEWPOINT, P_PASS, P_HOTEL, P_CHARGING, P_MOTO_SHOP, P_PICNIC = 10, 11, 12, 13, 14, 15, 16, 17, 18
POI_TAGS = (
    (("amenity", "fuel"), P_FUEL), (("amenity", "restaurant"), P_RESTAURANT), (("amenity", "cafe"), P_CAFE),
    (("amenity", "fast_food"), P_RESTAURANT), (("tourism", "viewpoint"), P_VIEWPOINT),
    (("mountain_pass", "yes"), P_PASS), (("natural", "saddle"), P_PASS),
    (("tourism", "hotel"), P_HOTEL), (("tourism", "guest_house"), P_HOTEL), (("tourism", "motel"), P_HOTEL),
    (("amenity", "charging_station"), P_CHARGING), (("shop", "motorcycle"), P_MOTO_SHOP),
    (("shop", "motorcycle_repair"), P_MOTO_SHOP), (("tourism", "picnic_site"), P_PICNIC),
)
NODE_FILTER = ["n/highway=speed_camera"] + ["n/%s=%s" % kv for kv, _ in POI_TAGS]

IMPLICIT = {"PL:urban": 50, "PL:rural": 90, "PL:motorway": 140, "PL:expressway": 120, "PL:living_street": 20,
            "PL:trunk": 100, "urban": 50, "rural": 90, "walk": 7, "none": 0,
            "CZ:urban": 50, "CZ:rural": 90, "CZ:motorway": 130, "SK:urban": 50, "SK:rural": 90, "SK:motorway": 130,
            "DE:urban": 50, "DE:rural": 100, "LT:urban": 50, "LT:rural": 90, "UA:urban": 50, "UA:rural": 90,
            "BY:urban": 60, "BY:rural": 90}


def parse_maxspeed(v):
    if not v:
        return 0
    v = v.strip()
    if v in IMPLICIT:
        return IMPLICIT[v]
    try:
        mph = v.endswith("mph")
        n = float(v.replace("mph", "").replace("km/h", "").strip())
        if mph:
            n *= 1.609
        return max(0, min(255, int(round(n))))
    except ValueError:
        return 0


def zigzag(n):
    return (n << 1) ^ (n >> 63)


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def cell_of(lat, lon):
    return math.floor(lat * CELL), math.floor(lon * CELL)


class Cell:
    def __init__(self, key):
        self.key = key
        self.strings = {}
        self.string_bytes = bytearray()
        self.offsets = []
        self.ways = bytearray()
        self.nways = 0
        self.points = bytearray()
        self.npoints = 0

    def string(self, s):
        if not s:
            return 0xFFFF
        s = s[:60]
        i = self.strings.get(s)
        if i is None:
            if len(self.offsets) >= 0xFFFE:
                return 0xFFFF
            i = len(self.offsets)
            self.strings[s] = i
            self.offsets.append(len(self.string_bytes))
            self.string_bytes += s.encode("utf-8") + b"\0"
        return i

    def add_way(self, wid, cls, flags, limit, limit_back, name, ref, pts, junctions):
        rec = bytearray(struct.pack("<IBBBBHHHH", wid, cls, flags, limit, limit_back, self.string(name),
                                    self.string(ref), len(pts), len(junctions)))
        plat, plon = int(round(pts[0][0] * 1e6)), int(round(pts[0][1] * 1e6))
        rec += struct.pack("<ii", plat, plon)
        for lat, lon in pts[1:]:
            ilat, ilon = int(round(lat * 1e6)), int(round(lon * 1e6))
            rec += varint(zigzag(ilat - plat)) + varint(zigzag(ilon - plon))
            plat, plon = ilat, ilon
        for idx, nid in junctions:
            rec += struct.pack("<HI", idx, nid & 0xFFFFFFFF)
        self.ways += rec
        self.nways += 1

    def add_point(self, nid, lat, lon, kind, limit, name, pair):
        self.points += struct.pack("<IiiBBHH", nid & 0xFFFFFFFF, int(round(lat * 1e6)), int(round(lon * 1e6)),
                                   kind, limit, self.string(name), pair)
        self.npoints += 1

    def write(self, path):
        head = struct.pack("<4sBBhhIIII", b"NTT1", FORMAT, 0, self.key[0], self.key[1], self.nways, self.npoints,
                           len(self.offsets), len(self.string_bytes))
        with open(path, "wb") as f:
            f.write(head)
            f.write(struct.pack("<%dI" % len(self.offsets), *self.offsets))
            f.write(self.string_bytes)
            f.write(self.ways)
            f.write(self.points)
        return len(head) + 4 * len(self.offsets) + len(self.string_bytes) + len(self.ways) + len(self.points)


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def way_cells(pts):
    cells = set()
    prev = None
    for p in pts:
        c = cell_of(*p)
        cells.add(c)
        if prev and prev != c:
            # a long segment may cross a cell diagonally: add the middle too
            cells.add(cell_of((prev[0] + c[0]) / 2 / CELL + 0.05, (prev[1] + c[1]) / 2 / CELL + 0.05))
        prev = c
    return cells


def build(pbf, out, bbox=None):
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "_praca")
    os.makedirs(work, exist_ok=True)
    src = pbf
    if bbox:
        src = os.path.join(work, "wycinek.pbf")
        run(["osmium", "extract", "-b", bbox, pbf, "-o", src, "--overwrite", "-s", "smart"])
    roads = os.path.join(work, "drogi.pbf")
    run(["osmium", "tags-filter", src, "w/highway=" + ROAD_FILTER, "r/type=enforcement"] + NODE_FILTER +
        ["-o", roads, "--overwrite"])

    # 1. węzły używane przez >= 2 drogi = skrzyżowania (sort -n | uniq -d)
    refs = os.path.join(work, "wezly.txt")
    junction_file = os.path.join(work, "skrzyzowania.txt")
    print("+ osmium cat (drogi) | refs ->", refs, flush=True)
    way_refs = {}
    with open(refs, "w") as rf, subprocess.Popen(["osmium", "cat", roads, "-t", "way", "-f", "opl"],
                                                 stdout=subprocess.PIPE, text=True, bufsize=1 << 20) as p:
        for line in p.stdout:
            a = line.split(" N", 1)
            if len(a) < 2:
                continue
            nodes = a[1].strip()
            if not nodes:
                continue
            ids = nodes.replace("n", "").split(",")
            rf.write("\n".join(ids) + "\n")
            # endpoints count double: a road that ends on another road is a junction
            rf.write(ids[0] + "\n" + ids[-1] + "\n")
    env = dict(os.environ, LC_ALL="C")
    with open(junction_file, "w") as jf:
        p1 = subprocess.Popen(["sort", "-n", "-S", "25%", "-T", work, refs], stdout=subprocess.PIPE, env=env)
        run(["uniq", "-d"], stdin=p1.stdout, stdout=jf)
        p1.wait()
    junctions = set()
    with open(junction_file) as jf:
        for line in jf:
            junctions.add(int(line))
    os.remove(refs)
    print("skrzyżowań: %d (%.0f s)" % (len(junctions), time.time() - t0), flush=True)

    # 2. odcinkowe pomiary: relacje enforcement z from/to
    sections = {}  # node id -> (kind, limit, pair)
    pair_no = 0
    with subprocess.Popen(["osmium", "cat", roads, "-t", "relation", "-f", "opl"], stdout=subprocess.PIPE,
                          text=True) as p:
        for line in p.stdout:
            tags, members = {}, {}
            for part in line.split(" "):
                if part.startswith("T"):
                    for kv in part[1:].split(","):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            tags[k] = v.replace("%20", " ")
                elif part.startswith("M"):
                    for m in part[1:].strip().split(","):
                        if "@" in m:
                            ref, role = m.split("@", 1)
                            members.setdefault(role, []).append(ref)
            if tags.get("type") != "enforcement":
                continue
            if tags.get("enforcement") not in ("average_speed", "maxspeed", "section_control"):
                continue
            fr, to = members.get("from", []), members.get("to", [])
            if not fr or not to or not fr[0].startswith("n") or not to[0].startswith("n"):
                continue
            pair_no += 1
            limit = parse_maxspeed(tags.get("maxspeed"))
            sections[int(fr[0][1:])] = (P_SECTION_START, limit, pair_no)
            sections[int(to[0][1:])] = (P_SECTION_END, limit, pair_no)
    section_pts = {}
    if sections:
        ids = os.path.join(work, "odcinki-wezly.txt")
        with open(ids, "w") as f:
            f.write("\n".join("n%d" % n for n in sections) + "\n")
        secpbf = os.path.join(work, "odcinki.pbf")
        run(["osmium", "getid", src, "-i", ids, "-o", secpbf, "--overwrite"])
        with subprocess.Popen(["osmium", "cat", secpbf, "-t", "node", "-f", "opl"], stdout=subprocess.PIPE,
                              text=True) as p:
            for line in p.stdout:
                a = line.split(" ")
                nid = int(a[0][1:])
                x = y = None
                for part in a:
                    if part.startswith("x"):
                        x = float(part[1:])
                    elif part.startswith("y"):
                        y = float(part[1:])
                if x is not None and y is not None:
                    section_pts[nid] = (y, x)
    print("odcinkowych pomiarów: %d" % pair_no, flush=True)

    # 3. geometria (osmium export) + numery węzłów (opl) złączone po id drogi
    cells = {}

    def cell(key):
        c = cells.get(key)
        if c is None:
            c = cells[key] = Cell(key)
        return c

    opl = subprocess.Popen(["osmium", "cat", roads, "-t", "way", "-f", "opl"], stdout=subprocess.PIPE, text=True,
                           bufsize=1 << 20)
    exp = subprocess.Popen(["osmium", "export", roads, "-f", "geojsonseq", "--add-unique-id=type_id"],
                           stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    opl_line = None
    nways = npts = npoints = 0
    for line in exp.stdout:
        line = line.lstrip("\x1e")
        if not line.startswith("{"):
            continue
        f = json.loads(line)
        fid, geom, tags = f.get("id", ""), f.get("geometry") or {}, f.get("properties") or {}
        if fid.startswith("n") and geom.get("type") == "Point":
            lon, lat = geom["coordinates"]
            nid = int(fid[1:])
            if nid in sections:
                continue  # dodane niżej z relacji
            if tags.get("highway") == "speed_camera":
                cell(cell_of(lat, lon)).add_point(nid, lat, lon, P_CAMERA, parse_maxspeed(tags.get("maxspeed")),
                                                  "", 0)
                npoints += 1
                continue
            for (k, v), kind in POI_TAGS:
                if tags.get(k) == v:
                    name = tags.get("name") or tags.get("brand") or tags.get("operator") or ""
                    cell(cell_of(lat, lon)).add_point(nid, lat, lon, kind, 0, name, 0)
                    npoints += 1
                    break
            continue
        if not fid.startswith("w") or geom.get("type") != "LineString":
            continue
        wid = int(fid[1:])
        hw = tags.get("highway")
        cls = CLASSES.get(hw)
        if not cls:
            continue
        if hw == "service" and tags.get("service") in SKIP_SERVICE:
            continue
        acc = tags.get("motor_vehicle") or tags.get("motorcar") or tags.get("vehicle") or tags.get("access")
        if acc in ("no", "private", "agricultural", "forestry", "delivery", "customers") and \
                tags.get("motorcycle") not in ("yes", "designated"):
            continue
        # numery węzłów tej drogi (strumień opl jest w tej samej kolejności id)
        refs_ids = None
        while True:
            if opl_line is None:
                opl_line = opl.stdout.readline()
                if not opl_line:
                    break
            oid = int(opl_line.split(" ", 1)[0][1:])
            if oid < wid:
                opl_line = None
                continue
            if oid == wid:
                a = opl_line.split(" N", 1)
                refs_ids = [int(x) for x in a[1].strip().replace("n", "").split(",")] if len(a) > 1 else []
                opl_line = None
            break
        coords = geom["coordinates"]
        pts = [(c[1], c[0]) for c in coords]
        if len(pts) < 2:
            continue
        juncs = []
        if refs_ids and len(refs_ids) == len(pts):
            for i, nid in enumerate(refs_ids):
                if nid in junctions or i == 0 or i == len(refs_ids) - 1:
                    juncs.append((i, nid))
        flags = 0
        oneway = tags.get("oneway")
        if tags.get("junction") in ("roundabout", "circular"):
            flags |= F_ROUNDABOUT
            if oneway != "no":
                flags |= F_ONEWAY
        if oneway in ("yes", "1", "true") or hw in ("motorway", "motorway_link") and oneway != "no":
            flags |= F_ONEWAY
        if oneway == "-1":
            pts.reverse()
            juncs = [(len(pts) - 1 - i, n) for i, n in juncs]
            flags |= F_ONEWAY
        surf = tags.get("surface", "")
        if surf.split(":")[0] in UNPAVED or hw == "track" and surf not in ("asphalt", "paved", "concrete") \
                or tags.get("tracktype") in ("grade3", "grade4", "grade5"):
            flags |= F_UNPAVED
        if tags.get("toll") not in (None, "no"):
            flags |= F_TOLL
        if tags.get("tunnel") not in (None, "no"):
            flags |= F_TUNNEL
        if tags.get("bridge") not in (None, "no"):
            flags |= F_BRIDGE
        if tags.get("lit") == "yes":
            flags |= F_LIT
        limit = parse_maxspeed(tags.get("maxspeed"))
        limit_back = parse_maxspeed(tags.get("maxspeed:backward")) if tags.get("maxspeed:backward") else 0
        if tags.get("maxspeed:forward"):
            limit = parse_maxspeed(tags.get("maxspeed:forward"))
        name = tags.get("name") or ""
        ref = tags.get("ref") or ""
        if len(juncs) > 0xFFFF or len(pts) > 0xFFFF:
            continue
        for key in way_cells(pts):
            cell(key).add_way(wid, cls, flags, limit, limit_back, name, ref, pts, juncs)
        nways += 1
        npts += len(pts)
        if nways % 100000 == 0:
            print("dróg: %d, punktów dróg: %d (%.0f s)" % (nways, npts, time.time() - t0), flush=True)
    exp.wait()
    opl.kill()
    for nid, (kind, limit, pair) in sections.items():
        if nid in section_pts:
            lat, lon = section_pts[nid]
            cell(cell_of(lat, lon)).add_point(nid, lat, lon, kind, limit, "", pair)
            npoints += 1

    # 4. zapis
    files = []
    total = 0
    lats = [k[0] for k in cells]
    lons = [k[1] for k in cells]
    for key in sorted(cells):
        name = "c_%d_%d.ntt" % key
        n = cells[key].write(os.path.join(out, name))
        files.append([name, n])
        total += n
    manifest = {
        "format": FORMAT, "cell_deg": 1.0 / CELL, "built": time.strftime("%Y-%m-%d"),
        "source": os.path.basename(pbf), "ways": nways, "points": npoints, "bytes": total,
        "bbox": [min(lats) / CELL, min(lons) / CELL, (max(lats) + 1) / CELL, (max(lons) + 1) / CELL] if cells else None,
        "files": files,
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    for name in os.listdir(work):
        os.remove(os.path.join(work, name))
    os.rmdir(work)
    print("gotowe: %d kwadratów, %d dróg, %d punktów, %.1f MB, %.0f s" %
          (len(files), nways, npoints, total / 1e6, time.time() - t0), flush=True)
    return manifest


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    bbox = None
    if "--bbox" in sys.argv:
        bbox = sys.argv[sys.argv.index("--bbox") + 1]
    build(sys.argv[1], sys.argv[2], bbox)


if __name__ == "__main__":
    main()
