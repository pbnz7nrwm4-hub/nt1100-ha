"""NT1100 Jazdy: Home Assistant add-on for the NT1100 ride recorder.

Two HTTP servers:
  * port 8099 (Home Assistant Ingress, panel in the side menu): the same ride
    page as on the box, with the same /api/* (rides, names, deletion, files);
  * port 8098 (published by Home Assistant, also behind Cloudflare): only
    /api/ping and /api/ingest, both need the key in the "X-Klucz" header.

Rides are kept in /share/nt1100/rides/NNNN.{trk,thm,json,nam}, like on the
box's SD card. Python standard library only.
"""

import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
import traceback
import urllib.parse
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.4"
SHARE = os.environ.get("NT_SHARE", "/share/nt1100")
DATA = os.environ.get("NT_DATA", "/data")
WWW = os.environ.get("NT_WWW", os.path.join(os.path.dirname(os.path.abspath(__file__)), "www"))
INGRESS_PORT = int(os.environ.get("NT_INGRESS_PORT", "8099"))
INGEST_PORT = int(os.environ.get("NT_INGEST_PORT", "8098"))
# Only Home Assistant's ingress proxy may open the page (no login otherwise).
INGRESS_PEERS = set(os.environ.get("NT_INGRESS_PEERS", "172.30.32.2").split(","))
SUPERVISOR = os.environ.get("NT_SUPERVISOR", "http://supervisor")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
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

RIDES = os.path.join(SHARE, "rides")
INCOMING = os.path.join(SHARE, "incoming")
INDEX = os.path.join(SHARE, "index.json")
STATE = os.path.join(DATA, "stan.json")
KEYFILE = os.path.join(DATA, "klucz")
EXTS = ("trk", "thm", "nam", "json")
MAX_FILE = 40 * 1024 * 1024
LOCK = threading.RLock()


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


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


def read_small(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(65536)
    except Exception:
        return ""


def summary(n):
    try:
        return json.loads(read_small(ride_path(n, "json")))
    except Exception:
        return None


def name_info(n):
    try:
        j = json.loads(read_small(ride_path(n, "nam")))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def ride_key(ride_id, json_bytes):
    """The same ride sent again lands on the same number."""
    if ride_id and ride_id not in ("bez-czasu",) and not ride_id.startswith("nr"):
        return ride_id
    return "%s-%08x" % (ride_id or "jazda", zlib.crc32(json_bytes) & 0xFFFFFFFF)


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
        if not addr:
            log("Adres IP: brak w /network/info:", json.dumps(info)[:300])
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


def fmt_num(v, d=0):
    if v is None:
        return None
    try:
        return round(float(v), d) if d else int(round(float(v)))
    except (TypeError, ValueError):
        return None


def newest_ride():
    best, best_key = None, None
    for n in ride_numbers():
        s = summary(n) or {}
        k = (s.get("start") or "", n)
        if best_key is None or k > best_key:
            best, best_key = n, k
    return best


def publish_sensors():
    """Sensors of the last ride and totals. States set over the API are lost
    when Home Assistant restarts, so this runs again every 10 minutes."""
    if not TOKEN:
        return
    rides = ride_numbers()
    total_km = 0.0
    for n in rides:
        s = summary(n) or {}
        total_km += float(s.get("distance_km") or 0)
    n = newest_ride()
    s = (summary(n) if n else None) or {}
    nm = name_info(n) if n else {}
    attrs_ride = {"przejazd": n, "nazwa": nm.get("name") or None}
    dev = "NT1100 "
    items = [
        ("sensor.nt1100_ostatnia_jazda_dystans", fmt_num(s.get("distance_km"), 1),
         {"unit_of_measurement": "km", "device_class": "distance", "icon": "mdi:map-marker-distance",
          "friendly_name": dev + "ostatnia jazda: dystans"}),
        ("sensor.nt1100_ostatnia_jazda_czas", fmt_num(s.get("moving_min")),
         {"unit_of_measurement": "min", "device_class": "duration", "icon": "mdi:timer-outline",
          "friendly_name": dev + "ostatnia jazda: czas jazdy"}),
        ("sensor.nt1100_ostatnia_jazda_predkosc_maks", fmt_num(s.get("max_speed")),
         {"unit_of_measurement": "km/h", "device_class": "speed", "icon": "mdi:speedometer",
          "friendly_name": dev + "ostatnia jazda: prędkość maks."}),
        ("sensor.nt1100_ostatnia_jazda_predkosc_srednia", fmt_num(s.get("avg_speed")),
         {"unit_of_measurement": "km/h", "device_class": "speed", "icon": "mdi:speedometer-medium",
          "friendly_name": dev + "ostatnia jazda: prędkość średnia"}),
        ("sensor.nt1100_ostatnia_jazda_przechyl_lewo", fmt_num(s.get("max_lean_left")),
         {"unit_of_measurement": "°", "icon": "mdi:angle-acute",
          "friendly_name": dev + "ostatnia jazda: maks. przechył w lewo"}),
        ("sensor.nt1100_ostatnia_jazda_przechyl_prawo", fmt_num(s.get("max_lean_right")),
         {"unit_of_measurement": "°", "icon": "mdi:angle-acute",
          "friendly_name": dev + "ostatnia jazda: maks. przechył w prawo"}),
        ("sensor.nt1100_ostatnia_jazda_start", s.get("start"),
         {"device_class": "timestamp", "icon": "mdi:motorbike", "friendly_name": dev + "ostatnia jazda: start"}),
        ("sensor.nt1100_ostatnia_jazda_nazwa", (nm.get("name") or s.get("ride") or None),
         {"icon": "mdi:motorbike", "friendly_name": dev + "ostatnia jazda: nazwa"}),
        ("sensor.nt1100_jazdy_liczba", len(rides),
         {"icon": "mdi:counter", "state_class": "total", "friendly_name": dev + "jazdy w Home Assistant"}),
        ("sensor.nt1100_jazdy_km_razem", round(total_km, 1),
         {"unit_of_measurement": "km", "device_class": "distance", "state_class": "total_increasing",
          "icon": "mdi:road-variant", "friendly_name": dev + "kilometry razem"}),
    ]
    try:
        for entity, value, attrs in items:
            a = dict(attrs)
            if entity.startswith("sensor.nt1100_ostatnia"):
                a.update(attrs_ride)
            ha_call("POST", "/core/api/states/" + entity,
                    {"state": "unknown" if value is None else value, "attributes": a})
    except Exception as e:
        log("Czujniki: Home Assistant nie odpowiada:", e)


def hm(minutes):
    m = int(round(float(minutes or 0)))
    return "%d h %02d min" % (m // 60, m % 60) if m >= 60 else "%d min" % m


def notify_ride(n, s):
    nm = name_info(n).get("name")
    parts = ["%s km" % str(fmt_num(s.get("distance_km"), 1)).replace(".", ","), hm(s.get("moving_min"))]
    if s.get("max_speed") is not None:
        parts.append("maks. %d km/h" % fmt_num(s.get("max_speed")))
    if s.get("max_lean_left") is not None and s.get("max_lean_right") is not None:
        parts.append("przechył L %d° / P %d°" % (fmt_num(s.get("max_lean_left")), fmt_num(s.get("max_lean_right"))))
    msg = " · ".join(parts)
    title = "NT1100: " + (nm or "nowa jazda")
    target = (options().get("powiadomienie") or "").strip()
    panel = panel_url()
    if target.startswith("notify."):
        target = target[len("notify."):]
    try:
        ha_call("POST", "/core/api/events/nt1100_nowa_jazda", dict(s, przejazd=n, nazwa=nm))
        if target:
            ha_call("POST", "/core/api/services/notify/" + target,
                    {"title": title, "message": msg,
                     "data": {"url": panel, "clickAction": panel, "group": "nt1100"}})
        else:
            ha_call("POST", "/core/api/services/persistent_notification/create",
                    {"title": title, "message": msg + "\n\n[Pokaż jazdy](" + panel + ")",
                     "notification_id": "nt1100_jazda"})
        log("Powiadomienie:", title, "-", msg)
    except Exception as e:
        log("Powiadomienie nieudane (sprawdz pole 'powiadomienie' w konfiguracji):", e)
        save_state(last_error="powiadomienie nieudane: %s" % e, last_error_at=int(time.time() * 1000))


def sensor_loop():
    for _ in range(30):  # Home Assistant may still be starting
        try:
            ha_call("GET", "/core/api/")
            break
        except Exception:
            time.sleep(10)
    while True:
        publish_sensors()
        time.sleep(600)


# ---------------------------------------------------------------- ingest

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
        write_json(INDEX, index)
        save_state(last_ingest=int(time.time() * 1000), last_ride=n, last_from=source, last_error="",
                   last_error_at=None)
        log("Jazda zapisana: przejazd %04d (ze skrzynki nr %d, %s)%s" % (n, box_n, k, "" if is_new else " - ponownie"))
    threading.Thread(target=lambda: (publish_sensors(), is_new and notify_ride(n, s)), daemon=True).start()
    return n


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
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def query(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path, {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}

    def read_body(self, limit):
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            out = bytearray()
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    return bytes(out)
                if len(out) + size > limit:
                    raise ValueError("plik za duzy")
                out += self.rfile.read(size)
                self.rfile.readline()
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("plik za duzy")
        data = b""
        while len(data) < n:
            chunk = self.rfile.read(n - len(data))
            if not chunk:
                break
            data += chunk
        return data


class Ingest(Base):
    """Port 8098: the box sends rides here (home network or Cloudflare)."""

    def authorized(self):
        got = (self.headers.get("X-Klucz") or "").strip()
        return bool(got) and hmac.compare_digest(got.encode(), key().encode())

    def source(self):
        return "przez internet" if self.headers.get("CF-Connecting-IP") else "sieć domowa"

    def do_GET(self):
        path, _ = self.query()
        if path == "/api/ping":
            if not self.authorized():
                log("Odrzucono: zly klucz (", self.client_address[0], ")")
                return self.send(401, {"ok": False, "error": "zly klucz"})
            return self.send(200, {"ok": True, "app": "NT1100 Jazdy", "version": VERSION})
        self.send(404, {"ok": False, "error": "brak"})

    def do_POST(self):
        path, q = self.query()
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
            if not (0 < box_n < 1000000) or ext not in EXTS or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", ride_id) \
                    or not (0 <= size <= MAX_FILE):
                raise ValueError
        except ValueError:
            return self.send(400, {"ok": False, "error": "zle parametry"})
        try:
            data = self.read_body(MAX_FILE)
        except ValueError as e:
            return self.send(413, {"ok": False, "error": str(e)})
        if len(data) != size or (zlib.crc32(data) & 0xFFFFFFFF) != crc:
            log("Plik %s jazdy %d dotarl uszkodzony (%d z %d B)" % (ext, box_n, len(data), size))
            return self.send(422, {"ok": False, "error": "plik dotarl niepelny albo uszkodzony"})
        stage = os.path.join(INCOMING, "%d-%s" % (box_n, ride_id))
        os.makedirs(stage, exist_ok=True)
        with open(os.path.join(stage, ext + ".tmp"), "wb") as f:
            f.write(data)
        os.replace(os.path.join(stage, ext + ".tmp"), os.path.join(stage, ext))
        if ext != "json":
            return self.send(200, {"ok": True})
        try:
            n = commit(box_n, ride_id, stage, self.source())
        except Exception as e:
            traceback.print_exc()
            save_state(last_error="zapis jazdy: %s" % e, last_error_at=int(time.time() * 1000))
            return self.send(500, {"ok": False, "error": str(e)})
        self.send(200, {"ok": True, "n": n})


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
            rides.append(r)
        return {"fw": VERSION, "source": "ha", "trip_gap_h": state().get("trip_gap_h", 3), "free_mb": None,
                "battery": None, "vbus": False, "upload": False, "rides": rides}

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
        if path == "/api/rides":
            return self.send(200, self.rides_json())
        if path == "/api/scans":
            return self.send(200, {"scans": []})
        if path == "/api/status":
            s = state()
            target = (options().get("powiadomienie") or "").strip()
            return self.send(200, {"ha": {
                "rides": len(ride_numbers()), "last_ingest": s.get("last_ingest"), "last_ride": s.get("last_ride"),
                "last_from": s.get("last_from"), "last_error": s.get("last_error") or None,
                "last_error_at": s.get("last_error_at"), "notify": target or None}})
        if path == "/api/settings":
            remote = (options().get("adres_spoza_domu") or "").strip().rstrip("/")
            return self.send(200, {"trip_gap_h": state().get("trip_gap_h", 3), "key": key(),
                                   "local_url": local_url(), "remote_url": remote})
        if path == "/dl":
            f = q.get("f", "")
            m = re.fullmatch(r"/rides/(\d{1,7})\.(trk|thm|json|nam)", f)
            if not m:
                return self.send(400, "zla sciezka", "text/plain")
            p = ride_path(int(m.group(1)), m.group(2))
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except FileNotFoundError:
                return self.send(404, "brak pliku", "text/plain")
            if "view" in q:
                return self.send(200, data, "text/plain; charset=utf-8")
            return self.send(200, data, "application/octet-stream",
                             {"Content-Disposition": 'attachment; filename="%s"' % os.path.basename(p)})
        self.send(404, "brak", "text/plain")

    def do_POST(self):
        if not self.allowed():
            return
        path, q = self.query()
        body = self.read_body(65536)
        if path == "/api/settings":
            try:
                j = json.loads(body or b"{}")
                g = int(j.get("trip_gap_h", state().get("trip_gap_h", 3)))
                if not 0 <= g <= 48:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                return self.send(400, "zle dane", "text/plain")
            save_state(trip_gap_h=g)
            return self.send(200, {"trip_gap_h": g})
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
                for ext in EXTS:
                    if os.path.exists(ride_path(n, ext)):
                        os.remove(ride_path(n, ext))
                index = read_json(INDEX, {})
                write_json(INDEX, {k: v for k, v in index.items() if v != n})
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
    os.makedirs(RIDES, exist_ok=True)
    os.makedirs(INCOMING, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    key()
    serve(INGRESS_PORT, Page)
    serve(INGEST_PORT, Ingest)
    log("NT1100 Jazdy %s: %d jazd w %s; strona przez panel HA, odbior jazd na porcie %d" %
        (VERSION, len(ride_numbers()), RIDES, INGEST_PORT))
    threading.Thread(target=sensor_loop, daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
