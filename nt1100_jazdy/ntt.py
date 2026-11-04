"""Mapa dla ekranu: czytanie kwadratów .ntt (format z silnik-tras/build_map.py)
i proste zapytania przestrzenne (drogi i punkty w pobliżu).

Kwadrat 0,1° × 0,1°: nagłówek, tablica napisów, drogi (polilinie z klasą,
limitem, nazwą i skrzyżowaniami), punkty (fotoradary, odcinki, POI).
"""
import json
import math
import os
import struct
import threading

CELL = 10
F_ONEWAY, F_UNPAVED, F_TOLL, F_ROUNDABOUT, F_FERRY, F_TUNNEL, F_BRIDGE, F_LIT = 1, 2, 4, 8, 16, 32, 64, 128
P_CAMERA, P_SECTION_START, P_SECTION_END = 1, 2, 3
P_FUEL, P_RESTAURANT, P_CAFE, P_VIEWPOINT, P_PASS, P_HOTEL, P_CHARGING, P_MOTO_SHOP, P_PICNIC = 10, 11, 12, 13, 14, 15, 16, 17, 18
POINT_NAMES = {P_CAMERA: "fotoradar", P_SECTION_START: "odcinkowy pomiar: początek", P_SECTION_END: "odcinkowy pomiar: koniec",
               P_FUEL: "stacja paliw", P_RESTAURANT: "restauracja", P_CAFE: "kawiarnia", P_VIEWPOINT: "punkt widokowy",
               P_PASS: "przełęcz", P_HOTEL: "nocleg", P_CHARGING: "ładowarka", P_MOTO_SHOP: "sklep/serwis moto",
               P_PICNIC: "miejsce piknikowe"}
CLASS_NAMES = {1: "autostrada", 2: "ekspresowa", 3: "krajowa", 4: "wojewódzka", 5: "powiatowa", 6: "lokalna",
               7: "osiedlowa", 8: "dojazd", 9: "gruntowa", 10: "strefa zamieszkania", 11: "łącznik A", 12: "łącznik S",
               13: "łącznik", 14: "łącznik", 15: "łącznik"}
# Typowa prędkość jazdy po klasie drogi (km/h) do szacowania czasu bez silnika tras.
CLASS_SPEED = {1: 120, 2: 100, 3: 75, 4: 65, 5: 55, 6: 45, 7: 30, 8: 20, 9: 25, 10: 15, 11: 60, 12: 60, 13: 50, 14: 50, 15: 45}


def cell_of(lat, lon):
    return math.floor(lat * CELL), math.floor(lon * CELL)


def cell_name(key):
    return "c_%d_%d.ntt" % key


def dist_m(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return 6371000.0 * math.hypot(x, y)


def bearing(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return math.degrees(math.atan2(x, y)) % 360.0


def angle_diff(a, b):
    """Różnica kierunków w stopniach, -180..180."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


def point_segment(p, a, b):
    """Odległość punktu p od odcinka a-b w metrach i parametr 0..1 rzutu."""
    lat0 = math.radians((a[0] + p[0]) / 2)
    kx = 111320.0 * math.cos(lat0)
    ky = 111320.0
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 0:
        return math.hypot(ax, ay), 0.0
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / l2))
    return math.hypot(ax + t * dx, ay + t * dy), t


class Way:
    __slots__ = ("id", "cls", "flags", "limit", "limit_back", "name", "ref", "pts", "junctions")

    def __init__(self, wid, cls, flags, limit, limit_back, name, ref, pts, junctions):
        self.id, self.cls, self.flags, self.limit, self.limit_back = wid, cls, flags, limit, limit_back
        self.name, self.ref, self.pts, self.junctions = name, ref, pts, junctions

    def label(self):
        return self.ref or self.name or ""


class Point:
    __slots__ = ("id", "lat", "lon", "kind", "limit", "name", "pair")

    def __init__(self, nid, lat, lon, kind, limit, name, pair):
        self.id, self.lat, self.lon, self.kind, self.limit, self.name, self.pair = nid, lat, lon, kind, limit, name, pair


def read_varint(buf, pos):
    n = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, pos
        shift += 7


def unzigzag(n):
    return (n >> 1) ^ -(n & 1)


def read_cell(path):
    """Czyta kwadrat: (lista Way, lista Point)."""
    return _read(path)[:2]


def read_background(path):
    """Tło kwadratu dla ekranu: {"waters": [(rodzaj, nazwa, pkt)], "rivers": [...], "places": [(lat, lon, rodzaj, ranga, nazwa)]}."""
    return _read(path, True)[2]


def _coords(buf, pos, n):
    lat, lon = struct.unpack_from("<ii", buf, pos)
    pos += 8
    pts = [(lat / 1e6, lon / 1e6)]
    for _ in range(n - 1):
        d, pos = read_varint(buf, pos)
        lat += unzigzag(d)
        d, pos = read_varint(buf, pos)
        lon += unzigzag(d)
        pts.append((lat / 1e6, lon / 1e6))
    return pts, pos


def _read(path, background=False):
    with open(path, "rb") as f:
        buf = f.read()
    magic, ver, hflags, lat10, lon10, nways, npoints, nstr, strbytes = struct.unpack_from("<4sBBhhIIII", buf, 0)
    if magic != b"NTT1" or ver != 1:
        raise ValueError("zły plik mapy: " + path)
    pos = struct.calcsize("<4sBBhhIIII")
    offsets = struct.unpack_from("<%dI" % nstr, buf, pos)
    pos += 4 * nstr
    strings = []
    for i in range(nstr):
        end = buf.index(b"\0", pos + offsets[i])
        strings.append(buf[pos + offsets[i]:end].decode("utf-8", "replace"))
    pos += strbytes

    def s(i):
        return strings[i] if i < nstr else ""
    ways = []
    for _ in range(nways):
        wid, cls, flags, limit, limit_back, name, ref, npts, njunc = struct.unpack_from("<IBBBBHHHH", buf, pos)
        pos += 16
        lat, lon = struct.unpack_from("<ii", buf, pos)
        pos += 8
        pts = [(lat / 1e6, lon / 1e6)]
        for _ in range(npts - 1):
            d, pos = read_varint(buf, pos)
            lat += unzigzag(d)
            d, pos = read_varint(buf, pos)
            lon += unzigzag(d)
            pts.append((lat / 1e6, lon / 1e6))
        juncs = []
        for _ in range(njunc):
            idx, nid = struct.unpack_from("<HI", buf, pos)
            pos += 6
            juncs.append((idx, nid))
        ways.append(Way(wid, cls, flags, limit, limit_back, s(name), s(ref), pts, juncs))
    points = []
    for _ in range(npoints):
        nid, lat, lon, kind, limit, name, pair = struct.unpack_from("<IiiBBHH", buf, pos)
        pos += 18
        points.append(Point(nid, lat / 1e6, lon / 1e6, kind, limit, s(name), pair))
    bg = {"waters": [], "rivers": [], "places": []}
    if background and hflags & 1:
        nw, nr, npl = struct.unpack_from("<III", buf, pos)
        pos += 12
        for key, n in (("waters", nw), ("rivers", nr)):
            for _ in range(n):
                kind, name, npts = struct.unpack_from("<BHH", buf, pos)
                pts, pos = _coords(buf, pos + 5, npts)
                bg[key].append((kind, s(name), pts))
        for _ in range(npl):
            lat, lon, kind, rank, name = struct.unpack_from("<iiBBH", buf, pos)
            pos += 12
            bg["places"].append((lat / 1e6, lon / 1e6, kind, rank, s(name)))
    return ways, points, bg


GRID = 0.005  # oczko siatki odcinków (ok. 550 × 350 m) do szybkiego dopasowania drogi


def segment_grid(ways):
    """Siatka: oczko -> lista (Way, indeks odcinka) przechodzących przez oczko."""
    grid = {}
    for w in ways:
        p = w.pts
        for i in range(len(p) - 1):
            a, b = p[i], p[i + 1]
            g0, g1 = int(math.floor(min(a[0], b[0]) / GRID)), int(math.floor(max(a[0], b[0]) / GRID))
            h0, h1 = int(math.floor(min(a[1], b[1]) / GRID)), int(math.floor(max(a[1], b[1]) / GRID))
            for gi in range(g0, g1 + 1):
                for hj in range(h0, h1 + 1):
                    grid.setdefault((gi, hj), []).append((w, i))
    return grid


class Map:
    """Mapa z katalogu kwadratów; kwadraty wczytywane na żądanie i trzymane
    w pamięci (do kilkudziesięciu naraz)."""

    def __init__(self, directory, max_cells=60):
        self.dir = directory
        self.max_cells = max_cells
        self.cells = {}
        self.order = []
        self.lock = threading.Lock()

    def manifest(self):
        try:
            with open(os.path.join(self.dir, "manifest.json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def available(self):
        return os.path.exists(os.path.join(self.dir, "manifest.json"))

    def cell(self, key):
        """(lista Way, lista Point, siatka odcinków) jednego kwadratu."""
        with self.lock:
            c = self.cells.get(key)
            if c is not None:
                return c
            path = os.path.join(self.dir, cell_name(key))
            if os.path.exists(path):
                try:
                    ways, points = read_cell(path)
                except (OSError, ValueError, struct.error, IndexError):
                    ways, points = [], []
            else:
                ways, points = [], []
            c = (ways, points, segment_grid(ways))
            self.cells[key] = c
            self.order.append(key)
            while len(self.order) > self.max_cells:
                self.cells.pop(self.order.pop(0), None)
            return c

    def cells_around(self, lat, lon, radius_m):
        dl = radius_m / 111320.0
        dlon = radius_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))
        c0, c1 = cell_of(lat - dl, lon - dlon), cell_of(lat + dl, lon + dlon)
        return [(a, b) for a in range(c0[0], c1[0] + 1) for b in range(c0[1], c1[1] + 1)]

    def ways_near(self, lat, lon, radius_m):
        seen = set()
        out = []
        for key in self.cells_around(lat, lon, radius_m):
            for w in self.cell(key)[0]:
                if w.id in seen:
                    continue
                seen.add(w.id)
                out.append(w)
        return out

    def match_road(self, lat, lon, heading=None, radius_m=30.0):
        """Najbliższa droga (Way, odległość, kierunek_zgodny, indeks odcinka).
        Sprawdza tylko odcinki z oczek siatki wokół punktu."""
        best = None
        dlat = radius_m / 111320.0
        dlon = radius_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))
        g0, g1 = int(math.floor((lat - dlat) / GRID)), int(math.floor((lat + dlat) / GRID))
        h0, h1 = int(math.floor((lon - dlon) / GRID)), int(math.floor((lon + dlon) / GRID))
        seen = set()
        for key in self.cells_around(lat, lon, radius_m):
            grid = self.cell(key)[2]
            for gi in range(g0, g1 + 1):
                for hj in range(h0, h1 + 1):
                    for w, i in grid.get((gi, hj), ()):
                        k = (w.id, i)
                        if k in seen:
                            continue
                        seen.add(k)
                        a, b = w.pts[i], w.pts[i + 1]
                        if (min(a[0], b[0]) > lat + dlat or max(a[0], b[0]) < lat - dlat or
                                min(a[1], b[1]) > lon + dlon or max(a[1], b[1]) < lon - dlon):
                            continue
                        d, t = point_segment((lat, lon), a, b)
                        if d > radius_m:
                            continue
                        score = d
                        fwd = True
                        if heading is not None:
                            bb = bearing(a, b)
                            diff = abs(angle_diff(heading, bb))
                            if diff > 90:
                                fwd = False
                                diff = 180 - diff
                                if w.flags & F_ONEWAY:
                                    score += 40
                            score += diff * 0.15
                        if best is None or score < best[0]:
                            best = (score, w, d, fwd, i)
        if best is None:
            return None
        return best[1], best[2], best[3], best[4]

    def points_near(self, lat, lon, radius_m, kinds=None):
        out = []
        for key in self.cells_around(lat, lon, radius_m):
            for p in self.cell(key)[1]:
                if kinds and p.kind not in kinds:
                    continue
                d = dist_m((lat, lon), (p.lat, p.lon))
                if d <= radius_m:
                    out.append((d, p))
        out.sort(key=lambda x: x[0])
        return out

    def points_in_bbox(self, s, w, n, e, kinds=None, limit=500):
        """Punkty w prostokącie; gdy jest ich więcej niż limit, równomierna
        próbka z całego obszaru (fotoradary zawsze), a nie pierwsze kwadraty."""
        out = []
        c0, c1 = cell_of(s, w), cell_of(n, e)
        for a in range(c0[0], c1[0] + 1):
            for b in range(c0[1], c1[1] + 1):
                for p in self.cell((a, b))[1]:
                    if kinds and p.kind not in kinds:
                        continue
                    if s <= p.lat <= n and w <= p.lon <= e:
                        out.append(p)
        if len(out) <= limit:
            return out
        keep = [p for p in out if p.kind in (P_CAMERA, P_SECTION_START, P_SECTION_END)][:limit]
        rest = [p for p in out if p.kind not in (P_CAMERA, P_SECTION_START, P_SECTION_END)]
        room = limit - len(keep)
        if room > 0 and rest:
            step = len(rest) / float(room)
            keep += [rest[int(i * step)] for i in range(min(room, len(rest)))]
        return keep
        return out
