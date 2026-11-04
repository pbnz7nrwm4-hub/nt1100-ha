"""NT1100 Jazdy: Home Assistant add-on for the NT1100 ride recorder.

Two HTTP servers:
  * port 8099 (Home Assistant Ingress, panel in the side menu): the same ride
    page as on the box, with the same /api/* (rides, names, deletion, files)
    and the add-on's own settings (odometer, service, notifications);
  * port 8098 (published by Home Assistant, also behind Cloudflare): only
    /api/ping, /api/ingest and the box firmware, all need the key in the
    "X-Klucz" header.

Rides are kept in /share/nt1100/rides/NNNN.{trk,thm,json,nam,rep,mtl,wx},
like on the box's SD card (.wx = weather along the route, from Open-Meteo).
Entities go to Home Assistant over MQTT discovery (device "NT1100"); without
MQTT they are set over the REST API like before.
"""

import hmac
import json
import math
import os
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import navapi  # noqa: E402

VERSION = "1.5.11"
SHARE = os.environ.get("NT_SHARE", "/share/nt1100")
DATA = os.environ.get("NT_DATA", "/data")
HERE = os.path.dirname(os.path.abspath(__file__))
WWW = os.environ.get("NT_WWW", os.path.join(HERE, "www"))
INGRESS_PORT = int(os.environ.get("NT_INGRESS_PORT", "8099"))
INGEST_PORT = int(os.environ.get("NT_INGEST_PORT", "8098"))
# Only Home Assistant's ingress proxy may open the page (no login otherwise).
INGRESS_PEERS = set(os.environ.get("NT_INGRESS_PEERS", "172.30.32.2").split(","))
SUPERVISOR = os.environ.get("NT_SUPERVISOR", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
WEATHER_ON = os.environ.get("NT_WEATHER", "1") == "1"  # tests switch the network off

RIDES = os.path.join(SHARE, "rides")
INCOMING = os.path.join(SHARE, "incoming")
CACHE = os.path.join(SHARE, "cache")
INDEX = os.path.join(SHARE, "index.json")
STATE = os.path.join(DATA, "stan.json")
KEYFILE = os.path.join(DATA, "klucz")
FIRMWARE = os.environ.get("NT_FIRMWARE", os.path.join(HERE, "firmware"))
# Files of a ride sent by the box (the summary .json last = ride complete).
EXTS = ("trk", "thm", "nam", "rep", "mtl", "json")
# Sent again after the ride was saved: a changed name, the raw log copy.
LATE_EXTS = ("nam", "rep", "mtl")
# Every file of a ride kept here (.wx made by this add-on).
ALL_EXTS = EXTS + ("wx",)
MAX_FILE = 40 * 1024 * 1024
MAX_RAW = 1024 * 1024 * 1024
LOCK = threading.RLock()

DEFAULT_SERVICE = [
    {"id": "olej", "name": "Olej i filtr oleju", "interval_km": 12000, "last_km": None},
    {"id": "lancuch", "name": "Smarowanie łańcucha", "interval_km": 800, "last_km": None},
    {"id": "przeglad", "name": "Przegląd okresowy", "interval_km": 12000, "last_km": None},
]
SERVICE_WARN_KM = 300


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def now_ms():
    return int(time.time() * 1000)


# ---------------------------------------------------------------- storage

def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def options():
    o = read_json(os.path.join(DATA, "options.json"), {})
    return o if isinstance(o, dict) else {}


def ride_path(n, ext):
    return os.path.join(RIDES, "%04d.%s" % (n, ext))


def key():
    k = (options().get("klucz") or "").strip()
    if k:
        return k
    try:
        with open(KEYFILE, encoding="utf-8") as f:
            k = f.read().strip()
    except FileNotFoundError:
        k = ""
    if not k:
        k = secrets.token_urlsafe(18)
        with open(KEYFILE, "w", encoding="utf-8") as f:
            f.write(k)
        log("Nowy klucz dla skrzynki zapisany (widoczny w zakladce Ustawienia na stronie dodatku).")
    return k


def state():
    s = read_json(STATE, {})
    return s if isinstance(s, dict) else {}


def save_state(**kw):
    with LOCK:
        s = state()
        s.update(kw)
        write_json(STATE, s)


def ride_numbers():
    out = set()
    try:
        names = os.listdir(RIDES)
    except FileNotFoundError:
        return []
    for name in names:
        m = re.fullmatch(r"(\d+)\.json", name)
        if m:
            out.add(int(m.group(1)))
    return sorted(out)


def read_small(path, limit=65536):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(limit)
    except Exception:
        return ""


def summary(n):
    try:
        j = json.loads(read_small(ride_path(n, "json")))
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def name_info(n):
    try:
        j = json.loads(read_small(ride_path(n, "nam")))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def report(n):
    try:
        j = json.loads(read_small(ride_path(n, "rep")))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def ride_key(ride_id, json_bytes):
    """The same ride sent again lands on the same number."""
    if ride_id and ride_id not in ("bez-czasu",) and not ride_id.startswith("nr"):
        return ride_id
    return "%s-%08x" % (ride_id or "jazda", zlib.crc32(json_bytes) & 0xFFFFFFFF)


def parse_time(iso):
    """Start of a ride ("2026-10-04T07:46:40Z") in seconds, or None."""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def fmt_num(v, d=0):
    f = num(v)
    if f is None:
        return None
    return round(f, d) if d else int(round(f))


def km_str(v):
    return str(fmt_num(v, 1) or 0).replace(".", ",")


def hm(minutes):
    m = int(round(float(minutes or 0)))
    return "%d h %02d min" % (m // 60, m % 60) if m >= 60 else "%d min" % m


def read_track(n):
    """Points of the route: [lat, lon, lean, speed, alt, t] (1 per second
    from .trk, or the coarser .thm)."""
    for ext in ("trk", "thm"):
        p = ride_path(n, ext)
        if not os.path.exists(p):
            continue
        pts = []
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                a = line.strip().split(",")
                if len(a) < 6 or not a[0]:
                    continue
                lat, lon = num(a[0]), num(a[1])
                if lat is None or lon is None or (lat == 0 and lon == 0):
                    continue
                pts.append([lat, lon, num(a[2]), num(a[3]), num(a[4]), num(a[5])])
        if pts:
            return pts, ext
    return [], None


# ---------------------------------------------------------------- route analysis

def dist_m(a, b):
    """Distance between two points in metres (equirectangular, fine at this scale)."""
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return 6371000.0 * math.hypot(x, y)


def bearing(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return math.degrees(math.atan2(x, y)) % 360.0


CURVY_STEP_M = 50.0     # the route sampled every 50 m (GPS noise stays out)
CURVY_MIN_TURN = 4.0    # smaller direction changes are noise
CORNER_LEAN = 15.0      # a corner: lean of at least 15 degrees ...
CORNER_SPEED = 15.0     # ... at 15 km/h or more
CURVY_LEVELS = ((30, "prosta"), (80, "lekko kręta"), (150, "kręta"), (1e9, "bardzo kręta"))


def curviness(pts):
    """How curvy the route was: turning in degrees per km, corners per 100 km
    and the 5 deepest corners. The ride page computes the same in JS."""
    total_turn = 0.0
    dist = 0.0
    anchor = None
    last_b = None
    for p in pts:
        if anchor is None:
            anchor = p
            continue
        d = dist_m(anchor, p)
        if d < CURVY_STEP_M:
            continue
        dist += d
        b = bearing(anchor, p)
        moving = p[3] is None or p[3] >= 10
        if last_b is not None and moving:
            turn = abs((b - last_b + 540.0) % 360.0 - 180.0)
            if CURVY_MIN_TURN <= turn <= 150:
                total_turn += turn
        last_b = b
        anchor = p
    corners = []
    cur = None
    for i, p in enumerate(pts):
        lean, speed = p[2], p[3]
        if lean is not None and speed is not None and abs(lean) >= CORNER_LEAN and speed >= CORNER_SPEED:
            if cur is None or (p[5] is not None and cur["t_end"] is not None and p[5] - cur["t_end"] > 2):
                if cur:
                    corners.append(cur)
                cur = {"i": i, "lean": lean, "speed": speed, "t": p[5], "lat": p[0], "lon": p[1], "t_end": p[5]}
            else:
                if abs(lean) > abs(cur["lean"]):
                    cur.update(i=i, lean=lean, speed=speed, t=p[5], lat=p[0], lon=p[1])
                cur["t_end"] = p[5]
        elif cur is not None and (p[5] is None or cur["t_end"] is None or p[5] - cur["t_end"] > 2):
            corners.append(cur)
            cur = None
    if cur:
        corners.append(cur)
    km = dist / 1000.0
    deg_km = total_turn / km if km >= 1 else None
    rating = None
    if deg_km is not None:
        rating = next(name for lim, name in CURVY_LEVELS if deg_km < lim)
    top = sorted(corners, key=lambda c: -abs(c["lean"]))[:5]
    return {
        "deg_km": None if deg_km is None else round(deg_km),
        "rating": rating,
        "corners": len(corners),
        "per100": None if km < 1 else round(len(corners) * 100.0 / km),
        "left": sum(1 for c in corners if c["lean"] < 0),
        "right": sum(1 for c in corners if c["lean"] > 0),
        "top": [{"i": c["i"], "lean": round(c["lean"]), "speed": round(c["speed"]), "t": c["t"],
                 "lat": round(c["lat"], 6), "lon": round(c["lon"], 6)} for c in top],
    }


_CURVY = {}


def curvy_of(n):
    """Curviness of a ride; the description follows the thresholds set in the
    Nawigacja settings (the cached value keeps only the numbers)."""
    v = _curvy_of(n)
    if v and v.get("deg_km") is not None:
        lv = (settings().get("nav") or {}).get("curvy_levels")
        v = dict(v, rating=navapi.nav.curvy_name(v["deg_km"], lv if lv else None))
    return v


def _curvy_of(n):
    """Curviness of a ride, cached in /share/nt1100/cache (keyed by file time)."""
    p = ride_path(n, "trk")
    if not os.path.exists(p):
        return None
    mt = int(os.path.getmtime(p))
    with LOCK:
        if not _CURVY:
            _CURVY.update(read_json(os.path.join(CACHE, "kretosc.json"), {}))
        c = _CURVY.get(str(n))
        if c and c.get("mt") == mt:
            return c["v"]
    pts, _ = read_track(n)
    v = curviness(pts)
    with LOCK:
        _CURVY[str(n)] = {"mt": mt, "v": v}
        os.makedirs(CACHE, exist_ok=True)
        write_json(os.path.join(CACHE, "kretosc.json"), _CURVY)
    return v


def problems(rep):
    """Problems of a ride from its report (.rep), in plain words."""
    out = []
    if not rep:
        return out
    g = rep.get("gnss") or {}
    if g:
        if not g.get("found"):
            out.append("GPS nie działał")
        else:
            if (num(g.get("fix_pct")) or 0) < 80:
                out.append("GPS miał pozycję tylko przez %d%% czasu" % (fmt_num(g.get("fix_pct")) or 0))
            if (num(g.get("outages")) or 0) > 3:
                out.append("GPS gubił pozycję %d× (razem %d s)" % (fmt_num(g.get("outages")), fmt_num(g.get("outage_s")) or 0))
    imu = rep.get("imu") or {}
    if imu and not imu.get("ok"):
        out.append("czujnik ruchu nie działał")
    if rep.get("calib") and not rep["calib"].get("ok"):
        out.append("przechył bez kalibracji")
    can = rep.get("can") or {}
    if can.get("mode") == 2 and can.get("obd") == "offline":
        out.append("brak danych z motocykla (OBD)")
    if ((rep.get("power") or {}).get("vbus_drops") or 0) > 0:
        out.append("zasilanie zanikało %d×" % rep["power"]["vbus_drops"])
    st = rep.get("storage") or {}
    if st.get("failed"):
        out.append("błąd karty pamięci")
    elif (st.get("dropped") or 0) > 0:
        out.append("karta nie nadążała (zgubione próbki: %d)" % st["dropped"])
    b = rep.get("battery")
    if isinstance(b, (int, float)) and 0 <= b < 20:
        out.append("bateria skrzynki %d%%" % b)
    return out


# ---------------------------------------------------------------- weather

WMO = [
    ((0,), "bezchmurnie", "☀️"), ((1,), "przeważnie słonecznie", "🌤️"), ((2,), "częściowe zachmurzenie", "⛅"),
    ((3,), "pochmurno", "☁️"), ((45, 48), "mgła", "🌫️"), ((51, 53, 55, 56, 57), "mżawka", "🌦️"),
    ((61, 63, 65, 66, 67), "deszcz", "🌧️"), ((71, 73, 75, 77, 85, 86), "śnieg", "🌨️"),
    ((80, 81, 82), "przelotny deszcz", "🌦️"), ((95, 96, 99), "burza", "⛈️"),
]


def wmo(code):
    for codes, text, icon in WMO:
        if code in codes:
            return text, icon
    return "", ""


FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_STEP_S = 1800  # a point every 30 minutes of the ride, plus start and end


def weather_points(pts):
    """Start, every 30 min and the end of the route: [t, lat, lon]."""
    if not pts:
        return []
    out = [pts[0]]
    next_t = (pts[0][5] or 0) + WEATHER_STEP_S
    for p in pts:
        if p[5] is not None and p[5] >= next_t:
            out.append(p)
            next_t = p[5] + WEATHER_STEP_S
    if pts[-1] is not out[-1]:
        if out[-1][5] is not None and pts[-1][5] is not None and pts[-1][5] - out[-1][5] < 600 and len(out) > 1:
            out[-1] = pts[-1]
        else:
            out.append(pts[-1])
    return [[p[5] or 0, p[0], p[1]] for p in out]


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "NT1100-Jazdy/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_weather(n):
    """Weather along the route from Open-Meteo history (no key needed).
    Recent rides from the forecast service (it keeps ~3 months), older ones
    from the archive. Saved as NNNN.wx."""
    s = summary(n) or {}
    start = parse_time(s.get("start"))
    if start is None:
        return None
    pts, _ = read_track(n)
    wp = weather_points(pts)
    if not wp:
        return None
    age_days = (time.time() - start) / 86400
    bases = [FORECAST, ARCHIVE] if age_days < 80 else [ARCHIVE, FORECAST]
    cache = {}
    out = []
    for t, lat, lon in wp:
        at = start + t
        day = time.strftime("%Y-%m-%d", time.gmtime(at))
        k = (round(lat, 2), round(lon, 2), day)
        if k not in cache:
            q = urllib.parse.urlencode({
                "latitude": "%.4f" % lat, "longitude": "%.4f" % lon, "start_date": day, "end_date": day,
                "hourly": "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
                "timezone": "GMT", "wind_speed_unit": "kmh"})
            err = None
            for base in bases:
                try:
                    j = http_json(base + "?" + q)
                except Exception as e:
                    err = e
                    continue
                # The archive has the last days still empty, the forecast
                # service only ~3 months: take the one that has data.
                if any(v is not None for v in (j.get("hourly") or {}).get("temperature_2m") or []):
                    cache[k] = j
                    break
            else:
                if err:
                    raise err
                cache[k] = {}
            time.sleep(0.3)
        h = cache[k].get("hourly") or {}
        times = h.get("time") or []
        if not times:
            continue
        hour = int(round(at / 3600.0)) * 3600
        want = time.strftime("%Y-%m-%dT%H:00", time.gmtime(hour))
        i = times.index(want) if want in times else min(range(len(times)), key=lambda j: abs(
            datetime.strptime(times[j], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).timestamp() - at))

        def val(name):
            arr = h.get(name) or []
            return arr[i] if i < len(arr) else None
        out.append({"t": int(t), "lat": round(lat, 4), "lon": round(lon, 4), "temp": val("temperature_2m"),
                    "rain": val("precipitation"), "code": val("weather_code"), "wind": val("wind_speed_10m"),
                    "gust": val("wind_gusts_10m")})
    if not out:
        return None
    wx = {"points": out, "source": "Open-Meteo", "fetched": now_ms()}
    write_json(ride_path(n, "wx"), wx)
    return wx


def weather_summary(wx):
    """Short weather of a ride for the list and the notification."""
    pts = (wx or {}).get("points") or []
    temps = [p["temp"] for p in pts if isinstance(p.get("temp"), (int, float))]
    if not temps:
        return None
    rain = sum(p.get("rain") or 0 for p in pts)
    codes = [p.get("code") for p in pts if isinstance(p.get("code"), int)]
    worst = max(codes) if codes else None
    text, icon = wmo(worst)
    winds = [p["wind"] for p in pts if isinstance(p.get("wind"), (int, float))]
    return {"tmin": round(min(temps)), "tmax": round(max(temps)), "rain": round(rain, 1), "code": worst,
            "text": text, "icon": icon, "wind": round(max(winds)) if winds else None}


def weather_on():
    return WEATHER_ON and bool(settings().get("weather", True))


_WX_FAILED = {}


def weather_loop():
    """Weather for new rides and, once, for the older ones (backfill)."""
    time.sleep(20)
    while True:
        try:
            if weather_on():
                for n in sorted(ride_numbers(), reverse=True):
                    if os.path.exists(ride_path(n, "wx")):
                        continue
                    if time.time() - _WX_FAILED.get(n, 0) < 6 * 3600:
                        continue
                    try:
                        if fetch_weather(n) is None:
                            _WX_FAILED[n] = time.time()
                        else:
                            log("Pogoda dla przejazdu %04d pobrana" % n)
                    except Exception as e:
                        _WX_FAILED[n] = time.time()
                        log("Pogoda dla przejazdu %04d nieudana: %s" % (n, e))
                    time.sleep(2)
        except Exception:
            traceback.print_exc()
        time.sleep(900)


# ---------------------------------------------------------------- settings of the add-on (page)

def settings():
    s = state()
    svc = s.get("service")
    if not isinstance(svc, list):
        svc = [dict(x) for x in DEFAULT_SERVICE]
    return {
        "trip_gap_h": s.get("trip_gap_h", 3),
        "notify": s.get("notify"),  # None = the add-on option "powiadomienie"
        "sd_min_free_pct": int(s.get("sd_min_free_pct", 0) or 0),
        "hotspot_min_kbit": int(s.get("hotspot_min_kbit", 1000) if s.get("hotspot_min_kbit") is not None else 1000),
        "weather": bool(s.get("weather", True)),
        "odo": s.get("odo") if isinstance(s.get("odo"), dict) else None,
        "service": svc,
        "nav": s.get("nav") if isinstance(s.get("nav"), dict) else {},
    }


def notify_target():
    st = settings()["notify"]
    t = (st if st is not None else (options().get("powiadomienie") or "")).strip()
    return t[len("notify."):] if t.startswith("notify.") else t


def ride_starts():
    out = []
    for n in ride_numbers():
        s = summary(n) or {}
        out.append((n, s, parse_time(s.get("start"))))
    return out


def odometer(rides=None):
    """The bike's odometer: the value entered on the page plus the rides
    recorded after it was entered."""
    odo = settings()["odo"]
    if not odo or num(odo.get("km")) is None:
        return None
    since = (num(odo.get("date")) or 0) / 1000.0
    km = float(odo["km"])
    for n, s, st in rides if rides is not None else ride_starts():
        if st is not None and st > since:
            km += float(num(s.get("distance_km")) or 0)
    return round(km)


def service_status(odo_km=None):
    if odo_km is None:
        odo_km = odometer()
    out = []
    for it in settings()["service"]:
        left = None
        if odo_km is not None and num(it.get("last_km")) is not None and num(it.get("interval_km")):
            left = int(round(float(it["last_km"]) + float(it["interval_km"]) - odo_km))
        out.append(dict(it, left_km=left))
    return out


# ---------------------------------------------------------------- Home Assistant

def ha_call(method, path, body=None, timeout=10):
    if not TOKEN:
        return None
    req = urllib.request.Request(
        SUPERVISOR + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        try:
            return json.loads(data or b"null")
        except ValueError:
            return None


_PANEL = []


def panel_url():
    """Side-menu panel of this add-on (the slug has a prefix that depends on
    where it was installed from: local_ or the repository's hash)."""
    if not _PANEL:
        try:
            info = ha_call("GET", "/addons/self/info") or {}
            slug = (info.get("data") or {}).get("slug")
            if slug:
                _PANEL.append("/hassio/ingress/" + slug)
        except Exception as e:
            log("Nie udalo sie odczytac nazwy dodatku:", e)
    return _PANEL[0] if _PANEL else "/hassio/dashboard"


_LOCAL = []


def local_url():
    """Home Assistant's address in the home network, for the box at home."""
    if _LOCAL:
        return _LOCAL[0]
    addr = ""
    try:
        info = ha_call("GET", "/network/info") or {}
        itfs = (info.get("data") or {}).get("interfaces") or []
        for itf in sorted(itfs, key=lambda i: not i.get("primary")):
            for a in (itf.get("ipv4") or {}).get("address") or []:
                ip = a.split("/")[0]
                if ip and not ip.startswith(("127.", "172.30.", "169.254.")):
                    addr = ip
                    break
            if addr:
                break
    except Exception as e:
        log("Adres IP z /network/info nieudany:", e)
    if not addr:
        try:
            cfg = ha_call("GET", "/core/api/config") or {}
            host = urllib.parse.urlsplit(cfg.get("internal_url") or "").hostname or ""
            if re.fullmatch(r"[\d.]+", host) or host.endswith(".local"):
                addr = host
        except Exception as e:
            log("Adres IP z konfiguracji HA nieudany:", e)
    if addr:
        _LOCAL.append("http://%s:%d" % (addr, INGEST_PORT))
        return _LOCAL[0]
    return ""


def addon_info(reload_store=False):
    """Version of this add-on and the newest one in the add-on store."""
    if reload_store:
        ha_call("POST", "/store/reload", {}, timeout=60)
    d = (ha_call("GET", "/addons/self/info") or {}).get("data") or {}
    return {"version": d.get("version") or VERSION, "latest": d.get("version_latest") or d.get("version") or VERSION,
            "update": bool(d.get("update_available")), "slug": d.get("slug") or ""}


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def device_version(installed, offer, seen):
    """Status of one device for the Versions card: ok / update / unknown."""
    if not installed:
        st = "unknown"
    elif offer and version_tuple(offer) > version_tuple(installed):
        st = "update"
    else:
        st = "ok"
    return {"installed": installed or None, "latest": offer or installed or None, "status": st, "seen": seen}


def engine_alive(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def versions(reload_store=False):
    """All software of the system in one place: installed vs newest."""
    try:
        a = addon_info(reload_store)
        addon = {"installed": a["version"], "latest": a["latest"], "status": "update" if a["update"] else "ok",
                 "can_update": a["update"]}
    except Exception as e:
        log("Wersja dodatku nieznana:", e)
        addon = {"installed": VERSION, "latest": None, "status": "unknown", "error": str(e)}
    s = state()
    box = device_version(s.get("box_fw"), (firmware_offer() or {}).get("version"),
                         int(s["box_seen"] / 1000) if s.get("box_seen") else None)
    sc = (navapi.NAV.screen_position() if navapi.NAV else None) or {}
    screen = device_version(sc.get("fw"), (navapi.screen_firmware_offer() or {}).get("version"),
                            sc.get("t_seen") or sc.get("t"))
    url = navapi.NAV.settings()["engine_url"] if navapi.NAV else ""
    engine = {"configured": bool(url), "alive": engine_alive(url) if url else False}
    return {"addon": addon, "box": box, "screen": screen, "engine": engine}


def notify_targets():
    """Phones and other notify services, for the list on the settings page."""
    try:
        services = ha_call("GET", "/core/api/services") or []
    except Exception as e:
        log("Lista powiadomien nieudana:", e)
        return []
    out = []
    for d in services:
        if d.get("domain") == "notify":
            for name in sorted((d.get("services") or {}).keys()):
                if name not in ("send_message", "persistent_notification"):
                    out.append(name)
    return out


def newest_ride(rides=None):
    best, best_key = None, None
    for n, s, st in rides if rides is not None else ride_starts():
        k = (st or 0, n)
        if best_key is None or k > best_key:
            best, best_key = n, k
    return best


def parking(n):
    """Where the bike stands: the last point of the newest ride."""
    if not n:
        return None
    p = ride_path(n, "trk")
    if not os.path.exists(p):
        p = ride_path(n, "thm")
        if not os.path.exists(p):
            return None
    last = None
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            a = line.strip().split(",")
            if len(a) >= 2 and num(a[0]) is not None and num(a[1]) is not None and not (num(a[0]) == 0 and num(a[1]) == 0):
                last = (num(a[0]), num(a[1]))
    if not last:
        return None
    return {"latitude": last[0], "longitude": last[1], "gps_accuracy": 10}


def collect_state():
    """Everything the entities show, as one dict."""
    rides = ride_starts()
    total_km = sum(float(num(s.get("distance_km")) or 0) for _, s, _ in rides)
    year = time.gmtime().tm_year
    km_year = sum(float(num(s.get("distance_km")) or 0) for _, s, st in rides
                  if st is not None and time.gmtime(st).tm_year == year)
    n = newest_ride(rides)
    s = (summary(n) if n else None) or {}
    nm = name_info(n) if n else {}
    st = state()
    wx = weather_summary(read_json(ride_path(n, "wx"), None)) if n else None
    cv = curvy_of(n) if n else None
    odo = odometer(rides)
    sd_total, sd_free = st.get("box_sd_total"), st.get("box_sd_free")
    out = {
        "przejazd": n,
        "nazwa": nm.get("name") or s.get("ride") or None,
        "dystans": fmt_num(s.get("distance_km"), 1),
        "czas": fmt_num(s.get("moving_min")),
        "v_maks": fmt_num(s.get("max_speed")),
        "v_sr": fmt_num(s.get("avg_speed")),
        "przechyl_l": fmt_num(s.get("max_lean_left")),
        "przechyl_p": fmt_num(s.get("max_lean_right")),
        "paliwo": fmt_num(s.get("fuel_l"), 2),
        "spalanie": fmt_num(s.get("fuel_l100"), 1),
        "sprzeglo": fmt_num(s.get("clutch_pulls")),
        "start": s.get("start"),
        "kretosc": (cv or {}).get("rating"),
        "zakrety_100km": (cv or {}).get("per100"),
        "temperatura": (wx or {}).get("tmax"),
        "liczba": len(rides),
        "km_razem": round(total_km, 1),
        "km_rok": round(km_year, 1),
        "przebieg": odo,
        "skrzynka_fw": st.get("box_fw"),
        "skrzynka_kontakt": (datetime.fromtimestamp(st["box_seen"] / 1000, timezone.utc).isoformat()
                             if st.get("box_seen") else None),
        "skrzynka_bateria": st.get("box_battery"),
        "skrzynka_karta": (round(100.0 * sd_free / sd_total) if sd_total and sd_free is not None else None),
        "problemy": len(problems(report(n))) if n else None,
    }
    for it in service_status(odo):
        out["serwis_" + it["id"]] = it["left_km"]
    return out


# Entities: key in the state, name, unit, device class, icon, state class.
ENTITIES = [
    ("dystans", "Ostatnia jazda dystans", "km", "distance", "mdi:map-marker-distance", "measurement"),
    ("czas", "Ostatnia jazda czas", "min", "duration", "mdi:timer-outline", None),
    ("v_maks", "Ostatnia jazda prędkość maks", "km/h", "speed", "mdi:speedometer", None),
    ("v_sr", "Ostatnia jazda prędkość średnia", "km/h", "speed", "mdi:speedometer-medium", None),
    ("przechyl_l", "Ostatnia jazda przechył lewo", "°", None, "mdi:angle-acute", None),
    ("przechyl_p", "Ostatnia jazda przechył prawo", "°", None, "mdi:angle-acute", None),
    ("paliwo", "Ostatnia jazda paliwo (szacunek)", "L", "volume", "mdi:gas-station", None),
    ("spalanie", "Ostatnia jazda spalanie (szacunek)", "L/100km", None, "mdi:gas-station-outline", None),
    ("sprzeglo", "Ostatnia jazda użycia sprzęgła", None, None, "mdi:car-clutch", None),
    ("start", "Ostatnia jazda start", None, "timestamp", "mdi:motorbike", None),
    ("nazwa", "Ostatnia jazda nazwa", None, None, "mdi:motorbike", None),
    ("kretosc", "Ostatnia jazda krętość", None, None, "mdi:road-variant", None),
    ("zakrety_100km", "Ostatnia jazda zakręty na 100 km", None, None, "mdi:sign-direction", None),
    ("temperatura", "Ostatnia jazda temperatura", "°C", "temperature", "mdi:thermometer", None),
    ("problemy", "Ostatnia jazda problemy", None, None, "mdi:alert-circle-outline", None),
    ("liczba", "Jazdy", None, None, "mdi:counter", "total"),
    ("km_razem", "Kilometry razem", "km", "distance", "mdi:road-variant", "total_increasing"),
    ("km_rok", "Kilometry w tym roku", "km", "distance", "mdi:calendar-range", "total"),
    ("przebieg", "Przebieg", "km", "distance", "mdi:counter", "total_increasing"),
    ("skrzynka_fw", "Skrzynka oprogramowanie", None, None, "mdi:chip", None),
    ("skrzynka_kontakt", "Skrzynka ostatni kontakt", None, "timestamp", "mdi:access-point", None),
    ("skrzynka_bateria", "Skrzynka bateria", "%", "battery", None, "measurement"),
    ("skrzynka_karta", "Skrzynka wolne miejsce na karcie", "%", None, "mdi:sd", "measurement"),
]
LEGACY_ENTITIES = [
    "sensor.nt1100_ostatnia_jazda_dystans", "sensor.nt1100_ostatnia_jazda_czas",
    "sensor.nt1100_ostatnia_jazda_predkosc_maks", "sensor.nt1100_ostatnia_jazda_predkosc_srednia",
    "sensor.nt1100_ostatnia_jazda_przechyl_lewo", "sensor.nt1100_ostatnia_jazda_przechyl_prawo",
    "sensor.nt1100_ostatnia_jazda_start", "sensor.nt1100_ostatnia_jazda_nazwa",
    "sensor.nt1100_jazdy_liczba", "sensor.nt1100_jazdy_km_razem",
]
DIAGNOSTIC = ("skrzynka_fw", "skrzynka_kontakt", "skrzynka_bateria", "skrzynka_karta")
TOPIC = "nt1100"
DISC = "homeassistant"


def slug_entity(name):
    tr = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return re.sub(r"[^a-z0-9]+", "_", name.translate(tr).lower()).strip("_")


class Mqtt:
    """Entities over MQTT discovery: one device "NT1100" in Home Assistant."""

    def __init__(self):
        self.client = None
        self.connected = False
        self.error = ""
        self.host = ""
        self.started = 0.0
        self.user = ""
        self.service_ids = set()
        self.lock = threading.Lock()

    def credentials(self):
        o = options()
        if (o.get("mqtt_host") or "").strip():
            return {"host": o["mqtt_host"].strip(), "port": int(o.get("mqtt_port") or 1883),
                    "username": o.get("mqtt_user") or "", "password": o.get("mqtt_password") or "", "ssl": False}
        try:
            d = (ha_call("GET", "/services/mqtt") or {}).get("data") or {}
        except Exception as e:
            self.error = "brak brokera MQTT w Home Assistant (%s)" % e
            return None
        if not d.get("host"):
            self.error = "brak brokera MQTT"
            return None
        c = {"host": d["host"], "port": int(d.get("port") or 1883), "username": d.get("username") or "",
             "password": d.get("password") or "", "ssl": bool(d.get("ssl"))}
        # Own user from the add-on configuration, the broker from the Supervisor.
        if (o.get("mqtt_user") or "").strip():
            c["username"], c["password"] = o["mqtt_user"].strip(), o.get("mqtt_password") or ""
        return c

    def start(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.error = "brak biblioteki MQTT"
            return False
        c = self.credentials()
        if not c:
            return False
        try:
            try:
                cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="nt1100_jazdy")
            except AttributeError:
                cl = mqtt.Client(client_id="nt1100_jazdy")
            if c["username"]:
                cl.username_pw_set(c["username"], c["password"])
            if c["ssl"]:
                cl.tls_set()
            cl.will_set(TOPIC + "/dostepnosc", "offline", retain=True)
            cl.on_connect = self.on_connect
            cl.on_disconnect = self.on_disconnect
            cl.on_message = self.on_message
            cl.on_connect_fail = self.on_connect_fail
            cl.reconnect_delay_set(5, 300)
            cl.connect_async(c["host"], c["port"], keepalive=60)
            cl.loop_start()
            self.client = cl
            self.host = "%s:%d" % (c["host"], c["port"])
            self.user = c["username"]
            self.started = time.time()
            log("MQTT: lacze z", self.host, "jako", c["username"] or "(bez loginu)")
            return True
        except Exception as e:
            self.error = "MQTT: %s" % e
            log("MQTT nieudane:", e)
            return False

    def on_connect(self, client, userdata, flags, rc, *props):
        code = getattr(rc, "value", rc)
        if code != 0:
            self.connected = False
            self.error = "broker MQTT odrzucił połączenie (%s): sprawdź login i hasło" % rc
            log("MQTT:", self.error)
            return
        self.connected = True
        self.error = ""
        log("MQTT polaczone")
        client.subscribe(TOPIC + "/serwis/+/zrobione")
        client.subscribe(DISC + "/status")
        threading.Thread(target=self.announce, daemon=True).start()

    def on_connect_fail(self, client, userdata):
        self.error = "broker %s nie odpowiada (czy dodatek Mosquitto działa?)" % self.host
        if time.time() - getattr(self, "_logged", 0) > 300:
            self._logged = time.time()
            log("MQTT:", self.error)

    def status_error(self):
        """What the page shows when MQTT is not connected."""
        if self.connected:
            return None
        if self.error:
            return self.error
        if self.client is not None and time.time() - self.started > 30:
            return "brak odpowiedzi brokera %s po %d s" % (self.host, time.time() - self.started)
        return None

    def on_disconnect(self, client, userdata, *args):
        if self.connected:
            log("MQTT rozlaczone")
        self.connected = False

    def on_message(self, client, userdata, msg):
        t = msg.topic
        if t == DISC + "/status" and msg.payload == b"online":
            threading.Thread(target=self.announce, daemon=True).start()
            return
        m = re.fullmatch(TOPIC + r"/serwis/([a-z0-9_]{1,24})/zrobione", t)
        if m:
            service_done(m.group(1))

    def pub(self, topic, payload, retain=True):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False)
        self.client.publish(topic, payload, qos=1, retain=retain)

    def device(self):
        st = state()
        return {"identifiers": ["nt1100_jazdy"], "name": "NT1100", "manufacturer": "Honda",
                "model": "NT1100 – rejestrator jazd", "sw_version": st.get("box_fw") or VERSION,
                "configuration_url": "homeassistant://" + panel_url()}

    def announce(self):
        """Discovery of every entity (also after Home Assistant restarts)."""
        with self.lock:
            if not self.connected:
                return
            st0 = state()
            if not st0.get("legacy_removed") or st0.get("api_states"):
                # Entities set over the REST API (1.1.0, or without MQTT
                # before): removed so the MQTT ones keep the same names.
                ours = ["sensor.nt1100_" + slug_entity(e[1]) for e in ENTITIES]
                for e in LEGACY_ENTITIES + ours + ["device_tracker.nt1100_parking"]:
                    try:
                        ha_call("DELETE", "/core/api/states/" + e)
                    except Exception:
                        pass
                save_state(legacy_removed=True, api_states=False)
            dev = self.device()
            avail = [{"topic": TOPIC + "/dostepnosc"}]
            for k, name, unit, dc, icon, sc in ENTITIES:
                cfg = {"name": name[len("NT1100 "):] if name.startswith("NT1100 ") else name,
                       "unique_id": "nt1100_" + k, "default_entity_id": "sensor.nt1100_" + slug_entity(name),
                       "state_topic": TOPIC + "/stan", "value_template": "{{ value_json.%s }}" % k,
                       "availability": avail, "device": dev}
                if k == "nazwa" or k == "start":
                    cfg["json_attributes_topic"] = TOPIC + "/ostatnia"
                if unit:
                    cfg["unit_of_measurement"] = unit
                if dc:
                    cfg["device_class"] = dc
                if icon:
                    cfg["icon"] = icon
                if sc:
                    cfg["state_class"] = sc
                if k in DIAGNOSTIC:
                    cfg["entity_category"] = "diagnostic"
                self.pub("%s/sensor/nt1100/%s/config" % (DISC, k), cfg)
            self.pub("%s/device_tracker/nt1100/parking/config" % DISC, {
                "name": "Parking", "unique_id": "nt1100_parking", "default_entity_id": "device_tracker.nt1100_parking",
                "json_attributes_topic": TOPIC + "/parking", "source_type": "gps", "icon": "mdi:parking",
                "availability": avail, "device": dev})
            ids = set()
            for it in settings()["service"]:
                sid = it["id"]
                ids.add(sid)
                self.pub("%s/sensor/nt1100/serwis_%s/config" % (DISC, sid), {
                    "name": "Serwis " + it["name"], "unique_id": "nt1100_serwis_" + sid,
                    "default_entity_id": "sensor.nt1100_serwis_" + sid,
                    "state_topic": TOPIC + "/stan", "value_template": "{{ value_json.serwis_%s }}" % sid,
                    "unit_of_measurement": "km", "device_class": "distance", "icon": "mdi:wrench-clock",
                    "availability": avail, "device": dev})
                self.pub("%s/button/nt1100/serwis_%s/config" % (DISC, sid), {
                    "name": "Serwis " + it["name"] + " zrobiony", "unique_id": "nt1100_serwis_%s_zrobione" % sid,
                    "default_entity_id": "button.nt1100_serwis_%s_zrobiony" % sid,
                    "command_topic": "%s/serwis/%s/zrobione" % (TOPIC, sid), "payload_press": "1",
                    "icon": "mdi:check-circle-outline", "availability": avail, "device": dev})
            gone = set(state().get("mqtt_service_ids") or []) - ids
            for sid in gone:
                self.pub("%s/sensor/nt1100/serwis_%s/config" % (DISC, sid), "")
                self.pub("%s/button/nt1100/serwis_%s/config" % (DISC, sid), "")
            save_state(mqtt_service_ids=sorted(ids))
            self.pub(TOPIC + "/dostepnosc", "online")
        time.sleep(1)  # Home Assistant creates the entities first
        self.publish()

    def publish(self):
        if not self.connected:
            return False
        st = collect_state()
        self.pub(TOPIC + "/stan", st)
        n = st.get("przejazd")
        if n:
            s = summary(n) or {}
            nm = name_info(n)
            self.pub(TOPIC + "/ostatnia", {"przejazd": n, "nazwa": nm.get("name") or None,
                                          "notatka": nm.get("note") or None, "koniec": s.get("end"),
                                          "problemy": problems(report(n)),
                                          "pogoda": weather_summary(read_json(ride_path(n, "wx"), None))})
            pk = parking(n)
            if pk:
                self.pub(TOPIC + "/parking", pk)
        return True


MQTT = Mqtt()


def publish_states_api(st):
    """Without MQTT: the main sensors over the REST API (they are lost when
    Home Assistant restarts, so this runs again every 10 minutes)."""
    for k, name, unit, dc, icon, sc in ENTITIES:
        a = {"friendly_name": "NT1100 " + name}
        if unit:
            a["unit_of_measurement"] = unit
        if dc:
            a["device_class"] = dc
        if icon:
            a["icon"] = icon
        if sc:
            a["state_class"] = sc
        v = st.get(k)
        ha_call("POST", "/core/api/states/sensor.nt1100_" + slug_entity(name),
                {"state": "unknown" if v is None else v, "attributes": a})
    pk = parking(st.get("przejazd"))
    if pk:
        ha_call("POST", "/core/api/states/device_tracker.nt1100_parking",
                {"state": "not_home", "attributes": dict(pk, friendly_name="NT1100 Parking", source_type="gps",
                                                        icon="mdi:parking")})


def publish_sensors():
    try:
        if MQTT.publish():
            return
        if TOKEN and MQTT.client is None:
            publish_states_api(collect_state())
            if not state().get("api_states"):
                save_state(api_states=True)
    except Exception as e:
        log("Czujniki: nie udalo sie opublikowac:", e)


def service_done(sid):
    """A service item was done now (button in HA or on the page)."""
    odo = odometer()
    with LOCK:
        st = state()
        svc = settings()["service"]
        for it in svc:
            if it["id"] == sid:
                it["last_km"] = odo
                it["last_date"] = now_ms()
                log("Serwis zrobiony:", it["name"], "przy", odo, "km")
        notified = st.get("svc_notified") or {}
        notified.pop(sid, None)
        save_state(service=svc, svc_notified=notified)
    threading.Thread(target=publish_sensors, daemon=True).start()
    return odo


# ---------------------------------------------------------------- notifications

def send_notification(title, msg, tag="nt1100_jazda", url=None, link_text="Pokaż jazdy"):
    """url: dokąd prowadzi dotknięcie (domyślnie panel dodatku), np. plik GPX dla OsmAnd."""
    target = notify_target()
    panel = url or panel_url()
    if target:
        ha_call("POST", "/core/api/services/notify/" + target,
                {"title": title, "message": msg,
                 "data": {"url": panel, "clickAction": panel, "group": "nt1100", "tag": tag}})
    else:
        ha_call("POST", "/core/api/services/persistent_notification/create",
                {"title": title, "message": msg + "\n\n[" + link_text + "](" + panel + ")", "notification_id": tag})


RECORDS = [
    ("distance_km", "najdłuższa jazda", lambda v: "%s km" % km_str(v)),
    ("max_speed", "najwyższa prędkość", lambda v: "%d km/h" % v),
    ("lean", "największy przechył", lambda v: "%d°" % v),
    ("elevation_gain", "największe przewyższenie", lambda v: "%d m" % v),
    ("max_brake_g", "najmocniejsze hamowanie", lambda v: ("%.2f g" % v).replace(".", ",")),
]


def lean_of(s):
    vals = [num(s.get("max_lean_left")), num(s.get("max_lean_right"))]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def records_line(n, s):
    """"How it went": new records of this ride against all the others."""
    others = [(m, summary(m) or {}) for m in ride_numbers() if m != n]
    if not others:
        return "Pierwsza jazda w archiwum."
    hits = []
    for k, label, f in RECORDS:
        v = lean_of(s) if k == "lean" else num(s.get(k))
        if v is None:
            continue
        prev = [lean_of(o) if k == "lean" else num(o.get(k)) for _, o in others]
        prev = [p for p in prev if p is not None]
        if prev and v > max(prev):
            hits.append("%s (%s)" % (label, f(v)))
    cv = curvy_of(n)
    if cv and cv.get("deg_km") is not None:
        prev = [(curvy_of(m) or {}).get("deg_km") for m, _ in others]
        prev = [p for p in prev if p is not None]
        if prev and cv["deg_km"] > max(prev):
            hits.append("najbardziej kręta trasa")
    if hits:
        return "🏆 Nowy rekord: " + ", ".join(hits) + "."
    dists = [num(o.get("distance_km")) for _, o in others if num(o.get("distance_km"))]
    d = num(s.get("distance_km"))
    if dists and d:
        avg = sum(dists) / len(dists)
        diff = (d - avg) / avg * 100
        if abs(diff) >= 10:
            return "%s niż przeciętna jazda (%s km)." % (
                ("o %d%% dłużej" % diff) if diff > 0 else ("o %d%% krócej" % -diff), km_str(avg))
    return "Jazda w normie."


def notify_ride(n, s):
    nm = name_info(n).get("name")
    parts = ["%s km" % km_str(s.get("distance_km")), hm(s.get("moving_min"))]
    if s.get("max_speed") is not None:
        parts.append("maks. %d km/h" % fmt_num(s.get("max_speed")))
    if s.get("max_lean_left") is not None and s.get("max_lean_right") is not None:
        parts.append("przechył L %d° / P %d°" % (fmt_num(s.get("max_lean_left")), fmt_num(s.get("max_lean_right"))))
    if s.get("fuel_l100") is not None:
        parts.append("ok. %s l/100 km" % str(fmt_num(s.get("fuel_l100"), 1)).replace(".", ","))
    lines = [" · ".join(parts)]
    cv = curvy_of(n)
    if cv and cv.get("rating"):
        lines.append("Trasa %s (%s zakrętów na 100 km)." % (cv["rating"], cv["per100"] if cv.get("per100") is not None else "?"))
    if weather_on():
        wx = None
        try:
            wx = read_json(ride_path(n, "wx"), None) or fetch_weather(n)
        except Exception as e:
            log("Pogoda do powiadomienia nieudana:", e)
        w = weather_summary(wx)
        if w:
            t = "%d°C" % w["tmin"] if w["tmin"] == w["tmax"] else "%d–%d°C" % (w["tmin"], w["tmax"])
            lines.append("%s %s, %s%s" % (w["icon"], t, w["text"], ", opady %s mm" % str(w["rain"]).replace(".", ",")
                                          if w["rain"] >= 0.2 else ""))
    lines.append(records_line(n, s))
    pr = problems(report(n))
    if pr:
        lines.append("⚠️ Problemy: " + "; ".join(pr) + ".")
    msg = "\n".join(lines)
    title = "NT1100: " + (nm or "nowa jazda")
    try:
        ha_call("POST", "/core/api/events/nt1100_nowa_jazda", dict(s, przejazd=n, nazwa=nm, problemy=pr))
        send_notification(title, msg)
        log("Powiadomienie:", title, "-", msg.replace("\n", " | "))
    except Exception as e:
        log("Powiadomienie nieudane (sprawdz ustawienie powiadomien):", e)
        save_state(last_error="powiadomienie nieudane: %s" % e, last_error_at=now_ms())
    notify_service()


def notify_service():
    """Service due soon: one notification per item until it is marked done."""
    odo = odometer()
    if odo is None:
        return
    with LOCK:
        notified = state().get("svc_notified") or {}
        due = []
        for it in service_status(odo):
            if it["left_km"] is None or it["left_km"] > SERVICE_WARN_KM:
                continue
            if notified.get(it["id"]) == it.get("last_km"):
                continue
            notified[it["id"]] = it.get("last_km")
            due.append(it)
        save_state(svc_notified=notified)
    for it in due:
        left = it["left_km"]
        msg = ("za %d km" % left) if left > 0 else ("%d km po terminie" % -left)
        try:
            send_notification("NT1100: serwis", "%s: %s (przebieg ok. %d km)." % (it["name"], msg, odo),
                              tag="nt1100_serwis_" + it["id"])
        except Exception as e:
            log("Powiadomienie o serwisie nieudane:", e)


def sensor_loop():
    for _ in range(30):  # Home Assistant may still be starting
        try:
            ha_call("GET", "/core/api/")
            break
        except Exception:
            time.sleep(10)
    for _ in range(15):  # first values after the discovery, not before
        if MQTT.connected or MQTT.client is None:
            break
        time.sleep(1)
    while True:
        publish_sensors()
        clean_incoming()
        time.sleep(600)


def mqtt_loop():
    """Connects to the broker at once and tries again every 30 s until it
    works (the broker add-on may start later than this one)."""
    while True:
        try:
            if MQTT.client is None and (TOKEN or options().get("mqtt_host")):
                if not MQTT.start() and not MQTT.error:
                    MQTT.error = "MQTT nie wystartował"
        except Exception as e:
            MQTT.error = "MQTT: %s" % e
            traceback.print_exc()
        time.sleep(30)


def clean_incoming(max_age_s=7 * 86400):
    """Parts of rides that never got their summary (sending broken off)."""
    try:
        names = os.listdir(INCOMING)
    except FileNotFoundError:
        return
    for name in names:
        p = os.path.join(INCOMING, name)
        try:
            if time.time() - os.path.getmtime(p) > max_age_s:
                shutil.rmtree(p, ignore_errors=True)
                log("Usunieto niedokonczona wysylke:", name)
        except OSError:
            pass


# ---------------------------------------------------------------- ingest

def after_commit(n, s, is_new):
    try:
        curvy_of(n)
    except Exception as e:
        log("Kretosc trasy nieudana:", e)
    publish_sensors()
    if is_new:
        notify_ride(n, s)


def commit(box_n, ride_id, stage, source):
    """The summary (sent last) arrived: move the ride into rides/."""
    with LOCK:
        jb = open(os.path.join(stage, "json"), "rb").read()
        try:
            s = json.loads(jb)
        except ValueError:
            raise ValueError("podsumowanie jazdy nie jest poprawnym JSON")
        index = read_json(INDEX, {})
        k = ride_key(ride_id, jb)
        n = index.get(k)
        is_new = n is None or not os.path.exists(ride_path(n, "json"))
        if n is None:
            n = box_n if not os.path.exists(ride_path(box_n, "json")) else max(ride_numbers() + [0]) + 1
        os.makedirs(RIDES, exist_ok=True)
        for ext in EXTS:
            src = os.path.join(stage, ext)
            if os.path.exists(src):
                os.replace(src, ride_path(n, ext))
        shutil.rmtree(stage, ignore_errors=True)
        index[k] = n
        # Files sent later (a new name, the raw log) find the ride by this.
        index["box:%d:%s" % (box_n, ride_id)] = n
        write_json(INDEX, index)
        save_state(last_ingest=now_ms(), last_ride=n, last_from=source, last_error="", last_error_at=None)
        log("Jazda zapisana: przejazd %04d (ze skrzynki nr %d, %s)%s" % (n, box_n, k, "" if is_new else " - ponownie"))
    threading.Thread(target=after_commit, args=(n, s, is_new), daemon=True).start()
    return n


def late_ride(box_n, ride_id):
    """Number of an already saved ride, for files sent after it."""
    index = read_json(INDEX, {})
    n = index.get("box:%d:%s" % (box_n, ride_id))
    if n is None and ride_id and ride_id != "bez-czasu" and not ride_id.startswith("nr"):
        n = index.get(ride_id)
    if n is not None and os.path.exists(ride_path(n, "json")):
        return n
    return None


def save_late(n, ext, tmp):
    with LOCK:
        if ext == "nam":
            try:
                with open(tmp, encoding="utf-8") as f:
                    j = json.loads(f.read() or "{}")
            except ValueError:
                j = {}
            if not isinstance(j, dict) or (not j.get("name") and not j.get("note") and not j.get("fav")):
                os.remove(tmp)
                if os.path.exists(ride_path(n, "nam")):
                    os.remove(ride_path(n, "nam"))
                log("Przejazd %04d: nazwa usunieta na skrzynce" % n)
                return
        os.replace(tmp, ride_path(n, ext))
    if ext == "mtl":
        log("Przejazd %04d: kopia surowego zapisu (%d MB)" % (n, os.path.getsize(ride_path(n, ext)) // 1048576))
    else:
        log("Przejazd %04d: plik %s zaktualizowany" % (n, ext))
    if ext == "nam":
        threading.Thread(target=publish_sensors, daemon=True).start()


class Base(BaseHTTPRequestHandler):
    server_version = "NT1100Jazdy/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            # Compact ("ok":true): the box looks for exactly this text.
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        if isinstance(body, str):
            body = body.encode("utf-8")
            if ctype in ("application/json", "text/plain", "text/html"):
                ctype += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_path(self, path, ctype, extra=None):
        """A file from disk, in pieces (raw logs can be big)."""
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, 256 * 1024)

    def query(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path, {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}

    def body_chunks(self, limit):
        """The request body in pieces (plain or chunked)."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            total = 0
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    return
                total += size
                if total > limit:
                    raise ValueError("plik za duzy")
                left = size
                while left:
                    c = self.rfile.read(min(left, 262144))
                    if not c:
                        return
                    left -= len(c)
                    yield c
                self.rfile.readline()
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("plik za duzy")
        while n > 0:
            c = self.rfile.read(min(n, 262144))
            if not c:
                return
            n -= len(c)
            yield c

    def read_body(self, limit):
        return b"".join(self.body_chunks(limit))


class Ingest(Base):
    """Port 8098: the box sends rides here (home network or Cloudflare)."""

    def authorized(self):
        got = (self.headers.get("X-Klucz") or "").strip()
        return bool(got) and hmac.compare_digest(got.encode(), key().encode())

    def source(self):
        return "przez internet" if self.headers.get("CF-Connecting-IP") else "sieć domowa"

    def seen(self, version):
        kw = {}
        if version and re.fullmatch(r"[0-9.]{1,16}", version):
            kw.update(box_fw=version, box_seen=now_ms())
        sd = (self.headers.get("X-SD") or "").split(",")
        if len(sd) == 2 and all(x.strip().isdigit() for x in sd):
            kw.update(box_sd_total=int(sd[0]), box_sd_free=int(sd[1]))
        b = (self.headers.get("X-Bateria") or "").strip()
        if re.fullmatch(r"\d{1,3}", b) and int(b) <= 100:
            kw.update(box_battery=int(b))
        if kw:
            old = state()
            save_state(**kw)
            if kw.get("box_fw") and kw["box_fw"] != old.get("box_fw") and MQTT.connected:
                threading.Thread(target=MQTT.announce, daemon=True).start()  # device firmware shown in HA

    def do_GET(self):
        path, q = self.query()
        if navapi.screen_get(self, path, q):
            return
        if path in ("/api/ping", "/api/fw", "/api/fw/bin") and not self.authorized():
            log("Odrzucono: zly klucz (", self.client_address[0], ")")
            return self.send(401, {"ok": False, "error": "zly klucz"})
        if path == "/api/ping":
            self.seen(self.headers.get("X-Wersja") or "")
            st = settings()
            return self.send(200, {"ok": True, "app": "NT1100 Jazdy", "version": VERSION,
                                   "sd_min_free_pct": st["sd_min_free_pct"],
                                   "hotspot_min_kbit": st["hotspot_min_kbit"]})
        if path == "/api/fw":
            self.seen(q.get("v", ""))
            o = firmware_offer()
            return self.send(200, {"version": o["version"] if o else "", "size": o["size"] if o else 0})
        if path == "/api/fw/bin":
            o = firmware_offer()
            if not o:
                return self.send(404, {"ok": False, "error": "brak pliku"})
            log("Skrzynka pobiera oprogramowanie", o["version"])
            return self.send_path(o["path"], "application/octet-stream")
        self.send(404, {"ok": False, "error": "brak"})

    def do_POST(self):
        path, q = self.query()
        if path.startswith("/api/nav/"):
            body = self.read_body(1024 * 1024)
            navapi.screen_post(self, path, q, body)
            return
        if path != "/api/ingest":
            return self.send(404, {"ok": False, "error": "brak"})
        if not self.authorized():
            log("Odrzucono wysylke: zly klucz (", self.client_address[0], ")")
            return self.send(401, {"ok": False, "error": "zly klucz"})
        try:
            box_n = int(q.get("n", ""))
            ride_id = q.get("id", "")
            ext = q.get("ext", "")
            size = int(q.get("size", ""))
            crc = int(q.get("crc", ""), 16)
            limit = MAX_RAW if ext == "mtl" else MAX_FILE
            if not (0 < box_n < 1000000) or ext not in EXTS or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", ride_id) \
                    or not (0 <= size <= limit):
                raise ValueError
        except ValueError:
            return self.send(400, {"ok": False, "error": "zle parametry"})
        late = late_ride(box_n, ride_id) if ext in LATE_EXTS else None
        stage = os.path.join(INCOMING, "%d-%s" % (box_n, ride_id))
        os.makedirs(stage, exist_ok=True)
        tmp = os.path.join(stage, ext + ".tmp")
        got, c = 0, 0
        try:
            with open(tmp, "wb") as f:
                for chunk in self.body_chunks(limit):
                    f.write(chunk)
                    got += len(chunk)
                    c = zlib.crc32(chunk, c)
        except ValueError as e:
            os.remove(tmp)
            return self.send(413, {"ok": False, "error": str(e)})
        if got != size or (c & 0xFFFFFFFF) != crc:
            os.remove(tmp)
            log("Plik %s jazdy %d dotarl uszkodzony (%d z %d B)" % (ext, box_n, got, size))
            return self.send(422, {"ok": False, "error": "plik dotarl niepelny albo uszkodzony"})
        if late is not None:
            save_late(late, ext, tmp)
            if not os.listdir(stage):
                os.rmdir(stage)
            return self.send(200, {"ok": True, "n": late})
        os.replace(tmp, os.path.join(stage, ext))
        if ext != "json":
            return self.send(200, {"ok": True})
        try:
            n = commit(box_n, ride_id, stage, self.source())
        except Exception as e:
            traceback.print_exc()
            save_state(last_error="zapis jazdy: %s" % e, last_error_at=now_ms())
            return self.send(500, {"ok": False, "error": str(e)})
        self.send(200, {"ok": True, "n": n})


def firmware_offer():
    """Newest box firmware shipped with this add-on (encrypted, signed)."""
    j = read_json(os.path.join(FIRMWARE, "skrzynka.json"), {})
    path = os.path.join(FIRMWARE, "skrzynka.bin")
    if not j.get("version") or not os.path.exists(path):
        return None
    return {"version": j["version"], "size": os.path.getsize(path), "path": path}


SETTING_LIMITS = {"sd_min_free_pct": (0, 50), "hotspot_min_kbit": (0, 100000), "trip_gap_h": (0, 48)}


def apply_settings(j):
    """Settings changed on the page; returns an error text or ""."""
    if not isinstance(j, dict):
        return "zle dane"
    upd = {}
    for k, (lo, hi) in SETTING_LIMITS.items():
        if k in j:
            try:
                v = int(j[k])
            except (TypeError, ValueError):
                return "zla wartosc: " + k
            if not lo <= v <= hi:
                return "poza zakresem: " + k
            upd[k] = v
    if "weather" in j:
        upd["weather"] = bool(j["weather"])
    if "notify" in j:
        t = j["notify"]
        if t is not None and (not isinstance(t, str) or not re.fullmatch(r"(notify\.)?[a-z0-9_]{0,64}", t)):
            return "zla nazwa powiadomienia"
        upd["notify"] = t
    if "odo" in j:
        o = j["odo"]
        if o is None:
            upd["odo"] = None
        else:
            km = num((o or {}).get("km"))
            if km is None or not 0 <= km < 1000000:
                return "zly przebieg"
            upd["odo"] = {"km": round(km), "date": int(num(o.get("date")) or now_ms())}
    if "service" in j:
        svc = j["service"]
        if not isinstance(svc, list) or len(svc) > 12:
            return "zla lista serwisu"
        out, seen = [], set()
        for it in svc:
            name = str((it or {}).get("name") or "").strip()[:40]
            interval = num(it.get("interval_km"))
            last = it.get("last_km")
            if not name or interval is None or not 50 <= interval <= 100000:
                return "zla pozycja serwisu"
            sid = str(it.get("id") or slug_entity(name))[:24]
            if not re.fullmatch(r"[a-z0-9_]{1,24}", sid) or sid in seen:
                sid = slug_entity(name)[:20] + "_%d" % len(out)
            seen.add(sid)
            last = num(last)
            out.append({"id": sid, "name": name, "interval_km": int(interval),
                        "last_km": None if last is None else int(last),
                        "last_date": None if num(it.get("last_date")) is None else int(num(it.get("last_date")))})
        upd["service"] = out
    save_state(**upd)
    if "service" in upd or "odo" in upd:
        if MQTT.connected:
            threading.Thread(target=MQTT.announce, daemon=True).start()
        else:
            threading.Thread(target=publish_sensors, daemon=True).start()
    return ""


class Page(Base):
    """Port 8099 (Ingress): the ride page and its API."""

    def allowed(self):
        if self.client_address[0] in INGRESS_PEERS:
            return True
        self.send(403, "tylko przez Home Assistant", "text/plain")
        return False

    def rides_json(self):
        rides = []
        try:
            names = os.listdir(RIDES)
        except FileNotFoundError:
            names = []
        files = {}
        for name in names:
            m = re.fullmatch(r"(\d+)\.([a-z]+)", name)
            if m:
                files.setdefault(int(m.group(1)), {})[m.group(2)] = os.path.getsize(os.path.join(RIDES, name))
        for n in sorted(files, reverse=True):
            if "json" not in files[n]:
                continue
            r = {"n": n, "files": files[n], "summary": summary(n)}
            nm = name_info(n)
            if nm.get("name"):
                r["name"] = nm["name"]
            if nm.get("fav"):
                r["fav"] = True
            if nm.get("note"):
                r["note"] = nm["note"]
            if "wx" in files[n]:
                w = weather_summary(read_json(ride_path(n, "wx"), None))
                if w:
                    r["wx"] = w
            if "rep" in files[n]:
                pr = problems(report(n))
                if pr:
                    r["problems"] = pr
            if "trk" in files[n]:
                try:
                    cv = curvy_of(n)
                    if cv:
                        r["curvy"] = cv
                except Exception as e:
                    log("Kretosc %04d nieudana: %s" % (n, e))
            rides.append(r)
        return {"fw": VERSION, "source": "ha", "trip_gap_h": settings()["trip_gap_h"], "free_mb": None,
                "battery": None, "vbus": False, "upload": False, "rides": rides}

    def status_json(self):
        s = state()
        st = settings()
        odo = odometer()
        return {"ha": {
            "version": VERSION,
            "rides": len(ride_numbers()), "last_ingest": s.get("last_ingest"), "last_ride": s.get("last_ride"),
            "last_from": s.get("last_from"), "last_error": s.get("last_error") or None,
            "last_error_at": s.get("last_error_at"), "notify": notify_target() or None,
            "box_fw": s.get("box_fw"), "box_seen": s.get("box_seen"), "box_battery": s.get("box_battery"),
            "box_sd_total": s.get("box_sd_total"), "box_sd_free": s.get("box_sd_free"),
            "sd_min_free_pct": st["sd_min_free_pct"],
            "fw_offer": (firmware_offer() or {}).get("version"),
            "odo": odo, "odo_set": st["odo"], "service": service_status(odo),
            "parking": parking(newest_ride()),
            "mqtt": {"connected": MQTT.connected, "host": MQTT.host, "user": MQTT.user or None,
                     "started": MQTT.client is not None, "error": MQTT.status_error()},
            "weather": st["weather"]}}

    def do_GET(self):
        if not self.allowed():
            return
        path, q = self.query()
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(WWW, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html")
            except FileNotFoundError:
                return self.send(500, "brak strony", "text/plain")
        if navapi.page_get(self, path, q):
            return
        if path == "/api/rides":
            return self.send(200, self.rides_json())
        if path == "/api/scans":
            return self.send(200, {"scans": []})
        if path == "/api/status":
            return self.send(200, self.status_json())
        if path == "/api/versions":
            return self.send(200, versions(reload_store=q.get("check") == "1"))
        if path == "/api/settings":
            remote = (options().get("adres_spoza_domu") or "").strip().rstrip("/")
            st = settings()
            return self.send(200, dict(st, key=key(), local_url=local_url(), remote_url=remote,
                                       notify_option=(options().get("powiadomienie") or "").strip(),
                                       notify_effective=notify_target()))
        if path == "/api/notify_targets":
            return self.send(200, {"targets": notify_targets()})
        if path == "/dl":
            f = q.get("f", "")
            m = re.fullmatch(r"/rides/(\d{1,7})\.(trk|thm|json|nam|rep|wx|mtl)", f)
            if not m:
                return self.send(400, "zla sciezka", "text/plain")
            p = ride_path(int(m.group(1)), m.group(2))
            if not os.path.exists(p):
                return self.send(404, "brak pliku", "text/plain")
            if "view" in q:
                return self.send_path(p, "text/plain; charset=utf-8")
            return self.send_path(p, "application/octet-stream",
                                  {"Content-Disposition": 'attachment; filename="%s"' % os.path.basename(p)})
        self.send(404, "brak", "text/plain")

    def do_POST(self):
        if not self.allowed():
            return
        path, q = self.query()
        body = self.read_body(8 * 1024 * 1024 if path == "/api/nav/gpx" else 65536)
        if navapi.page_post(self, path, q, body):
            return
        if path == "/api/settings":
            try:
                j = json.loads(body or b"{}")
            except ValueError:
                return self.send(400, "zle dane", "text/plain")
            err = apply_settings(j)
            if err:
                return self.send(400, err, "text/plain")
            return self.send(200, settings())
        if path == "/api/service/done":
            sid = q.get("id", "")
            if sid not in [it["id"] for it in settings()["service"]]:
                return self.send(404, "brak pozycji", "text/plain")
            odo = service_done(sid)
            return self.send(200, {"ok": True, "km": odo})
        if path == "/api/weather":
            try:
                n = int(q.get("n", ""))
                wx = fetch_weather(n)
            except Exception as e:
                return self.send(502, {"error": "pogoda nieudana: %s" % e})
            return self.send(200, wx or {"points": []})
        if path == "/api/name":
            try:
                n = int(q.get("n", ""))
            except ValueError:
                n = 0
            if n <= 0 or not os.path.exists(ride_path(n, "json")):
                return self.send(404, "brak jazdy", "text/plain")
            with LOCK:
                old = name_info(n)
                name, note, fav = old.get("name") or "", old.get("note") or "", bool(old.get("fav"))
                if "name" in q:
                    name = q["name"][:80]
                if "note" in q:
                    note = q["note"][:600]
                if "fav" in q:
                    fav = q["fav"] == "1"
                if not name and not note and not fav:
                    if os.path.exists(ride_path(n, "nam")):
                        os.remove(ride_path(n, "nam"))
                else:
                    write_json(ride_path(n, "nam"), {"name": name, "fav": fav, "note": note})
            threading.Thread(target=publish_sensors, daemon=True).start()
            return self.send(200, "OK", "text/plain")
        if path == "/api/delete":
            try:
                n = int(q.get("n", ""))
            except ValueError:
                n = 0
            if n <= 0:
                return self.send(400, "zly numer", "text/plain")
            with LOCK:
                for ext in ALL_EXTS:
                    if os.path.exists(ride_path(n, ext)):
                        os.remove(ride_path(n, ext))
                index = read_json(INDEX, {})
                write_json(INDEX, {k: v for k, v in index.items() if v != n})
                _CURVY.pop(str(n), None)
            log("Usunieto przejazd %04d" % n)
            threading.Thread(target=publish_sensors, daemon=True).start()
            return self.send(200, "OK", "text/plain")
        if path == "/api/addon/check":
            try:
                return self.send(200, addon_info(reload_store=True))
            except Exception as e:
                log("Sprawdzanie aktualizacji nieudane:", e)
                return self.send(502, {"error": "Home Assistant nie odpowiedział: %s" % e})
        if path == "/api/addon/update":
            try:
                info = addon_info()
                if not info["update"]:
                    return self.send(409, {"error": "brak nowszej wersji"})
                log("Aktualizacja dodatku do wersji", info["latest"])
                # The Supervisor builds the new version and restarts this add-on.
                threading.Thread(target=lambda: ha_call("POST", "/store/addons/%s/update" % info["slug"], {},
                                                        timeout=900), daemon=True).start()
                return self.send(200, {"ok": True, "latest": info["latest"]})
            except Exception as e:
                log("Aktualizacja nieudana:", e)
                return self.send(502, {"error": str(e)})
        if path == "/api/upload":
            return self.send(409, "wysyłkę robi skrzynka", "text/plain")
        self.send(404, "brak", "text/plain")


def serve(port, handler):
    srv = ThreadingHTTPServer(("0.0.0.0", port), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    for d in (RIDES, INCOMING, CACHE, DATA):
        os.makedirs(d, exist_ok=True)
    key()
    navapi.init(sys.modules[__name__])
    serve(INGRESS_PORT, Page)
    serve(INGEST_PORT, Ingest)
    log("NT1100 Jazdy %s: %d jazd w %s; strona przez panel HA, odbior jazd na porcie %d" %
        (VERSION, len(ride_numbers()), RIDES, INGEST_PORT))
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=sensor_loop, daemon=True).start()
    threading.Thread(target=weather_loop, daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
