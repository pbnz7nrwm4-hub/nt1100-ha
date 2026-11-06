"""Nawigacja: planer tras, paczki tras dla ekranu, mapa na kartę ekranu.

Co tu jest:
  * trasy: z pliku GPX (np. z Kurvigera) albo z silnika tras (GraphHopper
    w kontenerze, adres w ustawieniach) z wariantami krętości, punktami po
    drodze, omijaniem i trasą okrężną;
  * paczka trasy (.ntr + .json): linia, skręty, limity z mapy, fotoradary
    i odcinkowe pomiary, prognoza pogody dla punktów trasy, punkty po drodze;
  * mapa dla ekranu: kwadraty .ntt pobierane z kontenera (build_map.py)
    i podawane ekranowi;
  * szukanie miejsc (Photon/OpenStreetMap), cel z linku Map Google/Apple
    (skrót iOS "Wyślij na motocykl");
  * korki na trasie (TomTom, klucz opcjonalny) i przeliczanie trasy w jeździe;
  * dziennik ekranu (co i kiedy pokazał) i zgodność jazdy z planem.

Pliki w /share/nt1100/nawigacja/: trasy/<id>.json, trasy/<id>.ntr,
trasy.json (lista), mapa/ (kwadraty), ekran/ (dziennik), cele.json.
"""
import binascii
import concurrent.futures
import gzip
import json
import math
import os
import re
import struct
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import adresy
import graf
import ntt

VERSION_NTR = 1
# Rodzaje wskazówek (jak na ekranie).
T_STRAIGHT, T_SLIGHT_L, T_LEFT, T_SHARP_L, T_SLIGHT_R, T_RIGHT, T_SHARP_R, T_UTURN = 0, 1, 2, 3, 4, 5, 6, 7
T_ROUNDABOUT, T_KEEP_L, T_KEEP_R, T_WAYPOINT, T_FINISH, T_FERRY = 8, 9, 10, 11, 12, 13
TURN_TEXT = {T_STRAIGHT: "prosto", T_SLIGHT_L: "lekko w lewo", T_LEFT: "w lewo", T_SHARP_L: "ostro w lewo",
             T_SLIGHT_R: "lekko w prawo", T_RIGHT: "w prawo", T_SHARP_R: "ostro w prawo", T_UTURN: "zawróć",
             T_ROUNDABOUT: "rondo", T_KEEP_L: "trzymaj się lewej", T_KEEP_R: "trzymaj się prawej",
             T_WAYPOINT: "punkt trasy", T_FINISH: "cel", T_FERRY: "prom"}
GH_SIGNS = {-3: T_SHARP_L, -2: T_LEFT, -1: T_SLIGHT_L, 0: T_STRAIGHT, 1: T_SLIGHT_R, 2: T_RIGHT, 3: T_SHARP_R,
            4: T_FINISH, 5: T_WAYPOINT, 6: T_ROUNDABOUT, -7: T_KEEP_L, 7: T_KEEP_R, -8: T_UTURN, 8: T_UTURN,
            -98: T_UTURN, 101: T_FERRY}
# pliki mapy z kontenera: kwadraty .ntt i (od mapy 3) graf tras .ntg
MAP_FILE = re.compile(r"c_-?\d+_-?\d+\.ntt|g_-?\d+_-?\d+\.ntg|a_-?\d+_-?\d+\.nta|a_index\.nta|a_poi\.nta")
# części mapy obok kwadratów: graf tras (mapa 3) i adresy (mapa 4)
MAP_EXTRA = ("graph", "addr")
WX_CACHE = {}  # (lat, lon) zaokrąglone do 0,1° -> (czas, prognoza Open-Meteo)
WX_LOCK = threading.Lock()
WX_TTL = 900
VARIANTS = (("szybko", "Najszybciej"), ("lekko", "Lekko kręto"), ("kreto", "Kręto"), ("bardzo", "Bardzo kręto"))
# trasa z odcinków o różnych wariantach (wybór przy każdym odcinku w planerze)
MIX = ("mix", "Mój plan")
# Suwaki wariantów 0–100: glowne = unikanie autostrad i dróg krajowych,
# zakrety = szukanie dróg krętych, dluzej = zgoda na dłuższą trasę.
CURVY_DEFAULT = {
    "lekko": {"glowne": 45, "zakrety": 25, "dluzej": 60},
    "kreto": {"glowne": 90, "zakrety": 60, "dluzej": 60},
    "bardzo": {"glowne": 100, "zakrety": 100, "dluzej": 60},
}
CURVY_KEYS = ("glowne", "zakrety", "dluzej")
# progi opisu krętości (°/km): poniżej 1. prosta, 2. lekko kręta, 3. kręta, wyżej bardzo kręta
CURVY_LEVELS_DEFAULT = [30, 80, 150]
CURVY_NAMES = ("prosta", "lekko kręta", "kręta", "bardzo kręta")


def curvy_sliders(raw):
    """Suwaki z ustawień, uzupełnione domyślnymi i przycięte do 0–100."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for v, d in CURVY_DEFAULT.items():
        r = raw.get(v) if isinstance(raw.get(v), dict) else {}
        out[v] = {}
        for k in CURVY_KEYS:
            try:
                x = int(r.get(k, d[k]))
            except (TypeError, ValueError):
                x = d[k]
            out[v][k] = max(0, min(100, x))
    return out


def curvy_levels(raw):
    try:
        lv = [int(x) for x in raw]
        if len(lv) == 3 and 0 < lv[0] < lv[1] < lv[2] <= 1000:
            return lv
    except (TypeError, ValueError):
        pass
    return list(CURVY_LEVELS_DEFAULT)


def curvy_name(deg_km, levels=None):
    lv = curvy_levels(levels) if levels is not None else CURVY_LEVELS_DEFAULT
    for lim, name in zip(lv, CURVY_NAMES):
        if deg_km < lim:
            return name
    return CURVY_NAMES[-1]
AVOID = ("gruntowe", "szutrowe", "platne", "autostrady", "promy")
FAV_MAX = 30
MAX_ROUTE_PTS = 20000
LOG = print


def log(*a):
    if LOG is print:
        print(time.strftime("%H:%M:%S"), "[nawigacja]", *a, flush=True)
    else:
        LOG("[nawigacja]", *a)


def http_json(url, data=None, headers=None, timeout=25):
    h = {"User-Agent": "NT1100-Jazdy", "Accept": "application/json"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------- ceny paliw (1.5.23)

FUEL_PB95 = ("REGULAR_UNLEADED", "SP95", "SP95_E10")


def fuel_price_google(key, lat, lon, radius_m=250):
    """Cena Pb95 najbliższej stacji wg Google Places (ceny zgłaszane przez kierowców).
    Zwraca {"text", "pb95", "age_min", "station"} albo None."""
    j = http_json("https://places.googleapis.com/v1/places:searchNearby",
                  data={"includedTypes": ["gas_station"], "maxResultCount": 3, "languageCode": "pl",
                        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon},
                                                           "radius": radius_m}}},
                  headers={"X-Goog-Api-Key": key,
                           "X-Goog-FieldMask": "places.displayName,places.location,places.fuelOptions"},
                  timeout=12)
    return fuel_price_from_places(j, time.time())


def fuel_price_from_places(j, now):
    best = None
    for pl in (j or {}).get("places") or []:
        for fp in ((pl.get("fuelOptions") or {}).get("fuelPrices") or []):
            if fp.get("type") not in FUEL_PB95:
                continue
            pr = fp.get("price") or {}
            try:
                val = float(pr.get("units") or 0) + float(pr.get("nanos") or 0) / 1e9
            except (TypeError, ValueError):
                continue
            if not 2 <= val <= 20:
                continue
            upd = parse_iso(fp.get("updateTime"))
            age = int((now - upd) / 60) if upd else None
            cand = (age if age is not None else 10 ** 6, val)
            if best is None or cand < best[0]:
                best = (cand, val, age, (pl.get("displayName") or {}).get("text") or "")
        if best:
            break
    if not best:
        return None
    _, val, age, name = best
    if age is None:
        when = ""
    elif age < 60:
        when = " · %d min temu" % age
    elif age < 48 * 60:
        when = " · %d h temu" % (age // 60)
    else:
        when = " · %d dni temu" % (age // 1440)
    return {"text": ("%.2f zł" % val).replace(".", ",") + when, "pb95": round(val, 2), "age_min": age, "station": name}


def parse_iso(s):
    """ISO 8601 (Z albo +hh:mm) -> unix; None gdy nie da się."""
    if not s or not isinstance(s, str):
        return None
    try:
        import datetime
        t = s.replace("Z", "+00:00")
        if "." in t:
            # ułamki sekund o dowolnej długości
            head, tail = t.split(".", 1)
            m = re.match(r"(\d+)(.*)", tail)
            t = head + (m.group(2) if m else "")
        d = datetime.datetime.fromisoformat(t)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d.timestamp()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- geometria

def cum_dist(pts):
    out = [0.0]
    for i in range(1, len(pts)):
        out.append(out[-1] + ntt.dist_m(pts[i - 1], pts[i]))
    return out


def simplify(pts, tol_m=3.0):
    """Douglas-Peucker (iteracyjnie), punkty jako (lat, lon[, ...])."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        best, bi = 0.0, -1
        for i in range(a + 1, b):
            d, _ = ntt.point_segment(pts[i], pts[a], pts[b])
            if d > best:
                best, bi = d, i
        if best > tol_m:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [p for p, k in zip(pts, keep) if k]


def densify(pts, step_m=25.0):
    """Dokłada punkty, żeby odcinki były krótsze niż step_m (ekran rzutuje
    pozycję na linię; limity i fotoradary mają wtedy dokładny indeks)."""
    out = [pts[0]]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        d = ntt.dist_m(a, b)
        n = int(d // step_m)
        for k in range(1, n + 1):
            t = k / (n + 1)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


def nearest_index(pts, p, start=0, window=None):
    """Indeks punktu trasy najbliższego p (opcjonalnie w oknie od start)."""
    best, bi = None, start
    end = len(pts) if window is None else min(len(pts), start + window)
    for i in range(start, end):
        d = ntt.dist_m(pts[i], p)
        if best is None or d < best:
            best, bi = d, i
    return bi, best


def turns_from_geometry(pts, cum):
    """Skręty z kształtu trasy (plik GPX bez wskazówek): zmiana kierunku
    mierzona na ok. 25 m przed i za punktem; skręt tam, gdzie zmiana jest
    największa w oknie 40 m, od 35 stopni."""
    n = len(pts)
    ang = [0.0] * n
    for i in range(1, n - 1):
        a = i
        while a > 0 and cum[i] - cum[a] < 25:
            a -= 1
        b = i
        while b < n - 1 and cum[b] - cum[i] < 25:
            b += 1
        if a == i or b == i:
            continue
        ang[i] = ntt.angle_diff(ntt.bearing(pts[a], pts[i]), ntt.bearing(pts[i], pts[b]))
    out = []
    i = 1
    while i < n - 1:
        if abs(ang[i]) < 35:
            i += 1
            continue
        j = i
        k = i
        while k < n - 1 and cum[k] - cum[i] <= 40:
            if abs(ang[k]) > abs(ang[j]):
                j = k
            k += 1
        d = ang[j]
        ad = abs(d)
        if ad >= 150:
            t = T_UTURN
        elif ad >= 100:
            t = T_SHARP_L if d < 0 else T_SHARP_R
        elif ad >= 55:
            t = T_LEFT if d < 0 else T_RIGHT
        else:
            t = T_SLIGHT_L if d < 0 else T_SLIGHT_R
        out.append({"idx": j, "type": t, "exit": 0, "text": ""})
        i = j + 1
        while i < n - 1 and cum[i] - cum[j] <= 40:
            i += 1
    return out


# ---------------------------------------------------------------- GPX

def parse_gpx(data):
    """Plik GPX -> {"name", "pts": [(lat, lon)], "wpts": [{"lat","lon","name"}], "rte_turns": [...]}.
    Bierze pierwszy <trk> (wszystkie segmenty), a bez niego <rte>."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError("zły plik GPX: %s" % e)

    def tag(el):
        return el.tag.split("}")[-1]
    name = ""
    pts = []
    wpts = []
    rte_turns = []
    # nazwa trasy: <name> bezpośrednio w trk/rte/metadata/gpx (nie nazwy punktów)
    for parent in root.iter():
        if tag(parent) in ("gpx", "metadata", "trk", "rte"):
            for el in parent:
                if tag(el) == "name" and (el.text or "").strip():
                    name = (el.text or "").strip()
                    break
        if name:
            break
    for trk in [e for e in root.iter() if tag(e) == "trk"]:
        for p in trk.iter():
            if tag(p) == "trkpt":
                pts.append((float(p.get("lat")), float(p.get("lon"))))
        if pts:
            break
    if not pts:
        for rte in [e for e in root.iter() if tag(e) == "rte"]:
            for p in rte:
                if tag(p) == "rtept":
                    pts.append((float(p.get("lat")), float(p.get("lon"))))
                    nm = ""
                    for c in p:
                        if tag(c) in ("name", "desc"):
                            nm = (c.text or "").strip()
                            break
                    rte_turns.append(nm)
            if pts:
                break
    for w in [e for e in root.iter() if tag(e) == "wpt"]:
        nm = ""
        for c in w:
            if tag(c) == "name":
                nm = (c.text or "").strip()
        wpts.append({"lat": float(w.get("lat")), "lon": float(w.get("lon")), "name": nm[:40]})
    if len(pts) < 2:
        raise ValueError("plik GPX nie ma trasy (trk/rte)")
    if len(pts) > 200000:
        raise ValueError("za dużo punktów w GPX")
    return {"name": name[:40], "pts": pts, "wpts": wpts, "rte_turns": rte_turns}


# Skręty w zapisie OsmAnd (TurnType): z nimi OsmAnd prowadzi głosowo po naszej trasie
# bez „Przyciągnij do dróg”. Plik z creator="OsmAndRouter" OsmAnd czyta jak własną trasę:
# ślad = droga, punkty <rte> = manewry (offset = numer punktu śladu).
OSMAND_TURN = {T_STRAIGHT: "C", T_SLIGHT_L: "TSLL", T_LEFT: "TL", T_SHARP_L: "TSHL", T_SLIGHT_R: "TSLR",
               T_RIGHT: "TR", T_SHARP_R: "TSHR", T_UTURN: "TU", T_KEEP_L: "KL", T_KEEP_R: "KR"}
OSMAND_ANGLE = {"TSLL": -30, "TL": -90, "TSHL": -135, "TSLR": 30, "TR": 90, "TSHR": 135, "TU": 180}
PL_TURN = {"C": "Prosto", "TSLL": "Lekko w lewo", "TL": "Skręć w lewo", "TSHL": "Ostro w lewo",
           "TSLR": "Lekko w prawo", "TR": "Skręć w prawo", "TSHR": "Ostro w prawo", "TU": "Zawróć",
           "KL": "Trzymaj się lewej", "KR": "Trzymaj się prawej"}


def osmand_turns(route):
    """Manewry trasy jako [(offset, turn, kąt, opis)] dla OsmAnd."""
    pts = route["pts"]
    out = []
    for t in sorted(route.get("turns") or [], key=lambda x: x["idx"]):
        if t["type"] == T_ROUNDABOUT:
            n = max(1, int(t.get("exit") or 1))
            tt, desc = "RNDB%d" % n, "Na rondzie %d. zjazd" % n
        elif t["type"] in OSMAND_TURN:
            tt = OSMAND_TURN[t["type"]]
            desc = PL_TURN[tt]
        else:
            continue
        if t.get("text"):
            desc += " – " + t["text"]
        out.append((min(max(0, int(t["idx"])), len(pts) - 1), tt, OSMAND_ANGLE.get(tt, 0), desc))
    return out


def to_gpx(route, osmand=False):
    if osmand:
        return to_gpx_osmand(route)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="NT1100 Jazdy" xmlns="http://www.topografix.com/GPX/1/1">']
    name = route.get("name") or "Trasa"
    for w in route.get("waypoints") or []:
        p = route["pts"][w["idx"]]
        out.append('<wpt lat="%.6f" lon="%.6f"><name>%s</name></wpt>' % (p[0], p[1], esc(w.get("name") or "")))
    out.append("<trk><name>%s</name><trkseg>" % esc(name))
    for p in route["pts"]:
        out.append('<trkpt lat="%.6f" lon="%.6f"/>' % (p[0], p[1]))
    out.append("</trkseg></trk></gpx>")
    return "\n".join(out)


def to_gpx_osmand(route, start=None):
    pts = route["pts"]
    times = route.get("times") or []
    name = esc(route.get("name") or "Trasa")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="OsmAndRouter" xmlns="http://www.topografix.com/GPX/1/1" '
           'xmlns:osmand="https://osmand.net">',
           "<metadata><name>%s</name></metadata>" % name]
    for w in route.get("waypoints") or []:
        p = pts[w["idx"]]
        out.append('<wpt lat="%.6f" lon="%.6f"><name>%s</name></wpt>' % (p[0], p[1], esc(w.get("name") or "")))
    out.append("<trk><name>%s</name><trkseg>" % name)
    # czas przy każdym punkcie (od teraz): bez niego OsmAnd po „Dołącz do dróg” liczy przyjazd z zera
    t0 = int(time.time() if start is None else start)
    tt = times if len(times) == len(pts) else [0] * len(pts)
    for p, ts in zip(pts, tt):
        out.append('<trkpt lat="%.6f" lon="%.6f"><time>%s</time></trkpt>'
                   % (p[0], p[1], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0 + int(ts)))))
    out.append("</trkseg></trk>")
    # punkty trasy: start, każdy manewr, cel; time = sekundy do następnego punktu
    turns = [(0, "C", 0, "Start")] + [t for t in osmand_turns(route) if 0 < t[0] < len(pts) - 1]
    out.append("<rte><name>%s</name>" % name)
    for k, (off, tt, ang, desc) in enumerate(turns):
        nxt = turns[k + 1][0] if k + 1 < len(turns) else len(pts) - 1
        dt = int(times[nxt] - times[off]) if len(times) == len(pts) else 0
        p = pts[off]
        ext = "<osmand:time>%d</osmand:time><osmand:offset>%d</osmand:offset>" % (max(0, dt), off)
        if k > 0:
            ext += "<osmand:turn>%s</osmand:turn><osmand:turn-angle>%d</osmand:turn-angle>" % (tt, ang)
        out.append('<rtept lat="%.6f" lon="%.6f"><desc>%s</desc><extensions>%s</extensions></rtept>'
                   % (p[0], p[1], esc(desc), ext))
    p = pts[-1]
    out.append('<rtept lat="%.6f" lon="%.6f"><desc>Cel</desc><extensions><osmand:time>0</osmand:time>'
               '<osmand:offset>%d</osmand:offset></extensions></rtept>' % (p[0], p[1], len(pts) - 1))
    out.append("</rte></gpx>")
    return "\n".join(out)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


RT_KMH = {"szybko": 62, "lekko": 52, "kreto": 46, "bardzo": 41}  # typowa średnia na trasie okrężnej


def circle(lat, lon, r_m, n=20):
    """Wielokąt (lon, lat) przybliżający koło o promieniu r_m metrów."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append([round(lon + r_m * math.sin(a) / (111320.0 * math.cos(math.radians(lat))), 6),
                    round(lat + r_m * math.cos(a) / 110540.0, 6)])
    return out + [out[0]]


def file_crc(path):
    crc = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 16)
            if not b:
                break
            crc = binascii.crc32(b, crc)
    return crc


# ---------------------------------------------------------------- paczka trasy

class Nav:
    def __init__(self, share, data, settings_fn, log_fn=None):
        self.dir = os.path.join(share, "nawigacja")
        self.routes_dir = os.path.join(self.dir, "trasy")
        self.map_dir = os.path.join(self.dir, "mapa")
        self.screen_dir = os.path.join(self.dir, "ekran")
        for d in (self.routes_dir, self.map_dir, self.screen_dir):
            os.makedirs(d, exist_ok=True)
        self.data = data
        self.settings_fn = settings_fn  # -> dict z ustawieniami nawigacji
        self.map = ntt.Map(self.map_dir)
        self.graph = graf.Graph(self.map_dir)
        self.addresses = adresy.Addresses(self.map_dir)
        self.lock = threading.RLock()
        self.state_path = os.path.join(data, "nawigacja.json")
        self.state = self._read(self.state_path, {})
        self.traffic_cache = {}
        self.fuel_cache = {}   # 1.5.23: (lat4, lon4) -> (czas, wynik)
        if log_fn:
            global LOG
            LOG = log_fn

    # ---- pliki
    @staticmethod
    def _read(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    @staticmethod
    def _write(path, obj):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)

    def save_state(self, **kw):
        with self.lock:
            self.state.update(kw)
            self._write(self.state_path, self.state)

    def settings(self):
        s = self.settings_fn() or {}
        return {
            "engine_url": (s.get("engine_url") or "").rstrip("/"),
            "map_url": (s.get("map_url") or "").rstrip("/"),
            "tomtom_key": s.get("tomtom_key") or "",
            # 1.5.23: ceny paliw (Google Places) i kalendarz na ekran 5"
            "google_key": s.get("google_key") or "",
            "calendar_entity": s.get("calendar_entity") or "",
            "lean_popup_deg": int(s.get("lean_popup_deg") or 20),
            "traffic_min": int(s.get("traffic_min") or 5),
            "car_alert_min": int(s.get("car_alert_min") or 5),
            "phone_tracker": s.get("phone_tracker") or "",
            # brama i garaż dla ekranu 5" (encje HA: cover / button / switch / lock; puste = brak)
            "gate_entity": s.get("gate_entity") or "",
            "garage_entity": s.get("garage_entity") or "",
            "offroute_m": int(s.get("offroute_m") or 150),
            "free_km": float(s.get("free_km") or 2),
            "default_variant": s.get("default_variant") or "kreto",
            # tryb pojazdu: w samochodzie trasy „jedź do”, objazdy i powroty liczą się najszybciej
            "vehicle": "auto" if s.get("vehicle") == "auto" else "moto",
            "go_variant": "szybko" if s.get("vehicle") == "auto" else (s.get("default_variant") or "kreto"),
            "curvy": curvy_sliders(s.get("curvy")),
            "curvy_levels": curvy_levels(s.get("curvy_levels") or CURVY_LEVELS_DEFAULT),
            "avoid": s.get("avoid") if isinstance(s.get("avoid"), list) else ["gruntowe", "platne"],
            "home": s.get("home") if isinstance(s.get("home"), dict) else None,
            "fav": [f for f in s.get("fav") if isinstance(f, dict)][:FAV_MAX] if isinstance(s.get("fav"), list) else [],
        }

    # ---- lista tras
    def index(self):
        return self._read(os.path.join(self.dir, "trasy.json"), {"routes": [], "current": None, "next_id": 1})

    def save_index(self, idx):
        self._write(os.path.join(self.dir, "trasy.json"), idx)

    def route_path(self, rid, ext):
        return os.path.join(self.routes_dir, "%d.%s" % (int(rid), ext))

    def route(self, rid):
        return self._read(self.route_path(rid, "json"), None)

    def list_routes(self):
        idx = self.index()
        out = []
        for r in idx["routes"]:
            out.append(r)
        return {"routes": sorted(out, key=lambda r: (-r.get("created", 0), -r["id"])), "current": idx.get("current")}

    def store_route(self, route, make_current=True):
        """Zapisuje trasę (json + ntr) i oznacza jako bieżącą dla ekranu."""
        with self.lock:
            idx = self.index()
            rid = route.get("id") or idx["next_id"]
            idx["next_id"] = max(idx["next_id"], rid + 1)
            route["id"] = rid
            route["version"] = int(time.time())
            route.setdefault("created", route["version"])
            self._write(self.route_path(rid, "json"), route)
            with open(self.route_path(rid, "ntr"), "wb") as f:
                f.write(pack_ntr(route))
            entry = {"id": rid, "name": route.get("name"), "km": round(route["dist_m"] / 1000, 1),
                     "min": int(route.get("time_s", 0) / 60), "variant": route.get("variant"),
                     "created": route["created"], "version": route["version"], "source": route.get("source"),
                     "curvy": route.get("curvy"), "waypoints": len(route.get("waypoints") or [])}
            idx["routes"] = [r for r in idx["routes"] if r["id"] != rid] + [entry]
            if make_current:
                idx["current"] = rid
            self.save_index(idx)
        return rid

    def delete_route(self, rid):
        with self.lock:
            idx = self.index()
            idx["routes"] = [r for r in idx["routes"] if r["id"] != rid]
            if idx.get("current") == rid:
                idx["current"] = None
            self.save_index(idx)
            for ext in ("json", "ntr"):
                try:
                    os.remove(self.route_path(rid, ext))
                except OSError:
                    pass

    def set_current(self, rid):
        with self.lock:
            idx = self.index()
            idx["current"] = rid if any(r["id"] == rid for r in idx["routes"]) else None
            self.save_index(idx)

    # ---- budowa paczki
    def build_route(self, pts, name="", source="gpx", instructions=None, waypoints=None, times=None,
                    variant=None, with_weather=True, start_time=None, limits_hint=None):
        """Z linii trasy robi pełną paczkę: skręty, limity, fotoradary, pogoda.
        Indeksy wskazówek (instructions[].idx) liczą się względem podanych pts;
        po zagęszczeniu są przeliczane. limits_hint: [{lat, lon, kmh}] z silnika,
        używane gdy mapa na karcie nie zna limitów."""
        pts = [(float(p[0]), float(p[1])) for p in pts]
        anchors = []
        for t in instructions or []:
            p = pts[max(0, min(len(pts) - 1, int(t.get("idx") or 0)))]
            anchors.append(p)
        if len(pts) > 4000:
            pts = simplify(pts, 4.0)
        pts = densify(pts, 30.0)
        if len(pts) > MAX_ROUTE_PTS:
            step = len(pts) / MAX_ROUTE_PTS
            pts = [pts[int(i * step)] for i in range(MAX_ROUTE_PTS)] + [pts[-1]]
        start = 0
        for t, p in zip(instructions or [], anchors):
            start, _ = nearest_index(pts, p, start)
            t["idx"] = start
        cum = cum_dist(pts)
        route = {"name": name[:40] or "Trasa", "source": source, "variant": variant, "pts": pts,
                 "dist_m": int(cum[-1]), "cum": [int(c) for c in cum]}
        # limity i etykiety dróg z mapy
        limits, labels = self.limits_along(pts, cum)
        if not limits and limits_hint:
            start = 0
            cur = None
            for h in limits_hint:
                start, _ = nearest_index(pts, (h["lat"], h["lon"]), start)
                if h["kmh"] != cur:
                    limits.append({"idx": start, "kmh": int(h["kmh"])})
                    cur = h["kmh"]
        route["limits"] = limits
        # skręty
        if instructions:
            instr = instructions
        else:
            instr = turns_from_geometry(pts, cum)
        for t in instr:
            if not t.get("text"):
                lab = labels.get(min(len(pts) - 1, t["idx"] + 3)) or labels.get(t["idx"])
                t["text"] = (lab or "")[:30]
        route["turns"] = instr
        # punkty po drodze
        wps = []
        for w in waypoints or []:
            i = w.get("idx")
            if i is None:
                i, _ = nearest_index(pts, (w["lat"], w["lon"]))
            wps.append({"idx": int(i), "name": (w.get("name") or "")[:30], "kind": int(w.get("kind", 1))})
        if not wps or wps[-1]["idx"] < len(pts) - 2:
            wps.append({"idx": len(pts) - 1, "name": "cel", "kind": 2})
        else:
            wps[-1]["idx"] = len(pts) - 1
        wps[-1]["kind"] = 2
        route["waypoints"] = wps
        # czas: z silnika albo z klasy drogi
        if times and len(times) == len(pts):
            route["times"] = [int(t) for t in times]
        else:
            route["times"] = self.estimate_times(pts, cum, limits, labels)
        route["time_s"] = route["times"][-1] if route["times"] else 0
        # fotoradary i odcinki
        route["cameras"] = self.cameras_along(pts, cum)
        # krętość (jak dla jazd): suma zmian kierunku co 50 m na km
        route["curvy"] = curviness(pts, cum, self.settings()["curvy_levels"], instr if instructions else None)
        # pogoda dla punktów trasy
        route["weather"] = []
        if with_weather:
            try:
                route["weather"] = self.weather_along(pts, cum, route["times"], start_time)
            except Exception as e:
                log("pogoda dla trasy nieudana:", e)
        return route

    def limits_along(self, pts, cum):
        """Limity prędkości wzdłuż trasy (z mapy na karcie) i nazwy dróg."""
        limits = []
        labels = {}
        if not self.map.available():
            return limits, labels
        cur = None
        last_i = -1
        i = 0
        n = len(pts)
        while i < n:
            heading = ntt.bearing(pts[i], pts[min(n - 1, i + 2)]) if i < n - 1 else None
            m = self.map.match_road(pts[i][0], pts[i][1], heading, 25.0)
            if m:
                w, _, fwd, _ = m
                lim = w.limit if fwd or not w.limit_back else w.limit_back
                lab = w.label()
                if lab:
                    labels[i] = lab
                if lim != cur:
                    if limits and i - last_i < 3:
                        limits[-1] = {"idx": i, "kmh": lim}
                    else:
                        limits.append({"idx": i, "kmh": lim})
                    cur = lim
                    last_i = i
            # co ~60 m wystarczy
            step = 2
            while i + step < n and cum[i + step] - cum[i] < 60:
                step += 1
            i += step
        return limits, labels

    def estimate_times(self, pts, cum, limits, labels):
        """Czas przejazdu bez silnika tras: z limitu (85 %) albo klasy drogi."""
        times = [0]
        lim_i = 0
        lim = 0
        for i in range(1, len(pts)):
            while lim_i < len(limits) and limits[lim_i]["idx"] <= i:
                lim = limits[lim_i]["kmh"]
                lim_i += 1
            v = lim * 0.85 if lim else 60.0
            v = max(20.0, min(120.0, v))
            times.append(times[-1] + (cum[i] - cum[i - 1]) / (v / 3.6))
        return [int(t) for t in times]

    def cameras_along(self, pts, cum):
        out = []
        if not self.map.available():
            return out
        seen = set()
        sections = {}
        i = 0
        n = len(pts)
        while i < n:
            for d, p in self.map.points_near(pts[i][0], pts[i][1], 90.0,
                                              (ntt.P_CAMERA, ntt.P_SECTION_START, ntt.P_SECTION_END)):
                if p.id in seen:
                    continue
                j, dj = nearest_index(pts, (p.lat, p.lon), max(0, i - 10), 30)
                if dj > 40:
                    continue
                seen.add(p.id)
                out.append({"idx": j, "type": p.kind, "limit": p.limit, "pair": p.pair})
                if p.kind in (ntt.P_SECTION_START, ntt.P_SECTION_END):
                    sections.setdefault(p.pair, set()).add(p.kind)
            step = 2
            while i + step < n and cum[i + step] - cum[i] < 70:
                step += 1
            i += step
        # odcinek bez obu końców na trasie nie jest odcinkiem na tej trasie
        out = [c for c in out if c["type"] == ntt.P_CAMERA or len(sections.get(c["pair"], ())) == 2]
        out.sort(key=lambda c: c["idx"])
        return out

    def weather_along(self, pts, cum, times, start_time=None):
        """Prognoza Open-Meteo dla punktów co 30 min jazdy, na przewidywaną
        godzinę przejazdu (start = teraz albo podany czas). Wszystkie brakujące
        punkty idą jednym zapytaniem; prognozy są pamiętane 15 min (wspólnie
        dla wariantów liczonych równolegle)."""
        start = start_time or time.time()
        idxs = [0]
        next_t = 1800
        for i, t in enumerate(times):
            if t >= next_t:
                idxs.append(i)
                next_t = t + 1800
        if idxs[-1] != len(pts) - 1:
            idxs.append(len(pts) - 1)
        keys = [(round(pts[i][0], 1), round(pts[i][1], 1)) for i in idxs]
        now = time.time()
        with WX_LOCK:
            for k in [k for k, v in WX_CACHE.items() if now - v[0] > WX_TTL]:
                WX_CACHE.pop(k, None)
            missing = [k for k in dict.fromkeys(keys) if k not in WX_CACHE]
        if missing:
            q = urllib.parse.urlencode({
                "latitude": ",".join("%.1f" % k[0] for k in missing),
                "longitude": ",".join("%.1f" % k[1] for k in missing), "forecast_days": 3,
                "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
                "timezone": "GMT", "wind_speed_unit": "kmh"})
            j = http_json("https://api.open-meteo.com/v1/forecast?" + q, timeout=20)
            got = j if isinstance(j, list) else [j]
            with WX_LOCK:
                for k, v in zip(missing, got):
                    WX_CACHE[k] = (now, v)
        out = []
        for i, k in zip(idxs, keys):
            with WX_LOCK:
                fc = (WX_CACHE.get(k) or (0, {}))[1]
            h = fc.get("hourly") or {}
            tms = h.get("time") or []
            if not tms:
                continue
            at = start + times[i]
            want = time.strftime("%Y-%m-%dT%H:00", time.gmtime(int(round(at / 3600.0)) * 3600))
            j = tms.index(want) if want in tms else (0 if at < time.time() + 3600 else len(tms) - 1)

            def val(name):
                arr = h.get(name) or []
                return arr[j] if j < len(arr) else None
            out.append({"idx": i, "t": int(at), "temp": val("temperature_2m"), "rain_prob": val("precipitation_probability"),
                        "rain": val("precipitation"), "code": val("weather_code"), "wind": val("wind_speed_10m"),
                        "gust": val("wind_gusts_10m")})
        return out

    def along_route(self, route, kinds=None, max_m=2000.0, limit=300):
        """POI wzdłuż trasy (np. stacje paliw): do max_m od linii, posortowane
        po kilometrze trasy. Zwraca [{lat, lon, kind, name, km, off_m}]."""
        pts = [(float(p[0]), float(p[1])) for p in route.get("pts") or []]
        if len(pts) < 2 or not self.map.available():
            return []
        cum = route.get("cum") or cum_dist(pts)
        found = {}
        i = 0
        n = len(pts)
        while i < n:
            for d, p in self.map.points_near(pts[i][0], pts[i][1], max_m + 300.0, kinds):
                if p.id in found and found[p.id][0] <= d:
                    continue
                found[p.id] = (d, i, p)
            step = 1
            while i + step < n and cum[i + step] - cum[i] < 500:
                step += 1
            i += step
        out = []
        for d0, i0, p in found.values():
            j, d = nearest_index(pts, (p.lat, p.lon), max(0, i0 - 30), 60)
            if d > max_m:
                continue
            out.append({"lat": round(p.lat, 6), "lon": round(p.lon, 6), "kind": p.kind, "name": p.name,
                        "km": round(cum[j] / 1000.0, 1), "off_m": int(d), "idx": j})
        out.sort(key=lambda x: (x["km"], x["off_m"]))
        return out[:limit]

    # ---- silnik tras (GraphHopper)
    def engine_ok(self):
        return bool(self.settings()["engine_url"])

    def gh_custom_model(self, variant, avoid):
        pr = []
        if variant == "szybko":
            pass
        else:
            sl = self.settings()["curvy"][variant]
            g, z = sl["glowne"] / 100.0, sl["zakrety"] / 100.0
            straight = round(1 - 0.65 * z, 3)
            pr += [{"if": "road_class == MOTORWAY", "multiply_by": str(round(max(0.05, 1 - 0.9 * g), 3))},
                   {"else_if": "road_class == TRUNK", "multiply_by": str(round(max(0.05, 1 - 0.8 * g), 3))},
                   {"else_if": "road_class == PRIMARY", "multiply_by": str(round(1 - 0.5 * g, 3))},
                   {"if": "curvature > 0.97", "multiply_by": str(straight)},
                   {"else_if": "curvature > 0.9", "multiply_by": str(min(1.0, round(straight + 0.2, 3)))}]
            if variant == "bardzo":
                pr.append({"if": "road_class == SECONDARY", "multiply_by": "0.8"})
                pr.append({"if": "road_environment == TUNNEL", "multiply_by": "0.5"})
        # gruntowe: polne i leśne (track, ziemia, trawa, piach); szutrowe: drogi publiczne
        # z nawierzchnią szutrową/utwardzoną, legalne dla motocykla – osobna opcja
        if "gruntowe" in avoid:
            pr.append({"if": "road_class == TRACK || surface == UNPAVED || surface == DIRT || surface == GROUND || "
                             "surface == GRASS || surface == SAND", "multiply_by": "0.05"})
        if "szutrowe" in avoid:
            pr.append({"if": "surface == GRAVEL || surface == FINE_GRAVEL || surface == COMPACTED",
                       "multiply_by": "0.1"})
        if "platne" in avoid:
            pr.append({"if": "toll == ALL || toll == HGV", "multiply_by": "0.1"})
        if "autostrady" in avoid:
            pr.append({"if": "road_class == MOTORWAY", "multiply_by": "0"})
        if "promy" in avoid:
            pr.append({"if": "road_environment == FERRY", "multiply_by": "0"})
        if variant == "szybko":
            di = 70
        else:
            # dluzej 0 = jak najkrócej (70), 100 = długość prawie bez znaczenia (5)
            di = int(round(70 - 0.65 * self.settings()["curvy"][variant]["dluzej"]))
        return {"priority": pr, "distance_influence": di}

    def gh_route(self, points, variant, avoid, round_trip_km=None, heading=None, skip=None, seed=None,
                 avoid_segment=None):
        s = self.settings()
        if not s["engine_url"]:
            raise RuntimeError("brak adresu silnika tras w ustawieniach")
        body = {"points": [[p[1], p[0]] for p in points], "profile": "motocykl", "locale": "pl",
                "instructions": True, "points_encoded": False, "calc_points": True, "elevation": False,
                "details": ["time", "max_speed", "road_class", "surface"], "ch.disable": True,
                "custom_model": self.gh_custom_model(variant, avoid)}
        seg = avoid_segment
        if seg and len(seg) >= 2:
            # objazd: pas 60 m wokół omijanego odcinka jako obszar zakazany
            sm = list(seg[::max(1, len(seg) // 40)])
            if sm[-1] != seg[-1]:
                sm.append(seg[-1])
            left, right = [], []
            for i, p in enumerate(sm):
                q = sm[min(len(sm) - 1, i + 1)] if i < len(sm) - 1 else sm[i - 1]
                h = math.radians(ntt.bearing(p, q) if i < len(sm) - 1 else ntt.bearing(q, p))
                dlat = 40.0 * math.cos(h + math.pi / 2) / 111320.0
                dlon = 40.0 * math.sin(h + math.pi / 2) / (111320.0 * math.cos(math.radians(p[0])))
                left.append([p[1] + dlon, p[0] + dlat])
                right.append([p[1] - dlon, p[0] - dlat])
            ring = left + right[::-1] + [left[0]]
            body["custom_model"].setdefault("areas", {"type": "FeatureCollection", "features": []})["features"].append(
                {"type": "Feature", "id": "objazd", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
            body["custom_model"]["priority"].insert(0, {"if": "in_objazd", "multiply_by": "0"})
        for k, sp in enumerate(skip or []):
            # pomiń miejscowość: koło wokół niej prawie zakazane (start w środku nadal da się wyjechać)
            body["custom_model"].setdefault("areas", {"type": "FeatureCollection", "features": []})["features"].append(
                {"type": "Feature", "id": "pomin%d" % k, "properties": {},
                 "geometry": {"type": "Polygon", "coordinates": [circle(sp["lat"], sp["lon"], sp["r"])]}})
            body["custom_model"]["priority"].insert(0, {"if": "in_pomin%d" % k, "multiply_by": "0.02"})
        if round_trip_km:
            body["algorithm"] = "round_trip"
            body["round_trip.distance"] = int(round_trip_km * 1000)
            body["round_trip.seed"] = seed if seed is not None else int(time.time()) % 1000
            if heading is not None:
                body["heading"] = [int(heading)]
        j = http_json(s["engine_url"] + "/route", body, timeout=90)
        if not j.get("paths"):
            raise RuntimeError(j.get("message") or "silnik nie zwrócił trasy")
        path = j["paths"][0]
        pts = [(c[1], c[0]) for c in path["points"]["coordinates"]]
        # czas narastająco z detali "time" (ms na odcinek punktów)
        times = [0.0] * len(pts)
        for a, b, ms in path.get("details", {}).get("time", []):
            seg = max(1, b - a)
            for k in range(a + 1, b + 1):
                if k < len(pts):
                    times[k] = times[a] + ms / 1000.0 * (k - a) / seg
        instr = []
        for ins in path.get("instructions", []):
            t = GH_SIGNS.get(ins.get("sign", 0), T_STRAIGHT)
            iv = ins.get("interval") or [0, 0]
            if t == T_STRAIGHT and ins.get("sign", 0) == 0:
                continue
            instr.append({"idx": int(iv[0]), "type": t, "exit": int(ins.get("exit_number") or 0),
                          "text": (ins.get("street_name") or ins.get("street_ref") or "")[:30]})
        limits = []
        for a, b, v in path.get("details", {}).get("max_speed", []):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v <= 0 or v > 250 or a >= len(pts):
                continue
            limits.append({"lat": pts[a][0], "lon": pts[a][1], "kmh": int(round(v))})
        return {"pts": pts, "times": [int(t) for t in times], "instr": instr, "dist_m": path.get("distance", 0),
                "time_s": path.get("time", 0) / 1000.0, "snapped": path.get("snapped_waypoints"), "limits": limits}

    def gh_mix(self, points, legs, avoid, heading=None, skip=None, avoid_segment=None):
        """Trasa z odcinków liczonych osobno, każdy swoim wariantem
        (legs[i] = wariant odcinka points[i] → points[i+1]), sklejona w jedną."""
        if len(legs) != len(points) - 1:
            raise RuntimeError("zła liczba odcinków")
        pairs = [((points[i]["lat"], points[i]["lon"]), (points[i + 1]["lat"], points[i + 1]["lon"])) for i in range(len(legs))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4, len(legs)))) as ex:
            futs = [ex.submit(self.gh_route, list(pr), lv, avoid, None, heading if i == 0 else None, skip, None,
                              avoid_segment)
                    for i, (pr, lv) in enumerate(zip(pairs, legs))]
            parts = [f.result() for f in futs]
        pts, times, instr, limits = [], [], [], []
        dist = tsec = 0.0
        for part in parts:
            off = len(pts) - 1 if pts else 0
            t0 = times[-1] if times else 0
            if pts:
                # pierwszy punkt odcinka = ostatni poprzedniego
                pts += part["pts"][1:]
                times += [t0 + t for t in part["times"][1:]]
            else:
                pts += part["pts"]
                times += part["times"]
            instr += [dict(i, idx=i["idx"] + off) for i in part["instr"] if not (off and i["idx"] == 0)]
            limits += part["limits"]
            dist += part["dist_m"]
            tsec += part["time_s"]
        return {"pts": pts, "times": times, "instr": instr, "dist_m": dist, "time_s": tsec, "snapped": None,
                "limits": limits, "leg_m": [int(p["dist_m"]) for p in parts]}

    def plan(self, points, variants=None, avoid=None, name="", round_trip_km=None, heading=None, with_weather=False,
             legs=None, skip=None, round_trip_min=None, avoid_segment=None):
        """Warianty tras przez punkty [{lat, lon, name}]; zwraca listę tras
        (bez zapisu). Pierwszy punkt = start. legs = wariant każdego odcinka
        (dodaje wariant „mix”, czyli „Mój plan”). skip = [{lat, lon, r, name}]
        miejscowości do pominięcia. round_trip_min = trasa okrężna na czas.
        avoid_segment = odcinek trasy [(lat, lon)] do ominięcia (objazd korka albo
        „objazd X km” z ekranu); podawany jawnie, bo planowania z ekranu, strony
        i pilnowania korków mogą iść naraz w osobnych wątkach."""
        s = self.settings()
        skip = list(skip or [])
        if round_trip_km or round_trip_min:
            points = points[:1]
            legs = None
        seed = int(time.time()) % 1000
        avoid = avoid if avoid is not None else s["avoid"]
        variants = list(variants or [v for v, _ in VARIANTS])
        if legs and not round_trip_km and len(legs) == len(points) - 1 and MIX[0] not in variants:
            variants.append(MIX[0])
        errors = {}

        def one(v):
            rt_km = round_trip_km
            if v == MIX[0]:
                r = self.gh_mix(points, legs, avoid, heading, skip, avoid_segment)
            elif round_trip_min:
                # na czas: długość z typowej średniej wariantu, potem poprawka o różnicę czasu
                rt_km = max(10.0, round_trip_min / 60.0 * RT_KMH.get(v, 50))
                r = None
                for _ in range(3):
                    r = self.gh_route([(p["lat"], p["lon"]) for p in points], v, avoid, rt_km, heading, skip, seed,
                                      avoid_segment)
                    got = r["time_s"] / 60.0 if r["time_s"] else None
                    if not got or abs(got - round_trip_min) <= max(5, 0.12 * round_trip_min):
                        break
                    rt_km = max(10.0, min(1500.0, rt_km * round_trip_min / got))
            else:
                r = self.gh_route([(p["lat"], p["lon"]) for p in points], v, avoid, round_trip_km, heading, skip, seed,
                                  avoid_segment)
            wps = []
            for k, p in enumerate(points[1:] if not (round_trip_km or round_trip_min) else []):
                wps.append({"lat": p["lat"], "lon": p["lon"], "name": p.get("name") or "", "kind": 2 if k == len(points) - 2 else 1})
            route = self.build_route(r["pts"], name or self.auto_name(points, round_trip_km, round_trip_min), "silnik",
                                     r["instr"], wps,
                                     None, v, with_weather, limits_hint=r["limits"])
            # czas z silnika zamiast szacunku: przeskaluj na nasze punkty
            if r["time_s"]:
                k = r["time_s"] / max(1, route["time_s"])
                route["times"] = [int(t * k) for t in route["times"]]
                route["time_s"] = int(r["time_s"])
            route["avoid"] = avoid
            route["points"] = points
            route["round_trip_km"] = round_trip_km
            if round_trip_min:
                route["round_trip_min"] = round_trip_min
            if skip:
                route["skip"] = skip
            if v == MIX[0]:
                route["legs"] = list(legs)
                route["leg_m"] = r.get("leg_m")
            return route

        # warianty liczą się naraz (silnik ma kilka rdzeni, pogoda i sieć czekają równolegle)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4, len(variants)))) as ex:
            futs = [(v, ex.submit(one, v)) for v in variants]
        out = []
        for v, f in futs:
            try:
                out.append(f.result())
            except Exception as e:
                errors[v] = self.engine_error(e)
        return out, errors

    def engine_error(self, e):
        """Błąd silnika tras po ludzku (zamiast „Errno 111”)."""
        txt = str(e)
        down = isinstance(e, (ConnectionError, TimeoutError)) or any(
            k in txt for k in ("Connection refused", "Errno 111", "timed out", "No route to host", "Errno 113"))
        if not down:
            return txt
        st = self.build_status() or {}
        if st.get("pracuje"):
            return "silnik tras jest wyłączony na czas przebudowy w kontenerze (%s) – wróci sam po jej końcu" % (
                st.get("etap") or "budowa")
        return ("silnik tras nie odpowiada – kontener wyłączony albo usługa stoi; w konsoli kontenera: "
                "systemctl start nt1100-trasy")

    @staticmethod
    def auto_name(points, round_trip_km=None, round_trip_min=None):
        if round_trip_min:
            h, m = divmod(int(round_trip_min), 60)
            return "Okrężna " + ("%d h" % h if h else "") + (" %d min" % m if m else "")
        if round_trip_km:
            return "Okrężna %d km" % int(round_trip_km)
        names = [p.get("name") for p in points if p.get("name")]
        if len(names) >= 2:
            return "%s → %s" % (names[0][:16], names[-1][:16])
        if names:
            return "→ " + names[-1][:30]
        return "Trasa"

    def route_from_gpx(self, data, name=""):
        g = parse_gpx(data)
        # punkty GPX bliżej niż 100 m od linii to punkty po drodze (w kolejności na trasie)
        near = []
        for w in g["wpts"]:
            i, d = nearest_index(g["pts"], (w["lat"], w["lon"]))
            if d is not None and d < 100:
                near.append((i, {"lat": w["lat"], "lon": w["lon"], "name": w["name"]}))
        wps = [w for _, w in sorted(near, key=lambda x: x[0])]
        route = self.build_route(g["pts"], name or g["name"], "gpx", None, wps)
        return route

    def reroute(self, rid, lat, lon, heading=None, skip_waypoint=False, avoid_km=None):
        """Nowa trasa z pozycji do pozostałych punktów bieżącej trasy
        (po zjeździe, objazd następnych km, pominięcie punktu)."""
        route = self.route(rid)
        if not route:
            raise RuntimeError("brak trasy")
        pts = route["pts"]
        i, _ = nearest_index(pts, (lat, lon))
        remaining = [w for w in route.get("waypoints", []) if w["idx"] > i + 5]
        if skip_waypoint and len(remaining) > 1:
            remaining = remaining[1:]
        points = [{"lat": lat, "lon": lon, "name": "pozycja"}]
        avoid = list(route.get("avoid") or self.settings()["avoid"])
        if avoid_km:
            # omiń następne km: punkt pośredni za omijanym odcinkiem, a sam odcinek
            # jako obszar zakazany (prostokąty wokół trasy)
            j = i
            while j < len(pts) - 1 and route["cum"][j] - route["cum"][i] < avoid_km * 1000:
                j += 1
            points.append({"lat": pts[j][0], "lon": pts[j][1], "name": "za objazdem"})
            avoid_segment = pts[i + 2:j - 2] if j - i > 6 else []
        else:
            avoid_segment = []
        for w in remaining:
            p = pts[w["idx"]]
            points.append({"lat": p[0], "lon": p[1], "name": w.get("name") or ""})
        variant = route.get("variant") or self.settings()["go_variant"]
        legs = None
        if variant == MIX[0]:
            # odcinki do pozostałych punktów zachowują swoje warianty
            old = route.get("legs") or []
            n = len(points) - 1
            tail = old[len(old) - len(remaining):] if remaining and len(old) >= len(remaining) else []
            if avoid_km and tail:
                tail = [tail[0]] + tail
            legs = tail if len(tail) == n else [self.settings()["go_variant"]] * n
        routes, errors = self.plan(points, [variant], avoid, route.get("name"), heading=heading, legs=legs,
                                   skip=route.get("skip"), avoid_segment=avoid_segment)
        if not routes:
            raise RuntimeError(errors.get(variant) or "silnik nie policzył objazdu")
        new = routes[0]
        new["id"] = rid
        new["created"] = route.get("created")
        new["parent_version"] = route.get("version")
        new["weather"] = route.get("weather") or []
        self.store_route(new, make_current=(self.index().get("current") == rid))
        return new

    # ---- decyzje w trasie: co jest przed motocyklem i zjazd do miejsca
    def nearby(self, lat, lon, kinds, limit=30):
        """Miejsca przed motocyklem na bieżącej trasie (gdy jedzie po niej),
        inaczej najbliższe wokół. dist_km = po trasie albo w linii prostej."""
        cur = self.index().get("current")
        route = self.route(cur) if cur else None
        if route and route.get("pts"):
            pts = route["pts"]
            i, d = nearest_index(pts, (lat, lon))
            if d is not None and d < 500:
                cum = route.get("cum") or cum_dist(pts)
                here = cum[i] / 1000.0
                out = []
                for p in self.along_route(route, kinds, 3000.0, 400):
                    if p["km"] < here - 0.2:
                        continue
                    p = dict(p)
                    p["dist_km"] = round(max(0.0, p["km"] - here), 1)
                    out.append(p)
                return {"mode": "trasa", "route": cur, "points": out[:limit]}
        out = []
        for d, p in self.map.points_near(lat, lon, 15000.0, kinds)[:limit]:
            out.append({"lat": round(p.lat, 6), "lon": round(p.lon, 6), "kind": p.kind, "name": p.name,
                        "dist_km": round(d / 1000.0, 1), "off_m": None})
        return {"mode": "wokol", "route": None, "points": out}

    def via_place(self, lat, lon, place, heading=None):
        """Zjazd do miejsca (stacja, jedzenie): gdy motocykl jest na bieżącej
        trasie, dojazd do miejsca i powrót na trasę ~300 m dalej, reszta planu
        bez zmian; inaczej nowa trasa z pozycji do miejsca. Zapisuje jako bieżącą."""
        cur = self.index().get("current")
        route = self.route(cur) if cur else None
        target = (float(place["lat"]), float(place["lon"]))
        name = (place.get("name") or "postój")[:30]
        if route and route.get("pts"):
            pts = [tuple(p) for p in route["pts"]]
            cum = route.get("cum") or cum_dist(pts)
            i, d = nearest_index(pts, (lat, lon))
            if d is not None and d < 500:
                jp, _ = nearest_index(pts, target, i)
                j = jp
                while j < len(pts) - 1 and cum[j] - cum[jp] < 300:
                    j += 1
                legs = [(lat, lon), target] + ([pts[j]] if j < len(pts) - 1 else [])
                r = self.gh_route(legs, "szybko", list(route.get("avoid") or self.settings()["avoid"]), heading=heading)
                head = list(r["pts"])
                tail = pts[j + 1:]
                instr = [dict(t) for t in r["instr"]]
                shift = len(head) - (j + 1)
                for t in route.get("turns") or []:
                    if t["idx"] > j:
                        t = dict(t)
                        t["idx"] = t["idx"] + shift
                        instr.append(t)
                wps = [{"lat": target[0], "lon": target[1], "name": name, "kind": 1}]
                for w in route.get("waypoints") or []:
                    if w["idx"] > j:
                        p = pts[w["idx"]]
                        wps.append({"lat": p[0], "lon": p[1], "name": w.get("name") or "", "kind": w.get("kind", 1)})
                new = self.build_route(head + tail, route.get("name") or "Trasa", route.get("source") or "silnik", instr,
                                       wps, None, route.get("variant"), True)
                new["id"] = cur
                new["created"] = route.get("created")
                new["parent_version"] = route.get("version")
                new["avoid"] = route.get("avoid")
                new["points"] = route.get("points")
                self.store_route(new, True)
                return new
        s = self.settings()
        routes, errors = self.plan([{"lat": lat, "lon": lon, "name": "pozycja"},
                                    {"lat": target[0], "lon": target[1], "name": name}],
                                   [s["go_variant"]], s["avoid"], "→ " + name, heading=heading, with_weather=True)
        if not routes:
            raise RuntimeError(errors.get(s["go_variant"]) or "silnik tras nie odpowiedział")
        rid = self.store_route(routes[0], True)
        return self.route(rid)

    # ---- szukanie i cel z linku
    def search(self, q, lat=None, lon=None, limit=8):
        # Photon nie obsługuje "pl" (odrzuca zapytanie); domyślnie zwraca nazwy lokalne, czyli polskie.
        params = {"q": q, "limit": limit}
        if lat is not None and lon is not None:
            params.update({"lat": "%.4f" % lat, "lon": "%.4f" % lon})
        j = http_json("https://photon.komoot.io/api/?" + urllib.parse.urlencode(params), timeout=15)
        out = []
        for f in j.get("features", []):
            p = f.get("properties") or {}
            c = (f.get("geometry") or {}).get("coordinates") or [None, None]
            name = p.get("name") or p.get("street") or ""
            parts = [x for x in (p.get("street"), p.get("housenumber"), p.get("city") or p.get("town") or p.get("village"),
                                 p.get("county"), p.get("country")) if x]
            label = ", ".join(dict.fromkeys([name] + parts)) if name else ", ".join(parts)
            item = {"name": name or label, "label": label, "lat": c[1], "lon": c[0], "type": p.get("osm_value")}
            ext = p.get("extent")  # [zachód, północ, wschód, południe] dla miejscowości i obszarów
            if isinstance(ext, list) and len(ext) == 4:
                item["extent"] = ext
            out.append(item)
        return out

    def reverse(self, lat, lon):
        try:
            j = http_json("https://photon.komoot.io/reverse?lat=%.5f&lon=%.5f" % (lat, lon), timeout=10)
            f = (j.get("features") or [{}])[0]
            p = f.get("properties") or {}
            return p.get("name") or p.get("street") or p.get("city") or p.get("village") or ""
        except Exception:
            return ""

    @staticmethod
    def parse_place_link(text):
        """Współrzędne (i nazwa) z linku Map Google/Apple, geo: albo 'lat, lon'."""
        text = (text or "").strip()
        m = re.search(r"(?<![\d.])(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)(?![\d])", text)
        name = ""
        if "google" in text or "goo.gl" in text:
            mm = re.search(r"/place/([^/@]+)", text)
            if mm:
                name = urllib.parse.unquote_plus(mm.group(1))
            mq = re.search(r"[?&]q=([^&]+)", text)
            if mq and not re.match(r"-?\d", urllib.parse.unquote(mq.group(1))):
                name = urllib.parse.unquote_plus(mq.group(1))
            mm = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", text)
            if mm:
                m = mm
        if "apple.com" in text:
            mq = re.search(r"[?&](?:q|name|address)=([^&]+)", text)
            if mq:
                name = urllib.parse.unquote_plus(mq.group(1))
            mm = re.search(r"[?&](?:ll|sll|daddr|coordinate)=(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)", text)
            if mm:
                m = mm
        if not m:
            return None
        return {"lat": float(m.group(1)), "lon": float(m.group(2)), "name": name[:40]}

    def resolve_place(self, text):
        """Jak parse_place_link, ale rozwija skrócone linki (maps.app.goo.gl)
        i szuka nazwy, gdy link nie ma współrzędnych."""
        p = self.parse_place_link(text)
        if p:
            if not p["name"]:
                p["name"] = self.reverse(p["lat"], p["lon"])
            return p
        m = re.search(r"https?://\S+", text or "")
        if m:
            url = m.group(0)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
                with urllib.request.urlopen(req, timeout=15) as r:
                    final = r.geturl()
                    body = r.read(200000).decode("utf-8", "replace")
                p = self.parse_place_link(final) or self.parse_place_link(body)
                if p:
                    if not p["name"]:
                        mt = re.search(r"<title>([^<]{1,80})</title>", body)
                        p["name"] = (mt.group(1).replace(" - Google Maps", "") if mt else "")[:40]
                    return p
                mq = re.search(r"[?&]q=([^&]+)", final)
                if mq:
                    text = urllib.parse.unquote_plus(mq.group(1))
            except Exception as e:
                log("link celu nie otwarty:", e)
        q = re.sub(r"https?://\S+", "", text or "").strip()
        if q:
            res = self.search(q, limit=1)
            if res:
                return {"lat": res[0]["lat"], "lon": res[0]["lon"], "name": res[0]["name"][:40]}
        return None

    # ---- ekran: pozycja, dziennik, korki
    def screen_seen(self, lat, lon, speed, heading, extra=None):
        st = {"lat": lat, "lon": lon, "speed": speed, "heading": heading, "t": int(time.time())}
        if extra:
            st.update(extra)
        self.save_state(screen=st)

    def screen_position(self):
        return self.state.get("screen")

    def screen_log(self, entries):
        """Dziennik ekranu: [{t, what, idx, value}] -> plik dzienny."""
        if not entries:
            return
        day = time.strftime("%Y-%m-%d", time.gmtime(entries[0].get("t") or time.time()))
        with open(os.path.join(self.screen_dir, day + ".jsonl"), "a", encoding="utf-8") as f:
            for e in entries[:2000]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def screen_events(self, t0, t1):
        out = []
        for day in {time.strftime("%Y-%m-%d", time.gmtime(t)) for t in (t0, t1, (t0 + t1) / 2)}:
            p = os.path.join(self.screen_dir, day + ".jsonl")
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if t0 <= (e.get("t") or 0) <= t1:
                        out.append(e)
        return out

    # ---- ceny paliw (1.5.23): Google Places, stacja po stacji, pamięć 1 h
    def fuel_prices(self, places):
        """[{lat, lon, name}] -> lista tej samej długości: {"text": "6,19 zł · 2 h temu",
        "pb95": 6.19, "age_min": 120, "station": "Orlen"} albo None (brak ceny / stacji).
        Bez klucza Google: ValueError."""
        s = self.settings()
        if not s["google_key"]:
            raise ValueError("brak klucza Google (Ustawienia nawigacji)")
        out = []
        for p in places[:6]:
            lat, lon = p.get("lat"), p.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                out.append(None)
                continue
            key = (round(lat, 4), round(lon, 4))
            c = self.fuel_cache.get(key)
            if c and time.time() - c[0] < 3600:
                out.append(c[1])
                continue
            try:
                r = fuel_price_google(s["google_key"], lat, lon)
            except Exception as e:
                log("ceny paliw:", e)
                r = None
            self.fuel_cache[key] = (time.time(), r)
            if len(self.fuel_cache) > 400:
                oldest = sorted(self.fuel_cache.items(), key=lambda kv: kv[1][0])[:200]
                for k, _ in oldest:
                    self.fuel_cache.pop(k, None)
            out.append(r)
        return out

    def traffic(self, rid, lat, lon):
        """Korki na najbliższych 50 km trasy (TomTom Incident Details, 1 zapytanie).
        Zwraca {delay_s, incidents:[{idx, km, delay_s, text}]} albo None bez klucza."""
        s = self.settings()
        if not s["tomtom_key"]:
            return None
        route = self.route(rid)
        if not route:
            return None
        pts, cum = route["pts"], route["cum"]
        i, _ = nearest_index(pts, (lat, lon))
        j = i
        while j < len(pts) - 1 and cum[j] - cum[i] < 50000:
            j += 1
        seg = pts[i:j + 1]
        lats = [p[0] for p in seg]
        lons = [p[1] for p in seg]
        bbox = "%.4f,%.4f,%.4f,%.4f" % (min(lons) - 0.01, min(lats) - 0.01, max(lons) + 0.01, max(lats) + 0.01)
        key = (rid, round(lat, 2), round(lon, 2))
        c = self.traffic_cache.get(key)
        if c and time.time() - c[0] < 150:
            return c[1]
        q = urllib.parse.urlencode({"key": s["tomtom_key"], "bbox": bbox, "language": "pl-PL",
                                    "fields": "{incidents{geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,delay,length,events{description}}}}",
                                    "timeValidityFilter": "present"})
        j = http_json("https://api.tomtom.com/traffic/services/5/incidentDetails?" + q, timeout=15)
        incidents = []
        total = 0
        for inc in j.get("incidents", []):
            g = inc.get("geometry") or {}
            coords = g.get("coordinates") or []
            if g.get("type") == "Point":
                coords = [coords]
            if not coords:
                continue
            p0 = (coords[0][1], coords[0][0])
            k, d = nearest_index(pts, p0, i, j - i + 1)
            if d > 60:
                continue
            pr = inc.get("properties") or {}
            delay = int(pr.get("delay") or 0)
            if pr.get("magnitudeOfDelay", 0) < 2 and delay < 60:
                continue
            ev = pr.get("events") or [{}]
            incidents.append({"idx": k, "km": round((cum[k] - cum[i]) / 1000, 1), "delay_s": delay,
                              "len_m": int(pr.get("length") or 0), "text": (ev[0].get("description") or "")[:40],
                              "cat": pr.get("iconCategory")})
            total += delay
        incidents.sort(key=lambda x: x["idx"])
        out = {"delay_s": total, "incidents": incidents[:10], "t": int(time.time())}
        now = time.time()
        for k in [k for k, v in self.traffic_cache.items() if now - v[0] > 600]:
            self.traffic_cache.pop(k, None)
        self.traffic_cache[key] = (now, out)
        return out

    # ---- zgodność jazdy z planem
    def compliance(self, track_pts, t_start, t_end):
        """Procent punktów jazdy w 50 m od trasy, która była bieżąca w czasie
        jazdy, i odstępstwa (km od, km do)."""
        rid = self.route_at(t_start)
        if rid is None:
            return None
        route = self.route(rid)
        if not route:
            return None
        pts = route["pts"]
        n_on = 0
        devs = []
        cur = None
        j = 0
        for k, p in enumerate(track_pts):
            jj, d = nearest_index(pts, (p[0], p[1]), max(0, j - 50), 400)
            if d > 300:
                jj, d = nearest_index(pts, (p[0], p[1]))
            j = jj
            on = d <= 50
            n_on += on
            if not on and cur is None:
                cur = k
            if on and cur is not None:
                devs.append((cur, k))
                cur = None
        if cur is not None:
            devs.append((cur, len(track_pts) - 1))
        pct = int(round(100.0 * n_on / max(1, len(track_pts))))
        return {"route": rid, "name": route.get("name"), "pct": pct,
                "deviations": [{"from": a, "to": b} for a, b in devs if b - a >= 20][:20],
                "events": self.screen_events(t_start, t_end)}

    def route_at(self, t):
        """Trasa bieżąca w chwili t (dziennik zmian w stanie). Bez wpisu sprzed t
        nie ma planu: jazda sprzed zaplanowania trasy nie jest z nią porównywana
        (wcześniej dostawała bieżącą trasę i „zgodność 0%”)."""
        hist = self.state.get("current_history") or []
        best = None
        for h in hist:
            if h["t"] <= t and (best is None or h["t"] >= best["t"]):
                best = h
        return best["rid"] if best else None

    def note_current(self, rid):
        hist = (self.state.get("current_history") or [])[-200:]
        hist.append({"t": int(time.time()), "rid": rid})
        self.save_state(current_history=hist)

    # ---- mapa z kontenera
    def map_status(self):
        m = self.map.manifest()
        g = (m or {}).get("graph") or {}
        return {"available": bool(m), "built": m.get("built") if m else None, "files": len(m.get("files", [])) if m else 0,
                "mb": round(m.get("bytes", 0) / 1e6, 1) if m else 0, "source_url": self.settings()["map_url"],
                # graf tras do nawigacji offline na ekranie 5" (mapa wersja 3)
                "graph_files": len(g.get("cells", [])), "graph_mb": round(g.get("bytes", 0) / 1e6, 1),
                "addr_mb": round(((m or {}).get("addr") or {}).get("bytes", 0) / 1e6, 1),
                "sync": self.state.get("map_sync")}

    def map_sync(self, force=False):
        """Pobiera nowszą mapę z kontenera (manifest + kwadraty) do mapa/."""
        s = self.settings()
        if not s["map_url"]:
            return {"ok": False, "error": "brak adresu mapy w ustawieniach"}
        try:
            remote = http_json(s["map_url"] + "/mapa/manifest.json", timeout=20)
        except Exception as e:
            self.save_state(map_sync={"t": int(time.time()), "error": str(e)})
            return {"ok": False, "error": "kontener nie odpowiada: %s" % e}
        local = self.map.manifest()
        if local and not force and local.get("built") == remote.get("built") and local.get("bytes") == remote.get("bytes"):
            self.save_state(map_sync={"t": int(time.time()), "built": remote.get("built"), "changed": False})
            return {"ok": True, "changed": False, "built": remote.get("built")}
        tmp = self.map_dir + ".nowa"
        if os.path.exists(tmp):
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        have = {}  # nazwa -> (bajty, crc) kwadratów, które już mamy
        for f in (local or {}).get("files", []):
            if len(f) >= 3:
                have[f[0]] = (f[1], f[2])
        for part in MAP_EXTRA:
            for f in ((local or {}).get(part) or {}).get("cells", []):
                if len(f) >= 3:
                    have[f[0]] = (f[1], f[2])
        n = kept = 0
        files = []
        extra = {part: (remote.get(part), []) for part in MAP_EXTRA if isinstance(remote.get(part), dict)}
        wanted = list(remote.get("files", []))
        for part, (r, _) in extra.items():
            wanted += [list(f) + [part] for f in r.get("cells", [])]
        for f in wanted:
            part = f[3] if len(f) >= 4 else None
            f = f[:3]
            name, size = f[0], f[1]
            crc = f[2] if len(f) >= 3 else None
            if not MAP_FILE.fullmatch(name):
                continue
            dst = os.path.join(tmp, name)
            if crc is not None and have.get(name) == (size, crc) and os.path.exists(os.path.join(self.map_dir, name)):
                os.link(os.path.join(self.map_dir, name), dst)  # bez zmian: nie pobieramy drugi raz
                kept += 1
            else:
                req = urllib.request.Request(s["map_url"] + "/mapa/" + name, headers={"User-Agent": "NT1100-Jazdy"})
                with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as out:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                n += 1
            if crc is None:
                crc = file_crc(dst)
            (extra[part][1] if part else files).append([name, size, crc])
        remote = dict(remote, files=files)
        for part, (r, got) in extra.items():
            remote[part] = dict(r, cells=got)
        self._write(os.path.join(tmp, "manifest.json"), remote)
        with self.map.lock:
            old = self.map_dir + ".stara"
            if os.path.exists(old):
                import shutil
                shutil.rmtree(old, ignore_errors=True)
            if os.path.exists(self.map_dir):
                os.rename(self.map_dir, old)
            os.rename(tmp, self.map_dir)
            self.map.cells.clear()
            self.map.order.clear()
            import shutil
            shutil.rmtree(old, ignore_errors=True)
        self.save_state(map_sync={"t": int(time.time()), "built": remote.get("built"), "changed": True, "files": n,
                                  "kept": kept})
        log("mapa pobrana: %d kwadratów nowych, %d bez zmian, %s" % (n, kept, remote.get("built")))
        threading.Thread(target=self.map_zip, daemon=True).start()
        return {"ok": True, "changed": True, "built": remote.get("built"), "files": n, "kept": kept}

    def map_manifest(self):
        """Manifest z sumami crc32 (dopisywanymi do starszych map)."""
        with self.map.lock:
            m = self.map.manifest()
            if not m:
                return None
            if any(not isinstance(f, list) or len(f) < 3 for f in m.get("files", [])):
                files = []
                for f in m["files"]:
                    if isinstance(f, dict):
                        f = [f.get("name"), f.get("size"), f.get("crc")]
                    f = list(f) + [None] * (3 - len(f))
                    p = os.path.join(self.map_dir, str(f[0]))
                    if not os.path.exists(p):
                        continue
                    files.append([f[0], os.path.getsize(p), f[2] if f[2] is not None else file_crc(p)])
                m = dict(m, files=files)
                self._write(os.path.join(self.map_dir, "manifest.json"), m)
            return m

    def screen_manifest(self):
        """Manifest dla ekranu: kwadraty w kolejności pobierania (dom, bieżąca trasa, reszta od domu)."""
        m = self.map_manifest()
        if not m:
            return None
        home = self.settings().get("home")
        route = None
        cur = self.index().get("current")
        if cur:
            r = self.route(cur)
            route = r.get("pts") if r else None
        first = {}
        if home:
            hk = ntt.cell_of(home["lat"], home["lon"])
            for dl in range(-2, 3):          # ok. 20 × 30 km wokół domu
                for do in range(-2, 3):
                    first.setdefault(ntt.cell_name((hk[0] + dl, hk[1] + do)), 0)
        if route:
            step = max(1, len(route) // 2000)
            for p in route[::step] + route[-1:]:
                first.setdefault(ntt.cell_name(ntt.cell_of(p[0], p[1])), 1)
        cen = (home["lat"], home["lon"]) if home else None

        def key(f):
            if f[0] in ("a_index.nta", "a_poi.nta"):
                return (-1, f[0])                    # spisy miejscowości i miejsc najpierw
            c = "c_" + f[0][2:-4] + ".ntt"             # g_/a_ w kolejności swojego kwadratu mapy
            if c in first:
                return (first[c], 0)
            if not cen:
                return (2, 0)
            a = f[0][2:-4].split("_")
            la, lo = (int(a[0]) + 0.5) / 10, (int(a[1]) + 0.5) / 10
            return (2, (la - cen[0]) ** 2 + ((lo - cen[1]) * math.cos(math.radians(cen[0]))) ** 2)
        out = dict(m, files=sorted(m.get("files", []), key=key), gz=True)
        for part in MAP_EXTRA:
            if isinstance(m.get(part), dict):
                out[part] = dict(m[part], cells=sorted(m[part].get("cells", []), key=key))
        return out

    def map_gz(self, name):
        """Kwadrat spakowany gzip (do szybszej wysyłki na ekran); pamiętany obok mapy."""
        p = self.map_file(name)
        if not p or name == "manifest.json":
            return None
        gdir = os.path.join(self.dir, "mapa-gz")
        os.makedirs(gdir, exist_ok=True)
        g = os.path.join(gdir, name + ".gz")
        if not os.path.exists(g) or os.path.getmtime(g) < os.path.getmtime(p):
            with open(p, "rb") as f:
                data = gzip.compress(f.read(), 6, mtime=0)
            with open(g + ".tmp", "wb") as f:
                f.write(data)
            os.replace(g + ".tmp", g)
        return g

    def zip_path(self):
        return os.path.join(self.dir, "mapa-ekranu.zip")

    def zip_status(self):
        m = self.map.manifest()
        z = self.zip_path()
        st = self.state.get("map_zip") or {}
        ready = bool(m) and os.path.exists(z) and st.get("built") == m.get("built") and st.get("bytes") == m.get("bytes")
        return {"ready": ready, "mb": round(os.path.getsize(z) / 1e6, 1) if ready else 0,
                "working": bool(getattr(self, "_zipping", False))}

    def map_zip(self):
        """Paczka ZIP całej mapy do rozpakowania na kartę ekranu (folder mapa/)."""
        import zipfile
        if getattr(self, "_zipping", False):
            return False
        m = self.map_manifest()
        if not m:
            return False
        self._zipping = True
        try:
            tmp = self.zip_path() + ".tmp"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for f in m.get("files", []) + [c for part in MAP_EXTRA for c in ((m.get(part) or {}).get("cells") or [])]:
                    p = os.path.join(self.map_dir, f[0])
                    if os.path.exists(p):
                        z.write(p, "mapa/" + f[0])
                z.writestr("mapa/manifest.json", json.dumps(m))
            os.replace(tmp, self.zip_path())
            self.save_state(map_zip={"built": m.get("built"), "bytes": m.get("bytes"), "t": int(time.time())})
            log("paczka mapy na kartę gotowa: %.0f MB" % (os.path.getsize(self.zip_path()) / 1e6))
            return True
        except Exception as e:
            log("paczka mapy nieudana: %s" % e)
            return False
        finally:
            self._zipping = False

    def build_status(self):
        """Co robi kontener (stan.json z aktualizuj.sh), pamiętane 30 s."""
        c = getattr(self, "_build", None)
        now = time.time()
        if c and now - c[0] < 30:
            return c[1]
        st = None
        url = self.settings()["map_url"]
        if url:
            try:
                st = http_json(url + "/stan.json", timeout=4)
            except Exception:
                st = None
        self._build = (now, st)
        return st

    def map_file(self, name):
        if name == "manifest.json" or MAP_FILE.fullmatch(name):
            p = os.path.join(self.map_dir, name)
            return p if os.path.exists(p) else None
        return None


JUNCTION_TURNS = (T_LEFT, T_SHARP_L, T_RIGHT, T_SHARP_R, T_UTURN, T_ROUNDABOUT)


def curviness(pts, cum, levels=None, turns=None):
    """Krętość jak dla jazd: suma zmian kierunku (próbki co 50 m) na km.
    1.5.27: gdy znane są skręty z silnika tras (turns), skręty na skrzyżowaniach (±40 m) się nie liczą –
    trasa przez wsie z wieloma skrętami pod kątem prostym nie wychodzi „krętsza” od drogi z zakrętami."""
    jd = sorted(cum[t["idx"]] for t in (turns or []) if t.get("type") in JUNCTION_TURNS and 0 <= t.get("idx", -1) < len(cum))
    if cum[-1] < 500:
        return None
    samples = []
    want = 0.0
    for i, c in enumerate(cum):
        if c >= want:
            samples.append((pts[i], c))
            want = c + 50.0
    total = 0.0
    k = 0
    for i in range(2, len(samples)):
        d = abs(ntt.angle_diff(ntt.bearing(samples[i - 2][0], samples[i - 1][0]), ntt.bearing(samples[i - 1][0], samples[i][0])))
        if d < 4:
            continue
        c = samples[i - 1][1]
        while k < len(jd) and jd[k] < c - 40:
            k += 1
        if k < len(jd) and abs(jd[k] - c) < 40:
            continue
        total += d
    per_km = total / (cum[-1] / 1000.0)
    return {"deg_km": int(per_km), "level": curvy_name(per_km, levels)}


def utf8_cut(text, max_bytes):
    """Tekst w UTF-8 obcięty do max_bytes bez przecinania polskiej litery
    (ucięty w połowie znak ekran rysował jako krzaczek)."""
    b = (text or "").encode("utf-8")
    if len(b) <= max_bytes:
        return b
    return b[:max_bytes].decode("utf-8", "ignore").encode("utf-8")


def pack_ntr(route):
    """Paczka binarna dla ekranu (patrz nagłówek nav.py / firmware ekranu)."""
    pts, cum, times = route["pts"], route["cum"], route.get("times") or [0] * len(route["pts"])
    turns = route.get("turns") or []
    limits = route.get("limits") or []
    cams = route.get("cameras") or []
    wx = route.get("weather") or []
    wps = route.get("waypoints") or []
    name = utf8_cut(route.get("name"), 39)
    out = bytearray(struct.pack("<4sBBHIIIHHHHH40s", b"NTR1", VERSION_NTR, 0, len(wps), int(route.get("id") or 0),
                                int(route.get("version") or 0), len(pts), len(turns), len(limits), len(cams), len(wx), 0,
                                name))
    for i, p in enumerate(pts):
        out += struct.pack("<iiIH", int(round(p[0] * 1e6)), int(round(p[1] * 1e6)), int(cum[i]),
                           min(65535, int(times[i] / 10)))
    for t in turns:
        out += struct.pack("<IBBH32s", t["idx"], t["type"], t.get("exit", 0), 0, utf8_cut(t.get("text"), 31))
    for l in limits:
        out += struct.pack("<IBBH", l["idx"], l["kmh"], 0, 0)
    for c in cams:
        out += struct.pack("<IBBH", c["idx"], c["type"], c.get("limit", 0), c.get("pair", 0))
    for w in wx:
        temp = w.get("temp")
        out += struct.pack("<IIbBBB", w["idx"], int(w.get("t") or 0), int(round(temp)) if temp is not None else -128,
                           int(w.get("rain_prob") or 0), int(w.get("code") or 0), min(255, int(w.get("wind") or 0)))
    for w in wps:
        out += struct.pack("<IBBH32s", w["idx"], w.get("kind", 1), 0, 0, utf8_cut(w.get("name"), 31))
    return bytes(out)
