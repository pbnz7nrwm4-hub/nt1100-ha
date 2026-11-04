"""Nawigacja: adresy HTTP dodatku (strona przez panel HA i port ekranu).

Strona (Ingress, bez klucza):
  GET  /nav.js, /api/nav/routes, /api/nav/route?id, /api/nav/gpx?id, /api/nav/search?q,
       /api/nav/poi?bbox, /api/nav/along?id|token&variant&kinds&max (POI wzdłuż trasy),
       /api/nav/nearby?kinds&lat&lon (miejsca przed motocyklem), /api/nav/resolve?text, /api/nav/settings,
       /api/nav/map, /api/nav/plan?n (zgodność jazdy), /api/nav/screen, /api/nav/recent
  POST /api/nav/plan, /api/nav/send, /api/nav/gpx, /api/nav/current, /api/nav/delete,
       /api/nav/settings, /api/nav/map/sync, /api/nav/goto, /api/nav/home, /api/nav/fav (ulubione), /api/nav/via (zjazd do miejsca)
Ekran (port 8098, klucz w X-Klucz albo ?klucz=):
  GET  /api/nav/ping, /api/nav/route.ntr?id, /api/nav/route.json?id, /api/nav/mapa/<plik> (też <kwadrat>.ntt.gz),
       /api/nav/traffic, /api/nav/fw, /api/nav/fw/bin, /api/nav/goto?text (skrót iOS)
  POST /api/nav/reroute, /api/nav/log, /api/nav/via (zjazd do miejsca i powrót na trasę)
"""
import json
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.error
import urllib.parse

import nav
import ntt

SRV = None
NAV = None
PLANS = {}  # token -> (czas, lista tras) z ostatnich planowań
NAV_LIMITS = {"lean_popup_deg": (5, 60), "traffic_min": (1, 60), "offroute_m": (50, 1000)}
RECENT_MAX = 12


def gpx_disposition(name):
    """Nagłówek pobrania GPX. Nagłówki HTTP są w latin-1: polskie litery idą
    w filename* (RFC 5987), a filename dostaje wersję bez ogonków."""
    fn = re.sub(r"[^\w.-]+", "_", name or "trasa", flags=re.UNICODE).strip("_")[:40] or "trasa"
    ascii_fn = unicodedata.normalize("NFKD", fn.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode() or "trasa"
    return 'attachment; filename="%s.gpx"; filename*=UTF-8\'\'%s.gpx' % (ascii_fn, urllib.parse.quote(fn))

def init(server):
    global SRV, NAV
    SRV = server
    NAV = nav.Nav(server.SHARE, server.DATA, lambda: server.settings().get("nav") or {}, server.log)
    threading.Thread(target=map_loop, daemon=True).start()
    return NAV


def map_loop():
    """Raz dziennie sprawdza, czy kontener ma nowszą mapę."""
    time.sleep(90)
    while True:
        try:
            if NAV.settings()["map_url"]:
                NAV.map_sync()
        except Exception as e:
            SRV.log("mapa: sprawdzanie nieudane:", e)
        time.sleep(24 * 3600)


def nav_settings_apply(j):
    """Ustawienia nawigacji ze strony (klucz 'nav' w /api/settings)."""
    if not isinstance(j, dict):
        return "zle dane nawigacji"
    cur = dict(SRV.settings().get("nav") or {})
    for k in ("engine_url", "map_url", "tomtom_key", "default_variant"):
        if k in j:
            v = str(j[k] or "").strip()
            if k.endswith("_url") and v and not re.fullmatch(r"https?://[^\s/]+(:\d+)?(/[^\s]*)?", v):
                return "zly adres: " + k
            if k == "default_variant" and v not in [x for x, _ in nav.VARIANTS]:
                return "zly wariant"
            cur[k] = v[:200]
    for k, (lo, hi) in NAV_LIMITS.items():
        if k in j:
            try:
                v = int(j[k])
            except (TypeError, ValueError):
                return "zla wartosc: " + k
            if not lo <= v <= hi:
                return "poza zakresem: " + k
            cur[k] = v
    if "vehicle" in j:
        if j["vehicle"] not in ("moto", "auto"):
            return "zly pojazd"
        cur["vehicle"] = j["vehicle"]
    if "free_km" in j:
        v = SRV.num(j["free_km"])
        if v is None or not 0.5 <= v <= 20:
            return "poza zakresem: free_km"
        cur["free_km"] = v
    if "curvy" in j:
        c = j["curvy"]
        if not isinstance(c, dict) or any(v not in nav.CURVY_DEFAULT or not isinstance(x, dict) for v, x in c.items()):
            return "zle suwaki krętości"
        for x in c.values():
            for k, val in x.items():
                if k not in nav.CURVY_KEYS or not isinstance(val, (int, float)) or not 0 <= val <= 100:
                    return "zle suwaki krętości"
        cur["curvy"] = nav.curvy_sliders(c)
    if "curvy_levels" in j:
        lv = j["curvy_levels"]
        if lv is None:
            cur.pop("curvy_levels", None)
        else:
            ok = isinstance(lv, list) and all(isinstance(x, (int, float)) for x in lv)
            if not ok or nav.curvy_levels(lv) != [int(x) for x in lv]:
                return "progi krętości: trzy rosnące liczby, np. 30, 80, 150"
            cur["curvy_levels"] = [int(x) for x in lv]
    if "avoid" in j:
        a = j["avoid"]
        if not isinstance(a, list) or any(x not in nav.AVOID for x in a):
            return "zle omijanie"
        cur["avoid"] = a
    if "home" in j:
        h = j["home"]
        if h is None:
            cur["home"] = None
        else:
            lat, lon = SRV.num((h or {}).get("lat")), SRV.num((h or {}).get("lon"))
            if lat is None or lon is None:
                return "zly dom"
            cur["home"] = {"lat": lat, "lon": lon, "name": str(h.get("name") or "Dom")[:40]}
    if "fav" in j:
        fl = j["fav"]
        if not isinstance(fl, list) or len(fl) > nav.FAV_MAX:
            return "ulubione: najwyżej %d miejsc" % nav.FAV_MAX
        out = []
        for f in fl:
            lat, lon = SRV.num((f or {}).get("lat")), SRV.num((f or {}).get("lon"))
            name = str((f or {}).get("name") or "").strip()[:30]
            if lat is None or lon is None or not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return "zle ulubione miejsce"
            if any(o["name"].lower() == name.lower() for o in out):
                return "dwa ulubione o nazwie „%s”" % name
            out.append({"lat": round(lat, 6), "lon": round(lon, 6), "name": name})
        cur["fav"] = out
    SRV.save_state(nav=cur)
    return ""


def fav_place(text):
    """Ulubione miejsce (albo dom) po nazwie, np. „praca” – dla skrótu iPhone’a i „jedź do”."""
    t = (text or "").strip().lower()
    if not t:
        return None
    s = NAV.settings()
    for f in s["fav"]:
        if f["name"].lower() == t:
            return {"lat": f["lat"], "lon": f["lon"], "name": f["name"]}
    if s["home"] and t in ("dom", "do domu", (s["home"].get("name") or "").lower()):
        return {"lat": s["home"]["lat"], "lon": s["home"]["lon"], "name": s["home"].get("name") or "Dom"}
    return None


def recent():
    return NAV.state.get("recent") or []


def add_recent(place):
    r = [p for p in recent() if abs(p["lat"] - place["lat"]) > 1e-4 or abs(p["lon"] - place["lon"]) > 1e-4]
    r.insert(0, {"lat": place["lat"], "lon": place["lon"], "name": place.get("name") or ""})
    NAV.save_state(recent=r[:RECENT_MAX])


def start_point():
    """Start trasy bez podanego: pozycja ekranu z ostatnich 3 h, inaczej dom."""
    sc = NAV.screen_position()
    if sc and time.time() - sc.get("t", 0) < 3 * 3600:
        return {"lat": sc["lat"], "lon": sc["lon"], "name": "pozycja motocykla"}
    home = NAV.settings()["home"]
    if home:
        return dict(home)
    return None


def bike_position(q_lat=None, q_lon=None):
    """Pozycja do decyzji w trasie: ekran (do 30 min), inaczej podana z telefonu."""
    sc = NAV.screen_position()
    if sc and time.time() - sc.get("t", 0) < 1800:
        return {"lat": sc["lat"], "lon": sc["lon"], "src": "ekran", "age_s": int(time.time() - sc.get("t", 0))}
    if q_lat is not None and q_lon is not None:
        return {"lat": q_lat, "lon": q_lon, "src": "telefon", "age_s": 0}
    return None


DEMO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo-trasa.json")


def demo_route():
    """Trasa demo (Start – Meta, 22 km) z fotoradarem, odcinkowym pomiarem
    i postojem; czasy pogody są względne, tu przesunięte na teraz."""
    with open(DEMO_PATH, encoding="utf-8") as f:
        r = json.load(f)
    now = int(time.time())
    for w in r.get("weather") or []:
        w["t"] = now + int(w.get("t") or 0)
    r.pop("id", None)
    r.pop("version", None)
    r.pop("created", None)
    return r


def route_summary(r, with_pts=True, full=False):
    out = {k: r.get(k) for k in ("id", "name", "variant", "source", "dist_m", "time_s", "curvy", "waypoints", "turns",
                                 "limits", "cameras", "weather", "avoid", "points", "version", "created", "round_trip_km",
                                 "round_trip_min", "skip", "legs", "leg_m")}
    out["km"] = round((r.get("dist_m") or 0) / 1000, 1)
    out["min"] = int((r.get("time_s") or 0) / 60)
    if with_pts and full:
        # symulacja w przeglądarce: każdy punkt, odległości i czasy (indeksy wskazówek pasują 1:1)
        out["pts"] = [[round(p[0], 6), round(p[1], 6)] for p in r["pts"]]
        out["cum"] = r.get("cum")
        out["times"] = r.get("times")
    elif with_pts:
        # co 3. punkt wystarczy na mapę w przeglądarce (ekran dostaje pełną paczkę)
        pts = r["pts"]
        out["pts"] = [[round(p[0], 5), round(p[1], 5)] for p in pts[::3]] + [[round(pts[-1][0], 5), round(pts[-1][1], 5)]]
    return out


def goto(text, variant=None, name=None):
    """Cel z tekstu/linku: trasa z pozycji motocykla (albo domu) i oznaczenie
    jako bieżąca dla ekranu."""
    place = fav_place(text) or NAV.resolve_place(text)
    if not place:
        raise ValueError("nie rozpoznałem miejsca w: %s" % (text or "")[:60])
    start = start_point()
    if not start:
        raise ValueError("nie znam pozycji motocykla ani domu (ustaw dom w zakładce Nawigacja)")
    s = NAV.settings()
    v = variant or s["go_variant"]
    routes, errors = NAV.plan([start, {"lat": place["lat"], "lon": place["lon"], "name": place["name"]}], [v],
                              s["avoid"], name or ("→ " + (place["name"] or "cel"))[:40], with_weather=True)
    if not routes:
        raise ValueError(errors.get(v) or "silnik tras nie odpowiedział")
    rid = NAV.store_route(routes[0], True)
    NAV.note_current(rid)
    add_recent(place)
    return route_summary(routes[0], False), place


# ---------------------------------------------------------------- mapa w przeglądarce (kafelki z kontenera)

FONTS = ("Noto Sans Regular", "Noto Sans Bold", "Noto Sans Italic")
FONT_RE = re.compile(r"^/fonty/([A-Za-z ]+)/(\d+-\d+)\.pbf$")
DEM_RE = re.compile(r"^/api/nav/dem/(\d{1,2})/(\d{1,5})/(\d{1,5})\.png$")
TILE_RE = re.compile(r"^/api/nav/kafelki/(\d{1,2})/(\d{1,5})/(\d{1,5})\.pbf$")
_TILES = {"t": 0, "info": None}


def tiles_info():
    """Czy kontener ma własne kafelki mapy (kafelki.pmtiles)? Pamiętane przez minutę."""
    now = time.time()
    if _TILES["info"] is not None and now - _TILES["t"] < 60:
        return _TILES["info"]
    base = NAV.settings()["map_url"]
    info = {"local": False}
    if base:
        try:
            j = nav.http_json(base + "/kafelki/info.json", timeout=4)
            info = {"local": bool(j.get("ok")), "built": j.get("built"), "maxzoom": int(j.get("maxzoom") or 14),
                    "minzoom": int(j.get("minzoom") or 0), "bounds": j.get("bounds"), "dem": bool(j.get("dem"))}
        except Exception:
            pass
    _TILES.update(t=now, info=info)
    return info


def dem_tile(z, x, y):
    """Kafelek wysokości (PNG Terrarium) z kontenera albo None."""
    import urllib.request
    base = NAV.settings()["map_url"]
    if not base or z > 12:
        return None
    try:
        with urllib.request.urlopen("%s/dem/%d/%d/%d.png" % (base, z, x, y), timeout=10) as r:
            return r.read()
    except Exception:
        return None


def tile(z, x, y):
    """Kafelek wektorowy z kontenera (rozpakowany); b"" = pusty, None = brak kontenera."""
    import gzip
    import urllib.request
    base = NAV.settings()["map_url"]
    if not base or z > 14:
        return None
    try:
        with urllib.request.urlopen("%s/kafelki/%d/%d/%d.pbf" % (base, z, x, y), timeout=10) as r:
            data = r.read()
            if r.status == 204:
                return b""
    except urllib.error.HTTPError as e:
        return b"" if e.code in (204, 404) else None
    except Exception:
        return None
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


# ---------------------------------------------------------------- strona

def page_get(h, path, q):
    """True = obsłużone."""
    if path == "/nav.js":
        p = os.path.join(SRV.WWW, "nav.js")
        if os.path.exists(p):
            h.send_path(p, "application/javascript; charset=utf-8")
        else:
            h.send(404, "brak", "text/plain")
        return True
    if path in ("/mapa-ciemna.json", "/mapa-jasna.json"):
        h.send_path(os.path.join(SRV.WWW, path[1:]), "application/json", {"Cache-Control": "max-age=3600"})
        return True
    m = FONT_RE.match(urllib.parse.unquote(path))
    if m and m.group(1) in FONTS:
        p = os.path.join(SRV.WWW, "fonty", m.group(1), m.group(2) + ".pbf")
        if os.path.exists(p):
            h.send_path(p, "application/x-protobuf", {"Cache-Control": "max-age=604800"})
        else:
            h.send(404, "brak", "text/plain")
        return True
    if path == "/api/nav/mapa.zip":
        st = NAV.zip_status()
        if not st["ready"]:
            if not st["working"]:
                threading.Thread(target=NAV.map_zip, daemon=True).start()
            return h.send(202, {"ok": False, "working": True,
                                "error": "paczka mapy się przygotowuje, spróbuj za kilka minut"}) or True
        return h.send_path(NAV.zip_path(), "application/zip",
                           {"Content-Disposition": 'attachment; filename="mapa-ekranu.zip"'}) or True
    if path == "/api/nav/kafelki/info":
        return h.send(200, tiles_info()) or True
    m = DEM_RE.match(path)
    if m:
        data = dem_tile(*(int(v) for v in m.groups()))
        if data is None:
            return h.send(404, "brak", "text/plain") or True
        return h.send(200, data, "image/png", {"Cache-Control": "max-age=604800"}) or True
    m = TILE_RE.match(path)
    if m:
        z, x, y = (int(v) for v in m.groups())
        data = tile(z, x, y)
        if data is None:
            return h.send(404, "brak", "text/plain") or True
        if data == b"":
            return h.send(204, b"", "application/x-protobuf", {"Cache-Control": "max-age=86400"}) or True
        return h.send(200, data, "application/x-protobuf", {"Cache-Control": "max-age=86400"}) or True
    if not path.startswith("/api/nav/"):
        return False
    try:
        if path == "/api/nav/routes":
            lst = NAV.list_routes()
            lst.update(map=NAV.map_status(), zip=NAV.zip_status(), build=NAV.build_status(), engine=NAV.engine_ok(), screen=NAV.screen_position(),
                       settings=NAV.settings(), recent=recent(), variants=nav.VARIANTS, mix=nav.MIX,
                       avoid_all=nav.AVOID, curvy_default=nav.CURVY_DEFAULT,
                       curvy_levels_default=nav.CURVY_LEVELS_DEFAULT)
            lst["settings"]["tomtom_key"] = bool(lst["settings"]["tomtom_key"])
            return h.send(200, lst) or True
        if path == "/api/nav/route":
            r = NAV.route(int(q.get("id", "0")))
            if not r:
                return h.send(404, {"error": "brak trasy"}) or True
            return h.send(200, route_summary(r, full=q.get("full") == "1")) or True
        if path == "/api/nav/gpx":
            r = NAV.route(int(q.get("id", "0")))
            if not r:
                return h.send(404, "brak trasy", "text/plain") or True
            return h.send(200, nav.to_gpx(r).encode(), "application/gpx+xml",
                          {"Content-Disposition": gpx_disposition(r.get("name"))}) or True
        if path == "/api/nav/search":
            qq = (q.get("q") or "").strip()[:100]
            if not qq:
                return h.send(200, {"results": []}) or True
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            return h.send(200, {"results": NAV.search(qq, lat, lon)}) or True
        if path == "/api/nav/poi":
            try:
                s, w, n, e = [float(x) for x in q.get("bbox", "").split(",")]
            except ValueError:
                return h.send(400, {"error": "zly bbox"}) or True
            kinds = {int(k) for k in q.get("kinds", "").split(",") if k.strip().isdigit()} or None
            if (n - s) * (e - w) > 4:
                return h.send(200, {"points": [], "too_big": True}) or True
            pts = NAV.map.points_in_bbox(s, w, n, e, kinds, 400)
            return h.send(200, {"points": [{"lat": p.lat, "lon": p.lon, "kind": p.kind, "name": p.name, "limit": p.limit}
                                           for p in pts]}) or True
        if path == "/api/nav/nearby":
            kinds = {int(k) for k in q.get("kinds", "").split(",") if k.strip().isdigit()} or {ntt.P_FUEL}
            pos = bike_position(SRV.num(q.get("lat")), SRV.num(q.get("lon")))
            if not pos:
                return h.send(200, {"pos": None, "points": []}) or True
            if not NAV.map.available():
                return h.send(200, {"pos": pos, "points": [], "no_map": True}) or True
            out = NAV.nearby(pos["lat"], pos["lon"], kinds)
            out["pos"] = pos
            return h.send(200, out) or True
        if path == "/api/nav/along":
            # POI wzdłuż trasy: zapisanej (id) albo świeżo policzonej (token + wariant)
            route = None
            if q.get("token"):
                plan = PLANS.get(q.get("token"))
                if not plan:
                    return h.send(410, {"error": "planowanie wygasło, policz jeszcze raz"}) or True
                route = next((r for r in plan[1] if r.get("variant") == q.get("variant")), None)
            elif q.get("id", "").isdigit():
                route = NAV.route(int(q["id"]))
            if not route:
                return h.send(404, {"error": "brak trasy"}) or True
            kinds = {int(k) for k in q.get("kinds", "").split(",") if k.strip().isdigit()} or {ntt.P_FUEL}
            max_m = min(5000.0, max(200.0, SRV.num(q.get("max")) or 2000.0))
            if not NAV.map.available():
                return h.send(200, {"points": [], "no_map": True}) or True
            return h.send(200, {"points": NAV.along_route(route, kinds, max_m)}) or True
        if path == "/api/nav/resolve":
            place = fav_place((q.get("text") or "")[:60]) or NAV.resolve_place((q.get("text") or "")[:500])
            if not place:
                return h.send(404, {"error": "nie rozpoznałem miejsca"}) or True
            return h.send(200, {"place": place}) or True
        if path == "/api/nav/settings":
            s = NAV.settings()
            s["tomtom_key"] = bool(s["tomtom_key"])
            return h.send(200, s) or True
        if path == "/api/nav/map":
            return h.send(200, NAV.map_status()) or True
        if path == "/api/nav/screen":
            return h.send(200, {"screen": NAV.screen_position()}) or True
        if path == "/api/nav/recent":
            return h.send(200, {"recent": recent(), "home": NAV.settings()["home"], "fav": NAV.settings()["fav"]}) or True
        if path == "/api/nav/plan":
            n = int(q.get("n", "0"))
            s = SRV.summary(n) or {}
            start = SRV.parse_time(s.get("start"))
            if start is None:
                return h.send(404, {"error": "brak jazdy"}) or True
            pts, _ = SRV.read_track(n)
            end = start + (pts[-1][5] or 0) if pts else start
            c = NAV.compliance([(p[0], p[1]) for p in pts], start, end) if pts else None
            if c:
                r = NAV.route(c["route"])
                if r:
                    c["pts"] = [[round(p[0], 5), round(p[1], 5)] for p in r["pts"][::4]]
            return h.send(200, {"plan": c}) or True
    except ValueError as e:
        return h.send(400, {"error": str(e)}) or True
    except Exception as e:
        SRV.log("nawigacja:", path, e)
        return h.send(502, {"error": str(e)}) or True
    return False


def page_post(h, path, q, body):
    if not path.startswith("/api/nav/"):
        return False
    try:
        j = json.loads(body or b"{}") if path != "/api/nav/gpx" else None
    except ValueError:
        return h.send(400, {"error": "zle dane"}) or True
    try:
        if path == "/api/nav/plan":
            pts = j.get("points") or []
            if not isinstance(pts, list) or not 1 <= len(pts) <= 30:
                return h.send(400, {"error": "podaj od 1 do 30 punktów"}) or True
            points = []
            for p in pts:
                lat, lon = SRV.num((p or {}).get("lat")), SRV.num((p or {}).get("lon"))
                if lat is None or lon is None:
                    return h.send(400, {"error": "zly punkt"}) or True
                points.append({"lat": lat, "lon": lon, "name": str(p.get("name") or "")[:40]})
            rt = SRV.num(j.get("round_trip_km"))
            if rt is not None and not 10 <= rt <= 1500:
                return h.send(400, {"error": "trasa okrężna 10–1500 km"}) or True
            rtm = SRV.num(j.get("round_trip_min"))
            if rtm is not None and not 15 <= rtm <= 720:
                return h.send(400, {"error": "trasa okrężna na czas: 15 min – 12 h"}) or True
            if rt and rtm:
                return h.send(400, {"error": "trasa okrężna: podaj km albo czas"}) or True
            skip = []
            for sp in (j.get("skip") or [])[:10]:
                lat, lon, r = SRV.num((sp or {}).get("lat")), SRV.num((sp or {}).get("lon")), SRV.num((sp or {}).get("r"))
                if lat is None or lon is None:
                    return h.send(400, {"error": "zly punkt do pominiecia"}) or True
                skip.append({"lat": lat, "lon": lon, "r": int(min(8000, max(200, r or 1000))),
                             "name": str(sp.get("name") or "")[:40]})
            if len(points) < 2 and not rt and not rtm:
                return h.send(400, {"error": "podaj cel"}) or True
            variants = [v for v in (j.get("variants") or []) if v in [x for x, _ in nav.VARIANTS]] or None
            avoid = j.get("avoid") if isinstance(j.get("avoid"), list) else None
            legs = j.get("legs")
            if legs is not None:
                names = [x for x, _ in nav.VARIANTS]
                if not isinstance(legs, list) or len(legs) != len(points) - 1 or any(v not in names for v in legs):
                    return h.send(400, {"error": "zły wariant odcinka"}) or True
                if len(set(legs)) < 2:
                    legs = None  # wszystkie odcinki tak samo = zwykły wariant
            routes, errors = NAV.plan(points, variants, avoid, str(j.get("name") or "")[:40], rt, SRV.num(j.get("heading")),
                                      with_weather=bool(j.get("weather", True)), legs=legs, skip=skip,
                                      round_trip_min=rtm)
            token = secrets.token_hex(8)
            PLANS[token] = (time.time(), routes)
            for k in [k for k, v in PLANS.items() if time.time() - v[0] > 3600]:
                PLANS.pop(k, None)
            return h.send(200, {"token": token, "routes": [route_summary(r) for r in routes], "errors": errors}) or True
        if path == "/api/nav/demo":
            rid = NAV.store_route(demo_route(), make_current=bool(j.get("current")))
            return h.send(200, {"id": rid}) or True
        if path == "/api/nav/send":
            plan = PLANS.get(j.get("token") or "")
            if not plan:
                return h.send(410, {"error": "planowanie wygasło, policz jeszcze raz"}) or True
            v = j.get("variant")
            route = next((r for r in plan[1] if r.get("variant") == v), plan[1][0] if plan[1] else None)
            if not route:
                return h.send(404, {"error": "brak wariantu"}) or True
            route = json.loads(json.dumps(route))
            if j.get("name"):
                route["name"] = str(j["name"])[:40]
            rid = NAV.store_route(route, bool(j.get("current", True)))
            if j.get("current", True):
                NAV.note_current(rid)
            for p in (route.get("points") or [])[1:]:
                add_recent(p)
            return h.send(200, {"id": rid, "route": route_summary(route, False)}) or True
        if path == "/api/nav/gpx":
            if not body:
                return h.send(400, {"error": "brak pliku"}) or True
            route = NAV.route_from_gpx(body, q.get("name", ""))
            rid = NAV.store_route(route, True)
            NAV.note_current(rid)
            return h.send(200, {"id": rid, "route": route_summary(route)}) or True
        if path == "/api/nav/current":
            rid = int(j.get("id") or 0) or None
            NAV.set_current(rid)
            NAV.note_current(rid)
            return h.send(200, {"ok": True, "current": rid}) or True
        if path == "/api/nav/delete":
            NAV.delete_route(int(j.get("id") or 0))
            return h.send(200, {"ok": True}) or True
        if path == "/api/nav/settings":
            err = nav_settings_apply(j)
            if err:
                return h.send(400, {"error": err}) or True
            s = NAV.settings()
            s["tomtom_key"] = bool(s["tomtom_key"])
            return h.send(200, s) or True
        if path == "/api/nav/map/sync":
            return h.send(200, NAV.map_sync(force=bool(j.get("force")))) or True
        if path == "/api/nav/goto":
            r, place = goto(str(j.get("text") or ""), j.get("variant"), j.get("name"))
            return h.send(200, {"route": r, "place": place}) or True
        if path == "/api/nav/via":
            place = {"lat": SRV.num(j.get("lat")), "lon": SRV.num(j.get("lon")), "name": str(j.get("name") or "")[:30]}
            if place["lat"] is None or place["lon"] is None:
                return h.send(400, {"error": "zly punkt"}) or True
            fr = j.get("from") or {}
            pos = bike_position(SRV.num(fr.get("lat")), SRV.num(fr.get("lon")))
            if not pos:
                return h.send(400, {"error": "nie znam pozycji motocykla – włącz hotspot albo użyj pozycji telefonu"}) or True
            r = NAV.via_place(pos["lat"], pos["lon"], place)
            NAV.note_current(r["id"])
            return h.send(200, {"route": route_summary(r, False), "pos": pos}) or True
        if path == "/api/nav/fav":
            err = nav_settings_apply({"fav": j.get("fav")})
            if err:
                return h.send(400, {"error": err}) or True
            return h.send(200, {"fav": NAV.settings()["fav"]}) or True
        if path == "/api/nav/home":
            err = nav_settings_apply({"home": j.get("home")})
            if err:
                return h.send(400, {"error": err}) or True
            return h.send(200, {"home": NAV.settings()["home"]}) or True
    except ValueError as e:
        return h.send(400, {"error": str(e)}) or True
    except Exception as e:
        SRV.log("nawigacja:", path, e)
        return h.send(502, {"error": str(e)}) or True
    return False


# ---------------------------------------------------------------- ekran (port 8098)

def screen_firmware_offer():
    j = SRV.read_json(os.path.join(SRV.FIRMWARE, "ekran.json"), {})
    path = os.path.join(SRV.FIRMWARE, "ekran.bin")
    if not j.get("version") or not os.path.exists(path):
        return None
    return {"version": j["version"], "size": os.path.getsize(path), "path": path}


def screen_authorized(h, q):
    if h.authorized():
        return True
    k = (q.get("klucz") or "").strip()
    import hmac
    return bool(k) and hmac.compare_digest(k.encode(), SRV.key().encode())


def note_screen(h, q):
    lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
    extra = {}
    v = (q.get("v") or "").strip()
    if re.fullmatch(r"[0-9.]{1,16}", v):
        extra["fw"] = v
    b = SRV.num(q.get("bat"))
    if b is not None:
        extra["battery"] = int(b)
    if q.get("route"):
        extra["route"] = int(SRV.num(q.get("route")) or 0)
        extra["route_version"] = int(SRV.num(q.get("ver")) or 0)
    extra["map"] = (q.get("map") or "")[:16]
    extra["ip"] = h.client_address[0]
    extra["via"] = h.source()
    if lat is not None and lon is not None and (lat or lon):
        NAV.screen_seen(lat, lon, SRV.num(q.get("speed")) or 0, SRV.num(q.get("hdg")) or 0, extra)
    else:
        st = dict(NAV.screen_position() or {})
        st.update(extra)
        st["t_seen"] = int(time.time())
        NAV.save_state(screen=st)


def screen_get(h, path, q):
    if not path.startswith("/api/nav/"):
        return False
    if not screen_authorized(h, q):
        SRV.log("Odrzucono ekran: zly klucz (", h.client_address[0], ")")
        return h.send(401, {"ok": False, "error": "zly klucz"}) or True
    try:
        if path == "/api/nav/ping":
            note_screen(h, q)
            idx = NAV.index()
            cur = idx.get("current")
            route = None
            if cur:
                r = next((x for x in idx["routes"] if x["id"] == cur), None)
                if r:
                    route = {"id": r["id"], "version": r["version"], "name": r["name"], "km": r["km"]}
            m = NAV.map.manifest() or {}
            s = NAV.settings()
            out = {"ok": True, "time": int(time.time()), "route": route,
                   "map": {"built": m.get("built"), "files": len(m.get("files", [])), "bytes": m.get("bytes", 0)} if m else None,
                   "settings": dict({k: s[k] for k in ("lean_popup_deg", "traffic_min", "offroute_m", "free_km")},
                                    # w samochodzie bez „wyniku zakrętu” (pochył auta nic nie znaczy)
                                    vehicle=s["vehicle"], **({"lean_popup_deg": 90} if s["vehicle"] == "auto" else {})),
                   "traffic": bool(s["tomtom_key"]), "fw": (screen_firmware_offer() or {}).get("version") or ""}
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            if route and lat is not None and s["tomtom_key"] and q.get("traffic") == "1":
                try:
                    out["traffic_now"] = NAV.traffic(route["id"], lat, lon)
                except Exception as e:
                    SRV.log("korki nieudane:", e)
            return h.send(200, out) or True
        if path in ("/api/nav/route.ntr", "/api/nav/route.json"):
            rid = int(SRV.num(q.get("id")) or 0)
            p = NAV.route_path(rid, path.rsplit(".", 1)[1])
            if rid <= 0 or not os.path.exists(p):
                return h.send(404, {"ok": False, "error": "brak trasy"}) or True
            return h.send_path(p, "application/octet-stream" if p.endswith(".ntr") else "application/json") or True
        if path == "/api/nav/mapa/manifest.json":
            m = NAV.screen_manifest()
            if not m:
                return h.send(404, {"ok": False, "error": "brak mapy"}) or True
            return h.send(200, m) or True
        if path.startswith("/api/nav/mapa/") and path.endswith(".ntt.gz"):
            p = NAV.map_gz(path.rsplit("/", 1)[1][:-3])
            if not p:
                return h.send(404, {"ok": False, "error": "brak pliku"}) or True
            return h.send_path(p, "application/gzip") or True
        if path.startswith("/api/nav/mapa/"):
            p = NAV.map_file(path.rsplit("/", 1)[1])
            if not p:
                return h.send(404, {"ok": False, "error": "brak pliku"}) or True
            return h.send_path(p, "application/octet-stream") or True
        if path == "/api/nav/traffic":
            rid = int(SRV.num(q.get("id")) or 0)
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            if lat is None or lon is None:
                return h.send(400, {"ok": False, "error": "brak pozycji"}) or True
            return h.send(200, {"ok": True, "traffic": NAV.traffic(rid, lat, lon)}) or True
        if path == "/api/nav/fw":
            note_screen(h, q)
            o = screen_firmware_offer()
            return h.send(200, {"version": o["version"] if o else "", "size": o["size"] if o else 0}) or True
        if path == "/api/nav/fw/bin":
            o = screen_firmware_offer()
            if not o:
                return h.send(404, {"ok": False, "error": "brak pliku"}) or True
            SRV.log("Ekran pobiera oprogramowanie", o["version"])
            return h.send_path(o["path"], "application/octet-stream") or True
        if path == "/api/nav/goto":
            r, place = goto(q.get("text") or q.get("q") or "", q.get("variant"))
            return h.send(200, {"ok": True, "route": r, "place": place}) or True
    except ValueError as e:
        return h.send(400, {"ok": False, "error": str(e)}) or True
    except Exception as e:
        SRV.log("nawigacja (ekran):", path, e)
        return h.send(502, {"ok": False, "error": str(e)}) or True
    return h.send(404, {"ok": False, "error": "brak"}) or True


def screen_post(h, path, q, body):
    if not path.startswith("/api/nav/"):
        return False
    if not screen_authorized(h, q):
        return h.send(401, {"ok": False, "error": "zly klucz"}) or True
    try:
        j = json.loads(body or b"{}")
    except ValueError:
        return h.send(400, {"ok": False, "error": "zle dane"}) or True
    try:
        if path == "/api/nav/reroute":
            rid = int(j.get("id") or 0)
            lat, lon = SRV.num(j.get("lat")), SRV.num(j.get("lon"))
            if lat is None or lon is None:
                return h.send(400, {"ok": False, "error": "brak pozycji"}) or True
            r = NAV.reroute(rid, lat, lon, SRV.num(j.get("heading")), bool(j.get("skip")), SRV.num(j.get("avoid_km")))
            return h.send(200, {"ok": True, "id": r["id"], "version": r["version"], "km": round(r["dist_m"] / 1000, 1),
                                "min": int(r["time_s"] / 60)}) or True
        if path == "/api/nav/via":
            # ekran: zjazd do wybranego miejsca (stacja, jedzenie) i powrót na trasę
            lat, lon = SRV.num(j.get("lat")), SRV.num(j.get("lon"))
            place = {"lat": SRV.num(j.get("plat")), "lon": SRV.num(j.get("plon")), "name": str(j.get("name") or "")[:30]}
            if None in (lat, lon, place["lat"], place["lon"]):
                return h.send(400, {"ok": False, "error": "brak pozycji"}) or True
            r = NAV.via_place(lat, lon, place, SRV.num(j.get("heading")))
            NAV.note_current(r["id"])
            return h.send(200, {"ok": True, "id": r["id"], "version": r["version"], "km": round(r["dist_m"] / 1000, 1),
                                "min": int(r["time_s"] / 60)}) or True
        if path == "/api/nav/log":
            entries = j.get("entries") if isinstance(j, dict) else j
            if not isinstance(entries, list):
                return h.send(400, {"ok": False, "error": "zle dane"}) or True
            clean = []
            for e in entries[:2000]:
                if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and isinstance(e.get("what"), str):
                    clean.append({"t": int(e["t"]), "what": e["what"][:24], "idx": e.get("idx"), "value": e.get("value"),
                                  "lat": e.get("lat"), "lon": e.get("lon")})
            NAV.screen_log(clean)
            return h.send(200, {"ok": True, "saved": len(clean)}) or True
        if path == "/api/nav/goto":
            r, place = goto(str(j.get("text") or ""), j.get("variant"), j.get("name"))
            return h.send(200, {"ok": True, "route": r, "place": place}) or True
    except ValueError as e:
        return h.send(400, {"ok": False, "error": str(e)}) or True
    except Exception as e:
        SRV.log("nawigacja (ekran):", path, e)
        return h.send(502, {"ok": False, "error": str(e)}) or True
    return h.send(404, {"ok": False, "error": "brak"}) or True
