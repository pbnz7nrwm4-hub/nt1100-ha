"""Serwer mapy dla dodatku Home Assistant.

- /mapa/...                 pliki mapy na kartę ekranu (katalog www/mapa)
- /kafelki/info.json        czy jest mapa do przeglądarki (www/kafelki.pmtiles)
- /kafelki/Z/X/Y.pbf        kafelek wektorowy z kafelki.pmtiles (skompresowany gzip)
- /dem/Z/X/Y.png            wysokości do cieniowania gór (dem.py)

Użycie: mapa-serwer.py KATALOG PORT"""
import gzip
import json
import os
import re
import struct
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


# ---------------------------------------------------------------- PMTiles v3 (tylko odczyt)

def tile_id(z, x, y):
    """Numer kafelka w krzywej Hilberta (specyfikacja PMTiles v3)."""
    acc = ((1 << (2 * z)) - 1) // 3
    n = 1 << z
    d = 0
    s = n >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        s >>= 1
    return acc + d


def _varint(b, i):
    v = shift = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << shift
        if c < 0x80:
            return v, i
        shift += 7


def _directory(raw, compression):
    if compression == 2:
        raw = gzip.decompress(raw)
    n, i = _varint(raw, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        v, i = _varint(raw, i)
        last += v
        ids.append(last)
    for _ in range(n):
        v, i = _varint(raw, i)
        runs.append(v)
    for _ in range(n):
        v, i = _varint(raw, i)
        lens.append(v)
    for k in range(n):
        v, i = _varint(raw, i)
        offs.append(offs[k - 1] + lens[k - 1] if v == 0 and k > 0 else v - 1)
    return ids, runs, lens, offs


class PMTiles:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.lock = threading.Lock()
        h = self._read(0, 127)
        if h[:7] != b"PMTiles" or h[7] != 3:
            raise ValueError("to nie jest plik PMTiles v3")
        (self.root_off, self.root_len, self.meta_off, self.meta_len, self.leaf_off, self.leaf_len,
         self.data_off, self.data_len) = struct.unpack_from("<8Q", h, 8)
        self.internal, self.tile_comp, self.tile_type, self.minzoom, self.maxzoom = h[97], h[98], h[99], h[100], h[101]
        w, s, e, n = struct.unpack_from("<4i", h, 102)
        self.bounds = [w / 1e7, s / 1e7, e / 1e7, n / 1e7]
        self.mtime = os.path.getmtime(path)
        self.cache = {}
        self.root = _directory(self._read(self.root_off, self.root_len), self.internal)

    def _read(self, off, n):
        with self.lock:
            self.f.seek(off)
            return self.f.read(n)

    def _leaf(self, off, n):
        d = self.cache.get(off)
        if d is None:
            if len(self.cache) > 256:
                self.cache.clear()
            d = self.cache[off] = _directory(self._read(self.leaf_off + off, n), self.internal)
        return d

    def get(self, z, x, y):
        """Bajty kafelka (tak jak w pliku, zwykle gzip) albo None."""
        if z < self.minzoom or z > self.maxzoom or x >= (1 << z) or y >= (1 << z):
            return None
        tid = tile_id(z, x, y)
        d = self.root
        for _ in range(4):
            ids, runs, lens, offs = d
            lo, hi = 0, len(ids) - 1
            k = -1
            while lo <= hi:
                mid = (lo + hi) // 2
                if ids[mid] <= tid:
                    k = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            if k < 0:
                return None
            if runs[k] == 0:
                d = self._leaf(offs[k], lens[k])
                continue
            if tid < ids[k] + runs[k]:
                return self._read(self.data_off + offs[k], lens[k])
            return None
        return None

    def info(self):
        return {"ok": True, "built": time.strftime("%Y-%m-%d", time.localtime(self.mtime)),
                "minzoom": self.minzoom, "maxzoom": self.maxzoom, "bounds": self.bounds,
                "gzip": self.tile_comp == 2}


# ---------------------------------------------------------------- serwer

TILE = re.compile(r"^/kafelki/(\d{1,2})/(\d{1,5})/(\d{1,5})\.pbf$")
_PM = {"obj": None}


def pmtiles(root):
    """Otwarty plik kafelków; po podmianie pliku (co miesiąc) otwiera nowy."""
    p = os.path.join(root, "kafelki.pmtiles")
    if not os.path.exists(p):
        _PM["obj"] = None
        return None
    o = _PM["obj"]
    if o is None or o.mtime != os.path.getmtime(p):
        try:
            o = _PM["obj"] = PMTiles(p)
        except Exception:
            o = _PM["obj"] = None
    return o


class H(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        if not getattr(self, "_cache_set", False):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self._cache_set = True
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/kafelki/info.json":
            pm = pmtiles(self.directory)
            info = pm.info() if pm else {"ok": False}
            info["dem"] = os.path.isdir(os.path.join(self.directory, "dem", "12"))
            body = json.dumps(info).encode()
            return self._send(200, body, "application/json")
        m = TILE.match(path)
        if m:
            pm = pmtiles(self.directory)
            if pm is None:
                return self._send(404, b"", "text/plain")
            data = pm.get(*(int(v) for v in m.groups()))
            if not data:
                return self._send(204, b"", "application/x-protobuf", {"Cache-Control": "max-age=86400"})
            extra = {"Cache-Control": "max-age=86400"}
            if pm.tile_comp == 2:
                extra["Content-Encoding"] = "gzip"
            return self._send(200, data, "application/x-protobuf", extra)
        return super().do_GET()


if __name__ == "__main__":
    root, port = sys.argv[1], int(sys.argv[2])
    os.makedirs(os.path.join(root, "mapa"), exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", port), partial(H, directory=root)).serve_forever()
