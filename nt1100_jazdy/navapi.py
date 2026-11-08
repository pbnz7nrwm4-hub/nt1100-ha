"""Nawigacja: adresy HTTP dodatku (strona przez panel HA i port ekranu).

Strona (Ingress, bez klucza):
  GET  /nav.js, /api/nav/routes, /api/nav/route?id, /api/nav/gpx?id, /api/nav/search?q,
       /api/nav/poi?bbox, /api/nav/along?id|token&variant&kinds&max (POI wzdłuż trasy),
       /api/nav/nearby?kinds&lat&lon (miejsca przed motocyklem), /api/nav/resolve?text, /api/nav/settings,
       /api/nav/map, /api/nav/plan?n (zgodność jazdy), /api/nav/screen, /api/nav/recent,
       /api/nav/offline?from=lat,lon&to=lat,lon&variant&avoid (trasa tak, jak policzy ją ekran bez internetu),
       /api/nav/adres?miasto&ulica&nr&lat&lon (adres ze spisu na karcie, jak na ekranie)
       /api/nav/miejsca?q&lat&lon&kinds (nazwane miejsca ze spisu na karcie, jak na ekranie)
  POST /api/nav/plan, /api/nav/send, /api/nav/gpx, /api/nav/current, /api/nav/delete,
       /api/nav/settings, /api/nav/map/sync, /api/nav/goto, /api/nav/home, /api/nav/fav (ulubione), /api/nav/drive (jazda autem: korki), /api/nav/via (zjazd do miejsca)
Ekran (port 8098, klucz w X-Klucz albo ?klucz=):
  GET  /api/nav/ping, /api/nav/route.ntr?id, /api/nav/route.json?id, /api/nav/mapa/<plik> (też <kwadrat>.ntt.gz, graf .ntg.gz, adresy .nta.gz),
       /api/nav/traffic, /api/nav/fw, /api/nav/fw/bin, /api/nav/goto?text (skrót iOS),
       /api/nav/search?q&lat&lon (szukanie celu przez hotspot)
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

import graf
import nav
import ntt

SRV = None
NAV = None
PLANS = {}  # token -> (czas, lista tras) z ostatnich planowań
HOME_ENTITY_RE = re.compile(r"(cover|button|switch|lock)\.[a-z0-9_]+")
CALENDAR_ENTITY_RE = re.compile(r"calendar\.[a-z0-9_]+")
NAV_LIMITS = {"lean_popup_deg": (5, 60), "traffic_min": (1, 60), "offroute_m": (50, 1000), "car_alert_min": (2, 30)}
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
    threading.Thread(target=drive_loop, daemon=True).start()
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


# ---------------------------------------------------------------- jazda autem z OsmAnd: korki i objazd
# Trasa jedzie do OsmAnd jako GPX; dodatek co kilka minut sprawdza korki przed telefonem
# (pozycja z aplikacji Home Assistant) i gdy objazd jest szybszy, wysyła powiadomienie
# z linkiem do nowego GPX. iPhone nie pozwala podmienić trasy w OsmAnd w tle.
DRIVE_MAX_S = 8 * 3600
DRIVE_END_M = 800
DRIVE_SAVE_S = 180


def gpx_token(rid, ver):
    import hmac
    import hashlib
    return hmac.new(SRV.key().encode(), ("gpx:%d:%d" % (int(rid), int(ver))).encode(), hashlib.sha256).hexdigest()[:20]


def gpx_link(rid):
    """Link do GPX trasy działający poza HA (z telefonu, z powiadomienia): adres spoza domu
    z konfiguracji dodatku, a bez niego adres w sieci domowej. Podpisany dla tej wersji trasy."""
    r = NAV.route(rid)
    if not r:
        return ""
    base = (SRV.options().get("adres_spoza_domu") or "").strip().rstrip("/") or SRV.local_url()
    if not base:
        return ""
    return "%s/api/nav/trasa.gpx?id=%d&v=%d&t=%s" % (base, rid, r["version"], gpx_token(rid, r["version"]))


def phone_entity():
    """Telefon z aplikacją Home Assistant: z ustawień albo z celu powiadomień
    (notify.mobile_app_iphone → device_tracker.iphone)."""
    e = NAV.settings()["phone_tracker"]
    if e:
        return e
    t = SRV.notify_target()
    return "device_tracker." + t[len("mobile_app_"):] if t.startswith("mobile_app_") else ""


def phone_position():
    ent = phone_entity()
    if not ent:
        return None
    st = SRV.ha_call("GET", "/core/api/states/" + ent) or {}
    a = st.get("attributes") or {}
    lat, lon = SRV.num(a.get("latitude")), SRV.num(a.get("longitude"))
    if lat is None or lon is None:
        return None
    try:
        from datetime import datetime
        t = datetime.fromisoformat(str(st.get("last_updated")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        t = time.time()
    return {"lat": lat, "lon": lon, "age_s": int(time.time() - t), "entity": ent}


def drive():
    return NAV.state.get("drive") or None


def drive_set(**kw):
    d = drive()
    if d is None:
        return
    d.update(kw)
    NAV.save_state(drive=d)


def drive_start(rid):
    r = NAV.route(rid)
    if not r:
        raise ValueError("brak trasy")
    end = r["pts"][-1]
    d = {"rids": [rid], "name": r.get("name") or "trasa", "start": int(time.time()), "last": 0,
         "dest": [end[0], end[1]], "status": "czekam na pierwsze sprawdzenie", "alert": None}
    NAV.save_state(drive=d)
    return d


def drive_stop(status=""):
    NAV.save_state(drive=None)
    if status:
        SRV.log("jazda autem:", status)


def drive_loop():
    while True:
        time.sleep(30)
        try:
            d = drive()
            if d and time.time() - d.get("last", 0) >= NAV.settings()["traffic_min"] * 60:
                drive_check()
        except Exception as e:
            SRV.log("jazda autem: sprawdzanie nieudane:", e)
            drive_set(last=int(time.time()), status="błąd sprawdzania: %s" % str(e)[:80])


def jam_span(route, i, incidents):
    """Indeksy początku i końca korków (od pierwszego do końca ostatniego istotnego)."""
    cum = route["cum"]
    k0 = min(x["idx"] for x in incidents)
    last = max(incidents, key=lambda x: x["idx"])
    k1 = last["idx"]
    while k1 < len(cum) - 1 and cum[k1] - cum[last["idx"]] < max(200, last.get("len_m") or 0):
        k1 += 1
    return max(i + 1, k0 - 1), k1


def drive_check(now=None):
    now = now or time.time()
    d = drive()
    if not d:
        return None
    drive_set(last=int(now))
    if now - d["start"] > DRIVE_MAX_S:
        drive_stop("koniec po 8 h")
        return "koniec"
    pos = phone_position()
    if not pos:
        drive_set(status="brak pozycji telefonu (%s)" % (phone_entity() or "ustaw telefon w Ustawieniach nawigacji"))
        return "brak pozycji"
    if pos["age_s"] > 1200:
        drive_set(status="pozycja telefonu sprzed %d min" % (pos["age_s"] // 60))
        return "stara pozycja"
    here = (pos["lat"], pos["lon"])
    if ntt.dist_m(here, d["dest"]) < DRIVE_END_M:
        drive_stop("na miejscu")
        return "na miejscu"
    best = None
    for rid in d["rids"]:
        r = NAV.route(rid)
        if not r:
            continue
        i, dist = nav.nearest_index(r["pts"], here)
        if best is None or dist < best[2]:
            best = (rid, r, dist, i)
    if not best:
        drive_stop("trasa usunięta")
        return "brak trasy"
    rid, route, dist, i = best
    if dist > 1000:
        drive_set(status="telefon %.1f km od trasy (OsmAnd prowadzi po swojemu)" % (dist / 1000))
        return "poza trasa"
    tr = NAV.traffic(rid, pos["lat"], pos["lon"])
    if tr is None:
        drive_set(status="brak klucza TomTom (Ustawienia nawigacji)")
        return "brak klucza"
    big = [x for x in tr["incidents"] if x["delay_s"] >= 60]
    delay = sum(x["delay_s"] for x in big)
    hhmm = time.strftime("%H:%M", time.localtime(now))
    if delay < NAV.settings()["car_alert_min"] * 60:
        drive_set(status="%s: bez korków na trasie przed Tobą" % hhmm + (" (opóźnienie %d min)" % round(delay / 60) if delay >= 60 else ""))
        return "ok"
    first = min(big, key=lambda x: x["km"])
    al = d.get("alert") or {}
    # to samo zgłoszenie (korek w tym samym miejscu, nie urósł o 3 min) nie wraca co 5 minut
    same = al.get("rid") == rid and abs(al.get("abs_km", -99) - (route["cum"][first["idx"]] / 1000.0)) < 2 \
        and delay < al.get("delay_s", 0) + 180
    if same:
        drive_set(status="%s: korek %d min za %s km (już zgłoszony)" % (hhmm, round(delay / 60), first["km"]))
        return "zgloszony"
    where = ("za %s km" % str(first["km"]).replace(".", ",")) + (" (%s)" % first["text"] if first.get("text") else "")
    # objazd: od telefonu do celu (i pozostałych punktów) z zakazanym odcinkiem korka
    k0, k1 = jam_span(route, i, big)
    points = [{"lat": pos["lat"], "lon": pos["lon"], "name": "pozycja"}]
    for w in route.get("waypoints") or []:
        if w["idx"] > max(i + 5, k1):
            p = route["pts"][w["idx"]]
            points.append({"lat": p[0], "lon": p[1], "name": w.get("name") or ""})
    end = route["pts"][-1]
    if len(points) < 2 or (points[-1]["lat"], points[-1]["lon"]) != (end[0], end[1]):
        points.append({"lat": end[0], "lon": end[1], "name": "cel"})
    jam = route["pts"][k0:k1 + 1] if k1 - k0 >= 1 else []
    routes, errors = NAV.plan(points, ["szybko"], route.get("avoid") or NAV.settings()["avoid"],
                              ("objazd: " + d["name"])[:40], skip=route.get("skip"), avoid_segment=jam)
    rest_s = route.get("time_s", 0) * (1 - route["cum"][i] / max(1.0, route["dist_m"])) + delay
    alert = {"rid": rid, "abs_km": route["cum"][first["idx"]] / 1000.0, "delay_s": delay, "t": int(now)}
    if routes:
        alt = routes[0]
        alt["source"] = "objazd korka"
        alt_id = NAV.store_route(alt, make_current=False)
        tr2 = NAV.traffic(alt_id, pos["lat"], pos["lon"]) or {"incidents": []}
        alt_s = alt.get("time_s", 0) + sum(x["delay_s"] for x in tr2["incidents"] if x["delay_s"] >= 60)
        save = rest_s - alt_s
        if save >= DRIVE_SAVE_S:
            link = gpx_link(alt_id)
            alert.update(alt=alt_id, save_s=int(save))
            d = drive() or d
            drive_set(rids=(d.get("rids") or [])[-3:] + [alt_id], alert=alert,
                      status="%s: korek %d min %s – objazd szybszy o %d min (wysłany)" % (hhmm, round(delay / 60), where, round(save / 60)))
            SRV.send_notification("Korek %d min %s" % (round(delay / 60), where),
                                  "Objazd szybszy o ok. %d min (%s km). Dotknij, żeby otworzyć nową trasę, i wybierz „Otwórz w OsmAnd”."
                                  % (round(save / 60), round(alt["dist_m"] / 1000)),
                                  tag="nt1100_korek", url=link or None, link_text="Otwórz nową trasę")
            return "objazd"
        NAV.delete_route(alt_id)
    drive_set(alert=alert, status="%s: korek %d min %s – objazd nie jest szybszy" % (hhmm, round(delay / 60), where))
    SRV.send_notification("Korek %d min %s" % (round(delay / 60), where),
                          "Objazd nie jest szybszy, zostań na trasie.", tag="nt1100_korek")
    return "bez objazdu"


def nav_settings_apply(j):
    """Ustawienia nawigacji ze strony (klucz 'nav' w /api/settings)."""
    if not isinstance(j, dict):
        return "zle dane nawigacji"
    cur = dict(SRV.settings().get("nav") or {})
    for k in ("engine_url", "map_url", "tomtom_key", "google_key", "default_variant"):
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
    if "phone_tracker" in j:
        v = str(j["phone_tracker"] or "").strip()
        if v and not re.fullmatch(r"(device_tracker|person)\.[a-z0-9_]+", v):
            return "telefon: encja device_tracker.… albo person.…"
        cur["phone_tracker"] = v
    for k in ("gate_entity", "garage_entity"):
        if k in j:
            v = str(j[k] or "").strip()
            if v and not HOME_ENTITY_RE.fullmatch(v):
                return "brama/garaż: encja cover.…, button.…, switch.… albo lock.…"
            cur[k] = v
    if "calendar_entity" in j:
        v = str(j["calendar_entity"] or "").strip()
        if v and not CALENDAR_ENTITY_RE.fullmatch(v):
            return "kalendarz: encja calendar.…"
        cur["calendar_entity"] = v
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
        out = {"lat": sc["lat"], "lon": sc["lon"], "src": "ekran", "age_s": int(time.time() - sc.get("t", 0)),
               "speed": sc.get("speed") or 0}
        home = NAV.settings().get("home")
        if home:
            out["home_m"] = int(nav.ntt.dist_m((sc["lat"], sc["lon"]), (home["lat"], home["lon"])))
        return out
    if q_lat is not None and q_lon is not None:
        return {"lat": q_lat, "lon": q_lon, "src": "telefon", "age_s": 0}
    return None


DEMO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo-trasa.json")


def demo_route():
    """Trasa demo (22 km) z fotoradarem, odcinkowym pomiarem
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


def goto(text, variant=None, name=None, dest=None, avoid=None):
    """Cel z tekstu/linku (albo gotowy punkt dest = {lat, lon, name}, np. adres wybrany na ekranie
    z karty): trasa z pozycji motocykla (albo domu) i oznaczenie jako bieżąca dla ekranu.
    avoid = lista omijania z ekranu (domyślnie z ustawień)."""
    place = dest if dest else (fav_place(text) or NAV.resolve_place(text))
    if not place:
        raise ValueError("nie rozpoznałem miejsca w: %s" % (text or "")[:60])
    start = start_point()
    if not start:
        raise ValueError("nie znam pozycji motocykla ani domu (ustaw dom w zakładce Nawigacja)")
    s = NAV.settings()
    v = variant or s["go_variant"]
    av = [a for a in avoid if a in graf.AVOID] if isinstance(avoid, list) else s["avoid"]
    routes, errors = NAV.plan([start, {"lat": place["lat"], "lon": place["lon"], "name": place["name"]}], [v],
                              av, name or ("→ " + (place["name"] or "cel"))[:40], with_weather=True)
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
        if path == "/api/nav/drive":
            return h.send(200, {"drive": drive(), "phone": phone_entity()}) or True
        if path == "/api/nav/routes":
            lst = NAV.list_routes()
            lst.update(map=NAV.map_status(), zip=NAV.zip_status(), build=NAV.build_status(), engine=NAV.engine_ok(), screen=NAV.screen_position(),
                       settings=NAV.settings(), recent=recent(), variants=nav.VARIANTS, mix=nav.MIX,
                       avoid_all=nav.AVOID, curvy_default=nav.CURVY_DEFAULT,
                       curvy_levels_default=nav.CURVY_LEVELS_DEFAULT)
            lst["settings"]["tomtom_key"] = bool(lst["settings"]["tomtom_key"])
            lst["settings"]["google_key"] = bool(lst["settings"]["google_key"])
            lst["settings"]["google_usage"] = NAV.google_usage()
            lst["drive"] = drive()
            lst["phone_entity"] = phone_entity()
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
            return h.send(200, nav.to_gpx(r, osmand=q.get("plain") != "1").encode(), "application/gpx+xml",
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
        if path == "/api/nav/adres":
            # adres tak, jak znajdzie go ekran bez internetu (spis z karty)
            if not NAV.addresses.available():
                return h.send(200, {"ok": False, "error": "mapa bez adresów (potrzebna mapa w wersji 4)"}) or True
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            near = (lat, lon) if lat is not None and lon is not None else None
            return h.send(200, NAV.addresses.find(q.get("miasto") or "", q.get("ulica") or "", q.get("nr") or "",
                                                  near)) or True
        if path == "/api/nav/miejsca":
            # nazwane miejsca tak, jak znajdzie je ekran bez internetu (spis a_poi.nta z karty)
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            near = (lat, lon) if lat is not None and lon is not None else None
            kinds = {int(k) for k in q.get("kinds", "").split(",") if k.strip().isdigit()} or None
            res = NAV.addresses.places((q.get("q") or "")[:60], near, kinds)
            if not res and not NAV.addresses.poi_index():
                return h.send(200, {"results": [], "error": "mapa bez spisu miejsc (potrzebna mapa w wersji 5)"}) or True
            return h.send(200, {"results": res}) or True
        if path == "/api/nav/offline":
            # trasa tak, jak policzy ją ekran bez internetu (graf z karty), do porównania z silnikiem
            try:
                a = [float(x) for x in q.get("from", "").split(",")]
                b = [float(x) for x in q.get("to", "").split(",")]
                assert len(a) == 2 and len(b) == 2
            except (ValueError, AssertionError):
                return h.send(400, {"error": "podaj from=lat,lon i to=lat,lon"}) or True
            if not NAV.graph.available():
                return h.send(200, {"ok": False, "error": "mapa bez grafu tras (potrzebna mapa w wersji 3)"}) or True
            s = NAV.settings()
            avoid = [x for x in q.get("avoid", ",".join(s["avoid"])).split(",") if x]
            t0 = time.time()
            r = graf.route(NAV.graph, tuple(a), tuple(b), q.get("variant") or s["go_variant"], avoid, s["curvy"])
            if not r:
                return h.send(200, {"ok": False, "error": "brak drogi w grafie"}) or True
            pts = graf.geometry(NAV.graph, NAV.map, r)
            return h.send(200, {"ok": True, "km": r["km"], "min": r["min"], "variant": r["variant"], "avoid": r["avoid"],
                                "nodes": r["nodes"], "snap_m": r["snap_m"], "ms": int((time.time() - t0) * 1000),
                                "pts": [[round(y, 6), round(x, 6)] for y, x in pts]}) or True
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
            s["google_key"] = bool(s["google_key"])
            s["google_usage"] = NAV.google_usage()
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
            s["google_key"] = bool(s["google_key"])
            s["google_usage"] = NAV.google_usage()
            return h.send(200, s) or True
        if path == "/api/nav/fuel_prices":
            return fuel_prices_reply(h, j)  # 1.5.34: ceny stacji też w panelu
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
        if path == "/api/nav/drive":
            if j.get("stop"):
                drive_stop("zakończone ręcznie")
                return h.send(200, {"drive": None}) or True
            d = drive_start(int(j.get("id") or 0))
            if j.get("check_now"):
                drive_check()
            return h.send(200, {"drive": drive(), "link": gpx_link(d["rids"][0]), "phone": phone_entity()}) or True
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

SCREEN_KINDS = ("ekran", "ekran5")   # ekran 2,8" (1.x) i ekran 5" (2.x): osobne paczki


def screen_kind(q):
    k = (q.get("k") or "").strip()
    return k if k in SCREEN_KINDS else "ekran"


def screen_kind_of(fw):
    """Paczka dla ekranu o zgłoszonej wersji: 2.x = ekran 5", 1.x = 2,8" (od 1.5.35 bez paczki w dodatku).
    Ekran nieznany = ekran 5" (jedyny na motocyklu)."""
    try:
        return "ekran5" if int(str(fw or "").split(".")[0]) >= 2 else "ekran"
    except ValueError:
        return "ekran5"


def screen_firmware_offer(kind="ekran"):
    if SRV is None:  # nawigacja jeszcze nie wystartowała
        return None
    kind = kind if kind in SCREEN_KINDS else "ekran"
    j = SRV.read_json(os.path.join(SRV.FIRMWARE, kind + ".json"), {})
    path = os.path.join(SRV.FIRMWARE, kind + ".bin")
    if not j.get("version") or not os.path.exists(path):
        return None
    return {"version": j["version"], "size": os.path.getsize(path), "path": path}


# ---------------------------------------------------------------- dom dla ekranu 5" (brama, garaż, trasy)

HOME_STATES = {
    "gate": {"open": "otwarta", "closed": "zamknięta", "opening": "otwiera się", "closing": "zamyka się",
             "on": "otwarta", "off": "zamknięta", "unlocked": "otwarta", "locked": "zamknięta"},
    "garage": {"open": "otwarty", "closed": "zamknięty", "opening": "otwiera się", "closing": "zamyka się",
               "on": "otwarty", "off": "zamknięty", "unlocked": "otwarty", "locked": "zamknięty"},
}


def home_entity(which):
    return NAV.settings()["gate_entity" if which == "gate" else "garage_entity"]


def home_state(which):
    """{"state": "zamknięta", "open": False} albo None, gdy encji nie ustawiono."""
    ent = home_entity(which)
    if not ent:
        return None
    try:
        st = SRV.ha_call("GET", "/core/api/states/" + ent, timeout=5) or {}
    except Exception as e:
        SRV.log("brama/garaż: stan", ent, e)
        st = {}
    raw = str(st.get("state") or "")
    if ent.startswith("button."):
        return {"state": "przycisk", "open": False}
    if not raw or raw in ("unknown", "unavailable"):
        return {"state": "stan nieznany", "open": False}
    return {"state": HOME_STATES[which].get(raw, raw)[:20], "open": raw in ("open", "opening", "on", "unlocked")}


def screen_offline_settings(s):
    return {"variant": s["go_variant"], "avoid": s["avoid"], "curvy": s["curvy"],
            "fav": [{"name": f.get("name") or "", "lat": f["lat"], "lon": f["lon"]} for f in s["fav"]
                    if isinstance(f.get("lat"), (int, float)) and isinstance(f.get("lon"), (int, float))]}


def screen_home():
    s = NAV.settings()
    home = s["home"]
    if not home and not (s["gate_entity"] or s["garage_entity"]):
        return None
    out = {"lat": home["lat"], "lon": home["lon"], "name": home.get("name") or "Dom"} if home else {}
    for w in ("gate", "garage"):
        st = home_state(w)
        if st:
            out[w] = st
    return out


def home_press(which):
    """Jak pilot: brama w ruchu = stop, inaczej otwórz/zamknij (cover), naciśnij (button),
    przełącz (switch), otwórz/zamknij (lock)."""
    ent = home_entity(which)
    if not ent:
        raise ValueError("bramy/garażu nie ustawiono w dodatku")
    dom = ent.split(".", 1)[0]
    raw = ""
    if dom in ("cover", "lock"):
        raw = str((SRV.ha_call("GET", "/core/api/states/" + ent, timeout=5) or {}).get("state") or "")
    if dom == "cover":
        svc = "stop_cover" if raw in ("opening", "closing") else "toggle"
    elif dom == "button":
        svc = "press"
    elif dom == "switch":
        svc = "toggle"
    else:
        svc = "lock" if raw == "unlocked" else "unlock"
    SRV.ha_call("POST", "/core/api/services/%s/%s" % (dom, svc), {"entity_id": ent})
    SRV.log("Ekran:", "brama" if which == "gate" else "garaż", dom + "." + svc)
    return {"ok": True, "service": dom + "." + svc, "home": screen_home()}


def calendar_next(ent, n=3, now=None):
    """Najbliższe wydarzenia z kalendarza HA (3 dni), po polsku: [{"when": "dziś 14:00", "title": ...}]."""
    import datetime
    now = now or time.time()
    try:
        start = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        end = start + datetime.timedelta(days=3)
        q = urllib.parse.urlencode({"start": start.isoformat().replace("+00:00", "Z"),
                                    "end": end.isoformat().replace("+00:00", "Z")})
        ev = SRV.ha_call("GET", "/core/api/calendars/%s?%s" % (ent, q), timeout=5) or []
    except Exception as e:
        SRV.log("kalendarz:", ent, e)
        return []
    items = []
    for e in ev if isinstance(ev, list) else []:
        st = e.get("start") or {}
        title = str(e.get("summary") or "")[:40]
        if not title:
            continue
        if st.get("dateTime"):
            t = nav.parse_iso(st["dateTime"])
            if t is None:
                continue
            items.append((t, calendar_when(t, now, True), title))
        elif st.get("date"):
            t = nav.parse_iso(st["date"] + "T00:00:00" + time.strftime("%z", time.localtime(now))[:3] + ":" + time.strftime("%z", time.localtime(now))[3:])
            if t is None:
                continue
            items.append((t, calendar_when(t, now, False), title))
    items.sort()
    return [{"when": w, "title": t} for _, w, t in items[:n]]


def calendar_when(t, now, with_time):
    """„dziś 14:00”, „jutro 9:00”, „pt 9:00” (czas lokalny HA)."""
    lt, ln = time.localtime(t), time.localtime(now)
    day = (lt.tm_year, lt.tm_yday)
    today = (ln.tm_year, ln.tm_yday)
    lt_tomorrow = time.localtime(now + 86400)
    if day == today:
        d = "dziś"
    elif day == (lt_tomorrow.tm_year, lt_tomorrow.tm_yday):
        d = "jutro"
    else:
        d = ("pn", "wt", "śr", "cz", "pt", "sb", "nd")[lt.tm_wday]
    return d + (" %d:%02d" % (lt.tm_hour, lt.tm_min) if with_time else "")


# 1.5.40 (ekran 2.2.1, Adrian 8.11: "online = widzi Wi-Fi, ma połączenie z dodatkiem i z silnikiem tras"):
# whether the route engine answers /health, checked in the background at most once a minute so the
# ping of the screen never waits for it (the engine may stand during the nightly map rebuild)
_ENGINE = {"ok": None, "at": 0.0, "busy": False}
ENGINE_CHECK_S = 60


def engine_status():
    url = NAV.settings()["engine_url"]
    if not url:
        return False
    now = time.time()
    if not _ENGINE["busy"] and now - _ENGINE["at"] > ENGINE_CHECK_S:
        _ENGINE["busy"] = True

        def check():
            try:
                _ENGINE["ok"] = SRV.engine_alive(url)
            finally:
                _ENGINE["at"] = time.time()
                _ENGINE["busy"] = False
        threading.Thread(target=check, daemon=True).start()
    return _ENGINE["ok"]


def screen_routes(idx, n=8):
    """Trasy do wyboru na postoju (ekran 5"): ostatnie n, bieżąca pierwsza."""
    rs = sorted(idx.get("routes") or [], key=lambda r: (-(r.get("created") or 0), -r["id"]))
    cur = idx.get("current")
    rs = [r for r in rs if r["id"] == cur] + [r for r in rs if r["id"] != cur]
    return [{"id": r["id"], "version": r.get("version") or 0, "name": (r.get("name") or "")[:40], "km": r.get("km") or 0,
             "fav": bool(r.get("fav"))} for r in rs[:n]]


def screen_authorized(h, q):
    """Ekran: własny klucz ekranu zawsze; klucz skrzynki tylko, dopóki nie włączono „tylko klucz ekranu”
    (ekrany sprzed 1.5.35 mają wpisany klucz skrzynki). Klucz w nagłówku X-Klucz albo ?klucz=."""
    import hmac
    got = [x for x in ((h.headers.get("X-Klucz") or "").strip(), (q.get("klucz") or "").strip()) if x]
    keys = [SRV.screen_key()]
    if not SRV.settings().get("screen_key_only"):
        keys.append(SRV.key())
    return any(hmac.compare_digest(g.encode(), k.encode()) for g in got for k in keys)


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
    if path == "/api/nav/trasa.gpx":
        # link z powiadomienia (OsmAnd): podpis tylko dla tej trasy i wersji, bez klucza skrzynki
        import hmac
        rid = int(SRV.num(q.get("id")) or 0)
        r = NAV.route(rid) if rid > 0 else None
        if not r or not hmac.compare_digest(str(q.get("t") or ""), gpx_token(rid, r["version"])) \
                or str(q.get("v")) != str(r["version"]):
            return h.send(404, "trasa nieaktualna albo zły link", "text/plain") or True
        return h.send(200, nav.to_gpx(r, osmand=True).encode(), "application/gpx+xml",
                      {"Content-Disposition": gpx_disposition(r.get("name"))}) or True
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
                   "traffic": bool(s["tomtom_key"]),
                   "fw": (screen_firmware_offer(screen_kind(q)) or {}).get("version") or "",
                   # ekran 5": dom (brama, garaż) i trasy do wyboru na postoju
                   "home": screen_home(), "routes": screen_routes(idx),
                   # 1.5.40: the route engine answers (None = not checked yet)
                   "engine": engine_status()}
            # 1.5.23: kalendarz domu na postoju (3 najbliższe wydarzenia)
            if s["calendar_entity"]:
                out["calendar"] = calendar_next(s["calendar_entity"])
            if screen_kind(q) == "ekran5":
                # nawigacja offline na ekranie: te same suwaki wariantów i omijanie co w planerze
                out["offline"] = screen_offline_settings(s)
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
        if path.startswith("/api/nav/mapa/") and path[-7:] in (".ntt.gz", ".ntg.gz", ".nta.gz"):
            p = NAV.map_gz(path.rsplit("/", 1)[1][:-3])
            if not p:
                return h.send(404, {"ok": False, "error": "brak pliku"}) or True
            return h.send_path(p, "application/gzip") or True
        if path.startswith("/api/nav/mapa/"):
            p = NAV.map_file(path.rsplit("/", 1)[1])
            if not p:
                return h.send(404, {"ok": False, "error": "brak pliku"}) or True
            return h.send_path(p, "application/octet-stream") or True
        if path == "/api/nav/search":
            # ekran 5" przez hotspot: szukanie celu w internecie (adresy, firmy, miejsca) i w ulubionych
            qq = (q.get("q") or "").strip()
            if len(qq) < 2:
                return h.send(200, {"results": []}) or True
            fav = fav_place(qq)
            res = NAV.search(qq, SRV.num(q.get("lat")), SRV.num(q.get("lon")), 6)
            out = ([dict(fav, label=fav["name"], type="ulubione")] if fav else []) + \
                [{"name": r["name"][:40], "label": r["label"][:80], "lat": r["lat"], "lon": r["lon"]} for r in res
                 if r.get("lat") is not None]
            return h.send(200, {"results": out}) or True
        if path == "/api/nav/traffic":
            rid = int(SRV.num(q.get("id")) or 0)
            lat, lon = SRV.num(q.get("lat")), SRV.num(q.get("lon"))
            if lat is None or lon is None:
                return h.send(400, {"ok": False, "error": "brak pozycji"}) or True
            return h.send(200, {"ok": True, "traffic": NAV.traffic(rid, lat, lon)}) or True
        if path == "/api/nav/fw":
            note_screen(h, q)
            o = screen_firmware_offer(screen_kind(q))
            return h.send(200, {"version": o["version"] if o else "", "size": o["size"] if o else 0}) or True
        if path == "/api/nav/fw/bin":
            o = screen_firmware_offer(screen_kind(q))
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


def fuel_prices_reply(h, j):
    """1.5.34: wspólna odpowiedź na POST /api/nav/fuel_prices (ekran 5" i panel): ceny Pb95 z Google, pamięć 1 h."""
    places = j.get("places") if isinstance(j, dict) else None
    if not isinstance(places, list):
        return h.send(400, {"ok": False, "error": "zle dane"}) or True
    try:
        prices = NAV.fuel_prices([p for p in places if isinstance(p, dict)][:6])
    except ValueError as e:
        return h.send(200, {"ok": False, "error": str(e), "prices": [None] * min(6, len(places))}) or True
    return h.send(200, {"ok": True, "prices": prices}) or True


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
        if path == "/api/nav/fuel_prices":
            # 1.5.23: ekran 5" – ceny Pb95 dla stacji z karty (Google przez dodatek)
            return fuel_prices_reply(h, j)
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
            lat, lon = SRV.num(j.get("lat")), SRV.num(j.get("lon"))
            if lat is not None and lon is not None and (lat or lon):
                # ekran 5" „Do domu”: start z jego pozycji teraz
                NAV.screen_seen(lat, lon, 0, SRV.num(j.get("heading")) or 0, {"t_seen": int(time.time())})
            dest = None
            dlat, dlon = SRV.num(j.get("dest_lat")), SRV.num(j.get("dest_lon"))
            if dlat is not None and dlon is not None:
                # ekran 5": cel wybrany na ekranie (adres z karty, ulubione), te same ustawienia co offline
                dest = {"lat": dlat, "lon": dlon, "name": str(j.get("dest_name") or "")[:40]}
            r, place = goto(str(j.get("text") or ""), j.get("variant"), j.get("name"), dest, j.get("avoid"))
            return h.send(200, {"ok": True, "route": r, "place": place}) or True
        if path == "/api/nav/use":
            # ekran 5": jeździec wybrał na postoju inną trasę z listy
            rid = int(SRV.num(j.get("id")) or 0)
            if not any(r["id"] == rid for r in NAV.index()["routes"]):
                return h.send(404, {"ok": False, "error": "brak trasy"}) or True
            NAV.set_current(rid)
            NAV.note_current(rid)
            return h.send(200, {"ok": True, "current": rid}) or True
        if path == "/api/nav/dom":
            which = j.get("which")
            if which not in ("gate", "garage"):
                return h.send(400, {"ok": False, "error": "zle dane"}) or True
            return h.send(200, home_press(which)) or True
    except ValueError as e:
        return h.send(400, {"ok": False, "error": str(e)}) or True
    except Exception as e:
        SRV.log("nawigacja (ekran):", path, e)
        return h.send(502, {"ok": False, "error": str(e)}) or True
    return h.send(404, {"ok": False, "error": "brak"}) or True
