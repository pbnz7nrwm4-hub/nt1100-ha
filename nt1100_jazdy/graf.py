"""Nawigacja offline: graf tras z plików g_*.ntg (silnik-tras/build_map.py) i liczenie trasy
tymi samymi regułami, których dodatek używa w GraphHopperze (nav.Nav.gh_custom_model).

To wzorzec dla programu ekranu 5" (liczy tak samo, tylko w C++): wariant (szybko, lekko,
kręto, bardzo) i omijanie (autostrady, płatne, gruntowe, szutrowe, promy) znaczą offline to
samo co w domu. Dodatek używa go też do porównania z silnikiem tras (/api/nav/offline).

Waga krawędzi jak w GraphHopperze: czas / priorytet + długość × distance_influence / 1000.
Wyszukiwanie: A* z heurystyką odległości w linii prostej; drogi boczne (klasa 7–10) tylko
w pobliżu startu i celu (NEAR_M), dalej same główne – tak liczy też ekran, żeby czytać z karty
mało danych."""
import heapq
import math
import os
import struct

HEAD = struct.Struct("<4sBBhhIIII")
NODE = struct.Struct("<iiII")
EDGE = struct.Struct("<bbIHBBBBBBIHH")
RESTR = struct.Struct("<IIIB")
G_TOLL, G_TUNNEL, G_ROUNDABOUT, G_REVERSE, G_BRIDGE = 1, 2, 4, 8, 16
S_PAVED, S_GRAVEL, S_DIRT = 0, 1, 2
R_NO, R_ONLY = 1, 2
# klasa drogi jak road_class w GraphHopperze: łącznik należy do swojej drogi (motorway_link = MOTORWAY)
ROAD_CLASS = {11: 1, 12: 2, 13: 3, 14: 4, 15: 5}
MAX_KMH = 140.0
NEAR_M = 8000.0        # drogi boczne tylko tyle od startu i celu
SNAP_M = 1500.0        # najdalej tyle od drogi może być start i cel
MAX_SETTLED = 3000000  # zabezpieczenie: tyle węzłów najwyżej

VARIANTS = ("szybko", "lekko", "kreto", "bardzo")
AVOID = ("autostrady", "platne", "gruntowe", "szutrowe", "promy")


def cell_of(lat, lon):
    return math.floor(lat * 10), math.floor(lon * 10)


def dist_m(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((b[0] - a[0]) * 110540.0, (b[1] - a[1]) * 111320.0 * k)


class Edge:
    __slots__ = ("to", "length", "kmh", "cls", "flags", "surf", "prio", "curv", "way", "i0", "i1", "main")

    def __init__(self, to, length, kmh, cls, flags, surf, prio, curv, way, i0, i1, main):
        self.to, self.length, self.kmh, self.cls, self.flags = to, length, kmh, cls, flags
        self.surf, self.prio, self.curv, self.way, self.i0, self.i1, self.main = surf, prio, curv, way, i0, i1, main


class GCell:
    def __init__(self, key, data):
        magic, ver, _, la, lo, nn, nm, nb, nr = HEAD.unpack_from(data, 0)
        if magic != b"NTG1" or ver != 1 or (la, lo) != key:
            raise ValueError("zły plik grafu")
        pos = HEAD.size
        self.key = key
        self.pos = []
        firsts = []
        for i in range(nn):
            lat, lon, fm, fb = NODE.unpack_from(data, pos)
            pos += NODE.size
            self.pos.append((lat / 1e6, lon / 1e6))
            firsts.append((fm, fb))
        recs = []
        for _ in range(nm + nb):
            recs.append(EDGE.unpack_from(data, pos))
            pos += EDGE.size
        self.out = [[] for _ in range(nn)]
        for i, (fm, fb) in enumerate(firsts):
            em = firsts[i + 1][0] if i + 1 < nn else nm
            eb = firsts[i + 1][1] if i + 1 < nn else nb
            for j in list(range(fm, em)) + [nm + j for j in range(fb, eb)]:
                dla, dlo, to, lm, kmh, cls, fl, surf, prio, curv, way, i0, i1 = recs[j]
                self.out[i].append(Edge(((la + dla, lo + dlo), to), lm, kmh, cls, fl, surf, prio, curv, way, i0, i1,
                                        j < nm))
        self.restr = {}
        for _ in range(nr):
            node, fr, to, kind = RESTR.unpack_from(data, pos)
            pos += RESTR.size
            self.restr.setdefault(node, []).append((fr, to, kind))


class Graph:
    """Kwadraty grafu z katalogu mapy, wczytywane na żądanie."""

    def __init__(self, directory, max_cells=2000):
        self.dir = directory
        self.max_cells = max_cells
        self.cells = {}

    def available(self):
        try:
            return any(n.startswith("g_") and n.endswith(".ntg") for n in os.listdir(self.dir))
        except OSError:
            return False

    def cell(self, key):
        if key in self.cells:
            return self.cells[key]
        p = os.path.join(self.dir, "g_%d_%d.ntg" % key)
        c = None
        if os.path.exists(p):
            with open(p, "rb") as f:
                c = GCell(key, f.read())
        if len(self.cells) >= self.max_cells:
            self.cells.clear()
        self.cells[key] = c
        return c

    def node_pos(self, nid):
        c = self.cell(nid[0])
        return c.pos[nid[1]]

    def nearest(self, p, radius_m=SNAP_M):
        """Najbliższy węzeł z wyjazdem (szuka w kwadracie punktu i sąsiednich)."""
        best, bd = None, radius_m
        k = cell_of(*p)
        for dl in (-1, 0, 1):
            for do in (-1, 0, 1):
                c = self.cell((k[0] + dl, k[1] + do))
                if not c:
                    continue
                for i, q in enumerate(c.pos):
                    if not c.out[i]:
                        continue
                    d = dist_m(p, q)
                    if d < bd:
                        best, bd = (c.key, i), d
        return best, bd


def params(variant="szybko", avoid=(), curvy=None):
    """Ustawienia liczenia jak w dodatku: curvy = settings()["curvy"] (suwaki 0–100)."""
    variant = variant if variant in VARIANTS else "szybko"
    p = {"variant": variant, "avoid": set(a for a in (avoid or ()) if a in AVOID)}
    if variant == "szybko":
        p["di"] = 70
    else:
        sl = (curvy or {})[variant]
        p["g"], p["z"] = sl["glowne"] / 100.0, sl["zakrety"] / 100.0
        p["di"] = int(round(70 - 0.65 * sl["dluzej"]))
    return p


def priority(e, p):
    """Priorytet krawędzi: stały (motocykl.json) razy reguły wariantu i omijania (gh_custom_model)."""
    pr = e.prio / 100.0
    rc = ROAD_CLASS.get(e.cls, e.cls)
    if p["variant"] != "szybko":
        g, z = p["g"], p["z"]
        straight = round(1 - 0.65 * z, 3)
        if rc == 1:
            pr *= round(max(0.05, 1 - 0.9 * g), 3)
        elif rc == 2:
            pr *= round(max(0.05, 1 - 0.8 * g), 3)
        elif rc == 3:
            pr *= round(1 - 0.5 * g, 3)
        c = e.curv / 250.0
        if c > 0.97:
            pr *= straight
        elif c > 0.9:
            pr *= min(1.0, round(straight + 0.2, 3))
        if p["variant"] == "bardzo":
            if rc == 4:
                pr *= 0.8
            if e.flags & G_TUNNEL:
                pr *= 0.5
    av = p["avoid"]
    if "gruntowe" in av and (e.cls == 9 or e.surf == S_DIRT):
        pr *= 0.05
    if "szutrowe" in av and e.surf == S_GRAVEL:
        pr *= 0.1
    if "platne" in av and e.flags & G_TOLL:
        pr *= 0.1
    if "autostrady" in av and rc == 1:
        pr = 0.0
    # promy: graf nie ma przepraw promowych, więc offline zawsze omijane
    return pr


def weight(e, p):
    pr = priority(e, p)
    if pr <= 0:
        return None
    return e.length / (e.kmh / 3.6) / pr + e.length * p["di"] / 1000.0


def allowed(cell, node, way_in, e):
    if way_in is None or not cell.restr:
        return True
    for fr, to, kind in cell.restr.get(node, ()):
        if fr != way_in:
            continue
        if kind == R_NO and to == e.way:
            return False
        if kind == R_ONLY and to != e.way:
            return False
    return True


def route(graph, start, goal, variant="szybko", avoid=(), curvy=None):
    """Trasa offline z punktu start do goal (lat, lon). Zwraca dict albo None (nie ma drogi)."""
    p = params(variant, avoid, curvy)
    s, ds = graph.nearest(start)
    t, dt = graph.nearest(goal)
    if s is None or t is None:
        return None
    gpos = graph.node_pos(t)
    spos = graph.node_pos(s)
    hk = 1.0 / (MAX_KMH / 3.6) + p["di"] / 1000.0
    best = {s: 0.0}
    prev = {s: None}
    heap = [(dist_m(spos, gpos) * hk, 0.0, s)]
    settled = set()
    while heap:
        f, g, u = heapq.heappop(heap)
        if u in settled:
            continue
        settled.add(u)
        if u == t or len(settled) > MAX_SETTLED:
            break
        cell = graph.cell(u[0])
        upos = cell.pos[u[1]]
        near = dist_m(upos, spos) < NEAR_M or dist_m(upos, gpos) < NEAR_M
        way_in = prev[u][1].way if prev[u] else None
        for e in cell.out[u[1]]:
            if not e.main and not near:
                continue
            if not allowed(cell, u[1], way_in, e):
                continue
            w = weight(e, p)
            if w is None:
                continue
            ng = g + w
            if ng < best.get(e.to, float("inf")):
                tc = graph.cell(e.to[0])
                if tc is None:
                    continue
                best[e.to] = ng
                prev[e.to] = (u, e)
                heapq.heappush(heap, (ng + dist_m(tc.pos[e.to[1]], gpos) * hk, ng, e.to))
    if t not in settled:
        return None
    path = []
    v = t
    while prev[v]:
        u, e = prev[v]
        path.append((u, e))
        v = u
    path.reverse()
    length = sum(e.length for _, e in path)
    secs = sum(e.length / (e.kmh / 3.6) for _, e in path)
    return {"edges": path, "km": round(length / 1000.0, 2), "min": round(secs / 60.0, 1), "nodes": len(settled),
            "snap_m": (round(ds), round(dt)), "weight": round(best[t], 1), "variant": p["variant"],
            "avoid": sorted(p["avoid"])}


def geometry(graph, ntt_map, r):
    """Punkty trasy z kształtu dróg w kwadratach .ntt (ntt.Map); bez mapy – same węzły."""
    pts = []
    for u, e in r["edges"]:
        seg = None
        if ntt_map is not None:
            ways = None
            for key in (u[0],) + tuple((u[0][0] + a, u[0][1] + b) for a in (-1, 0, 1) for b in (-1, 0, 1)):
                c = ntt_map.cell(key)
                if not c:
                    continue
                ways = [w for w in c[0] if (w.id & 0xFFFFFFFF) == e.way]
                if ways:
                    break
            if ways:
                w = ways[0]
                if e.i0 <= e.i1:
                    seg = w.pts[e.i0:e.i1 + 1]
                else:
                    seg = w.pts[e.i1:e.i0 + 1][::-1]
        if not seg:
            seg = [graph.node_pos(u), graph.node_pos(e.to)]
        if pts and pts[-1] == seg[0]:
            seg = seg[1:]
        pts.extend(seg)
    return pts
