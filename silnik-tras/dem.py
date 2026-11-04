"""Dane wysokości do cieniowania gór na mapie dodatku.

Pobiera kafelki wysokości (format Terrarium, AWS Open Data „Terrain Tiles”,
źródła: SRTM, Copernicus i inne – https://registry.opendata.aws/terrain-tiles/)
dla prostokąta obszaru do katalogu www/dem/Z/X/Y.png. Wysokości się nie zmieniają,
więc istniejące pliki są pomijane; pierwszy raz ok. 1,5–2 GB dla Polski.

Użycie: dem.py KATALOG_WWW [--bbox W,S,E,N] [--maxzoom 12]"""
import argparse
import concurrent.futures
import math
import json
import os
import sys
import urllib.request

URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def tile_range(z, w, s, e, n):
    def tx(lon):
        return int((lon + 180) / 360 * (1 << z))

    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * (1 << z))
    return range(tx(w), tx(e) + 1), range(ty(n), ty(s) + 1)


def fetch(root, z, x, y):
    dst = os.path.join(root, str(z), str(x), "%d.png" % y)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers={"User-Agent": "nt1100-silnik-tras"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            with open(dst + ".tmp", "wb") as f:
                f.write(data)
            os.replace(dst + ".tmp", dst)
            return len(data)
        except Exception:
            continue
    return -1


def progress(www, pct):
    """Procent do stan.json (postęp w dodatku), gdy aktualizuj.sh jest na tym etapie."""
    p = os.path.join(www, "stan.json")
    try:
        with open(p) as f:
            st = json.load(f)
        if not st.get("pracuje"):
            return
        st["proc"] = pct
        with open(p + ".tmp", "w") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    except (OSError, ValueError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("www")
    ap.add_argument("--bbox", default="14.0,48.9,24.3,55.0", help="W,S,E,N (domyślnie Polska)")
    ap.add_argument("--maxzoom", type=int, default=12)
    a = ap.parse_args()
    w, s, e, n = (float(v) for v in a.bbox.split(","))
    root = os.path.join(a.www, "dem")
    jobs = []
    for z in range(5, a.maxzoom + 1):
        xs, ys = tile_range(z, w, s, e, n)
        jobs += [(z, x, y) for x in xs for y in ys]
    done = size = bad = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(lambda j: fetch(root, *j), jobs):
            done += 1
            if r < 0:
                bad += 1
            else:
                size += r
            if done % 2000 == 0:
                print("dem: %d/%d kafelków, %.0f MB nowych" % (done, len(jobs), size / 1e6), flush=True)
                progress(a.www, 100 * done // len(jobs))
    with open(os.path.join(root, "info.txt"), "w") as f:
        f.write("bbox=%s maxzoom=%d tiles=%d missing=%d\n" % (a.bbox, a.maxzoom, len(jobs), bad))
    print("dem: gotowe, %d kafelków (%d brakujących), %.0f MB nowych" % (len(jobs), bad, size / 1e6))
    return 0 if bad < len(jobs) // 20 else 1


if __name__ == "__main__":
    sys.exit(main())
