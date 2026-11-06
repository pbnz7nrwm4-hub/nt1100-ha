#!/usr/bin/env python3
"""Buduje mapę dla ekranu NT1100 z wycinka OpenStreetMap (plik .osm.pbf).

Wynik: katalog z plikami kwadratów 0,1° × 0,1° (c_<lat10>_<lon10>.ntt) i
manifest.json. Każdy kwadrat ma drogi (klasa, limit prędkości, nazwa,
skrzyżowania) oraz punkty (fotoradary, odcinkowe pomiary, stacje, POI).
Ten sam format czyta dodatek Home Assistant (nav.py) i ekran.

użycie: build_map.py WEJSCIE.osm.pbf KATALOG_WYJSCIOWY [--bbox S,W,N,E]
        build_map.py --wersja       (wersja zawartości mapy, dla aktualizuj.sh)

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
  (od 2026-11, gdy bajt 5 nagłówka ma bit 0 = 1) za punktami część „tło”:
  u32 n_wód u32 n_rzek u32 n_miejscowości
  wody (wielokąty przycięte do kwadratu z marginesem, uproszczone):
         u8 rodzaj (1 = woda, 2 = wyspa w wodzie, rysowana kolorem tła po wodach)
         u16 nazwa u16 n_pkt i32 lat1e6 i32 lon1e6, potem varint zygzak (dlat, dlon)
  rzeki: u8 rodzaj (1 = rzeka, 2 = kanał) u16 nazwa u16 n_pkt, punkty jak wyżej
  miejscowości: i32 lat1e6 i32 lon1e6 u8 rodzaj (1 miasto, 2 miasteczko, 3 wieś)
         u8 ranga (0–255, większa = ważniejsza, z liczby mieszkańców) u16 nazwa
  (od wersji mapy 2, gdy bajt 5 ma też bit 1 = 1) za tłem część „teren” do mapy w stylu B:
  u32 n_terenów, potem: u8 rodzaj u16 n_pkt i32 lat1e6 i32 lon1e6, varint zygzak (dlat, dlon)
         rodzaj: 1 las, 2 łąka/park/trawa, 4 osiedle, 5 przemysł/handel, 7 mokradło, 8 cmentarz, 9 boisko/sport;
         rodzaj | 0x80 = polana (dziura w lesie, rysowana kolorem tła po lasach). Pola uprawne = tło.
         Część „tło” jest wtedy zawsze zapisana (choćby z zerami).
Starsze czytniki kończą na punktach (albo na tle) i ignorują resztę pliku.

Od wersji mapy 3 obok kwadratów są pliki grafu tras g_<lat10>_<lon10>.ntg (nawigacja offline na
ekranie, te same kwadraty 0,1°). Węzeł = skrzyżowanie (albo koniec drogi) leżące w tym kwadracie,
krawędź = kawałek drogi między dwoma kolejnymi skrzyżowaniami, w kierunku, w którym wolno jechać.
  "NTG1" u8 wersja=1 u8 0 i16 lat10 i16 lon10 u32 n_węzłów u32 n_kraw_głównych u32 n_kraw_bocznych
  u32 n_zakazów
  węzły (16 B): i32 lat1e6 i32 lon1e6 u32 pierwsza_główna u32 pierwsza_boczna
         (krawędzie węzła i: od pierwsza[i] do pierwsza[i+1]-1, dla ostatniego do n_kraw)
  krawędzie główne (drogi klasy 1–6 i łączniki 11–15), potem boczne (7–10); każda 22 B:
         i8 dlat i8 dlon (kwadrat węzła końcowego minus ten kwadrat) u32 węzeł_końcowy (numer w tamtym
         kwadracie) u16 długość_m u8 prędkość_kmh u8 klasa u8 flagi (1 płatna, 2 tunel, 4 rondo,
         8 pod prąd geometrii drogi, 16 most) u8 nawierzchnia (0 utwardzona/nieznana, 1 szuter,
         2 grunt) u8 priorytet_% (stały, z motocykl.json) u8 krętość×250 (odległość w linii prostej
         / długość, jak curvature w GraphHopperze) u32 id_drogi (jak w .ntt) u16 pkt_od u16 pkt_do
         (indeksy punktów tej drogi w .ntt kwadratu węzła początkowego; pkt_od > pkt_do = pod prąd)
  zakazy skrętu (13 B): u32 węzeł (w tym kwadracie) u32 droga_z u32 droga_do u8 rodzaj
         (1 = zakaz wjazdu z drogi_z w drogę_do, 2 = z drogi_z wolno tylko w drogę_do)

manifest.json: {"format":1,"wersja":3,"built":"RRRR-MM-DD","bytes":N,"files":[[nazwa, bajty, crc32], ...],
"graph": {"format":1, "bytes":N, "cells":[[nazwa, bajty, crc32], ...]}, ...}
(lista grafu nazywa się „cells”, nie „files”, bo proste czytniki JSON na ekranie szukają pierwszego „files”).
crc32 jak w zlib (binascii.crc32), dziesiętnie.
"""
import binascii
import collections
import json
import math
import os
import struct
import subprocess
import sys
import time

FORMAT = 1
# Wersja zawartości mapy: aktualizuj.sh przebudowuje kwadraty, gdy kontener ma starszą
# (także gdy dane OSM się nie zmieniły). 1 = drogi, punkty, tło; 2 = + teren (styl B);
# 3 = + graf tras (g_*.ntg) do nawigacji offline na ekranie.
MAP_VERSION = 3
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

H_EXTRA = 1  # bajt 5 nagłówka: plik ma część „tło” (woda, rzeki, miejscowości)
H_TERRAIN = 2  # bajt 5 nagłówka: za tłem jest część „teren” (lasy, łąki, osiedla...)
W_WATER, W_ISLAND = 1, 2
R_RIVER, R_CANAL = 1, 2
PL_CITY, PL_TOWN, PL_VILLAGE = 1, 2, 3
PLACES = {"city": PL_CITY, "town": PL_TOWN, "village": PL_VILLAGE}
WATER_FILTER = ["a/natural=water", "a/landuse=reservoir", "w/waterway=river,canal", "n/place=city,town,village"]
WATER_MIN_M2 = 20000      # mniejsze stawy pomijamy
WATER_TOL = 0.00008       # uproszczenie konturu, ok. 6–9 m
CLIP_MARGIN = 0.002       # zapas przycięcia wokół kwadratu (ok. 200 m)

# Teren do mapy w stylu B (lasy z drzewkami, łąki, osiedla). Pola uprawne nie: to kolor tła.
T_FOREST, T_GRASS, T_HOMES, T_INDUSTRY, T_WETLAND, T_CEMETERY, T_SPORT = 1, 2, 4, 5, 7, 8, 9
T_HOLE = 0x80
TERRAIN_TAGS = (
    ("landuse", {"forest": T_FOREST, "meadow": T_GRASS, "grass": T_GRASS, "village_green": T_GRASS,
                 "recreation_ground": T_GRASS, "allotments": T_GRASS, "residential": T_HOMES,
                 "industrial": T_INDUSTRY, "commercial": T_INDUSTRY, "retail": T_INDUSTRY, "railway": T_INDUSTRY,
                 "garages": T_INDUSTRY, "cemetery": T_CEMETERY}),
    ("natural", {"wood": T_FOREST, "grassland": T_GRASS, "heath": T_GRASS, "scrub": T_GRASS,
                 "wetland": T_WETLAND}),
    ("leisure", {"park": T_GRASS, "pitch": T_SPORT, "sports_centre": T_SPORT, "golf_course": T_GRASS}),
)
TERRAIN_FILTER = ["a/%s=%s" % (k, ",".join(sorted(v))) for k, v in TERRAIN_TAGS]
TERRAIN_MIN_M2 = {T_FOREST: 15000, T_GRASS: 15000, T_HOMES: 15000, T_INDUSTRY: 15000, T_WETLAND: 15000,
                  T_CEMETERY: 5000, T_SPORT: 5000}
SPILL_PARTS = 200000      # co tyle kawałków terenu zapis na dysk (ok. 50–100 MB pamięci)
HOLE_MIN_M2 = 15000       # polany mniejsze niż 1,5 ha pomijamy
TERRAIN_TOL = 0.0001      # uproszczenie konturu, ok. 7–11 m

F_ONEWAY, F_UNPAVED, F_TOLL, F_ROUNDABOUT, F_FERRY, F_TUNNEL, F_BRIDGE, F_LIT = 1, 2, 4, 8, 16, 32, 64, 128

UNPAVED = {"unpaved", "gravel", "dirt", "ground", "grass", "sand", "mud", "fine_gravel", "compacted",
           "earth", "cobblestone", "sett", "pebblestone", "woodchips", "rock", "unhewn_cobblestone"}

# Graf tras dla ekranu (nawigacja offline). Prędkości jak domyślne „car_average_speed”
# GraphHoppera; z limitem: 0,9 × limit. Reguły wyboru drogi (warianty, omijanie) stosuje ekran
# tak samo jak dodatek w gh_custom_model (nav.py) – zob. nt1100_jazdy/graf.py.
GRAPH_FORMAT = 1
MAIN_CLASSES = {1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15}
CLASS_KMH = {1: 100, 2: 70, 3: 65, 4: 60, 5: 50, 6: 30, 7: 30, 8: 20, 9: 15, 10: 5,
             11: 70, 12: 65, 13: 60, 14: 50, 15: 40}
G_TOLL, G_TUNNEL, G_ROUNDABOUT, G_REVERSE, G_BRIDGE = 1, 2, 4, 8, 16
S_PAVED, S_GRAVEL, S_DIRT = 0, 1, 2
SURF_GRAVEL = {"gravel", "fine_gravel", "compacted"}
SURF_DIRT = {"unpaved", "dirt", "ground", "grass", "sand", "mud", "earth", "woodchips", "rock"}
R_NO, R_ONLY = 1, 2
EDGE_TMP = struct.Struct("<qqiiiiHBBBBBBqHH")   # krawędź w pliku roboczym (pełne id węzłów)
EDGE_REC = struct.Struct("<bbIHBBBBBBIHH")     # krawędź w pliku .ntg (22 B)
NODE_REC = struct.Struct("<iiII")
RESTR_REC = struct.Struct("<IIIB")
GRAPH_HEAD = struct.Struct("<4sBBhhIIII")

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
        self.waters = bytearray()
        self.nwaters = 0
        self.rivers = bytearray()
        self.nrivers = 0
        self.places = bytearray()
        self.nplaces = 0
        self.terrain = bytearray()
        self.nterrain = 0

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

    @staticmethod
    def _coords(pts):
        plat, plon = int(round(pts[0][0] * 1e6)), int(round(pts[0][1] * 1e6))
        rec = bytearray(struct.pack("<ii", plat, plon))
        for lat, lon in pts[1:]:
            ilat, ilon = int(round(lat * 1e6)), int(round(lon * 1e6))
            rec += varint(zigzag(ilat - plat)) + varint(zigzag(ilon - plon))
            plat, plon = ilat, ilon
        return rec

    def add_water(self, kind, name, ring):
        if len(ring) < 3 or len(ring) > 0xFFFF:
            return
        self.waters += struct.pack("<BHH", kind, self.string(name), len(ring)) + self._coords(ring)
        self.nwaters += 1

    def add_river(self, kind, name, pts):
        if len(pts) < 2 or len(pts) > 0xFFFF:
            return
        self.rivers += struct.pack("<BHH", kind, self.string(name), len(pts)) + self._coords(pts)
        self.nrivers += 1

    def add_terrain(self, kind, ring):
        if len(ring) < 3 or len(ring) > 0xFFFF:
            return
        self.terrain += struct.pack("<BH", kind, len(ring)) + self._coords(ring)
        self.nterrain += 1

    def spill_terrain(self, folder):
        """Teren całej Polski nie mieści się w pamięci kontenera: odkłada go na dysk."""
        if not self.terrain:
            return
        self.terrain_file = os.path.join(folder, "t_%d_%d.bin" % self.key)
        with open(self.terrain_file, "ab") as f:
            f.write(self.terrain)
        self.terrain = bytearray()

    def terrain_bytes(self):
        path = getattr(self, "terrain_file", None)
        if not path:
            return bytes(self.terrain)
        with open(path, "rb") as f:
            return f.read() + bytes(self.terrain)

    def add_place(self, lat, lon, kind, rank, name):
        self.places += struct.pack("<iiBBH", int(round(lat * 1e6)), int(round(lon * 1e6)), kind, rank,
                                   self.string(name))
        self.nplaces += 1

    def add_point(self, nid, lat, lon, kind, limit, name, pair):
        self.points += struct.pack("<IiiBBHH", nid & 0xFFFFFFFF, int(round(lat * 1e6)), int(round(lon * 1e6)),
                                   kind, limit, self.string(name), pair)
        self.npoints += 1

    def data(self):
        extra = self.nwaters or self.nrivers or self.nplaces or self.nterrain
        hflags = (H_EXTRA if extra else 0) | (H_TERRAIN if self.nterrain else 0)
        head = struct.pack("<4sBBhhIIII", b"NTT1", FORMAT, hflags, self.key[0], self.key[1],
                           self.nways, self.npoints, len(self.offsets), len(self.string_bytes))
        out = head + struct.pack("<%dI" % len(self.offsets), *self.offsets) + self.string_bytes + self.ways + self.points
        if extra:
            out += struct.pack("<III", self.nwaters, self.nrivers, self.nplaces) + self.waters + self.rivers + self.places
        if self.nterrain:
            out += struct.pack("<I", self.nterrain) + self.terrain_bytes()
        return bytes(out)

    def write(self, path):
        """Zapisuje kwadrat; zwraca (bajty, crc32)."""
        b = self.data()
        with open(path, "wb") as f:
            f.write(b)
        return len(b), binascii.crc32(b)


def simplify(pts, tol):
    """Douglas–Peucker (stopnie, długość skalowana cos(lat))."""
    if len(pts) < 4:
        return pts
    k = math.cos(math.radians(pts[0][0]))
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ay, ax = pts[a][0], pts[a][1] * k
        by, bx = pts[b][0], pts[b][1] * k
        dy, dx = by - ay, bx - ax
        L = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            py, px = pts[i][0], pts[i][1] * k
            if L == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
                d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > best:
                best, bi = d, i
        if bi > 0 and best > tol * tol:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [p for p, f in zip(pts, keep) if f]


def ring_area_m2(ring):
    k = math.cos(math.radians(ring[0][0])) * 111320.0
    a = 0.0
    for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
        a += (x1 * k) * (y2 * 110540.0) - (x2 * k) * (y1 * 110540.0)
    return abs(a) / 2


def clip_ring(ring, s, w, n, e):
    """Sutherland–Hodgman: wielokąt przycięty do prostokąta."""
    def edge(pts, inside, cut):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        return out

    def at_lat(v):
        return lambda a, b: (v, a[1] + (b[1] - a[1]) * (v - a[0]) / (b[0] - a[0]))

    def at_lon(v):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (v - a[1]) / (b[1] - a[1]), v)
    pts = ring
    for inside, cut in ((lambda p: p[0] >= s, at_lat(s)), (lambda p: p[0] <= n, at_lat(n)),
                        (lambda p: p[1] >= w, at_lon(w)), (lambda p: p[1] <= e, at_lon(e))):
        if not pts:
            break
        pts = edge(pts, inside, cut)
    return pts


def cell_box(key, margin=CLIP_MARGIN):
    return key[0] / CELL - margin, key[1] / CELL - margin, (key[0] + 1) / CELL + margin, (key[1] + 1) / CELL + margin


def box_cells(s, w, n, e):
    for la in range(math.floor(s * CELL), math.floor(n * CELL) + 1):
        for lo in range(math.floor(w * CELL), math.floor(e * CELL) + 1):
            yield la, lo


def line_pieces(pts):
    """Linia pocięta na kawałki w kwadratach (kawałek ma też punkt przed i za kwadratem)."""
    out = {}
    for a, b in zip(pts, pts[1:]):
        for key in box_cells(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
            runs = out.setdefault(key, [])
            if runs and runs[-1][-1] == a:
                runs[-1].append(b)
            else:
                runs.append([a, b])
    return out


def place_rank(kind, population):
    try:
        pop = int(str(population).replace(" ", "").split(";")[0])
    except (TypeError, ValueError):
        pop = {PL_CITY: 100000, PL_TOWN: 10000, PL_VILLAGE: 500}[kind]
    return max(1, min(255, int(round(math.log10(max(pop, 10)) * 40))))


def add_background(src, work, cell):
    """Woda, rzeki i miejscowości (do rysowania tła na ekranie)."""
    t0 = time.time()
    wpbf = os.path.join(work, "woda.pbf")
    run(["osmium", "tags-filter", src] + WATER_FILTER + ["-o", wpbf, "--overwrite"])
    nw = nr = npl = 0
    with subprocess.Popen(["osmium", "export", wpbf, "-f", "geojsonseq", "--add-unique-id=type_id"],
                          stdout=subprocess.PIPE, text=True, bufsize=1 << 20) as exp:
        for line in exp.stdout:
            line = line.lstrip("\x1e")
            if not line.startswith("{"):
                continue
            f = json.loads(line)
            geom, tags = f.get("geometry") or {}, f.get("properties") or {}
            gt = geom.get("type")
            name = tags.get("name") or ""
            if gt == "Point":
                kind = PLACES.get(tags.get("place"))
                if kind and name:
                    lon, lat = geom["coordinates"]
                    cell(cell_of(lat, lon)).add_place(lat, lon, kind, place_rank(kind, tags.get("population")), name)
                    npl += 1
            elif gt == "LineString":
                kind = {"river": R_RIVER, "canal": R_CANAL}.get(tags.get("waterway"))
                if not kind:
                    continue
                pts = simplify([(c[1], c[0]) for c in geom["coordinates"]], WATER_TOL)
                for key, runs in line_pieces(pts).items():
                    for r in runs:
                        cell(key).add_river(kind, name, r)
                nr += 1
            elif gt in ("Polygon", "MultiPolygon"):
                if tags.get("natural") != "water" and tags.get("landuse") != "reservoir":
                    continue
                polys = [geom["coordinates"]] if gt == "Polygon" else geom["coordinates"]
                for poly in polys:
                    for ri, ring in enumerate(poly):
                        pts = [(c[1], c[0]) for c in ring[:-1]]
                        if len(pts) < 3 or ring_area_m2(pts) < WATER_MIN_M2:
                            continue
                        pts = simplify(pts + pts[:1], WATER_TOL)[:-1]
                        if len(pts) < 3:
                            continue
                        lats = [p[0] for p in pts]
                        lons = [p[1] for p in pts]
                        for key in box_cells(min(lats), min(lons), max(lats), max(lons)):
                            part = clip_ring(pts, *cell_box(key))
                            if len(part) >= 3:
                                cell(key).add_water(W_WATER if ri == 0 else W_ISLAND, name if ri == 0 else "", part)
                    nw += 1
    print("tło: wód %d, rzek %d, miejscowości %d (%.0f s)" % (nw, nr, npl, time.time() - t0), flush=True)


def terrain_kind(tags):
    for key, kinds in TERRAIN_TAGS:
        k = kinds.get(tags.get(key))
        if k:
            return k
    return 0


def add_ring(cell, kind, pts):
    """Uproszczony wielokąt przycięty do każdego kwadratu, przez który przechodzi."""
    pts = simplify(pts + pts[:1], TERRAIN_TOL)[:-1]
    if len(pts) < 3:
        return 0
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    n = 0
    for key in box_cells(min(lats), min(lons), max(lats), max(lons)):
        part = clip_ring(pts, *cell_box(key))
        if len(part) >= 3:
            cell(key).add_terrain(kind, part)
            n += 1
    return n


def add_terrain(src, work, cell, cells):
    """Lasy, łąki, osiedla, przemysł, mokradła, cmentarze (mapa w stylu B)."""
    t0 = time.time()
    tpbf = os.path.join(work, "teren.pbf")
    run(["osmium", "tags-filter", src] + TERRAIN_FILTER + ["-o", tpbf, "--overwrite"])
    # indeks węzłów na dysku: mało pamięci także dla całej Polski (silnik tras w tym czasie działa)
    idx = os.path.join(work, "teren.idx")
    na = nh = nparts = spilled = 0
    with subprocess.Popen(["osmium", "export", tpbf, "-f", "geojsonseq", "--geometry-types=polygon",
                           "-i", "sparse_file_array," + idx], stdout=subprocess.PIPE, text=True,
                          bufsize=1 << 20) as exp:
        for line in exp.stdout:
            line = line.lstrip("\x1e")
            if not line.startswith("{"):
                continue
            f = json.loads(line)
            geom, tags = f.get("geometry") or {}, f.get("properties") or {}
            gt = geom.get("type")
            if gt not in ("Polygon", "MultiPolygon"):
                continue
            kind = terrain_kind(tags)
            if not kind:
                continue
            polys = [geom["coordinates"]] if gt == "Polygon" else geom["coordinates"]
            for poly in polys:
                for ri, ring in enumerate(poly):
                    if ri > 0 and kind != T_FOREST:
                        break  # dziury tylko w lasach (polany)
                    pts = [(c[1], c[0]) for c in ring[:-1]]
                    if len(pts) < 3:
                        continue
                    area = ring_area_m2(pts)
                    if area < (HOLE_MIN_M2 if ri else TERRAIN_MIN_M2[kind]):
                        continue
                    nparts += add_ring(cell, (kind | T_HOLE) if ri else kind, pts)
                    if ri:
                        nh += 1
                na += 1
            if nparts - spilled > SPILL_PARTS:
                for c in cells.values():
                    c.spill_terrain(work)
                spilled = nparts
    if exp.returncode:
        raise subprocess.CalledProcessError(exp.returncode, "osmium export (teren)")
    if os.path.exists(idx):
        os.remove(idx)
    print("teren: obszarów %d, polan %d, kawałków w kwadratach %d (%.0f s)" % (na, nh, nparts, time.time() - t0),
          flush=True)


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


def restriction_of(tags, members):
    """Zakaz skrętu z relacji type=restriction: (węzeł, droga_z, droga_do, rodzaj) albo None.
    Tylko „przez węzeł” (via = węzeł) i obowiązujące samochody/motocykle."""
    v = tags.get("restriction:motorcycle") or tags.get("restriction:motorcar") or tags.get("restriction")
    if not v or "motorcar" in (tags.get("except") or "") or "motorcycle" in (tags.get("except") or ""):
        return None
    if v.startswith("no_"):
        kind = R_NO
    elif v.startswith("only_"):
        kind = R_ONLY
    else:
        return None
    fr, via, to = members.get("from", []), members.get("via", []), members.get("to", [])
    if len(fr) != 1 or len(via) != 1 or len(to) != 1 or not via[0].startswith("n") or \
            not fr[0].startswith("w") or not to[0].startswith("w"):
        return None
    return int(via[0][1:]), int(fr[0][1:]), int(to[0][1:]), kind


def surface_kind(tags):
    surf = (tags.get("surface") or "").split(":")[0]
    if surf in SURF_GRAVEL:
        return S_GRAVEL
    if surf in SURF_DIRT:
        return S_DIRT
    return S_PAVED


def edge_kmh(cls, limit, surf):
    v = 0.9 * limit if limit else CLASS_KMH.get(cls, 30)
    if cls == 1:
        v = min(v, 130)
    if surf != S_PAVED:
        v = min(v, 40)
    return max(5, min(140, int(round(v))))


def base_priority(cls, tags):
    """Stały priorytet drogi (%), jak w silnik-tras/motocykl.json."""
    p = 1.0
    if cls in (7, 10):
        p *= 0.6
    if tags.get("tracktype") in ("grade3", "grade4", "grade5"):
        p *= 0.1
    return max(1, int(round(p * 100)))


def graph_edges(f, wid, cls, flags, tags, limit, limit_back, pts, juncs):
    """Krawędzie grafu z jednej drogi (między kolejnymi skrzyżowaniami) do pliku roboczego."""
    surf = surface_kind(tags)
    prio = base_priority(cls, tags)
    gfl = (G_TOLL if flags & F_TOLL else 0) | (G_TUNNEL if flags & F_TUNNEL else 0) | \
          (G_ROUNDABOUT if flags & F_ROUNDABOUT else 0) | (G_BRIDGE if flags & F_BRIDGE else 0)
    kmh = edge_kmh(cls, limit, surf)
    kmh_back = edge_kmh(cls, limit_back or limit, surf)
    js = sorted(juncs)
    n = 0
    for (i0, n0), (i1, n1) in zip(js, js[1:]):
        if n0 == n1 or i1 <= i0:
            continue
        length = 0.0
        for a, b in zip(pts[i0:i1], pts[i0 + 1:i1 + 1]):
            length += dist_m(a, b)
        if length < 0.5:
            continue
        curv = int(round(250 * min(1.0, dist_m(pts[i0], pts[i1]) / length)))
        lm = min(0xFFFF, int(round(length)))
        a, b = pts[i0], pts[i1]
        la, loa, lb, lob = (int(round(a[0] * 1e6)), int(round(a[1] * 1e6)), int(round(b[0] * 1e6)),
                            int(round(b[1] * 1e6)))
        f.write(EDGE_TMP.pack(n0, n1, la, loa, lb, lob, lm, kmh, cls, gfl, surf, prio, curv, wid, i0, i1))
        n += 1
        if not flags & F_ONEWAY:
            f.write(EDGE_TMP.pack(n1, n0, lb, lob, la, loa, lm, kmh_back, cls, gfl | G_REVERSE, surf, prio, curv,
                                  wid, i1, i0))
            n += 1
    return n


def dist_m(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((b[0] - a[0]) * 110540.0, (b[1] - a[1]) * 111320.0 * k)


def build_graph(edges_tmp, restrictions, out):
    """Składa graf z pliku roboczego krawędzi w pliki g_*.ntg (po kwadratach); zwraca część manifestu."""
    t0 = time.time()
    rec = EDGE_TMP.size
    # 1. węzły: id -> kwadrat i numer w kwadracie (posortowane po id, żeby wynik był powtarzalny)
    coords = {}
    with open(edges_tmp, "rb") as f:
        while True:
            chunk = f.read(rec * 20000)
            if not chunk:
                break
            for n0, n1, la, loa, lb, lob, *_ in EDGE_TMP.iter_unpack(chunk):
                coords[n0] = (la << 32) | (loa & 0xFFFFFFFF)   # jedna liczba zamiast pary: mniej pamięci
                coords[n1] = (lb << 32) | (lob & 0xFFFFFFFF)

    def unpack(v):
        lo = v & 0xFFFFFFFF
        return v >> 32, lo - (1 << 32) if lo & 0x80000000 else lo
    by_cell = collections.defaultdict(list)
    for nid, v in coords.items():
        la, lo = unpack(v)
        by_cell[(la // 100000, lo // 100000)].append(nid)
    index = {}
    for key, ids in by_cell.items():
        ids.sort()
        for i, nid in enumerate(ids):
            index[nid] = i
    # 2. krawędzie do kwadratów węzła początkowego: (numer węzła, główna?, rekord)
    edges = collections.defaultdict(bytearray)
    with open(edges_tmp, "rb") as f:
        while True:
            chunk = f.read(rec * 20000)
            if not chunk:
                break
            for n0, n1, la, loa, lb, lob, lm, kmh, cls, gfl, surf, prio, curv, wid, i0, i1 in \
                    EDGE_TMP.iter_unpack(chunk):
                k0 = (la // 100000, loa // 100000)
                k1 = (lb // 100000, lob // 100000)
                dla, dlo = k1[0] - k0[0], k1[1] - k0[1]
                if not (-127 <= dla <= 127 and -127 <= dlo <= 127):
                    continue
                edges[k0] += struct.pack(">IB", index[n0], 0 if cls in MAIN_CLASSES else 1) + \
                    EDGE_REC.pack(dla, dlo, index[n1], lm, kmh, cls, gfl, surf, prio, curv, wid & 0xFFFFFFFF,
                                  i0, i1)
    os.remove(edges_tmp)
    restr = collections.defaultdict(list)
    for via, fr, to, kind in restrictions:
        if via in coords:
            la, lo = unpack(coords[via])
            restr[(la // 100000, lo // 100000)].append(RESTR_REC.pack(index[via], fr & 0xFFFFFFFF,
                                                                      to & 0xFFFFFFFF, kind))
    # 3. zapis po kwadratach
    files = []
    total = 0
    step = 5 + EDGE_REC.size
    for key in sorted(by_cell):
        ids = by_cell[key]
        buf = edges.pop(key, b"")
        recs = sorted(buf[i:i + step] for i in range(0, len(buf), step))
        main = [r for r in recs if r[4] == 0]
        minor = [r for r in recs if r[4] == 1]
        nodes = bytearray()
        im = ib = 0
        for i, nid in enumerate(ids):
            la, lo = unpack(coords[nid])
            nodes += NODE_REC.pack(la, lo, im, ib)
            while im < len(main) and struct.unpack_from(">I", main[im])[0] == i:
                im += 1
            while ib < len(minor) and struct.unpack_from(">I", minor[ib])[0] == i:
                ib += 1
        rs = sorted(restr.get(key, []))
        data = GRAPH_HEAD.pack(b"NTG1", GRAPH_FORMAT, 0, key[0], key[1], len(ids), len(main), len(minor), len(rs)) + \
            bytes(nodes) + b"".join(bytes(r[5:]) for r in main) + b"".join(bytes(r[5:]) for r in minor) + b"".join(rs)
        name = "g_%d_%d.ntg" % key
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
        files.append([name, len(data), binascii.crc32(data)])
        total += len(data)
    print("graf: %d węzłów, %d kwadratów, %.1f MB (%.0f s)" % (len(coords), len(files), total / 1e6,
                                                                time.time() - t0), flush=True)
    return {"format": GRAPH_FORMAT, "bytes": total, "cells": files}


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
    run(["osmium", "tags-filter", src, "w/highway=" + ROAD_FILTER, "r/type=enforcement,restriction"] + NODE_FILTER +
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
    restrictions = []  # (węzeł, droga_z, droga_do, rodzaj) – zakazy skrętu dla grafu tras
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
            if tags.get("type") == "restriction":
                r = restriction_of(tags, members)
                if r:
                    restrictions.append(r)
                continue
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
        # kod 1 = część punktów odcinka leży poza obszarem pliku (np. odcinek na granicy wycinka);
        # takie odcinki odpadną niżej, bo nie mają obu końców
        print("+ osmium getid (odcinki)", flush=True)
        rc = subprocess.run(["osmium", "getid", src, "-i", ids, "-o", secpbf, "--overwrite"]).returncode
        if rc not in (0, 1):
            raise RuntimeError("osmium getid: kod %d" % rc)
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
    edges_tmp = os.path.join(work, "krawedzie.bin")
    etmp = open(edges_tmp, "wb")
    nedges = 0
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
        if refs_ids and len(refs_ids) == len(pts):
            nedges += graph_edges(etmp, wid, cls, flags, tags, limit, limit_back, pts, juncs)
        nways += 1
        npts += len(pts)
        if nways % 100000 == 0:
            print("dróg: %d, punktów dróg: %d (%.0f s)" % (nways, npts, time.time() - t0), flush=True)
    exp.wait()
    opl.kill()
    etmp.close()
    for nid, (kind, limit, pair) in sections.items():
        if nid in section_pts:
            lat, lon = section_pts[nid]
            cell(cell_of(lat, lon)).add_point(nid, lat, lon, kind, limit, "", pair)
            npoints += 1

    # 4. tło dla ekranu: woda, rzeki, miejscowości; teren do mapy w stylu B
    add_background(src, work, cell)
    add_terrain(src, work, cell, cells)

    # 5. zapis kwadratów (pamięć po nich zwalniamy przed składaniem grafu)
    files = []
    total = 0
    lats = [k[0] for k in cells]
    lons = [k[1] for k in cells]
    for key in sorted(cells):
        name = "c_%d_%d.ntt" % key
        n, crc = cells[key].write(os.path.join(out, name))
        files.append([name, n, crc])
        total += n
    cells.clear()

    # 6. graf tras do nawigacji offline (pliki g_*.ntg)
    graph = build_graph(edges_tmp, restrictions, out)
    print("graf tras: %d krawędzi, %d zakazów skrętu" % (nedges, len(restrictions)), flush=True)
    manifest = {
        "format": FORMAT, "wersja": MAP_VERSION, "cell_deg": 1.0 / CELL, "built": time.strftime("%Y-%m-%d"),
        "source": os.path.basename(pbf), "ways": nways, "points": npoints, "bytes": total,
        "bbox": [min(lats) / CELL, min(lons) / CELL, (max(lats) + 1) / CELL, (max(lons) + 1) / CELL] if cells else None,
        "files": files, "graph": graph,
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
    if len(sys.argv) > 1 and sys.argv[1] == "--wersja":
        print(MAP_VERSION)
        return
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    bbox = None
    if "--bbox" in sys.argv:
        bbox = sys.argv[sys.argv.index("--bbox") + 1]
    build(sys.argv[1], sys.argv[2], bbox)


if __name__ == "__main__":
    main()
