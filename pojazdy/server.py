"""Pojazdy: dodatek Home Assistant – tankowania, ładowania, koszty i terminy (jak Fuelio).

Panel w menu HA (Ingress, port 8099). Dane w /data/pojazdy.db (wchodzą do kopii HA),
co noc kopia do /share/pojazdy/kopie (baza + plik .fuelio). Ładowania auta wpisują się
same z historii HA (liczniki energii ładowarek, bilans sieci, ceny G13, % baterii).
Czujniki trafiają do HA przez REST API (sensor.pojazdy_*), co 10 min i po każdej zmianie.
"""

import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baza as bz  # noqa: E402
import fuelio  # noqa: E402
import ladowania as ld  # noqa: E402
import obliczenia as ob  # noqa: E402

VERSION = "1.7.0"
DATA = os.environ.get("PJ_DATA", "/data")
SHARE = os.environ.get("PJ_SHARE", "/share/pojazdy")
HERE = os.path.dirname(os.path.abspath(__file__))
WWW = os.environ.get("PJ_WWW", os.path.join(HERE, "www"))
PORT = int(os.environ.get("PJ_PORT", "8099"))
PEERS = set(os.environ.get("PJ_PEERS", "172.30.32.2").split(","))
# Rdzeń HA (automatyzacja Telegram) – tylko ścieżki /api/telegram/* (propozycja i zapis tankowania ze zdjęcia).
PEERS_HA = set(os.environ.get("PJ_PEERS_HA", "172.30.32.1").split(","))
SUPERVISOR = os.environ.get("PJ_SUPERVISOR", "http://supervisor")


def token():
    """Klucz do API Home Assistant od Supervisora: zmienna środowiska albo plik s6
    (przy starcie przez /init zmienne kontenera bywają tylko w /run/s6/container_environment)."""
    for k in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        if os.environ.get(k):
            return os.environ[k].strip()
    for d in ("/run/s6/container_environment", "/var/run/s6/container_environment"):
        for k in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
            try:
                with open(os.path.join(d, k), encoding="utf-8") as f:
                    v = f.read().strip()
                if v:
                    return v
            except OSError:
                pass
    return ""


TOKEN = token()
PETLA = os.environ.get("PJ_PETLA", "1") == "1"  # testy wyłączają pętlę w tle

DOMYSLNE = {
    "ladowarki": [
        {"miejsce": "dom", "nazwa": "Ładowarka (dom)", "licznik": "sensor.ladowarka_auta_energia_licznik", "pojazd": "eclipse"},
        {"miejsce": "hala", "nazwa": "Gniazdko w hali", "licznik": "sensor.ladowarka_w_hali_energia_licznik", "pojazd": "eclipse"},
    ],
    "siec_pobrana": "sensor.siec_pobrana_licznik",
    "siec_oddana": "sensor.siec_oddana_licznik",
    "ceny": {"przedpoludnie": "input_number.cena_przedpoludnie", "popoludnie": "input_number.cena_popoludnie",
             "pozostale": "input_number.cena_pozostale"},
    "ceny_zapas": {"przedpoludnie": 0.92, "popoludnie": 1.51, "pozostale": 0.64},
    "wartosc_kwh": "sensor.wartosc_kwh",
    "bateria": {"eclipse": "sensor.eclipse_bateria"},
    "ladowania_od": "2026-10-31T23:00:00+00:00",  # kursor (UTC) – dokąd już sprawdzone
    "dane_pradu_od": "2026-11-01",  # od kiedy HA mierzy ładowarki (wcześniejsze odcinki bez kWh)
    "grupuj_dni": True,  # Historia: tankowania/ładowania z jednego dnia w jednym rozwijanym wierszu
    "powiadomienie": "",
    "telegram_chat": "",  # numer czatu Telegram (tylko tutaj, nie w repo); puste = bez Telegrama
    "prog_km": 500,
    "kategorie": ["Serwis", "Eksploatacja", "Ubezpieczenie", "Przegląd", "Opony", "Rejestracja", "Parking",
                  "Myjnia", "Opłaty za przejazd", "Mandaty", "Akcesoria", "Inne"],
}
# Serwis motocykla z NT1100 Jazdy (domyślne okresy, gdy encja nie podaje własnego).
NT_SERWIS = {"olej": ("Olej i filtr oleju", 12000, 12), "lancuch": ("Smarowanie łańcucha", 800, None),
             "przeglad": ("Przegląd okresowy", 12000, 12)}

DB = None
LOCK = threading.RLock()
STAN = {"sync": None, "sync_blad": "", "ha": False, "import": None}


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def ust(k):
    return DB.ust(k, DOMYSLNE.get(k))


def teraz_lok():
    return ld.lok(datetime.now(timezone.utc))


# ---------------------------------------------------------------- Home Assistant

def ha_call(method, path, body=None, timeout=20):
    global TOKEN
    if not TOKEN:
        TOKEN = token()
    if not TOKEN:
        return None
    req = urllib.request.Request(
        SUPERVISOR + path, data=None if body is None else json.dumps(body).encode(), method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        try:
            return json.loads(data or b"null")
        except ValueError:
            return None


def ha_stan(encja):
    if not encja or not TOKEN:
        return None
    try:
        return ha_call("GET", "/core/api/states/" + encja)
    except Exception:
        return None


def ha_liczba(encja):
    s = ha_stan(encja)
    try:
        return float(s["state"])
    except (TypeError, ValueError, KeyError):
        return None


def ha_historia(encje, od, do):
    """{encja: [stany]} z API historii HA (UTC)."""
    encje = [e for e in encje if e]
    if not encje or not TOKEN:
        return {}
    q = urllib.parse.urlencode({"filter_entity_id": ",".join(encje), "end_time": do.isoformat(),
                                "minimal_response": "", "no_attributes": "", "significant_changes_only": "0"})
    path = "/core/api/history/period/%s?%s" % (urllib.parse.quote(od.isoformat()), q)
    out = {}
    for lst in ha_call("GET", path, timeout=60) or []:
        if lst:
            eid = lst[0].get("entity_id")
            out[eid] = lst
    return out


_PANEL = []


def panel_url():
    if not _PANEL and TOKEN:
        try:
            slug = ((ha_call("GET", "/addons/self/info") or {}).get("data") or {}).get("slug")
            if slug:
                _PANEL.append("/hassio/ingress/" + slug)
        except Exception:
            pass
    return _PANEL[0] if _PANEL else "/hassio/dashboard"


def telegram(tytul, tresc):
    chat = str(ust("telegram_chat") or "").strip()
    if not chat or not TOKEN:
        return
    try:
        ha_call("POST", "/core/api/services/telegram_bot/send_message",
                {"message": "%s\n%s" % (tytul, tresc), "target": int(chat) if re.fullmatch(r"-?\d+", chat) else chat})
    except Exception as e:
        log("Telegram nieudany:", e)


def powiadom(tytul, tresc, tag):
    telegram(tytul, tresc)
    cel = (ust("powiadomienie") or "").strip()
    if cel.startswith("notify."):
        cel = cel[7:]
    try:
        if cel:
            ha_call("POST", "/core/api/services/notify/" + cel, {
                "title": tytul, "message": tresc,
                "data": {"tag": tag, "url": panel_url(), "clickAction": panel_url()}})
        else:
            ha_call("POST", "/core/api/services/persistent_notification/create",
                    {"title": tytul, "message": tresc, "notification_id": tag})
    except Exception as e:
        log("Powiadomienie nieudane:", e)


# ---------------------------------------------------------------- dane pojazdu

def pojazd_po_kluczu(klucz):
    for p in DB.lista("pojazdy"):
        if p.get("klucz") == klucz or str(p["id"]) == str(klucz):
            return p
    return None


def dane_pojazdu(pid):
    return (DB.lista("tankowania", pojazd_id=pid), DB.lista("ladowania", pojazd_id=pid),
            DB.lista("koszty", pojazd_id=pid), DB.lista("odczyty", pojazd_id=pid))


def z_pradem(p):
    return p.get("rodzaj") in ("phev", "ev")


def prad_od(p, l):
    """Od kiedy znamy wszystkie ładowania pojazdu (ustawienie dane_pradu_od; po dopisaniu
    historii ładowań z auta można je cofnąć)."""
    if not z_pradem(p):
        return None
    return ust("dane_pradu_od") or "2026-11-01"


def korekta_baterii(p):
    """(pojemność baterii, sprawność ładowania) do korekty prądu o stan baterii w odcinku."""
    if z_pradem(p) and p.get("bateria_kwh"):
        return (float(p["bateria_kwh"]), SPRAWNOSC_LADOWANIA)
    return None


def przebieg_pojazdu(p, t=None, k=None, o=None, l=None):
    if t is None:
        t, l, k, o = dane_pojazdu(p["id"])
    pts = ob.przebiegi(t, k, o, l or [])
    return ob.przebieg_teraz(pts), pts


def stan_terminow(p, km):
    dzis = teraz_lok().date()
    out = []
    for t in DB.lista("terminy", pojazd_id=p["id"]):
        if not t.get("aktywny", 1):
            continue
        s = ob.stan_terminu(t, dzis, km, prog_km=float(ust("prog_km") or 500))
        s.update(id=t["id"], nazwa=t["nazwa"], kategoria=t.get("kategoria"), co_km=t.get("co_km"), klucz=t.get("klucz"),
                 co_mies=t.get("co_mies"), ostatnio_data=t.get("ostatnio_data"), ostatnio_km=t.get("ostatnio_km"),
                 pojazd_id=p["id"], pojazd=p["nazwa"])
        s["opis"] = ob.opis_terminu(s)
        out.append(s)

    def pilnosc(s):
        a = s["dni"] if s["dni"] is not None else 10 ** 6
        b = (s["km"] / 30.0) if s["km"] is not None else 10 ** 6  # ok. 30 km dziennie – tylko do kolejności
        return min(a, b)
    out.sort(key=pilnosc)
    return out


def okres(nazwa, dzis=None):
    dzis = dzis or teraz_lok().date()
    if nazwa == "miesiac":
        od = dzis.replace(day=1)
        return od.isoformat(), ob.dodaj_miesiace(od, 1).isoformat()
    if nazwa == "rok":
        return dzis.replace(month=1, day=1).isoformat(), date(dzis.year + 1, 1, 1).isoformat()
    if nazwa == "12m":
        return ob.dodaj_miesiace(dzis.replace(day=1), -11).isoformat(), ob.dodaj_miesiace(dzis.replace(day=1), 1).isoformat()
    return "1900-01-01", "2999-01-01"


def karta_pojazdu(p):
    t, l, k, o = dane_pojazdu(p["id"])
    km, pts = przebieg_pojazdu(p, t, k, o, l)
    odc = ob.odcinki(t, l if z_pradem(p) else None, prad_od(p, l), korekta_baterii(p))
    od, do = okres("miesiac")
    mies = ob.podsumowanie_okresu(t, l, k, o, od, do)
    ost = ob.srednie(odc, 3)
    out = {"id": p["id"], "klucz": p.get("klucz"), "nazwa": p["nazwa"], "rodzaj": p["rodzaj"], "przebieg": km,
           "srednie": ost, "ostatni_odcinek": odc[-1] if odc else None, "miesiac": mies,
           "terminy": stan_terminow(p, km)[:3], "ostatnie_tankowanie": t[0] if t else None,
           "bak_l": p.get("bak_l"), "bateria_kwh": p.get("bateria_kwh"), "polisy": polisy_krotko(polisy_pojazdu(p))}
    if z_pradem(p):
        enc = (ust("bateria") or {}).get(p.get("klucz") or "")
        out["bateria"] = ha_liczba(enc) if enc else None
        out["kwh100_licznik"] = ob.kwh100_z_licznika(l, ob.przebiegi(t, k, o), prad_od(p, l))
    return out


def statystyki(p, nazwa_okresu):
    t, l, k, o = dane_pojazdu(p["id"])
    od, do = okres(nazwa_okresu)
    odc_all = ob.odcinki(t, l if z_pradem(p) else None, prad_od(p, l), korekta_baterii(p))
    odc = [x for x in odc_all if od <= x["do"][:10] < do]
    out = {"pojazd": p, "okres": nazwa_okresu, "od": od, "do": do, "srednie": ob.srednie(odc), "prad_od": prad_od(p, l),
           "odcinki": odc_all[-40:], "podsumowanie": ob.podsumowanie_okresu(t, l, k, o, od, do),
           "miesiace": ob.koszty_miesieczne(t, l, k, od[:7], ob.dodaj_miesiace(ob.d10(do), -1).isoformat()[:7]),
           "kategorie": {}}
    for x in k:
        if od <= (x.get("data") or "")[:10] < do:
            out["kategorie"][x.get("kategoria") or "Inne"] = round(out["kategorie"].get(x.get("kategoria") or "Inne", 0) + float(x.get("kwota") or 0), 2)
    if z_pradem(p):
        out["benzyna"] = ob.porownanie_benzyna(odc, p.get("l100_bez_pradu"))
        lo = [x for x in l if not x.get("wykluczone") and od <= x["poczatek"][:10] < do]
        kwh = sum(float(x.get("kwh") or 0) for x in lo)
        # sprawność tylko z prawdziwych pomiarów (wpisy z ekranu auta mają gniazdko wyliczone z baterii)
        zm = [x for x in lo if x.get("kwh_bateria") and x.get("zrodlo") != "ekran_auta"]
        kwb = sum(float(x.get("kwh_bateria") or 0) for x in zm)
        kws = sum(float(x.get("kwh") or 0) for x in zm)
        out["prad"] = {"kwh": round(kwh, 2), "kwh_pv": round(sum(float(x.get("kwh_pv") or 0) for x in lo), 2),
                       "koszt": round(sum(float(x.get("koszt") or 0) for x in lo), 2),
                       "koszt_wartosc": round(sum(float(x.get("koszt_wartosc") or 0) for x in lo), 2),
                       "sprawnosc": round(kwb / kws, 3) if kws > 0 else None, "ladowan": len(lo)}
        out["pomiar_baterii"] = pomiar_baterii(p, l)
    return out


def pomiar_baterii(p, ladowania):
    """Na sucho: ile kWh z gniazdka idzie na 100 % wskaźnika baterii (z sesji, które mają % przed i po).
    To jest dokładnie to, co mnoży korekta odcinka (pojemność ÷ sprawność), więc można ją kiedyś zastąpić pomiarem.
    Ustawienie (pojemność brutto ÷ sprawność) pokazane obok do porównania; do obliczeń na razie NIE wchodzi."""
    ses = [x for x in ladowania if not x.get("wykluczone") and x.get("zrodlo") != "ekran_auta"
           and x.get("soc_od") is not None and x.get("soc_do") is not None and float(x.get("kwh") or 0) > 0
           and float(x["soc_do"]) - float(x["soc_od"]) >= 10]
    ustaw = None
    if p.get("bateria_kwh"):
        ustaw = round(float(p["bateria_kwh"]) / SPRAWNOSC_LADOWANIA, 2)
    ds = sum(float(x["soc_do"]) - float(x["soc_od"]) for x in ses)
    kwh = sum(float(x["kwh"]) for x in ses)
    return {"sesji": len(ses), "kwh_na_100": round(kwh / ds * 100, 2) if ds > 0 else None, "ustawienie_kwh_na_100": ustaw,
            "uwaga": "na sucho: do obliczeń wchodzi ustawienie, nie pomiar"}


def historia(pid=None, typ=None, limit=400):
    poj = {p["id"]: p for p in DB.lista("pojazdy")}
    out = []
    w = {"pojazd_id": int(pid)} if pid else {}
    if typ in (None, "", "paliwo"):
        for t in DB.lista("tankowania", **w):
            out.append(dict(t, typ="tankowanie", czas=t["data"], kwota_razem=ob.kwota_tankowania(t)))
    if typ in (None, "", "prad"):
        for l in DB.lista("ladowania", **w):
            out.append(dict(l, typ="ladowanie", czas=l["poczatek"], kwota_razem=l.get("koszt") or 0))
    if typ in (None, "", "koszty"):
        for k in DB.lista("koszty", **w):
            out.append(dict(k, typ="koszt", czas=k["data"], kwota_razem=k.get("kwota") or 0))
    out.sort(key=lambda x: (x["czas"] or "").replace("T", " "), reverse=True)
    # spalanie przy pełnych tankowaniach
    for pid_, p in poj.items():
        t, l, k, o = dane_pojazdu(pid_)
        for odc in ob.odcinki(t, l if z_pradem(p) else None, prad_od(p, l), korekta_baterii(p)):
            for x in out:
                if x["typ"] == "tankowanie" and x["id"] == odc["tankowanie_id"]:
                    x["l100"] = odc["l100"]
                    x["kwh100"] = odc.get("kwh100")
    for x in out:
        x["pojazd"] = poj.get(x["pojazd_id"], {}).get("nazwa", "?")
    return out[:limit]


# ---------------------------------------------------------------- ładowania z HA

def ceny_teraz():
    zap = ust("ceny_zapas") or DOMYSLNE["ceny_zapas"]
    out = {}
    for st, enc in (ust("ceny") or {}).items():
        v = ha_liczba(enc)
        out[st] = v if v else zap.get(st)
    return out


def synchronizuj_ladowania():
    """Nowe, zakończone sesje ładowania z liczników -> tabela ladowania."""
    if not TOKEN and not token():
        STAN["sync_blad"] = "brak klucza do Home Assistant (SUPERVISOR_TOKEN) – zrestartuj dodatek; jeśli zostaje, wyślij dziennik dodatku"
        return 0
    try:
        ha_call("GET", "/core/api/")
    except Exception as e:
        STAN["sync_blad"] = "Home Assistant nie odpowiada: %s" % e
        return 0
    teraz = datetime.now(timezone.utc)
    kursor = ld.utc(ust("ladowania_od"))
    od = kursor - timedelta(minutes=30)
    dodane = 0
    nowy_kursor = teraz - timedelta(minutes=ld.KONIEC_PO_MIN)
    ceny = None
    for lad in ust("ladowarki") or []:
        p = pojazd_po_kluczu(lad.get("pojazd"))
        if not p or not lad.get("licznik"):
            continue
        h = ha_historia([lad["licznik"]], od, teraz).get(lad["licznik"])
        ser = ld.seria(h)
        for s in ld.sesje(ser, teraz, min_kwh=0):
            if not s["skonczona"]:
                nowy_kursor = min(nowy_kursor, s["start"] - timedelta(minutes=1))
                continue
            if s["kwh"] < ld.MIN_KWH:
                continue
            uid = "auto:%s:%s" % (lad["miejsce"], s["start"].strftime("%Y%m%dT%H%M"))
            if DB.jest_uid("ladowania", uid):
                continue
            p0, k0 = ld.lok(s["start"]).strftime("%Y-%m-%d %H:%M"), ld.lok(s["koniec"]).strftime("%Y-%m-%d %H:%M")
            if any(x.get("miejsce") == lad["miejsce"] and x.get("zrodlo") == "auto" and x["poczatek"] <= k0
                   and (x.get("koniec") or x["poczatek"]) >= p0 for x in DB.lista("ladowania", pojazd_id=p["id"])):
                continue  # ta sama sesja już zapisana (inny początek okna) – bez dubla
            if ceny is None:
                ceny = ceny_teraz()
            okno_od = s["start"].replace(minute=0, second=0, microsecond=0) - timedelta(minutes=5)
            okno_do = s["koniec"] + timedelta(hours=1, minutes=5)
            siec = ha_historia([ust("siec_pobrana"), ust("siec_oddana"), ust("wartosc_kwh")], okno_od, okno_do)
            bat_enc = (ust("bateria") or {}).get(p.get("klucz") or "")
            bat = ld.seria(ha_historia([bat_enc], s["start"] - timedelta(hours=6), okno_do).get(bat_enc)) if bat_enc else []
            wyc = ld.wycen(s, ceny, ld.seria(siec.get(ust("siec_pobrana"))), ld.seria(siec.get(ust("siec_oddana"))),
                           ld.seria(siec.get(ust("wartosc_kwh"))), ha_liczba(ust("wartosc_kwh")))
            s0, s1 = ld.soc(bat, s["start"], s["koniec"]) if bat else (None, None)
            w = ld.do_wiersza(s, lad["miejsce"], p["id"], wyc, s0, s1, p.get("bateria_kwh"))
            w["notatka"] = lad.get("nazwa") or lad["miejsce"]
            if wyc.get("bez_bilansu"):
                w["notatka"] += " · bez bilansu sieci (całość wyceniona jak z sieci)"
            if DB.dodaj("ladowania", w, pomin_istniejace=True):
                dodane += 1
                log("Ładowanie:", w["poczatek"], lad["miejsce"], w["kwh"], "kWh", w["koszt"], "zł")
    DB.ustaw("ladowania_od", max(kursor, nowy_kursor).isoformat())
    STAN["sync"] = datetime.now(timezone.utc).isoformat()
    STAN["sync_blad"] = ""
    return dodane


# ---------------------------------------------------------------- przebieg z telemetrii, migracja serwisu

def przebieg_z_encji():
    dzis = teraz_lok().strftime("%Y-%m-%d")
    for p in DB.lista("pojazdy"):
        if not p.get("encja_przebiegu"):
            continue
        v = ha_liczba(p["encja_przebiegu"])
        if v is None:
            continue
        km, _ = przebieg_pojazdu(p)
        dzisiejsze = [o for o in DB.lista("odczyty", pojazd_id=p["id"]) if o["zrodlo"] == "telemetria" and o["data"][:10] == dzis]
        if dzisiejsze:
            if abs(dzisiejsze[0]["przebieg"] - v) >= 0.5:
                DB.zmien("odczyty", dzisiejsze[0]["id"], {"przebieg": v, "data": teraz_lok().strftime("%Y-%m-%d %H:%M")})
        elif km is None or v > km + 0.5:
            DB.dodaj("odczyty", {"pojazd_id": p["id"], "data": teraz_lok().strftime("%Y-%m-%d %H:%M"),
                                 "przebieg": v, "zrodlo": "telemetria"})


def migracja_serwisu_nt1100():
    """Jednorazowo: pozycje serwisu z NT1100 Jazdy (sensor.nt1100_serwis_*) -> terminy."""
    if DB.ust("migracja_nt1100") or not TOKEN:
        return
    p = pojazd_po_kluczu("nt1100")
    if not p:
        DB.ustaw("migracja_nt1100", "brak pojazdu")
        return
    try:
        stany = ha_call("GET", "/core/api/states") or []
    except Exception:
        return
    odo = None
    for s in stany:
        if s.get("entity_id") == "sensor.nt1100_przebieg":
            try:
                odo = float(s["state"])
            except (TypeError, ValueError):
                pass
    n = 0
    for s in stany:
        m = re.match(r"^sensor\.nt1100_serwis_([a-z0-9_]+)$", s.get("entity_id") or "")
        if not m:
            continue
        sid = m.group(1)
        nazwa, co_km, co_mies = NT_SERWIS.get(sid, ((s.get("attributes") or {}).get("friendly_name", sid).replace("NT1100 Serwis ", ""), None, None))
        try:
            left = float(s["state"])
        except (TypeError, ValueError):
            left = None
        t = {"pojazd_id": p["id"], "nazwa": nazwa, "kategoria": "Serwis", "co_km": co_km, "co_mies": co_mies,
             "klucz": "nt1100:" + sid}
        if left is not None and odo is not None and co_km:
            t["ostatnio_km"] = round(odo + left - co_km)
        elif left is not None and odo is not None:
            t["nastepny_km"] = round(odo + left)
        if DB.dodaj("terminy", t, pomin_istniejace=True):
            n += 1
    if n or odo is not None:
        DB.ustaw("migracja_nt1100", {"data": teraz_lok().isoformat(), "pozycji": n})
        log("Serwis NT1100 przeniesiony:", n, "pozycji")


# ---------------------------------------------------------------- terminy: powiadomienia

def powiadomienia_terminow():
    for p in DB.lista("pojazdy"):
        km, _ = przebieg_pojazdu(p)
        for s in stan_terminow(p, km):
            prog = ob.ktore_powiadomienie(s, prog_km=(int(ust("prog_km") or 500), 100, 0))
            t = DB.jeden("terminy", s["id"])
            if not prog or (t.get("powiadomiono") or "") == prog:
                continue
            DB.zmien("terminy", s["id"], {"powiadomiono": prog})
            powiadom("%s: %s" % (p["nazwa"], s["nazwa"]), "%s: %s." % (s["nazwa"], s["opis"]), "pojazdy_termin_%d" % s["id"])


# ---------------------------------------------------------------- polisy i raty

NAZWY_ZAKRESU = {"OC": "OC", "OC+AC": "OC + AC", "AC": "AC"}


def nazwa_polisy(p):
    return NAZWY_ZAKRESU.get(p.get("zakres"), p.get("zakres") or "Polisa")


def polisa_pelna(p, dzis=None, poj=None):
    """Polisa z ratami, stanem na dziś i nazwą pojazdu."""
    dzis = dzis or teraz_lok().date()
    raty = DB.lista("raty", polisa_id=p["id"])
    poj = poj or DB.jeden("pojazdy", p["pojazd_id"]) or {}
    return dict(p, raty=raty, stan=ob.stan_polisy(p, raty, dzis), pojazd=poj.get("nazwa"), nazwa=nazwa_polisy(p))


def biezaca(x):
    """Pokazywana jako bieżąca: nie zastąpiona nowszą, nie wygasła dawniej niż 60 dni temu (albo ma niezapłacone raty)."""
    st = x["stan"]
    return not x.get("odnowiona") and (st["dni_do_konca"] >= -60 or not st["oplacona"])


def polisy_pojazdu(p, wszystkie=False):
    out = [polisa_pelna(x, poj=p) for x in DB.lista("polisy", pojazd_id=p["id"])]
    if not wszystkie:
        out = [x for x in out if biezaca(x)]
    out.sort(key=lambda x: (not x["stan"]["pilne"], x["do"]))
    return out


def koszt_raty(pol, r, poj, n=None):
    """Zapłacona rata -> jeden koszt „Ubezpieczenie” (uid polisa:<id>:rata:<nr>); niezapłacona -> bez kosztu."""
    uid = "polisa:%d:rata:%d" % (pol["id"], r["nr"])
    if r.get("koszt_id") and DB.jeden("koszty", r["koszt_id"]):
        DB.usun("koszty", r["koszt_id"])
    for k in DB.lista("koszty", uid=uid):
        DB.usun("koszty", k["id"])
    kid = None
    if r.get("zaplacono"):
        n = n or len(DB.lista("raty", polisa_id=pol["id"]))
        kid = DB.dodaj("koszty", {"pojazd_id": pol["pojazd_id"], "data": r["zaplacono"][:10], "kategoria": "Ubezpieczenie",
                                  "tytul": "%s – rata %d z %d" % (nazwa_polisy(pol), r["nr"], n),
                                  "kwota": r.get("kwota"), "zrodlo": "polisa", "uid": uid})
    DB.zmien("raty", r["id"], {"koszt_id": kid})


def zapisz_polise(j, id_=None):
    """Nowa albo zmieniona polisa. Raty: lista z formularza albo rozłożone z liczby rat. Zapłacone raty mają koszt."""
    d = {}
    for k in ("pojazd_id", "zakres", "ubezpieczyciel", "numer", "od", "do", "skladka", "notatka", "wypowiedziana"):
        if k in j:
            d[k] = j[k]
    if "pojazd_id" in d:
        d["pojazd_id"] = int(d["pojazd_id"])
    if "skladka" in d:
        d["skladka"] = None if d["skladka"] in (None, "") else float(str(d["skladka"]).replace(",", "."))
    if "wypowiedziana" in d:
        d["wypowiedziana"] = 1 if d["wypowiedziana"] in (1, True, "1") else 0
    stara = DB.jeden("polisy", id_) if id_ else {}
    if id_ and not stara:
        raise KeyError("nie ma polisy")
    pelna = dict(stara or {}, **d)
    if not pelna.get("pojazd_id"):
        raise ValueError("wybierz pojazd")
    for k in ("od", "do"):
        if not pelna.get(k):
            raise ValueError("podaj daty od i do")
        pelna[k] = str(pelna[k])[:10]
        if k in d:
            d[k] = pelna[k]
        ob.d10(pelna[k])
    if pelna["do"] < pelna["od"]:
        raise ValueError("data „do” wcześniejsza niż „od”")
    for i, r in enumerate(j.get("raty") or []):
        if not r.get("termin"):
            raise ValueError("rata %d bez terminu" % (i + 1))
        ob.d10(str(r["termin"]))
    if id_:
        DB.zmien("polisy", id_, d)
    else:
        d.setdefault("zakres", "OC")
        id_ = DB.dodaj("polisy", d)
    pol = DB.jeden("polisy", id_)
    raty = j.get("raty")
    if raty is None and (j.get("liczba_rat") or not stara):
        raty = ob.rozloz_raty(pol["od"], pol.get("skladka"), j.get("liczba_rat") or 1)
    if raty is not None:
        poj = DB.jeden("pojazdy", pol["pojazd_id"]) or {}
        bylo = {}
        for r in DB.lista("raty", polisa_id=id_):
            bylo[(r["termin"], bool(r.get("zaplacono")))] = r.get("powiadomiono")
            if r.get("koszt_id"):
                DB.usun("koszty", r["koszt_id"])
            DB.usun("raty", r["id"])
        for i, r in enumerate(raty):
            kw = r.get("kwota")
            zap = str(r["zaplacono"])[:10] if r.get("zaplacono") else None
            # przypomnienie już wysłane dla tej samej raty nie wraca po edycji polisy
            rid = DB.dodaj("raty", {"polisa_id": id_, "nr": i + 1, "termin": str(r["termin"])[:10],
                                    "kwota": None if kw in (None, "") else round(float(str(kw).replace(",", ".")), 2),
                                    "zaplacono": zap, "powiadomiono": bylo.get((str(r["termin"])[:10], bool(zap)))})
            koszt_raty(pol, DB.jeden("raty", rid), poj, len(raty))
        if pol.get("skladka") is None:
            DB.zmien("polisy", id_, {"skladka": round(sum(float(r.get("kwota") or 0) for r in DB.lista("raty", polisa_id=id_)), 2)})
    elif stara:
        # zmiana pojazdu, zakresu itp. – koszty zapłaconych rat idą za polisą
        poj = DB.jeden("pojazdy", pol["pojazd_id"]) or {}
        lst = DB.lista("raty", polisa_id=id_)
        for r in lst:
            koszt_raty(pol, r, poj, len(lst))
    if j.get("z_terminu"):
        DB.zmien("terminy", int(j["z_terminu"]), {"aktywny": 0})
    if stara and (stara.get("do") != pol.get("do")):
        DB.zmien("polisy", id_, {"powiadomiono": ""})
    return id_


def usun_polise(id_):
    for r in DB.lista("raty", polisa_id=id_):
        if r.get("koszt_id"):
            DB.usun("koszty", r["koszt_id"])
        DB.usun("raty", r["id"])
    DB.usun("polisy", id_)


def zaplac_rate(id_, data=None, cofnij=False):
    r = DB.jeden("raty", id_)
    if not r:
        raise KeyError("nie ma raty")
    pol = DB.jeden("polisy", r["polisa_id"])
    DB.zmien("raty", id_, {"zaplacono": None if cofnij else (data or teraz_lok().strftime("%Y-%m-%d"))[:10], "powiadomiono": ""})
    koszt_raty(pol, DB.jeden("raty", id_), DB.jeden("pojazdy", pol["pojazd_id"]) or {})


def odnow_polise(id_):
    """Kopia polisy na kolejny rok: od = dzień po końcu, te same: zakres, ubezpieczyciel, składka, liczba rat."""
    p = DB.jeden("polisy", id_)
    if not p:
        raise KeyError("nie ma polisy")
    od = ob.d10(p["do"]) + timedelta(days=1)
    do = ob.dodaj_miesiace(od, 12) - timedelta(days=1)
    n = len(DB.lista("raty", polisa_id=id_)) or 1
    nid = zapisz_polise({"pojazd_id": p["pojazd_id"], "zakres": p["zakres"], "ubezpieczyciel": p.get("ubezpieczyciel"),
                         "numer": p.get("numer"), "od": od.isoformat(), "do": do.isoformat(), "skladka": p.get("skladka"),
                         "liczba_rat": n})
    DB.zmien("polisy", id_, {"odnowiona": 1})
    return nid


def tekst_konca(x):
    st, pj = x["stan"], x["pojazd"]
    do = ob.d10(x["do"]).strftime("%d.%m.%Y")
    if not ob.ma_oc(x.get("zakres")):
        return "%s kończy się %s. Jeśli chcesz dalej, kup nową polisę." % (x["nazwa"], do)
    if x.get("wypowiedziana"):
        return "%s kończy się %s i jest wypowiedziana – kup nową polisę przed tym dniem." % (x["nazwa"], do)
    if st["wznowi_sie"]:
        return ("%s kończy się %s. Raty zapłacone, więc wznowi się sama na rok. Chcesz zmienić ubezpieczyciela – "
                "wypowiedz do %s." % (x["nazwa"], do, ob.d10(st["wypowiedz_do"]).strftime("%d.%m.%Y")))
    return ("%s kończy się %s. Są niezapłacone raty (%s zł), więc sama się nie wznowi – zapłać albo kup nową."
            % (x["nazwa"], do, ("%.2f" % st["do_zaplaty"]).replace(".", ",")))


def tekst_raty(x, r, dni):
    kw = ("%.2f zł" % float(r["kwota"])).replace(".", ",") if r.get("kwota") is not None else "kwota?"
    term = ob.d10(r["termin"]).strftime("%d.%m.%Y")
    n = x["stan"]["liczba_rat"]
    if dni < 0:
        dop = "OC dalej chroni, ale grożą odsetki i windykacja." if ob.ma_oc(x.get("zakres")) else ""
        if "AC" in (x.get("zakres") or "").upper():
            dop += (" " if dop else "") + "AC może zostać rozwiązane – zapłać albo sprawdź warunki."
        return "%s, termin minął %d %s temu (%s). Rata %d z %d. %s" % (kw, -dni, "dzień" if dni == -1 else "dni", term, r["nr"], n, dop)
    kiedy = "dziś" if dni == 0 else ("jutro" if dni == 1 else "za %d dni" % dni)
    return "%s do %s (%s). Rata %d z %d." % (kw, term, kiedy, r["nr"], n)


def powiadomienia_polis():
    dzis = teraz_lok().date()
    for p in DB.lista("pojazdy"):
        for x in polisy_pojazdu(p):
            for r in x["raty"]:
                if r.get("zaplacono"):
                    continue
                dni = (ob.d10(r["termin"]) - dzis).days
                prog = ob.powiadomienie_raty(dni)
                if not prog or (r.get("powiadomiono") or "") == prog:
                    continue
                DB.zmien("raty", r["id"], {"powiadomiono": prog})
                tyt = "%s: rata %s%s" % (p["nazwa"], x["nazwa"], " po terminie" if dni < 0 else "")
                powiadom(tyt, tekst_raty(x, r, dni), "pojazdy_rata_%d" % r["id"])
            prog = ob.powiadomienie_konca(x["stan"]["dni_do_konca"])
            if prog and (x.get("powiadomiono") or "") != prog and x["stan"]["waznosc"] != "przyszla":
                DB.zmien("polisy", x["id"], {"powiadomiono": prog})
                d = x["stan"]["dni_do_konca"]
                powiadom("%s: %s kończy się %s" % (p["nazwa"], x["nazwa"], "dziś" if d == 0 else ("jutro" if d == 1 else "za %d dni" % d)),
                         tekst_konca(x), "pojazdy_polisa_%d" % x["id"])


def polisy_krotko(lst):
    return [{"id": x["id"], "nazwa": x["nazwa"], "zakres": x["zakres"], "od": x["od"], "do": x["do"],
             "opis": x["stan"]["opis"], "poziom": x["stan"]["poziom"], "pilne": x["stan"]["pilne"],
             "zaplaconych": x["stan"]["zaplaconych"], "liczba_rat": x["stan"]["liczba_rat"],
             "do_zaplaty": x["stan"]["do_zaplaty"], "nastepna": x["stan"]["nastepna"], "waznosc": x["stan"]["waznosc"],
             "wznowi_sie": x["stan"]["wznowi_sie"], "dni_do_konca": x["stan"]["dni_do_konca"]} for x in lst]


# ---------------------------------------------------------------- czujniki w HA

def slug(s):
    s = (s or "").lower()
    for a, b in zip("ąćęłńóśźż", "acelnoszz"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "pojazd"


def czujniki():
    out = []
    for p in DB.lista("pojazdy"):
        if not p.get("aktywny", 1):
            continue
        c = karta_pojazdu(p)
        s = slug(p.get("klucz") or p["nazwa"])
        dev = {"pojazd": p["nazwa"]}

        def add(k, stan, nazwa, jedn=None, ikona=None, attrs=None):
            a = dict(dev, friendly_name="%s %s" % (p["nazwa"], nazwa))
            if jedn:
                a["unit_of_measurement"] = jedn
            if ikona:
                a["icon"] = ikona
            a.update(attrs or {})
            out.append(("sensor.pojazdy_%s_%s" % (s, k), "unknown" if stan is None else stan, a))
        sr = c["srednie"]
        add("spalanie", sr.get("l100"), "spalanie", "L/100km", "mdi:gas-station", {"state_class": "measurement"})
        add("koszt_100km", sr.get("zl100"), "koszt na 100 km", "zł", "mdi:cash", {"state_class": "measurement"})
        add("koszt_miesiac", c["miesiac"]["razem"], "koszt w tym miesiącu", "zł", "mdi:calendar-month",
            {"paliwo": c["miesiac"]["paliwo"], "prad": c["miesiac"]["prad"], "inne": c["miesiac"]["inne"]})
        t, l, k, o = dane_pojazdu(p["id"])
        reczne = ob.przebiegi(t, k, [x for x in o if x.get("zrodlo") != "telemetria"])
        ost = reczne[-1] if reczne else (None, None)
        # ostatni odczyt wpisany ręcznie/z tankowania/kosztu: kotwica dla NT1100 Jazdy (bez telemetrii, żeby jazdy się nie dublowały)
        add("przebieg", c["przebieg"], "przebieg", "km", "mdi:counter",
            {"odczyt_reczny_km": ost[1], "odczyt_reczny_data": ost[0]})
        if z_pradem(p):
            add("zuzycie_pradu", sr.get("kwh100"), "zużycie prądu", "kWh/100km", "mdi:ev-station", {"state_class": "measurement"})
            kl = c.get("kwh100_licznik")
            add("zuzycie_pradu_licznik", kl["kwh100"] if kl else None, "zużycie prądu z licznika (na sucho)", "kWh/100km",
                "mdi:ev-station", dict(kl or {}))
        ter = stan_terminow(p, c["przebieg"])
        add("terminy", sum(1 for t in ter if t["pilne"]), "pilne terminy", None, "mdi:wrench-clock", {
            "najblizszy": ("%s: %s" % (ter[0]["nazwa"], ter[0]["opis"])) if ter else "",
            "terminy": [{"nazwa": t["nazwa"], "opis": t["opis"], "dni": t["dni"], "km": t["km"],
                         "klucz": t.get("klucz"), "co_km": t.get("co_km"), "ostatnio_km": t.get("ostatnio_km"),
                         "nastepny_data": t["nastepny_data"], "nastepny_km": t["nastepny_km"], "pilne": t["pilne"],
                         "kategoria": t.get("kategoria")} for t in ter],
            "panel": panel_url()})
        pol = c["polisy"]
        wazne = [x for x in pol if x["waznosc"] == "wazna"]
        gl = min(wazne, key=lambda x: x["do"]) if wazne else None
        add("polisa", gl["dni_do_konca"] if gl else None, "polisa – dni do końca", "d", "mdi:shield-car", {
            "do": gl["do"] if gl else None, "opis": gl["opis"] if gl else "brak ważnej polisy",
            "opłacona": all(x["do_zaplaty"] <= 0 for x in pol) if pol else None,
            "pilne": sum(1 for x in pol if x["pilne"]),
            "polisy": [{"nazwa": x["nazwa"], "od": x["od"], "do": x["do"], "opis": x["opis"],
                        "raty": "%d/%d" % (x["zaplaconych"], x["liczba_rat"]), "do_zaplaty": x["do_zaplaty"],
                        "nastepna_rata": x["nastepna"]["termin"] if x["nastepna"] else None,
                        "nastepna_kwota": x["nastepna"]["kwota"] if x["nastepna"] else None,
                        "wznowi_sie": x["wznowi_sie"]} for x in pol],
            "panel": panel_url()})
    return out


def publikuj():
    if not TOKEN:
        return
    try:
        for eid, stan, attrs in czujniki():
            ha_call("POST", "/core/api/states/" + eid, {"state": stan, "attributes": attrs})
        STAN["ha"] = True
    except Exception as e:
        STAN["ha"] = False
        log("Czujniki: nie udało się opublikować:", e)


def po_zmianie():
    threading.Thread(target=publikuj, daemon=True).start()


# ---------------------------------------------------------------- kopia

def eksport_fuelio(tylko=None):
    pozycje = []
    for p in DB.lista("pojazdy"):
        if tylko and p["id"] != tylko:
            continue
        pozycje.append((p, list(reversed(DB.lista("tankowania", pojazd_id=p["id"]))),
                        list(reversed(DB.lista("koszty", pojazd_id=p["id"])))))
    return fuelio.eksport(pozycje)


def zdublowane_ladowania():
    """Zachodzące na siebie sesje auto tej samej ładowarki: [(zostaje, [do_usuniecia])].
    Zostaje wpis z największą energią (przy remisie najwcześniejszy); usuwane tylko te, które mieszczą się
    w jego przedziale czasu i nie były ręcznie edytowane."""
    wyn = []
    for p in DB.lista("pojazdy"):
        grupy = {}
        for x in DB.lista("ladowania", pojazd_id=p["id"]):
            if x.get("zrodlo") == "auto":
                grupy.setdefault(x.get("miejsce"), []).append(x)
        for lst in grupy.values():
            lst.sort(key=lambda x: x["poczatek"])
            klaster = []
            for x in lst + [None]:
                if x is not None and klaster and x["poczatek"] <= max(k.get("koniec") or k["poczatek"] for k in klaster):
                    klaster.append(x)
                    continue
                if len(klaster) > 1:
                    zostaje = max(klaster, key=lambda k: (k.get("kwh") or 0, -klaster.index(k)))
                    kon = lambda k: k.get("koniec") or k["poczatek"]
                    usun = [k for k in klaster if k["id"] != zostaje["id"] and not k.get("zmienione")
                            and k["poczatek"] >= zostaje["poczatek"] and kon(k) <= kon(zostaje)]
                    if usun:
                        wyn.append((zostaje, usun))
                klaster = [x] if x is not None else []
    return wyn


def scal_ladowania(podglad):
    wyn = zdublowane_ladowania()
    n = sum(len(u) for _, u in wyn)
    if podglad or not n:
        return {"do_usuniecia": n, "grup": len(wyn)}
    kat = os.path.join(SHARE, "kopie")
    os.makedirs(kat, exist_ok=True)
    DB.kopia(os.path.join(kat, "pojazdy-przed-scaleniem-%s.db" % teraz_lok().strftime("%Y-%m-%d-%H%M")))
    for zostaje, usun in wyn:
        for k in usun:
            DB.usun("ladowania", k["id"])
            log("Scalono dubel ładowania:", k["poczatek"], k.get("kwh"), "kWh ->", zostaje["poczatek"], zostaje.get("kwh"))
    return {"do_usuniecia": n, "grup": len(wyn), "usuniete": n}


def kopia_nocna():
    kat = os.path.join(SHARE, "kopie")
    os.makedirs(kat, exist_ok=True)
    d = teraz_lok().strftime("%Y-%m-%d")
    DB.kopia(os.path.join(kat, "pojazdy-%s.db" % d))
    with open(os.path.join(kat, "pojazdy-%s.fuelio" % d), "wb") as f:
        f.write(eksport_fuelio())
    pliki = sorted(os.listdir(kat))
    for ext in (".db", ".fuelio"):
        stare = [x for x in pliki if x.endswith(ext)][:-30]
        for x in stare:
            try:
                os.remove(os.path.join(kat, x))
            except OSError:
                pass
    DB.ustaw("kopia_ostatnia", teraz_lok().strftime("%Y-%m-%d %H:%M"))
    log("Kopia zapisana:", kat)


def _data_tankowania(t):
    """Data tankowania jako czas lokalny; sama data (np. z Fuelio) = południe."""
    d = (t.get("data") or "").replace("T", " ")
    return datetime.strptime(d[:16], "%Y-%m-%d %H:%M") if len(d) >= 16 else datetime.strptime(d[:10] + " 12:00", "%Y-%m-%d %H:%M")


def uzupelnij_soc():
    """Stan baterii (%) w chwili tankowania z historii HA (tylko tankowania bez wpisanej wartości)."""
    for p in DB.lista("pojazdy"):
        enc = (ust("bateria") or {}).get(p.get("klucz") or "")
        if not (enc and z_pradem(p)):
            continue
        od = prad_od(p, None)
        brak = [t for t in DB.lista("tankowania", pojazd_id=p["id"]) if t.get("soc") is None and (t["data"] or "")[:10] >= od]
        if not brak:
            continue
        teraz = datetime.now(timezone.utc)
        pocz = min(ld.do_utc(_data_tankowania(t)) for t in brak) - timedelta(hours=12)
        ser = ld.seria(ha_historia([enc], pocz, teraz).get(enc))
        for t in brak:
            moment = ld.do_utc(_data_tankowania(t))
            if moment > teraz - timedelta(minutes=20):
                continue
            v = ld.wartosc_w(ser, moment)
            if v is not None:
                DB.zmien("tankowania", t["id"], {"soc": round(v, 1)})
                log("Stan baterii przy tankowaniu %s: %s %%" % (t["data"], round(v, 1)))


def petla():
    for _ in range(30):
        try:
            ha_call("GET", "/core/api/")
            break
        except Exception:
            time.sleep(10)
    ostatnia_kopia = DB.ust("kopia_ostatnia") or ""
    while True:
        for krok in (migracja_serwisu_nt1100, przebieg_z_encji, synchronizuj_ladowania, uzupelnij_soc, powiadomienia_terminow, powiadomienia_polis, publikuj):
            try:
                krok()
            except Exception as e:
                if krok is synchronizuj_ladowania:
                    STAN["sync_blad"] = str(e)
                log("Błąd (%s):" % krok.__name__, e)
                traceback.print_exc()
        n = teraz_lok()
        if n.hour >= 2 and (DB.ust("kopia_ostatnia") or "")[:10] != n.strftime("%Y-%m-%d"):
            try:
                kopia_nocna()
            except Exception as e:
                log("Kopia nieudana:", e)
        time.sleep(600)


# ---------------------------------------------------------------- import Fuelio

def propozycja_pojazdu(nazwa):
    n = (nazwa or "").lower()
    if re.search(r"\bnt\b|nt1100", n):
        p = pojazd_po_kluczu("nt1100")
        return p["id"] if p else None
    if "mitsubishi" in n or "eclipse" in n:
        p = pojazd_po_kluczu("eclipse")
        return p["id"] if p else None
    return None


SPRAWNOSC_LADOWANIA = 0.88  # bateria / gniazdko – do przeliczenia odczytów z ekranu auta (straty ładowarki ~12 %)


def import_podglad(dane, nazwa):
    lad = fuelio.czytaj_ladowania(dane)
    if lad is not None:
        if not lad:
            raise ValueError("w pliku nie ma żadnego wiersza od,do,kwh_bateria")
        STAN["import"] = {"dane": dane, "nazwa": nazwa, "czas": time.time()}
        p = pojazd_po_kluczu("eclipse") or next((x for x in DB.lista("pojazdy") if z_pradem(x)), None)
        nowe = sum(1 for x in lad if not DB.jest_uid("ladowania", "ekran:%s:%s" % (x["od"], x["do"])))
        kwb = sum(x["kwh_bateria"] for x in lad)
        teraz = ust("dane_pradu_od") or "2026-11-01"
        return {"ladowania": {"plik": "ekran", "ile": len(lad), "nowych": nowe, "od": lad[0]["od"], "do": lad[-1]["do"],
                              "kwh_bateria": round(kwb, 1), "kwh_gniazdko": round(kwb / SPRAWNOSC_LADOWANIA, 1),
                              "sprawnosc": SPRAWNOSC_LADOWANIA, "prad_od_teraz": teraz,
                              "prad_od_nowe": min(teraz, lad[0]["od"]), "pojazd_id": p["id"] if p else None,
                              "lista": lad},
                "pojazdy": [], "cele": [{"id": x["id"], "nazwa": x["nazwa"]} for x in DB.lista("pojazdy") if z_pradem(x)]}
    poj = fuelio.czytaj(dane, nazwa)
    STAN["import"] = {"dane": dane, "nazwa": nazwa, "czas": time.time()}
    out = []
    for v in poj:
        pid = propozycja_pojazdu(v["nazwa"])
        nowe = sum(1 for t in v["tankowania"] if not DB.jest_uid("tankowania", t["uid"]))
        out.append({"plik": v["plik"], "nazwa": v["nazwa"], "tankowan": len(v["tankowania"]), "nowych": nowe,
                    "kosztow": len(v["koszty"]), "terminow": len(v["terminy"]), "od": v["od"], "do": v["do"],
                    "podejrzane": v["podejrzane"], "pojazd_id": pid})
    return {"pojazdy": out, "cele": [{"id": p["id"], "nazwa": p["nazwa"]} for p in DB.lista("pojazdy")]}


def import_zapisz(mapowanie, popraw=True):
    imp = STAN.get("import")
    if not imp:
        raise ValueError("najpierw wybierz plik")
    wynik = {"tankowan": 0, "kosztow": 0, "terminow": 0, "poprawionych": 0, "ladowan": 0}
    lad = fuelio.czytaj_ladowania(imp["dane"])
    if lad is not None:
        pid = mapowanie.get("ekran")
        if pid:
            wynik.update(import_ladowan_z_auta(int(pid), lad))
        STAN["import"] = None
        po_zmianie()
        return wynik
    for v in fuelio.czytaj(imp["dane"], imp["nazwa"]):
        pid = mapowanie.get(v["plik"])
        if not pid:
            continue
        pid = int(pid)
        for t in v["tankowania"]:
            if popraw and t.get("podejrzana"):
                t["kwota"] = t["podejrzana"]
                t["notatka"] = ((t.get("notatka") or "") + " (kwota poprawiona przy imporcie: litry × cena)").strip()
                wynik["poprawionych"] += 1
            t["pojazd_id"] = pid
            if DB.dodaj("tankowania", t, pomin_istniejace=True):
                wynik["tankowan"] += 1
        for k in v["koszty"]:
            k["pojazd_id"] = pid
            if DB.dodaj("koszty", k, pomin_istniejace=True):
                wynik["kosztow"] += 1
        for t in v["terminy"]:
            t["pojazd_id"] = pid
            t["klucz"] = "fuelio:%s:%s" % (v["nazwa"], t["nazwa"])
            if DB.dodaj("terminy", t, pomin_istniejace=True):
                wynik["terminow"] += 1
    STAN["import"] = None
    log("Import Fuelio:", wynik)
    po_zmianie()
    return wynik


def import_ladowan_z_auta(pid, lad):
    """Ładowania odczytane z ekranu auta (energia do baterii, za dzień albo miesiąc).

    Gniazdko = bateria / sprawność; koszt szacunkowy wg bieżącej „Wartości kWh” (cen sprzed
    zapisu HA nie znamy). Od pierwszego dnia z pliku liczy się zużycie prądu (dane_pradu_od)."""
    try:
        wart = ha_liczba(ust("wartosc_kwh"))
    except Exception:
        wart = None
    n = 0
    for x in lad:
        kwh = round(x["kwh_bateria"] / SPRAWNOSC_LADOWANIA, 2)
        koszt = round(kwh * wart, 2) if wart else None
        notatka = ("z ekranu auta: %s kWh do baterii, gniazdko ≈ bateria / %d %%%s. %s" % (
            str(x["kwh_bateria"]).replace(".", ","), round(SPRAWNOSC_LADOWANIA * 100),
            ", koszt wg Wartości kWh %.2f zł" % wart if wart else "", x.get("notatka") or "")).strip()
        if DB.dodaj("ladowania", {"pojazd_id": pid, "poczatek": x["od"] + " 00:00", "koniec": x["do"] + " 23:59",
                                  "kwh": kwh, "kwh_bateria": x["kwh_bateria"], "koszt": koszt, "koszt_wartosc": koszt,
                                  "miejsce": "z ekranu auta", "zrodlo": "ekran_auta", "notatka": notatka,
                                  "uid": "ekran:%s:%s" % (x["od"], x["do"])}, pomin_istniejace=True):
            n += 1
    teraz = ust("dane_pradu_od") or "2026-11-01"
    if lad and lad[0]["od"] < teraz:
        DB.ustaw("dane_pradu_od", lad[0]["od"])
    log("Import ładowań z ekranu auta:", n, "wpisów, prąd liczony od", ust("dane_pradu_od"))
    return {"ladowan": n, "prad_od": ust("dane_pradu_od")}


# ---------------------------------------------------------------- HTTP

TABELE = {"tankowania", "ladowania", "koszty", "terminy", "pojazdy", "odczyty"}
LICZBY = {"przebieg", "litry", "cena_l", "kwota", "kwh", "kwh_pv", "kwh_bateria", "soc_od", "soc_do", "koszt",
          "koszt_wartosc", "soc", "bak_l", "bateria_kwh", "l100_bez_pradu", "co_km", "nastepny_km", "ostatnio_km"}


def oczysc(tabela, j, nowy=True):
    d = {}
    for k, v in j.items():
        if k in ("id",):
            continue
        if k in LICZBY:
            v = None if v in (None, "") else float(str(v).replace(",", "."))
        d[k] = v
    if tabela == "tankowania":
        l, c, k = ob.uzupelnij_tankowanie(d.get("litry"), d.get("cena_l"), d.get("kwota"))
        d.update(litry=l, cena_l=c, kwota=k)
        if not l:
            raise ValueError("podaj litry (albo kwotę i cenę)")
    # Przy edycji puste pole daty zostawia datę z bazy (nie nadpisuje jej chwilą obecną).
    if tabela in ("tankowania", "koszty", "odczyty") and not d.get("data"):
        if nowy:
            d["data"] = teraz_lok().strftime("%Y-%m-%d %H:%M")
        else:
            d.pop("data", None)
    if tabela == "ladowania":
        if nowy:
            d.setdefault("zrodlo", "recznie")
        if not d.get("poczatek"):
            if nowy:
                d["poczatek"] = teraz_lok().strftime("%Y-%m-%d %H:%M")
            else:
                d.pop("poczatek", None)
    if tabela == "terminy" and "co_mies" in d:
        d["co_mies"] = int(d["co_mies"]) if d["co_mies"] not in (None, "") else None
    if "pojazd_id" in d and d["pojazd_id"] not in (None, ""):
        d["pojazd_id"] = int(d["pojazd_id"])
    return d


def propozycja_tankowania(j):
    """Tankowanie odczytane ze zdjęcia dystrybutora (Telegram): NIC nie zapisuje.
    Wejście: pojazd (klucz/id), litry, cena_l, kwota (dwie z trzech), opcjonalnie przebieg, stacja, pelny.
    Wynik: znormalizowane pola + ostrzeżenia + tekst do potwierdzenia."""
    p = pojazd_po_kluczu(j.get("pojazd")) if j.get("pojazd") not in (None, "") else None
    if not p:
        return {"ok": False, "powod": "pojazd", "pojazdy": [{"klucz": x["klucz"], "nazwa": x["nazwa"]}
                                                           for x in DB.lista("pojazdy") if x.get("aktywny", 1)]}
    def liczba(v):
        return None if v in (None, "") else float(str(v).replace(",", "."))
    l, c, k = ob.uzupelnij_tankowanie(liczba(j.get("litry")), liczba(j.get("cena_l")), liczba(j.get("kwota")))
    if not l:
        return {"ok": False, "powod": "litry"}
    uw = []
    tank = DB.lista("tankowania", pojazd_id=p["id"])
    ost = tank[0] if tank else {}
    if p.get("bak_l") and l > float(p["bak_l"]) * 1.02:
        uw.append("litry większe niż bak (%s l)" % p["bak_l"])
    podej = ob.podejrzana_kwota({"litry": l, "cena_l": liczba(j.get("cena_l")), "kwota": liczba(j.get("kwota"))})
    if podej:
        uw.append("kwota niezgodna z litrami × ceną (wychodzi %.2f zł)" % podej)
    if ost.get("cena_l") and c and abs(c - ost["cena_l"]) > 0.25 * ost["cena_l"]:
        uw.append("cena za litr daleko od poprzedniej (%.2f)" % ost["cena_l"])
    km = liczba(j.get("przebieg"))
    zrodlo_km = "ze zdjęcia" if km is not None else None
    if km is None and p.get("encja_przebiegu"):
        km, zrodlo_km = ha_liczba(p["encja_przebiegu"]), "z telemetrii"
    if km is None:
        km, zrodlo_km = przebieg_pojazdu(p)[0], "ostatni znany"
    if km is None:
        zrodlo_km = None
    d = {"pojazd_id": p["id"], "data": teraz_lok().strftime("%Y-%m-%d %H:%M"), "przebieg": km, "litry": l,
         "cena_l": c, "kwota": k, "pelny": 0 if j.get("pelny") in (0, False, "0", "nie") else 1,
         "stacja": j.get("stacja") or ost.get("stacja") or "", "zrodlo": "telegram"}
    w = sprawdz_przebieg("tankowania", d)
    if w:
        uw.append(w)
    tekst = "%s: %s l, %s zł/l, %s zł, przebieg %s%s, %s" % (
        p["nazwa"], ("%.2f" % l).replace(".", ","), ("%.2f" % c).replace(".", ",") if c else "?",
        ("%.2f" % k).replace(".", ",") if k else "?", "%d km" % km if km is not None else "brak",
        " (%s)" % zrodlo_km if zrodlo_km else "", "do pełna" if d["pelny"] else "nie do pełna")
    return {"ok": True, "pojazd": p["klucz"], "tankowanie": d, "ostrzezenia": uw, "tekst": tekst}


def zapisz_z_telegramu(j):
    """Zapis po potwierdzeniu. Klucz `uid` (np. id wiadomości) chroni przed podwójnym zapisem po drugim kliknięciu."""
    pr = propozycja_tankowania(j)
    if not pr["ok"]:
        return pr
    d = pr["tankowanie"]
    uid = j.get("uid")
    if uid:
        d["uid"] = "telegram:%s" % uid
        if DB.jest_uid("tankowania", d["uid"]):
            return {"ok": True, "duplikat": True, "tekst": pr["tekst"]}
    nid = DB.dodaj("tankowania", d)
    po_zmianie()
    return {"ok": True, "id": nid, "tekst": pr["tekst"], "ostrzezenia": pr["ostrzezenia"]}


def sprawdz_przebieg(tabela, d, id_=None):
    """Ostrzeżenie (nie błąd): przebieg mniejszy niż wcześniejszy odczyt."""
    if tabela != "tankowania" or d.get("przebieg") is None or not d.get("pojazd_id"):
        return None
    pts = [(x["data"], x["przebieg"]) for x in DB.lista("tankowania", pojazd_id=d["pojazd_id"])
           if x["id"] != id_ and x.get("przebieg") is not None and x["data"] < d["data"]]
    if pts and max(k for _, k in pts) > d["przebieg"]:
        return "Przebieg mniejszy niż przy wcześniejszym tankowaniu (%d km)." % max(k for _, k in pts)
    return None


class Strona(BaseHTTPRequestHandler):
    server_version = "Pojazdy/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str)
        if isinstance(body, str):
            body = body.encode("utf-8")
            if ctype.startswith(("application/json", "text/")):
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

    def ok_peer(self):
        if self.client_address[0] in PEERS_HA and urllib.parse.urlsplit(self.path).path.startswith("/api/telegram/"):
            return True
        if self.client_address[0] not in PEERS:
            self.send(403, {"blad": "tylko przez panel Home Assistant"})
            return False
        return True

    def body(self, limit=25 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("plik za duży")
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        if not self.ok_peer():
            return
        u = urllib.parse.urlsplit(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(WWW, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html")
            if path == "/api/start":
                poj = [p for p in DB.lista("pojazdy") if p.get("aktywny", 1)]
                ter = []
                karty = []
                for p in poj:
                    c = karta_pojazdu(p)
                    karty.append(c)
                    ter += stan_terminow(p, c["przebieg"])
                ter.sort(key=lambda s: (not s["pilne"], s["dni"] if s["dni"] is not None else 99999))
                pol = [dict(x, pojazd=c["nazwa"], pojazd_id=c["id"]) for c in karty for x in c["polisy"] if x["pilne"]]
                return self.send(200, {"pojazdy": karty, "terminy": ter[:3], "polisy": pol, "wersja": VERSION,
                                       "miesiac": teraz_lok().strftime("%Y-%m")})
            if path == "/api/historia":
                return self.send(200, historia(q.get("pojazd"), q.get("typ")))
            if path == "/api/statystyki":
                if q.get("pojazd") in (None, "", "wszystkie"):
                    poj = [p for p in DB.lista("pojazdy") if p.get("aktywny", 1)]
                    od, do = okres(q.get("okres") or "rok")
                    t, l, k, o = [], [], [], []
                    per = []
                    for p in poj:
                        a = dane_pojazdu(p["id"])
                        t += a[0]; l += a[1]; k += a[2]
                        s = ob.podsumowanie_okresu(*a, od, do)
                        per.append({"nazwa": p["nazwa"], "razem": s["razem"], "zl_km": s["zl_km"], "km": s["km"]})
                    razem = {"razem": round(sum(x["razem"] for x in per), 2), "km": sum(x["km"] for x in per)}
                    razem["zl_km"] = round(razem["razem"] / razem["km"], 3) if razem["km"] else None
                    return self.send(200, {"okres": q.get("okres") or "rok", "od": od, "do": do, "pojazdy": per,
                                           "podsumowanie": razem,
                                           "miesiace": ob.koszty_miesieczne(t, l, k, od[:7], ob.dodaj_miesiace(ob.d10(do), -1).isoformat()[:7])})
                p = DB.jeden("pojazdy", int(q["pojazd"]))
                return self.send(200, statystyki(p, q.get("okres") or "rok"))
            if path == "/api/terminy":
                out = []
                for p in DB.lista("pojazdy"):
                    km, _ = przebieg_pojazdu(p)
                    out += stan_terminow(p, km)
                out.sort(key=lambda s: (s["dni"] if s["dni"] is not None else 99999))
                return self.send(200, out)
            if path == "/api/polisy":
                out = []
                for p in DB.lista("pojazdy"):
                    out += polisy_pojazdu(p, wszystkie=q.get("wszystkie") == "1")
                for x in out:
                    x["biezaca"] = biezaca(x)
                out.sort(key=lambda x: (not x["biezaca"], not x["stan"]["pilne"], x["do"]))
                return self.send(200, out)
            m = re.match(r"^/api/polisy/(\d+)$", path)
            if m:
                p = DB.jeden("polisy", int(m.group(1)))
                return self.send(200 if p else 404, polisa_pelna(p) if p else {"blad": "nie ma"})
            if path == "/api/pojazdy":
                return self.send(200, DB.lista("pojazdy"))
            m = re.match(r"^/api/(tankowania|ladowania|koszty|terminy|odczyty)/(\d+)$", path)
            if m:
                w = DB.jeden(m.group(1), int(m.group(2)))
                return self.send(200 if w else 404, w or {"blad": "nie ma"})
            if path == "/api/ustawienia":
                return self.send(200, {k: ust(k) for k in DOMYSLNE} | {
                    "stan": {k: v for k, v in STAN.items() if k != "import"}, "wersja": VERSION,
                    "kopia_ostatnia": DB.ust("kopia_ostatnia"), "migracja_nt1100": DB.ust("migracja_nt1100")})
            if path == "/api/podpowiedzi":
                pid = int(q.get("pojazd") or 0)
                t = DB.lista("tankowania", pojazd_id=pid)
                p = DB.jeden("pojazdy", pid) or {}
                km, _ = przebieg_pojazdu(p) if p else (None, None)
                tel = ha_liczba(p.get("encja_przebiegu")) if p.get("encja_przebiegu") else None
                stacje = []
                for x in t:
                    if x.get("stacja") and x["stacja"] not in stacje:
                        stacje.append(x["stacja"])
                return self.send(200, {"cena_l": t[0]["cena_l"] if t else None, "stacja": t[0]["stacja"] if t else "",
                                       "przebieg": km, "telemetria": tel, "stacje": stacje[:8],
                                       "ostatnio_km": t[0]["przebieg"] if t else None, "teraz": teraz_lok().strftime("%Y-%m-%dT%H:%M")})
            if path == "/api/eksport":
                pid = int(q["pojazd"]) if q.get("pojazd") else None
                nazwa = "pojazdy-%s.fuelio" % teraz_lok().strftime("%Y-%m-%d")
                return self.send(200, eksport_fuelio(pid), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="%s"' % nazwa})
            return self.send(404, {"blad": "nie ma"})
        except Exception as e:
            traceback.print_exc()
            return self.send(500, {"blad": str(e)})

    def do_POST(self):
        if not self.ok_peer():
            return
        path = urllib.parse.urlsplit(self.path).path.rstrip("/")
        try:
            if path == "/api/import/podglad":
                nazwa = urllib.parse.unquote(self.headers.get("X-Nazwa-Pliku") or "")
                return self.send(200, import_podglad(self.body(), nazwa))
            j = json.loads(self.body(2 * 1024 * 1024) or b"{}")
            if path == "/api/import/zapisz":
                return self.send(200, import_zapisz(j.get("mapowanie") or {}, bool(j.get("popraw", True))))
            if path == "/api/ladowania/scal":
                w = scal_ladowania(bool(j.get("podglad", True)))
                if not j.get("podglad", True):
                    po_zmianie()
                return self.send(200, w)
            if path == "/api/ladowania/synchronizuj":
                n = synchronizuj_ladowania()
                po_zmianie()
                return self.send(200, {"dodane": n, "blad": STAN["sync_blad"]})
            if path == "/api/ustawienia":
                for k, v in j.items():
                    if k in DOMYSLNE:
                        DB.ustaw(k, v)
                po_zmianie()
                return self.send(200, {"ok": True})
            m = re.match(r"^/api/terminy/(\d+)/zrobione$", path)
            if m:
                t = DB.jeden("terminy", int(m.group(1)))
                p = DB.jeden("pojazdy", t["pojazd_id"])
                km = j.get("przebieg")
                km = float(km) if km not in (None, "") else przebieg_pojazdu(p)[0]
                data = (j.get("data") or teraz_lok().strftime("%Y-%m-%d"))[:10]
                zm = {"ostatnio_data": data, "ostatnio_km": km, "powiadomiono": ""}
                if not t.get("co_mies"):
                    zm["nastepny_data"] = j.get("nastepny_data") or None
                if not t.get("co_km"):
                    zm["nastepny_km"] = j.get("nastepny_km") or None
                DB.zmien("terminy", t["id"], zm)
                if j.get("kwota") not in (None, ""):
                    DB.dodaj("koszty", {"pojazd_id": p["id"], "data": data, "przebieg": km, "kategoria": t.get("kategoria") or "Serwis",
                                        "tytul": t["nazwa"], "kwota": float(str(j["kwota"]).replace(",", "."))})
                po_zmianie()
                return self.send(200, {"ok": True})
            m = re.match(r"^/api/polisy(?:/(\d+)(/usun|/odnow)?)?$", path)
            if m:
                id_ = int(m.group(1)) if m.group(1) else None
                if m.group(2) == "/usun":
                    usun_polise(id_)
                    nid = None
                elif m.group(2) == "/odnow":
                    nid = odnow_polise(id_)
                else:
                    nid = zapisz_polise(j, id_)
                po_zmianie()
                return self.send(200, {"ok": True, "id": nid})
            m = re.match(r"^/api/raty/(\d+)/zaplac$", path)
            if m:
                zaplac_rate(int(m.group(1)), j.get("data"), bool(j.get("cofnij")))
                po_zmianie()
                return self.send(200, {"ok": True})
            if path == "/api/telegram/propozycja":
                return self.send(200, propozycja_tankowania(j))
            if path == "/api/telegram/zapisz":
                return self.send(200, zapisz_z_telegramu(j))
            m = re.match(r"^/api/(tankowania|ladowania|koszty|terminy|pojazdy|odczyty)(?:/(\d+)(/usun)?)?$", path)
            if m:
                tab, id_, usun = m.group(1), m.group(2), m.group(3)
                if usun:
                    DB.usun(tab, int(id_))
                    po_zmianie()
                    return self.send(200, {"ok": True})
                d = oczysc(tab, j, nowy=not id_)
                if tab == "ladowania" and id_:
                    d["zmienione"] = 1
                uwaga = sprawdz_przebieg(tab, dict(DB.jeden(tab, int(id_)) or {}, **d) if id_ else d, int(id_) if id_ else None)
                if id_:
                    DB.zmien(tab, int(id_), d)
                    nid = int(id_)
                else:
                    nid = DB.dodaj(tab, d)
                po_zmianie()
                return self.send(200, {"ok": True, "id": nid, "uwaga": uwaga})
            return self.send(404, {"blad": "nie ma"})
        except (ValueError, KeyError, TypeError) as e:
            return self.send(400, {"blad": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self.send(500, {"blad": str(e)})


def uruchom():
    global DB
    os.makedirs(DATA, exist_ok=True)
    DB = bz.Baza(os.path.join(DATA, "pojazdy.db"))
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Strona)
    srv.daemon_threads = True
    return srv


def main():
    srv = uruchom()
    log("Pojazdy %s – panel na porcie %d, klucz do HA: %s" % (VERSION, srv.server_address[1], "jest" if TOKEN else "BRAK"))
    if PETLA:
        threading.Thread(target=petla, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
