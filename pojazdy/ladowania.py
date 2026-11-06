"""Pojazdy: ładowania auta z historii Home Assistant (bez sieci – dane wchodzą gotowe).

Z liczników energii ładowarek (rosnące kWh) wycinamy sesje: przyrosty, między
którymi przerwa nie przekracza PRZERWA_MIN. Energia każdej sesji dzieli się na
godziny; dla każdej godziny:
  * strefa G13 (Tauron) liczona tu, tak samo jak sensor.g13_strefa w HA,
  * część z PV: bilans godzinowy domu (pobrane − oddane z liczników sieci);
    gdy dom w tej godzinie więcej oddał niż pobrał, ładowanie szło z nadwyżki.
    Ostrożnie: cały pobór z sieci w danej godzinie przypisujemy najpierw autu,
  * koszt = kWh z sieci × cena strefy; kWh z PV za 0 zł,
  * druga wycena: kWh × "Wartość kWh" (sensor.wartosc_kwh – z magazynem net-meteringu).
"""

from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PL = ZoneInfo("Europe/Warsaw")
except Exception:  # bez bazy stref czasowych – czas lokalny systemu
    PL = None

PRZERWA_MIN = 20       # dłuższa przerwa w przyroście = nowa sesja
MIN_KWH = 0.1          # mniejsze "sesje" to szum licznika
KONIEC_PO_MIN = 15     # sesja uznana za skończoną po tylu minutach bez przyrostu


def do_utc(lokalny):
    """datetime lokalny (Polska, bez strefy) -> UTC."""
    if PL is not None:
        return lokalny.replace(tzinfo=PL).astimezone(timezone.utc)
    return datetime.fromtimestamp(lokalny.timestamp(), timezone.utc)


def lok(dt):
    """datetime UTC -> lokalny (Polska), bez strefy."""
    if PL is not None:
        return dt.astimezone(PL).replace(tzinfo=None)
    import time
    return datetime.fromtimestamp(dt.timestamp())


def utc(s):
    """Czas z HA ("2026-11-05T21:10:03.12+00:00") -> datetime UTC."""
    s = s.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        d = datetime.fromisoformat(s[:19])
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def wielkanoc(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mies = (h + l - 7 * m + 114) // 31
    dz = ((h + l - 7 * m + 114) % 31) + 1
    return date(y, mies, dz)


STALE = {"01-01", "01-06", "05-01", "05-03", "08-15", "11-01", "11-11", "12-24", "12-25", "12-26"}


def strefa_g13(d):
    """Strefa Tauron G13 dla lokalnej chwili d: przedpoludnie / popoludnie / pozostale."""
    e = wielkanoc(d.year)
    swieto = d.strftime("%m-%d") in STALE or d.date() in (e + timedelta(days=1), e + timedelta(days=60))
    if d.weekday() >= 5 or swieto:
        return "pozostale"
    lato = d.month in (4, 5, 6, 7, 8, 9)
    od, do = (19, 22) if lato else (16, 21)
    if 7 <= d.hour < 13:
        return "przedpoludnie"
    if od <= d.hour < do:
        return "popoludnie"
    return "pozostale"


def seria(historia):
    """Lista stanów z API historii -> [(datetime UTC, float)] (bez 'unavailable')."""
    out = []
    for s in historia or []:
        try:
            v = float(s.get("state"))
        except (TypeError, ValueError):
            continue
        t = s.get("last_changed") or s.get("last_updated")
        if t:
            out.append((utc(t), v))
    out.sort(key=lambda x: x[0])
    return out


def wartosc_w(ser, t):
    """Ostatnia wartość nie później niż t (None, gdy brak)."""
    v = None
    for ts, x in ser:
        if ts <= t:
            v = x
        else:
            break
    return v


def przyrosty(ser):
    """Przyrosty licznika [(czas, kWh)] – spadki (zerowanie) pomijane."""
    out = []
    for (t0, a), (t1, b) in zip(ser, ser[1:]):
        d = b - a
        if 0 < d < 50:
            out.append((t0, t1, d))
    return out


def sesje(ser, teraz, przerwa_min=PRZERWA_MIN, min_kwh=MIN_KWH, koniec_po_min=KONIEC_PO_MIN):
    """Sesje z licznika: [{"start","koniec","kwh","godziny":{godzina_UTC: kWh},"skonczona"}]."""
    out = []
    cur = None
    for t0, t1, d in przyrosty(ser):
        if cur is None or (t0 - cur["koniec"]).total_seconds() > przerwa_min * 60:
            if cur:
                out.append(cur)
            cur = {"start": t0, "koniec": t1, "kwh": 0.0, "godziny": {}}
        cur["koniec"] = t1
        cur["kwh"] += d
        # przyrost dzielony proporcjonalnie na godziny, przez które przechodzi odcinek
        _rozdziel(cur["godziny"], t0, t1, d)
    if cur:
        out.append(cur)
    for s in out:
        s["skonczona"] = (teraz - s["koniec"]).total_seconds() > koniec_po_min * 60
        s["kwh"] = round(s["kwh"], 3)
    return [s for s in out if s["kwh"] >= min_kwh]


def _rozdziel(godziny, t0, t1, kwh):
    sek = (t1 - t0).total_seconds()
    if sek <= 0:
        h = t1.replace(minute=0, second=0, microsecond=0)
        godziny[h] = godziny.get(h, 0.0) + kwh
        return
    t = t0
    while t < t1:
        h = t.replace(minute=0, second=0, microsecond=0)
        nast = min(t1, h + timedelta(hours=1))
        godziny[h] = godziny.get(h, 0.0) + kwh * (nast - t).total_seconds() / sek
        t = nast


def bilans_godziny(pobrana, oddana, h):
    """Netto z sieci w godzinie h (UTC): >0 pobór, <0 oddanie. None bez danych."""
    a0, a1 = wartosc_w(pobrana, h), wartosc_w(pobrana, h + timedelta(hours=1))
    b0, b1 = wartosc_w(oddana, h), wartosc_w(oddana, h + timedelta(hours=1))
    if None in (a0, a1, b0, b1):
        return None
    return (a1 - a0) - (b1 - b0)


def srednia_w_godzinie(ser, h):
    pts = [v for t, v in ser if h <= t < h + timedelta(hours=1)]
    if pts:
        return sum(pts) / len(pts)
    return wartosc_w(ser, h)


def wycen(sesja, ceny, pobrana=(), oddana=(), wartosc=(), wartosc_teraz=None):
    """Koszt sesji godzina po godzinie. ceny = {"przedpoludnie":zł, "popoludnie":zł, "pozostale":zł}."""
    strefy = {"przedpoludnie": 0.0, "popoludnie": 0.0, "pozostale": 0.0}
    pv = koszt = koszt_w = 0.0
    bez_bilansu = False
    for h, kwh in sorted(sesja["godziny"].items()):
        st = strefa_g13(lok(h))
        netto = bilans_godziny(pobrana, oddana, h) if pobrana and oddana else None
        if netto is None:
            z_sieci = kwh
            bez_bilansu = True
        else:
            z_sieci = min(kwh, max(0.0, netto))
        z_pv = kwh - z_sieci
        pv += z_pv
        strefy[st] += z_sieci
        koszt += z_sieci * float(ceny.get(st) or 0)
        w = srednia_w_godzinie(wartosc, h) if wartosc else None
        if w is None:
            w = wartosc_teraz
        if w is not None:
            koszt_w += kwh * float(w)
    return {"kwh_pv": round(pv, 3), "strefy": {k: round(v, 3) for k, v in strefy.items()},
            "koszt": round(koszt, 2), "koszt_wartosc": round(koszt_w, 2) if (wartosc or wartosc_teraz is not None) else None,
            "bez_bilansu": bez_bilansu}


def soc(bateria, start, koniec):
    """% baterii przed (ostatni odczyt przed startem) i po (najwyższy do 1 h po końcu)."""
    s0 = wartosc_w(bateria, start)
    po = [v for t, v in bateria if start <= t <= koniec + timedelta(hours=1)]
    s1 = max(po) if po else None
    return s0, s1


def do_wiersza(sesja, miejsce, pojazd_id, wyc, soc_od=None, soc_do=None, bateria_kwh=None):
    """Wiersz tabeli ladowania z policzonej sesji."""
    kwh_b = None
    if soc_od is not None and soc_do is not None and bateria_kwh and soc_do > soc_od:
        kwh_b = round((soc_do - soc_od) / 100.0 * float(bateria_kwh), 2)
    p, k = lok(sesja["start"]), lok(sesja["koniec"])
    return {
        "pojazd_id": pojazd_id, "poczatek": p.strftime("%Y-%m-%d %H:%M"), "koniec": k.strftime("%Y-%m-%d %H:%M"),
        "kwh": round(sesja["kwh"], 2), "kwh_pv": round(wyc["kwh_pv"], 2), "kwh_bateria": kwh_b,
        "soc_od": soc_od, "soc_do": soc_do, "koszt": wyc["koszt"], "koszt_wartosc": wyc["koszt_wartosc"],
        "strefy": wyc["strefy"], "miejsce": miejsce, "zrodlo": "auto",
        "uid": "auto:%s:%s" % (miejsce, sesja["start"].strftime("%Y%m%dT%H%M")),
    }
