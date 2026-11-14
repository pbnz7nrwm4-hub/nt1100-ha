"""Pojazdy: opony – komplety, wymiany i przebieg liczony z odczytów licznika (bez Home Assistant).

Adrian wpisuje komplety i tylko daty wymian. Przebieg każdego kompletu liczy się z odczytów, które Pojazdy już mają
(tankowania, koszty, ręczne odczyty, telemetria, ładowania). Gdy w dniu wymiany nie ma odczytu, przebieg jest liczony
liniowo między najbliższym odczytem przed i po (znaczek „≈”).
Osie: auto = „komplet”; motocykl = „przod” i „tyl” osobno (zużywają się inaczej).
"""

from datetime import date

RODZAJE = {"zimowe": "zimowe", "letnie": "letnie", "caloroczne": "całoroczne", "opony": "opony"}
OSIE = {"komplet": "komplet", "przod": "przód", "tyl": "tył"}
# Bieżnik, przy którym poradniki zalecają wymianę zimówek (auto-świat, ok. 4 mm); dla pozostałych minimum prawne 1,6 mm.
BIEZNIK_MIN = {"zimowe": 4.0}
BIEZNIK_PRAWNY = 1.6
# Próg temperatury dla podpowiedzi o wymianie: zalecenie PZPO (7 °C). To tylko podpowiedź, nie termin.
TEMP_PROG = 7.0
DNI_NA_ZIMOWE = 3
DNI_NA_LETNIE = 7

ZRODLA = {"tankowania": "tankowanie", "koszty": "koszt", "odczyty": "odczyt", "telemetria": "telemetria",
          "ladowania": "ładowanie", "wymiana": "wpisany przy wymianie"}


def d10(s):
    a, b, c = str(s)[:10].split("-")
    return date(int(a), int(b), int(c))


def punkty(tankowania, koszty, odczyty, ladowania=()):
    """Odczyty licznika ze źródłem: [(„RRRR-MM-DD GG:MM”, km, źródło)] posortowane."""
    pts = []
    for nazwa, src in (("tankowania", tankowania), ("koszty", koszty), ("odczyty", odczyty), ("ladowania", ladowania)):
        for x in src:
            km = x.get("przebieg")
            d = x.get("data") or x.get("poczatek")
            if km in (None, "") or not d:
                continue
            zr = "telemetria" if nazwa == "odczyty" and x.get("zrodlo") == "telemetria" else nazwa
            pts.append((str(d).replace("T", " ")[:16], float(km), ZRODLA[zr]))
    pts.sort()
    return pts


def _dzien(s):
    return d10(s).toordinal()


def km_w_dniu(pts, dzien, koniec_dnia=False):
    """Przebieg w danym dniu: {"km", "dokladny", "opis"} albo None (brak odczytów).
    Odczyt z tego dnia = dokładny (dla początku dnia najmniejszy, dla końca największy). Inaczej liniowo między
    najbliższymi odczytami przed i po; tylko z jednej strony = najbliższy odczyt (też „≈”)."""
    if not pts:
        return None
    dz = str(dzien)[:10]
    tego = [p for p in pts if p[0][:10] == dz]
    if tego:
        p = max(tego, key=lambda x: x[1]) if koniec_dnia else min(tego, key=lambda x: x[1])
        return {"km": p[1], "dokladny": True, "opis": "%s %s" % (p[2], _krotko(p[0]))}
    przed = [p for p in pts if p[0][:10] < dz]
    po = [p for p in pts if p[0][:10] > dz]
    if przed and po:
        a, b = przed[-1], po[0]
        da, db, dx = _dzien(a[0]), _dzien(b[0]), _dzien(dz)
        km = a[1] + (b[1] - a[1]) * (dx - da) / float(db - da) if db > da else a[1]
        return {"km": round(km), "dokladny": False,
                "opis": "odczyty: %s %s i %s %s" % (a[2], _krotko(a[0]), b[2], _krotko(b[0]))}
    p = przed[-1] if przed else po[0]
    return {"km": p[1], "dokladny": False, "opis": "najbliższy odczyt: %s %s" % (p[2], _krotko(p[0]))}


def _krotko(s):
    d = d10(s)
    return "%d.%02d.%d" % (d.day, d.month, d.year)


def sezony(wymiany, opona_id, pts, dzis, km_teraz=None):
    """Okresy, w których komplet był na pojeździe: [{"od", "do" (None = nadal), "km", "dokladny", "opis_od", "opis_do"}].
    `wymiany`: lista wymian pojazdu [{"id","data","os","opona_id","przebieg"}]; komplet schodzi z osi przy następnej
    wymianie na tej samej osi (albo przy wymianie, która go zdejmuje: zdjeta_id)."""
    w = sorted(wymiany, key=lambda x: (x["data"], x.get("id") or 0))
    out = []
    for i, x in enumerate(w):
        if x.get("opona_id") != opona_id:
            continue
        os_ = x.get("os") or "komplet"
        kon = None
        for y in w[i + 1:]:
            if (y.get("os") or "komplet") == os_ or y.get("zdjeta_id") == opona_id:
                kon = y
                break
        a = _km_wymiany(x, pts)
        if kon:
            b = _km_wymiany(kon, pts)
        elif km_teraz is not None:
            b = {"km": float(km_teraz), "dokladny": True, "opis": "licznik teraz"}
        else:
            b = km_w_dniu(pts, dzis, koniec_dnia=True)
        km = None
        if a and b:
            km = max(0.0, b["km"] - a["km"])
        out.append({"od": x["data"][:10], "do": kon["data"][:10] if kon else None, "os": os_,
                    "km": None if km is None else round(km),
                    "dokladny": bool(a and b and a["dokladny"] and b["dokladny"]),
                    "km_od": a["km"] if a else None, "km_do": b["km"] if b else None,
                    "opis_od": a["opis"] if a else "brak odczytów", "opis_do": b["opis"] if b else "brak odczytów",
                    "wymiana_id": x.get("id")})
    return out


def _km_wymiany(x, pts):
    if x.get("przebieg") not in (None, ""):
        return {"km": float(x["przebieg"]), "dokladny": True, "opis": "wpisany przy wymianie"}
    return km_w_dniu(pts, x["data"])


def pomiary_bieznika(wymiany, opona_id):
    """[(data, mm)] z wymian: bieżnik zakładanych i zdejmowanych."""
    out = []
    for x in wymiany:
        if x.get("opona_id") == opona_id and x.get("bieznik_zakl") not in (None, ""):
            out.append((x["data"][:10], float(x["bieznik_zakl"])))
        if x.get("zdjeta_id") == opona_id and x.get("bieznik_zdjm") not in (None, ""):
            out.append((x["data"][:10], float(x["bieznik_zdjm"])))
    out.sort()
    return out


def km_kompletu_do(sez, dzien):
    """Łączne km kompletu do danego dnia (z sezonów, część bieżącego sezonu liczona proporcjonalnie po dniach)."""
    dz = str(dzien)[:10]
    km = 0.0
    for s in sez:
        if s["km"] is None or s["od"] >= dz:
            continue
        if s["do"] and s["do"] <= dz:
            km += s["km"]
        else:
            # pomiar w trakcie sezonu (np. przy zdjęciu w dniu wymiany) – do tego dnia
            do = s["do"] or dz
            dni = max(1, (d10(do) - d10(s["od"])).days)
            km += s["km"] * min(1.0, (d10(dz) - d10(s["od"])).days / float(dni))
    return km


def zuzycie_bieznika(sez, pomiary, rodzaj, km_sezonu=None):
    """Spadek bieżnika na 1000 km i ile zostało do minimum (prognoza liniowa). None, gdy za mało pomiarów."""
    if len(pomiary) < 2:
        return None
    (d1, m1), (d2, m2) = pomiary[0], pomiary[-1]
    k1, k2 = km_kompletu_do(sez, d1), km_kompletu_do(sez, d2)
    dk = k2 - k1
    spadek = m1 - m2
    mn = BIEZNIK_MIN.get(rodzaj, BIEZNIK_PRAWNY)
    out = {"od": d1, "do": d2, "mm_od": m1, "mm_do": m2, "km": round(dk), "minimum": mn,
           "minimum_zrodlo": "poradniki: ok. 4 mm dla zimowych" if rodzaj in BIEZNIK_MIN else "minimum prawne 1,6 mm",
           "mm_na_1000": None, "km_zostalo": None, "sezonow_zostalo": None}
    if dk < 300 or spadek <= 0:
        return out
    na1000 = spadek / dk * 1000
    out["mm_na_1000"] = round(na1000, 3)
    zost = max(0.0, (m2 - mn) / na1000 * 1000)
    out["km_zostalo"] = round(zost)
    if km_sezonu:
        out["sezonow_zostalo"] = round(zost / km_sezonu, 1)
    return out


def podpowiedz_wymiany(rodzaj_na_pojezdzie, dobowe, w_garazu):
    """Podpowiedź z termometru na dworze. `dobowe`: [(dzień, średnia °C)] pełnych dni, od najstarszego.
    Zwraca {"na": "zimowe"|"letnie", "dni", "srednia"} albo None."""
    if rodzaj_na_pojezdzie == "letnie" and "zimowe" in w_garazu and len(dobowe) >= DNI_NA_ZIMOWE:
        ost = dobowe[-DNI_NA_ZIMOWE:]
        if all(t < TEMP_PROG for _, t in ost):
            return {"na": "zimowe", "dni": DNI_NA_ZIMOWE, "srednia": round(sum(t for _, t in ost) / len(ost), 1)}
    if rodzaj_na_pojezdzie == "zimowe" and "letnie" in w_garazu and len(dobowe) >= DNI_NA_LETNIE:
        ost = dobowe[-DNI_NA_LETNIE:]
        if all(t > TEMP_PROG for _, t in ost):
            return {"na": "letnie", "dni": DNI_NA_LETNIE, "srednia": round(sum(t for _, t in ost) / len(ost), 1)}
    return None


def srednie_dobowe(stany, dzis):
    """Stany z historii HA [{"state","last_changed"}] -> [(dzień, średnia)] pełnych dni przed `dzis` (czas lokalny
    już w polu „lok”, jeśli podany; inaczej pierwsze 10 znaków last_changed)."""
    dni = {}
    for s in stany:
        try:
            v = float(s.get("state"))
        except (TypeError, ValueError):
            continue
        d = (s.get("lok") or s.get("last_changed") or s.get("last_updated") or "")[:10]
        if not d or d >= str(dzis)[:10]:
            continue
        dni.setdefault(d, []).append(v)
    return [(d, sum(v) / len(v)) for d, v in sorted(dni.items()) if len(v) >= 3]
