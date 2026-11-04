"""Style mapy dodatku (ciemny i jasny) z OpenFreeMap „dark” i „positron”.

Przekolorowuje ciemny styl pod barwy dodatku, usuwa ikony (sprite) i cieniowanie,
żeby mapa działała z kafelkami z kontenera i czcionkami z dodatku.
Użycie: python3 narzedzia/mapa_styl.py  (pobiera style z tiles.openfreemap.org)
Wynik: nt1100_jazdy/www/mapa-ciemna.json, nt1100_jazdy/www/mapa-jasna.json
"""
import json
import os
import urllib.request

WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nt1100_jazdy", "www")

P = {'background':{'background-color':'#132036'},
 'water':{'fill-color':'#0d2a47'},'waterway':{'line-color':'#0d2a47'},
 'landcover_ice_shelf':{'fill-color':'#132036'},'landcover_glacier':{'fill-color':'#1a2740'},
 'landuse_residential':{'fill-color':'#1b2943','fill-opacity':0.7},
 'landcover_wood':{'fill-color':'#17304a','fill-opacity':0.9},
 'landuse_park':{'fill-color':'#17304a'},
 'building':{'fill-color':'#2c3d5e','fill-outline-color':'#3a4e74'},
 'aeroway-taxiway':{'line-color':'#26365a'},'aeroway-runway-casing':{'line-color':'#26365a'},'aeroway-area':{'fill-color':'#1b2943'},'aeroway-runway':{'line-color':'#2c3e63'},
 'road_area_pier':{'fill-color':'#1b2943'},'road_pier':{'line-color':'#1b2943'},
 'highway_path':{'line-color':'#33466b'},
 'highway_minor':{'line-color':'#364d78','line-opacity':1},
 'highway_major_casing':{'line-color':'#0e1828'},
 'highway_major_inner':{'line-color':'#5b74a8'},
 'highway_major_subtle':{'line-color':'#5b74a8','line-width':['interpolate',['linear'],['zoom'],6,0.6,11,2.2]},
 'highway_motorway_casing':{'line-color':'#0e1828'},
 'highway_motorway_inner':{'line-color':['interpolate',['linear'],['zoom'],5.8,'#6a7fa8',6,'#6a7fa8']},
 'highway_motorway_subtle':{'line-color':'#56699a'},
 'railway_transit':{'line-color':'#2a3650'},'railway_minor':{'line-color':'#2a3650'},'railway':{'line-color':'#2a3650'},
 'railway_transit_dashline':{'line-color':'#132036'},'railway_minor_dashline':{'line-color':'#132036'},'railway_dashline':{'line-color':'#132036'},
 'water_name':{'text-color':'#6f8db5','text-halo-color':'#0b1220'},
 'highway_name_other':{'text-color':'#8b98ae','text-halo-color':'#0b1220'},
 'highway_name_motorway':{'text-color':'#a9b6cc'},
 'boundary_state':{'line-color':'#3a4a66'},'boundary_country_z0-4':{'line-color':'#4a5a78'},'boundary_country_z5-':{'line-color':'#4a5a78'},
}

def get(name):
    req = urllib.request.Request("https://tiles.openfreemap.org/styles/" + name, headers={"User-Agent": "nt1100-mapa-styl"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def clean(s, name):
    s["name"] = name
    s["sources"].pop("ne2_shaded", None)
    s.pop("sprite", None)
    out = []
    for l in s["layers"]:
        lay = l.get("layout", {})
        img = lay.get("icon-image")
        if img is not None and not lay.get("text-field"):
            continue  # sama ikona (strzałki jednokierunkowe, tarcze dróg, lotniska)
        for k in [k for k in lay if k.startswith("icon-")]:
            lay.pop(k)
        l.get("paint", {}).pop("fill-pattern", None)
        for k in [k for k in l.get("paint", {}) if k.startswith("icon-")]:
            l["paint"].pop(k)
        out.append(l)
    s["layers"] = out
    return s


DEM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def extras(s, dark):
    """Cieniowanie gór (wysokości z kontenera albo AWS) oraz szczyty i przełęcze."""
    s["sources"]["dem"] = {"type": "raster-dem", "tiles": [DEM_URL], "encoding": "terrarium",
                           "tileSize": 256, "minzoom": 5, "maxzoom": 12}
    shade = {"id": "hillshade", "type": "hillshade", "source": "dem", "minzoom": 5,
             "paint": {"hillshade-exaggeration": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 12, 0.3],
                       "hillshade-shadow-color": "#050a14" if dark else "#5a6577",
                       "hillshade-highlight-color": "#2a3a58" if dark else "#ffffff",
                       "hillshade-accent-color": "#0b1220" if dark else "#8a94a6"}}
    ids = [l["id"] for l in s["layers"]]
    at = ids.index("waterway") if "waterway" in ids else 1
    s["layers"].insert(at, shade)
    txt, halo = ("#c9b98f", "#0b1220") if dark else ("#6b5a35", "#ffffff")
    font = ["Noto Sans Italic"]
    peak = {"id": "mountain_peak", "type": "symbol", "source": "openmaptiles", "source-layer": "mountain_peak",
            "minzoom": 9, "filter": ["in", ["get", "class"], ["literal", ["peak", "volcano"]]],
            "layout": {"text-field": ["case", ["has", "ele"],
                                      ["concat", ["get", "name"], "\n", ["to-string", ["get", "ele"]], " m"],
                                      ["concat", ["get", "name"]]],
                       "text-font": font, "text-size": ["interpolate", ["linear"], ["zoom"], 9, 10, 14, 12],
                       "text-anchor": "top", "text-max-width": 8, "symbol-sort-key": ["-", 0, ["coalesce", ["get", "ele"], 0]]},
            "paint": {"text-color": txt, "text-halo-color": halo, "text-halo-width": 1.3}}
    saddle = {"id": "mountain_pass", "type": "symbol", "source": "openmaptiles", "source-layer": "mountain_peak",
              "minzoom": 11, "filter": ["==", ["get", "class"], "saddle"],
              "layout": {"text-field": ["concat", "przeł. ", ["get", "name"]], "text-font": font, "text-size": 11,
                         "text-max-width": 8},
              "paint": {"text-color": txt, "text-halo-color": halo, "text-halo-width": 1.3}}
    ids = [l["id"] for l in s["layers"]]
    at = next((i for i, x in enumerate(ids) if x.startswith("place_") or x.startswith("label_")), len(ids))
    s["layers"][at:at] = [peak, saddle]
    return s


def save(s, fn):
    with open(os.path.join(WWW, fn), "w") as f:
        json.dump(s, f, ensure_ascii=False, separators=(",", ":"))


d = get("dark")
for l in d["layers"]:
    p = P.get(l["id"])
    if p:
        l.setdefault("paint", {}).update(p)
    if l["id"].startswith("place_"):
        big = l["id"] in ("place_city", "place_city_large", "place_town")
        l["paint"].update({"text-color": "#d5deeb" if big else "#9aa7bd", "text-halo-color": "#0b1220",
                           "text-halo-width": 1.4, "text-halo-blur": 0})
save(extras(clean(d, "NT1100 ciemna"), True), "mapa-ciemna.json")
save(extras(clean(get("positron"), "NT1100 jasna"), False), "mapa-jasna.json")
print("zapisano")
