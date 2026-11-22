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
import shutil
import struct
import subprocess
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


def _plik_info(p):
    try:
        st = os.stat(p)
        return {"bajty": st.st_size, "t": int(st.st_mtime)}
    except OSError:
        return None


def info_mapy(root):
    """Tylko odczyt: co jest w kontenerze (wersja mapy, wiek danych OSM, rozmiar, wolne miejsce, stan budowy)."""
    out = {"t": int(time.time()), "mapa": None, "osm": None, "kafelki": None, "stan": None}
    try:
        with open(os.path.join(root, "mapa", "manifest.json")) as f:
            m = json.load(f)
        out["mapa"] = {k: m.get(k) for k in ("format", "wersja", "built", "bytes", "bbox", "source")}
        out["mapa"]["czesci"] = [k for k in ("graph", "addr", "lod1", "lod2", "lod3", "lod4", "znaki", "wys", "siec") if k in m]
    except (OSError, ValueError):
        pass
    out["osm"] = _plik_info(os.path.join(os.path.dirname(root.rstrip("/")), "dane", "mapa.osm.pbf")) \
        or _plik_info(os.path.join(root, "..", "dane", "mapa.osm.pbf"))
    out["kafelki"] = _plik_info(os.path.join(root, "kafelki.pmtiles"))
    try:
        with open(os.path.join(root, "stan.json")) as f:
            out["stan"] = json.load(f)
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(root, "kandydat.json")) as f:
            out["kandydat"] = json.load(f)
        out["kandydat"]["jest"] = os.path.isdir(os.path.join(root, "mapa.kandydat"))
    except (OSError, ValueError):
        out["kandydat"] = None
    try:
        v = os.statvfs(root)
        out["wolne_bajty"] = v.f_bavail * v.f_frsize
    except OSError:
        pass
    return out


BBOX = re.compile(r"^-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?$")
_BUDOWA = {"p": None}


def akcja(root, path, d):
    kat = os.path.dirname(os.path.abspath(root.rstrip("/")))
    www = os.path.abspath(root)
    p = _BUDOWA["p"]
    if p is not None and p.poll() is None:
        return {"ok": False, "blad": "budowa już trwa"}
    kand = os.path.join(www, "mapa.kandydat")
    if path == "/api/buduj":
        arg = []
        bb = str(d.get("bbox", "")).strip()
        if bb:
            if not BBOX.match(bb):
                return {"ok": False, "blad": "obszar: podaj 4 liczby oddzielone przecinkami"}
            arg = ["--bbox", bb]
        _BUDOWA["p"] = subprocess.Popen([os.path.join(kat, "bin", "aktualizuj.sh"), "--kandydat"] + arg,
                                        stdout=open("/var/log/nt1100-trasy.log", "a"), stderr=subprocess.STDOUT,
                                        start_new_session=True)
        return {"ok": True, "komunikat": "budowa kandydata ruszyła; bieżąca mapa bez zmian"}
    if path == "/api/odrzuc":
        shutil.rmtree(kand, ignore_errors=True)
        for n in ("kandydat.json",):
            try:
                os.remove(os.path.join(www, n))
            except OSError:
                pass
        return {"ok": True, "komunikat": "kandydat usunięty"}
    # /api/zatwierdz: tylko zgodny kandydat; stara mapa zostaje jako mapa.stara (Cofnij = /api/cofnij w kolejnym wydaniu)
    try:
        with open(os.path.join(www, "kandydat.json")) as f:
            k = json.load(f)
    except (OSError, ValueError):
        return {"ok": False, "blad": "brak wyniku kontroli kandydata"}
    if not k.get("ok") or not os.path.isdir(kand):
        return {"ok": False, "blad": "kandydat niezgodny z ekranem: " + "; ".join(k.get("powody", ["brak"]))}
    stara = os.path.join(www, "mapa.stara")
    shutil.rmtree(stara, ignore_errors=True)
    os.replace(os.path.join(www, "mapa"), stara)
    os.replace(kand, os.path.join(www, "mapa"))
    try:
        os.remove(os.path.join(www, "kandydat.json"))
    except OSError:
        pass
    return {"ok": True, "komunikat": "kandydat jest bieżącą mapą; poprzednia czeka jako mapa.stara"}


STRONA_INFO = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mapa tras</title><style>body{font:16px system-ui;margin:16px;max-width:520px}td{padding:4px 12px 4px 0}
.z{color:#080}.o{color:#b60}.c{color:#b00}</style><h2>Mapa tras</h2><div id=a>ładuję…</div>
<script>
const mb=b=>b==null?'-':(b/1048576).toFixed(0)+' MB',dni=t=>t?Math.floor((Date.now()/1000-t)/86400):null;
fetch('/info.json').then(r=>r.json()).then(i=>{const m=i.mapa,o=i.osm,s=i.stan,d=o?dni(o.t):null;
let h='<table>';
h+='<tr><td>Wersja mapy<td>'+(m?m.wersja+' (format '+m.format+')':'brak')+'<tr><td>Zbudowana<td>'+(m?m.built:'-')
+'<tr><td>Rozmiar<td>'+(m?mb(m.bytes):'-')+'<tr><td>Dane OSM<td>'+(d==null?'-':'<span class='+(d>60?'c':d>35?'o':'z')+'>'+d+' dni temu</span>')
+'<tr><td>Wolne miejsce<td>'+mb(i.wolne_bajty)+'<tr><td>Teraz<td>'+(s?(s.pracuje?s.etap+(s.krok?' ('+s.krok+'/'+s.z+')':''):(s.ok===false?'<span class=c>'+s.etap+'</span>':'nic nie trwa')):'-')+'</table>';
if(i.kandydat){const k=i.kandydat;h+='<h3>Kandydat</h3>'+(k.ok?'<span class=z>zgodny z ekranem</span>':'<span class=c>niezgodny: '+(k.powody||[]).join('; ')+'</span>')+(k.jest?' · wersja '+k.wersja+' · '+k.built:'');}
h+='<h3>Buduj</h3><p>Obszar (opcjonalnie: S,W,N,E):<br><input id=bb> <br>PIN: <input id=pin type=password><br><button onclick=akcja("buduj")>Zbuduj kandydata</button> <button onclick=akcja("zatwierdz")>Zatwierdź</button> <button onclick=akcja("odrzuc")>Odrzuć</button></p><div id=w></div>';
document.getElementById('a').innerHTML=h}).catch(e=>document.getElementById('a').textContent='błąd: '+e);
function akcja(a){fetch('/api/'+a,{method:'POST',body:JSON.stringify({pin:document.getElementById('pin').value,bbox:document.getElementById('bb').value})}).then(r=>r.json()).then(j=>document.getElementById('w').textContent=j.komunikat||j.blad)}
</script>"""


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

    def _pin_ok(self, d):
        """PIN w pliku pin_mapy obok katalogu www (poza repozytorium); bez pliku Buduj jest wyłączone."""
        try:
            with open(os.path.join(self.directory, "..", "pin_mapy")) as f:
                pin = f.read().strip()
        except OSError:
            return False
        import hmac
        return bool(pin) and hmac.compare_digest(pin, str(d.get("pin", "")))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
        except ValueError:
            return self._send(400, b'{"ok":false,"blad":"zly JSON"}', "application/json")
        if path not in ("/api/buduj", "/api/zatwierdz", "/api/odrzuc"):
            return self._send(404, b"", "text/plain")
        if not self._pin_ok(d):
            time.sleep(1)
            return self._send(403, '{"ok":false,"blad":"zly PIN albo Buduj wylaczone (brak pliku pin_mapy)"}'.encode(), "application/json")
        w = akcja(self.directory, path, d)
        return self._send(200 if w.get("ok") else 409, json.dumps(w, ensure_ascii=False).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/kafelki/info.json":
            pm = pmtiles(self.directory)
            info = pm.info() if pm else {"ok": False}
            info["dem"] = os.path.isdir(os.path.join(self.directory, "dem", "12"))
            body = json.dumps(info).encode()
            return self._send(200, body, "application/json")
        if path == "/info.json":
            return self._send(200, json.dumps(info_mapy(self.directory)).encode(), "application/json")
        if path in ("/info", "/info/"):
            return self._send(200, STRONA_INFO.encode(), "text/html; charset=utf-8")
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
