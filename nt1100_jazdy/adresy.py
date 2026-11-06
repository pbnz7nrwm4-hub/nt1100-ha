"""Adresy na karcie ekranu (a_index.nta + a_*.nta z silnik-tras/build_map.py): wybór celu bez
internetu – miejscowość, ulica, numer. Wzorzec dla programu ekranu 5" (szuka tak samo), dodatek
używa go do sprawdzenia mapy (/api/nav/adres)."""
import math
import os
import struct

PL_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold(s):
    return " ".join((s or "").translate(PL_FOLD).lower().replace("-", " ").split())


def _str(buf, pos):
    n = buf[pos]
    return buf[pos + 1:pos + 1 + n].decode("utf-8", "replace"), pos + 1 + n


def _dist_km(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((b[0] - a[0]) * 110.54, (b[1] - a[1]) * 111.32 * k)


class Addresses:
    def __init__(self, directory):
        self.dir = directory
        self._index = None
        self._mtime = None

    def available(self):
        return os.path.exists(os.path.join(self.dir, "a_index.nta"))

    def index(self):
        p = os.path.join(self.dir, "a_index.nta")
        try:
            mt = os.path.getmtime(p)
        except OSError:
            return []
        if self._index is not None and self._mtime == mt:
            return self._index
        with open(p, "rb") as f:
            buf = f.read()
        magic, ver, _, n = struct.unpack_from("<4sBBI", buf, 0)
        if magic != b"NTAI" or ver != 1:
            raise ValueError("zły spis adresów")
        pos = 10
        out = []
        for _ in range(n):
            fo, pos = _str(buf, pos)
            name, pos = _str(buf, pos)
            pc, pos = _str(buf, pos)
            lat, lon, cnt, kla, klo, off = struct.unpack_from("<iiIhhI", buf, pos)
            pos += 20
            out.append({"fold": fo, "name": name, "postcode": pc, "lat": lat / 1e6, "lon": lon / 1e6, "count": cnt,
                        "cell": (kla, klo), "off": off})
        self._index, self._mtime = out, mt
        return out

    def towns(self, text, near=None, limit=8):
        """Miejscowości zaczynające się od tekstu (bez ogonków); najpierw dokładne, potem bliższe/większe."""
        q = fold(text)
        if not q:
            return []
        found = [t for t in self.index() if t["fold"].startswith(q)]

        def key(t):
            exact = 0 if t["fold"] == q else 1
            d = _dist_km(near, (t["lat"], t["lon"])) if near else 0
            return (exact, d if near else -t["count"])
        found.sort(key=key)
        return found[:limit]

    def town(self, t):
        """Ulice miejscowości: {nazwa: [(numer, lat, lon), ...]}."""
        p = os.path.join(self.dir, "a_%d_%d.nta" % tuple(t["cell"]))
        with open(p, "rb") as f:
            buf = f.read()
        pos = t["off"]
        _, pos = _str(buf, pos)
        _, pos = _str(buf, pos)
        lat, lon, ns = struct.unpack_from("<iiI", buf, pos)
        pos += 12
        streets = {}
        for _ in range(ns):
            st, pos = _str(buf, pos)
            (nn,) = struct.unpack_from("<I", buf, pos)
            pos += 4
            nums = []
            for _ in range(nn):
                num, pos = _str(buf, pos)
                a, b = struct.unpack_from("<ii", buf, pos)
                pos += 8
                nums.append((num, a / 1e6, b / 1e6))
            streets[st] = nums
        return streets

    def find(self, town, street="", number="", near=None):
        """Adres jak na ekranie: miejscowość (pierwsza pasująca), ulica (początek nazwy), numer.
        Zwraca {"name", "lat", "lon", ...} albo listę podpowiedzi, gdy brakuje dokładności."""
        ts = self.towns(town, near, 8)
        if not ts:
            return {"ok": False, "towns": []}
        t = ts[0]
        streets = self.town(t)
        if not street and not number:
            return {"ok": True, "name": t["name"], "lat": t["lat"], "lon": t["lon"], "postcode": t["postcode"],
                    "towns": [x["name"] + (" " + x["postcode"] if x["postcode"] else "") for x in ts],
                    "streets": sorted(s for s in streets if s)[:20]}
        q = fold(street)
        cands = [s for s in streets if fold(s) == q] or [s for s in streets if fold(s).startswith(q)] or \
            [s for s in streets if q and q in fold(s)]
        if not cands:
            return {"ok": False, "town": t["name"], "streets": sorted(s for s in streets if s)[:20]}
        st = sorted(cands, key=lambda s: (len(s), s))[0]
        nums = streets[st]
        if not number:
            mid = nums[len(nums) // 2]
            return {"ok": True, "name": "%s, %s" % (st, t["name"]), "lat": mid[1], "lon": mid[2],
                    "numbers": [n[0] for n in nums][:50]}
        hit = [n for n in nums if n[0].lower() == number.strip().lower()]
        if not hit:
            return {"ok": False, "town": t["name"], "street": st, "numbers": [n[0] for n in nums][:50]}
        n = hit[0]
        return {"ok": True, "name": "%s %s, %s" % (st or t["name"], n[0], t["name"]) if st else "%s %s" % (t["name"], n[0]),
                "lat": n[1], "lon": n[2]}
