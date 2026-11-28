#!/usr/bin/env python3
"""Etap budowy kafli Apex: z eksportu osmium (GeoJSON Seq) robi warstwy o ustalonym schemacie.
Użycie: prep-vector.py <rodzaj> wejscie.jsonl wyjscie.jsonl
rodzaj: roads | building | landcover | water | waterway | rail | place | poi
Schemat (źródło warstw w stylach Apex):
  roads(highway,name,ref,kr)  kr = krętość 0..1 (jak w grafie: zakręty/km), 0 dla odcinków < 120 m
  building(h)                 wysokość w metrach (height, building:levels*3, domyślnie 6)
  landcover(class)            wood grass farmland wetland residential industrial park
  water(class) waterway(class) rail() place(name,class) poi(name,amenity)
Tylko standardowa biblioteka."""
import json, math, sys

def lines(path):
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip().lstrip("\x1e")
            if ln: yield json.loads(ln)

def kr(coords):
    length = turn = 0.0; prev = None
    for a, b in zip(coords, coords[1:]):
        dx = (b[0]-a[0])*111320*math.cos(math.radians(a[1])); dy = (b[1]-a[1])*110540
        l = math.hypot(dx, dy)
        if l < 1: continue
        h = math.degrees(math.atan2(dx, dy)); length += l
        if prev is not None:
            t = abs((h-prev+180) % 360-180)
            if t < 100: turn += t
        prev = h
    if length < 120: return 0.0
    return round(min(1.0, (turn/(length/1000))/900), 2)

def num(v, default=None):
    try: return float(str(v).split()[0].replace(",", "."))
    except Exception: return default

LAND = {"wood": ("natural", "wood"), "forest": ("landuse", "forest")}
def landclass(p):
    if p.get("natural") == "wood" or p.get("landuse") == "forest": return "wood"
    if p.get("natural") == "wetland": return "wetland"
    if p.get("landuse") in ("farmland", "orchard", "vineyard"): return "farmland"
    if p.get("landuse") in ("meadow", "grass", "village_green", "recreation_ground") or p.get("natural") in ("grassland", "scrub", "heath"): return "grass"
    if p.get("leisure") in ("park", "garden", "pitch", "playground") or p.get("landuse") == "cemetery": return "park"
    if p.get("landuse") in ("residential",): return "residential"
    if p.get("landuse") in ("industrial", "retail", "commercial"): return "industrial"
    return None

def main(kind, src, dst):
    out = open(dst, "w", encoding="utf-8"); n = 0
    for f in lines(src):
        p = f.get("properties") or {}; g = f.get("geometry") or {}
        props = None
        if kind == "roads" and g.get("type") == "LineString":
            props = {"highway": p.get("highway"), "kr": kr(g["coordinates"])}
            if p.get("name"): props["name"] = p["name"]
            if p.get("ref"): props["ref"] = p["ref"]
        elif kind == "building" and g.get("type") in ("Polygon", "MultiPolygon"):
            h = num(p.get("height")) or (num(p.get("building:levels"), 0) or 0)*3 or 6
            props = {"h": round(min(h, 60), 1)}
        elif kind == "landcover" and g.get("type") in ("Polygon", "MultiPolygon"):
            c = landclass(p); props = {"class": c} if c else None
        elif kind == "water" and g.get("type") in ("Polygon", "MultiPolygon"):
            props = {"class": "lake"}
        elif kind == "waterway" and g.get("type") == "LineString":
            props = {"class": p.get("waterway") or "stream"}
        elif kind == "rail" and g.get("type") == "LineString":
            props = {"class": "rail"}
        elif kind == "place" and g.get("type") == "Point" and p.get("name"):
            props = {"name": p["name"], "class": p.get("place")}
        elif kind == "poi" and g.get("type") == "Point":
            props = {"amenity": p.get("amenity"), "name": p.get("name", "")}
        if props is not None:
            out.write(json.dumps({"type": "Feature", "properties": props, "geometry": g}, ensure_ascii=False)+"\n"); n += 1
    out.close(); print(kind, n, file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 4: sys.exit(__doc__)
    main(*sys.argv[1:])
