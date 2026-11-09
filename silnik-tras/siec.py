"""Sieć przeskoków do liczenia długich tras na ekranie (ekran 2.8.0, decyzje Adriana 9.11 k2–k5).

Tak robi to OsmAnd (Highway Hierarchy, docs.osmand.net/blog/fast-routing): mapa jest podzielona
na obszary, a przy budowie mapy liczy się z góry przejazdy przez każdy obszar od wjazdu do wyjazdu.
U nas obszar = kwadrat grafu 0,1° (g_<lat10>_<lon10>.ntg). Ekran liczy dokładnie tylko 8 km wokół
startu i celu (wszystkie drogi), a po drodze skacze po gotowych przeskokach i na koniec rozwija
tylko kwadraty na znalezionej trasie. Prototyp 9.11 (200 losowych tras po Polsce): ta sama trasa
co pełne A*, ekran czyta 5–15 razy mniej (Katowice → Białystok 10,9 MB zamiast 89 MB).

Węzły sieci w kwadracie:
- wjazd  = węzeł, do którego wchodzi droga główna z innego kwadratu,
- wyjazd = węzeł, z którego droga główna wychodzi do innego kwadratu.
Łuki węzła: przeskoki wjazd → każdy osiągalny wyjazd tego samego kwadratu (koszt najtańszej drogi
po drogach głównych w środku kwadratu, z zakazami skrętu jak na ekranie) i krawędzie wyjazd → wjazd
sąsiedniego kwadratu.

Koszt krawędzi = ta sama waga co na ekranie (src/core/groute.cpp: priority/weight, czyli reguły
dodatku nav.gh_custom_model). Osobna sieć na każdy typ trasy (k3): PROFILES niżej.

Pliki: jeden na blok 1° i typ trasy, np. sa_490_190.nto = kwadraty 49,0–49,9° N, 19,0–19,9° E
(ekran: /m6/sa/490/sa_490_190.nto). Mniej plików do synchronizacji niż plik na kwadrat.

Format .nto (little endian):
  nagłówek 24 B: "NTO1", wersja u8 (1), typ trasy u8, wariant u8, omijanie u8 (bity), siły omijania 4 × u8,
                suwaki (główne, zakręty, dłużej) 3 × u8, 0 u8, lat10 i16, lon10 i16 (róg SW bloku), 0 × 4
  spis 100 × (offset u32, długość u32): kwadrat (lat10 + i, lon10 + j) pod numerem i*10 + j; długość 0 = brak
  rekord kwadratu: liczba węzłów sieci n u32, przeskoków ms u32, krawędzi między kwadratami mx u32,
                   liczba wszystkich węzłów grafu kwadratu u32, cechy dróg głównych kwadratu u32 (CECHY),
                   n × numer węzła w grafie kwadratu u32 (rosnąco), n × położenie (lat, lon) i32 × 1e6,
                   (n + 1) × pierwszy przeskok u32, (n + 1) × pierwsza krawędź u32,
                   ms × przeskok 7 B: numer węzła sieci tego kwadratu u16, koszt f32 (jednostki wagi ekranu),
                                      cechy dróg na przeskoku u8 (CECHY),
                   mx × krawędź 15 B: dlat i8, dlon i8, węzeł docelowy u32 (numer w grafie kwadratu docelowego),
                                      koszt f32, droga u32, cechy u8
"""
import binascii
import collections
import heapq
import math
import os
import struct
import sys
import time

HEAD = struct.Struct("<4sBBhhIIII")
NODE = struct.Struct("<iiII")
EDGE = struct.Struct("<bbIHBBBBBBIHH")
RESTR = struct.Struct("<IIIB")
# nagłówek pliku sieci: "NTO1", wersja, typ trasy, wariant, omijanie (bity), siły omijania ×4, suwaki ×3, lat10, lon10
OHEAD = struct.Struct("<4sBBBB4B3Bxhh4x")
ARC = struct.Struct("<bbIfIB")
SC = struct.Struct("<HfB")
FORMAT = 1

G_TOLL, G_TUNNEL = 1, 2
S_DIRT, S_GRAVEL = 2, 1
ROAD_CLASS = {11: 1, 12: 2, 13: 3, 14: 4, 15: 5}   # łącznik należy do swojej drogi (jak roadClass w groute.cpp)

# Typy tras (k3, Adrian 9.11: „Wszystko rób”, kolejno: auto z autostradami, bez autostrad, moto).
# variant jak RouteVariant ekranu: 1 szybko, 3 kręto; suwaki „kręto” = domyślne dodatku (nav.CURVY_DEFAULT).
# Omijanie jak ustawienie ekranu zmierzone 9.11 (log: „bity 6, siły 0/4/4/0”): płatne i gruntowe, siła 4.
# avoid: bity jak ekran (autostrady 1, płatne 2, gruntowe 4, szutrowe 8); lvl: siły 0–5 w tej samej kolejności
# (0 = stały współczynnik sprzed 2.4.0). Ekran sam wybiera sieć, która pasuje do jego ustawień (nagłówek pliku):
# ta sama albo omijająca mniej – wtedy przelicza na miejscu tylko przeskoki po omijanych drogach.
# "s0" (szybko, bez omijania) pasuje do każdego ustawienia „szybko” z autostradami (najwolniejsza ścieżka).
PROFILES = {
    "sa": {"nazwa": "szybko z autostradami, omija płatne i gruntowe", "variant": 1, "avoid": 6, "lvl": (0, 4, 4, 0)},
    "sb": {"nazwa": "szybko bez autostrad, omija płatne i gruntowe", "variant": 1, "avoid": 7, "lvl": (0, 4, 4, 0)},
    "sk": {"nazwa": "kręto (motocykl), omija płatne i gruntowe", "variant": 3, "avoid": 6, "lvl": (0, 4, 4, 0),
           "suwaki": (90, 80, 60)},
    "s0": {"nazwa": "szybko, bez omijania", "variant": 1, "avoid": 0, "lvl": (0, 0, 0, 0)},
}
PROFILE_NO = {"sa": 1, "sb": 2, "sk": 3, "s0": 4}
K_LVL = (1, 0.8, 0.5, 0.25, 0.1, 0.02)
# Cechy dróg (te same bity co omijanie na ekranie: autostrady 1, płatne 2, gruntowe 4, szutrowe 8): każdy przeskok
# i każda krawędź między kwadratami wie, po jakich drogach idzie. Sieć liczona jest bez omijania; omijanie tylko
# podnosi wagi (albo zabrania drogi), więc przeskok bez omijanej drogi zostaje najtańszy i dokładny. Ekran z innym
# omijaniem (Adrian 9.11: szybko, omijaj płatne i gruntowe) przelicza na miejscu tylko przeskoki z taką drogą –
# wynik ten sam co pełne liczenie, bez osobnej sieci na każde ustawienie.
F_MOTORWAY, F_TOLL, F_DIRT, F_GRAVEL = 1, 2, 4, 8


def feature(e):
    cls, fl, surf = e[5], e[6], e[7]
    f = 0
    if ROAD_CLASS.get(cls, cls) == 1:
        f |= F_MOTORWAY
    if fl & G_TOLL:
        f |= F_TOLL
    if cls == 9 or surf == S_DIRT:
        f |= F_DIRT
    if surf == S_GRAVEL:
        f |= F_GRAVEL
    return f


def features(edges):
    f = 0
    for e in edges:
        f |= feature(e)
    return f


def r3(v):
    """std::round(v * 1000) / 1000 z ekranu (zaokrąglenie połówek od zera, nie bankierskie)."""
    x = v * 1000.0
    return (math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)) / 1000.0


def prm(pr):
    p = {"variant": pr["variant"], "avoid": pr["avoid"], "lvl": tuple(min(5, x) for x in pr.get("lvl", (0, 0, 0, 0))),
         "g": 0.0, "z": 0.0, "di": 70}
    if pr["variant"] != 1:
        main, bends, longer = pr["suwaki"]
        p["g"], p["z"] = main / 100.0, bends / 100.0
        x = 70 - 0.65 * longer
        p["di"] = int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))
    return p


def weight(e, p):
    """Waga krawędzi jak nv::weight w groute.cpp; None = krawędź zakazana w tym typie trasy.
    e = (dlat, dlon, to, lengthM, kmh, cls, flags, surf, prio, curv, way, i0, i1)."""
    _, _, _, lm, kmh, cls, fl, surf, prio, curv, _, _, _ = e
    pr = prio / 100.0
    rc = ROAD_CLASS.get(cls, cls)
    if p["variant"] != 1:
        straight = r3(1 - 0.65 * p["z"])
        if rc == 1:
            pr *= r3(max(0.05, 1 - 0.9 * p["g"]))
        elif rc == 2:
            pr *= r3(max(0.05, 1 - 0.8 * p["g"]))
        elif rc == 3:
            pr *= r3(1 - 0.5 * p["g"])
        c = curv / 250.0
        if c > 0.97:
            pr *= straight
        elif c > 0.9:
            pr *= min(1.0, r3(straight + 0.2))
        if p["variant"] == 4:
            if rc == 4:
                pr *= 0.8
            if fl & G_TUNNEL:
                pr *= 0.5
    lvl, av = p["lvl"], p["avoid"]

    def f(bit, legacy):
        return K_LVL[lvl[bit]] if lvl[bit] else legacy
    if av & 4 and (cls == 9 or surf == S_DIRT):
        pr *= f(2, 0.05)
    if av & 8 and surf == S_GRAVEL:
        pr *= f(3, 0.1)
    if av & 2 and fl & G_TOLL:
        pr *= f(1, 0.1)
    if av & 1 and rc == 1:
        pr = pr * K_LVL[lvl[0]] if 0 < lvl[0] < 5 else 0.0
    if pr <= 0:
        return None
    return lm / (max(kmh, 5) / 3.6) / pr + lm * p["di"] / 1000.0


def read_cell(path):
    """Drogi główne kwadratu: (lat10, lon10), węzły [(lat, lon, fm, fb)], krawędzie główne węzłów, zakazy {węzeł: [...]}"""
    with open(path, "rb") as f:
        d = f.read()
    magic, ver, _, la, lo, nn, nm, nb, nr = HEAD.unpack_from(d, 0)
    if magic != b"NTG1" or ver != 1:
        raise ValueError("zły plik grafu: " + path)
    nodes = list(NODE.iter_unpack(d[HEAD.size:HEAD.size + nn * NODE.size]))
    e0 = HEAD.size + nn * NODE.size
    main = list(EDGE.iter_unpack(d[e0:e0 + nm * EDGE.size]))
    out = [None] * nn
    for i in range(nn):
        a = nodes[i][2]
        b = nodes[i + 1][2] if i + 1 < nn else nm
        if b > a:
            out[i] = main[a:b]
    r0 = e0 + (nm + nb) * EDGE.size
    restr = collections.defaultdict(list)
    for node, fr, to, kind in RESTR.iter_unpack(d[r0:r0 + nr * RESTR.size]):
        restr[node].append((fr, to, kind))
    return (la, lo), nodes, out, restr


def allowed(restr, node, way_in, way):
    if way_in is None:
        return True
    for fr, to, kind in restr.get(node, ()):
        if fr != way_in:
            continue
        if kind == 1 and to == way:
            return False
        if kind == 2 and to != way:
            return False
    return True


def shortcuts(out, restr, ws, entry, exits):
    """Dijkstra z wjazdu po drogach głównych w środku kwadratu: {wyjazd: (koszt, cechy dróg na drodze)}.
    ws[u] = wagi krawędzi out[u] w tym typie trasy (None = zakazana). Zakazy skrętu jak na ekranie
    (droga, którą się przyjechało do węzła); na samym wjeździe drogi przyjazdu nie znamy."""
    best = {entry: 0.0}
    way_in = {entry: None}
    feat = {entry: 0}
    done = set()
    res = {}
    left = len(exits)
    q = [(0.0, entry)]
    while q:
        g, u = heapq.heappop(q)
        if u in done:
            continue
        done.add(u)
        if u in exits:
            res[u] = (g, feat[u])
            left -= 1
            if left == 0:
                break
        eu = out[u]
        if not eu:
            continue
        wi = way_in[u]
        wu = ws[u]
        for k in range(len(eu)):
            e = eu[k]
            if e[0] or e[1]:
                continue
            w = wu[k]
            if w is None:
                continue
            if restr and wi is not None and not allowed(restr, u, wi, e[10]):
                continue
            v = e[2]
            ng = g + w
            if ng < best.get(v, 1e30):
                best[v] = ng
                way_in[v] = e[10]
                feat[v] = feat[u] | feature(e)
                heapq.heappush(q, (ng, v))
    return res


def graph_files(directory):
    """g_*.ntg w katalogu mapy (płasko, jak build_map) albo w układzie karty m6/g/<lat>/."""
    found = {}
    for root, _, names in os.walk(directory):
        for n in names:
            if n.startswith("g_") and n.endswith(".ntg"):
                a, b = n[2:-4].split("_")
                found[(int(a), int(b))] = os.path.join(root, n)
    return found


def build(directory, out_dir=None, profiles=None, log=lambda m: print(m, flush=True)):
    """Liczy sieci przeskoków z grafu w directory, zapisuje pliki .nto do out_dir; zwraca część manifestu."""
    t0 = time.time()
    out_dir = out_dir or directory
    names = list(profiles or PROFILES)
    prms = {n: prm(PROFILES[n]) for n in names}
    files = graph_files(directory)
    # 1. wyjazdy i krawędzie między kwadratami; wjazdy kwadratów sąsiednich
    cross = {n: {} for n in names}                       # profil -> kwadrat -> {wyjazd: [(dla, dlo, to, w, way)]}
    entries = {n: collections.defaultdict(set) for n in names}
    for key, path in files.items():
        _, gnodes, out, _ = read_cell(path)
        nn = len(gnodes)
        for n in names:
            p = prms[n]
            cx = {}
            for u in range(nn):
                eu = out[u]
                if not eu:
                    continue
                for e in eu:
                    if not (e[0] or e[1]):
                        continue
                    tk = (key[0] + e[0], key[1] + e[1])
                    if tk not in files:
                        continue
                    w = weight(e, p)
                    if w is None:
                        continue
                    cx.setdefault(u, []).append((e[0], e[1], e[2], w, e[10], feature(e)))
                    entries[n][tk].add(e[2])
            if cx:
                cross[n][key] = cx
    log("sieć: krawędzie między kwadratami policzone (%.0f s)" % (time.time() - t0))
    # 2. przeskoki w kwadratach
    recs = {n: {} for n in names}
    stats = {n: [0, 0, 0, 0] for n in names}   # węzły, przeskoki, krawędzie między kwadratami, przeskoki z płatną/gruntową/szutrem
    for key, path in files.items():
        _, gnodes, out, restr = read_cell(path)
        nn = len(gnodes)
        feat = 0
        for eu in out:
            if eu:
                feat |= features(eu)
        for n in names:
            p = prms[n]
            cx = cross[n].get(key, {})
            ent = entries[n].get(key, set())
            nodes = sorted(set(cx) | ent)
            if not nodes:
                continue
            exits = set(cx)
            ws = [None] * nn
            if exits and ent:
                for u in range(nn):
                    if out[u]:
                        ws[u] = [weight(e, p) for e in out[u]]
            if len(nodes) > 65535:
                raise ValueError("za dużo węzłów sieci w kwadracie %s" % (key,))
            local = {u: i for i, u in enumerate(nodes)}
            scs, xs = [], []
            fsc, fx = [], []
            for u in nodes:
                fsc.append(len(scs))
                fx.append(len(xs))
                if u in ent and exits:
                    sc = shortcuts(out, restr, ws, u, exits)
                    for x in sorted(sc):
                        if x != u:
                            scs.append((local[x], sc[x][0], sc[x][1]))
                for a in cx.get(u, ()):
                    xs.append(a)
            fsc.append(len(scs))
            fx.append(len(xs))
            stats[n][0] += len(nodes)
            stats[n][1] += len(scs)
            stats[n][2] += len(xs)
            stats[n][3] += sum(1 for a in scs if a[2] & (F_TOLL | F_DIRT | F_GRAVEL))
            rec = bytearray(struct.pack("<IIIII", len(nodes), len(scs), len(xs), nn, feat))
            rec += struct.pack("<%dI" % len(nodes), *nodes)
            for u in nodes:
                rec += struct.pack("<ii", gnodes[u][0], gnodes[u][1])
            rec += struct.pack("<%dI" % len(fsc), *fsc)
            rec += struct.pack("<%dI" % len(fx), *fx)
            for a in scs:
                rec += SC.pack(*a)
            for a in xs:
                rec += ARC.pack(*a)
            recs[n][key] = bytes(rec)
    # 3. pliki po blokach 1°
    cells = []
    total = 0
    for n in names:
        blocks = collections.defaultdict(dict)
        for key, rec in recs[n].items():
            blocks[(key[0] // 10 * 10, key[1] // 10 * 10)][key] = rec
        for bk in sorted(blocks):
            index = bytearray()
            body = bytearray()
            base = OHEAD.size + 100 * 8
            for i in range(10):
                for j in range(10):
                    rec = blocks[bk].get((bk[0] + i, bk[1] + j))
                    if rec:
                        index += struct.pack("<II", base + len(body), len(rec))
                        body += rec
                    else:
                        index += struct.pack("<II", 0, 0)
            pf = PROFILES[n]
            data = OHEAD.pack(b"NTO1", FORMAT, PROFILE_NO[n], pf["variant"], pf["avoid"], *pf["lvl"],
                              *pf.get("suwaki", (0, 0, 0)), bk[0], bk[1]) + bytes(index) + bytes(body)
            name = "%s_%d_%d.nto" % (n, bk[0], bk[1])
            with open(os.path.join(out_dir, name), "wb") as f:
                f.write(data)
            cells.append([name, len(data), binascii.crc32(data)])
            total += len(data)
        log("sieć %s (%s): %d węzłów, %d przeskoków (z drogą płatną, gruntową albo szutrem %d), %d krawędzi między kwadratami, %d plików" %
            (n, PROFILES[n]["nazwa"], stats[n][0], stats[n][1], stats[n][3], stats[n][2], len(blocks)))
    log("sieć przeskoków: %.1f MB, %.0f s" % (total / 1e6, time.time() - t0))
    return {"format": FORMAT, "bytes": total, "cells": cells,
            "profiles": {n: PROFILES[n]["nazwa"] for n in names}}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("użycie: siec.py <katalog z g_*.ntg> [katalog wyjściowy] [sa,sb,sk]")
        sys.exit(2)
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
          sys.argv[3].split(",") if len(sys.argv) > 3 else None)
