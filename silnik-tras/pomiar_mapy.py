#!/usr/bin/env python3
"""Pomiar kompletności mapy ekranu (decyzja Adriana 9.11, pkt 9 / a13): ile fotoradarów i odcinkowych pomiarów
prędkości ma nasza mapa (z OSM) i ile skrzyżowań ma pasy ruchu i kierunki z drogowskazów.

Czyta gotową mapę (katalog z c_*.ntt i n_*.ntn, także w podfolderach m6), niczego nie zmienia.

    python3 pomiar_mapy.py KATALOG_MAPY [--oficjalne plik.csv] [--json wynik.json]

--oficjalne: lista urządzeń z innego źródła (np. CANARD/GITD), CSV „lat;lon;rodzaj” (rodzaj: fotoradar albo
odcinkowy; separator ; albo ,). Wtedy pomiar podaje, ile z nich ma nasza mapa w promieniu 150 m (odcinkowy:
początek albo koniec). Bez listy: tylko liczby z naszej mapy (źródła oficjalnego tu nie zgadujemy).
"""
import argparse
import csv
import json
import math
import os
import struct

MATCH_M = 150.0
P_CAMERA, P_SECTION_START, P_SECTION_END = 1, 2, 3   # jak w ntt.py / build_map.py


def dist_m(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return 6371000.0 * math.hypot(x, math.radians(b[0] - a[0]))


def _varint(buf, pos):
    while True:
        b = buf[pos]
        pos += 1
        if not b & 0x80:
            return pos


def cell_points(path):
    """(rodzaj, lat, lon) punktów kwadratu c_*.ntt (format jak ntt.py dodatku; skrypt bez dodatku, do kontenera)."""
    with open(path, "rb") as f:
        buf = f.read()
    magic, ver, _, _, _, nways, npoints, nstr, strbytes = struct.unpack_from("<4sBBhhIIII", buf, 0)
    if magic != b"NTT1" or ver != 1:
        return []
    pos = struct.calcsize("<4sBBhhIIII") + 4 * nstr + strbytes
    for _ in range(nways):
        npts, njunc = struct.unpack_from("<HH", buf, pos + 12)
        pos += 24
        for _ in range(2 * (npts - 1)):
            pos = _varint(buf, pos)
        pos += 6 * njunc
    out = []
    for _ in range(npoints):
        _, lat, lon, kind = struct.unpack_from("<IiiB", buf, pos)
        pos += 18
        out.append((kind, lat / 1e6, lon / 1e6))
    return out


def files(root, prefix, ext):
    for d, _, names in os.walk(root):
        for n in names:
            if n.startswith(prefix) and n.endswith(ext):
                yield os.path.join(d, n)


def signs_of(path):
    """(znaki, z pasami, z kierunkami, z numerami dróg, zjazdy) z pliku n_*.ntn (opis formatu: build_map.py)."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"NTN1":
        return None
    nstr, nbytes = struct.unpack_from("<II", b, 10)
    pos = 18 + 4 * nstr + nbytes
    (nsig,) = struct.unpack_from("<I", b, pos)
    pos += 4
    lanes = dest = refs = 0
    for _ in range(nsig):
        _, _, ln, de, rf = struct.unpack_from("<IBHHH", b, pos)
        pos += 11
        lanes += ln != 0xFFFF
        dest += de != 0xFFFF
        refs += rf != 0xFFFF
    (nex,) = struct.unpack_from("<I", b, pos)
    return nsig, lanes, dest, refs, nex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mapa")
    ap.add_argument("--oficjalne")
    ap.add_argument("--json")
    a = ap.parse_args()
    cams, starts, ends = [], [], []
    cells = 0
    for p in files(a.mapa, "c_", ".ntt"):
        cells += 1
        for kind, lat, lon in cell_points(p):
            if kind == P_CAMERA:
                cams.append((lat, lon))
            elif kind == P_SECTION_START:
                starts.append((lat, lon))
            elif kind == P_SECTION_END:
                ends.append((lat, lon))
    sg = [0, 0, 0, 0, 0]
    ncells = 0
    for p in files(a.mapa, "n_", ".ntn"):
        r = signs_of(p)
        if r:
            ncells += 1
            sg = [x + y for x, y in zip(sg, r)]
    out = {"kwadraty_c": cells, "fotoradary": len(cams), "odcinkowe_poczatki": len(starts), "odcinkowe_konce": len(ends),
           "kwadraty_n": ncells, "znaki": sg[0], "znaki_z_pasami": sg[1], "znaki_z_kierunkami": sg[2],
           "znaki_z_numerami": sg[3], "zjazdy_z_numerem": sg[4]}
    if a.oficjalne:
        grid = {}
        for kind, lst in (("fotoradar", cams), ("odcinkowy", starts + ends)):
            for lat, lon in lst:
                grid.setdefault((kind, round(lat * 100), round(lon * 100)), []).append((lat, lon))
        total = {"fotoradar": 0, "odcinkowy": 0}
        found = {"fotoradar": 0, "odcinkowy": 0}
        missing = []
        with open(a.oficjalne, encoding="utf-8-sig") as f:
            sample = f.read(2048)
            f.seek(0)
            rd = csv.reader(f, delimiter=";" if sample.count(";") >= sample.count(",") else ",")
            for row in rd:
                try:
                    lat, lon = float(row[0].replace(",", ".")), float(row[1].replace(",", "."))
                except (ValueError, IndexError):
                    continue  # nagłówek albo pusty wiersz
                kind = "odcinkowy" if len(row) > 2 and "odc" in row[2].lower() else "fotoradar"
                total[kind] += 1
                hit = False
                ci, cj = round(lat * 100), round(lon * 100)
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        for q in grid.get((kind, ci + di, cj + dj), ()):
                            if dist_m((lat, lon), q) <= MATCH_M:
                                hit = True
                if hit:
                    found[kind] += 1
                else:
                    missing.append([lat, lon, kind])
        out["oficjalne"] = {k: {"wszystkie": total[k], "na_mapie": found[k],
                                "procent": round(100.0 * found[k] / total[k], 1) if total[k] else None} for k in total}
        out["brakujace"] = missing[:500]
    s = json.dumps(out, ensure_ascii=False, indent=1)
    print(s)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            f.write(s)


if __name__ == "__main__":
    main()
