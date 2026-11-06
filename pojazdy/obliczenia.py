"""Pojazdy: obliczenia bez bazy i bez sieci (spalanie, koszty, terminy).

Wejście to zwykłe słowniki (wiersze z bazy), więc wszystko da się łatwo testować.
Daty: tekst "RRRR-MM-DD GG:MM" (czas lokalny) albo "RRRR-MM-DD".
"""

from datetime import date, datetime, timedelta


def d10(s):
    """Data (bez godziny) z tekstu."""
    return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()


def dt16(s):
    s = (s or "").replace("T", " ")
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(s[:10], "%Y-%m-%d")


def r(v, n=2):
    return None if v is None else round(float(v), n)


def kwota_tankowania(t):
    """Kwota tankowania: wpisana, a gdy brak – litry × cena."""
    k = t.get("kwota")
    if k:
        return float(k)
    if t.get("litry") and t.get("cena_l"):
        return float(t["litry"]) * float(t["cena_l"])
    return 0.0


def uzupelnij_tankowanie(litry=None, cena_l=None, kwota=None):
    """Dwie z trzech wartości wystarczą – trzecia liczy się sama."""
    l, c, k = [None if v in (None, "") else float(v) for v in (litry, cena_l, kwota)]
    if l and c and not k:
        k = l * c
    elif l and k and not c:
        c = k / l
    elif c and k and not l:
        l = k / c
    return (r(l, 2), r(c, 3), r(k, 2))


def podejrzana_kwota(t):
    """Kwota niezgodna z litrami × ceną (np. literówka 1556,24 zamiast 118,78)."""
    l, c, k = t.get("litry"), t.get("cena_l"), t.get("kwota")
    if not (l and c and k):
        return None
    wyliczona = float(l) * float(c)
    if abs(float(k) - wyliczona) > max(2.0, 0.05 * wyliczona):
        return round(wyliczona, 2)
    return None


def _klucz(t):
    return (float(t.get("przebieg") or 0), t.get("data") or "", t.get("id") or 0)


def _dt(s):
    s = (s or "").replace("T", " ").strip()
    return datetime.strptime(s[:16], "%Y-%m-%d %H:%M") if len(s) >= 16 else datetime.strptime(s[:10], "%Y-%m-%d")


def czesc_okresu(l, od, do):
    """Ładowanie zapisane za okres (zrodlo "ekran_auta", np. cały miesiąc): jaka jego część
    przypada na czas od–do (0..1). None = zwykłe ładowanie (liczone w chwili początku)."""
    if l.get("zrodlo") != "ekran_auta" or not l.get("koniec"):
        return None
    a, b = _dt(l["poczatek"]), _dt(l["koniec"]) + timedelta(minutes=1)
    x, y = max(a, _dt(od)), min(b, _dt(do))
    if b <= a or y <= x:
        return 0.0
    return (y - x).total_seconds() / (b - a).total_seconds()


def odcinki(tankowania, ladowania=None, prad_od=None):
    """Odcinki "od pełnego do pełnego baku" (jak Fuelio).

    Litry niepełnych tankowań dolicza się do najbliższego pełnego. Tankowanie
    oznaczone "pominąłem poprzednie" przerywa liczenie (nowy początek).
    Dla aut z wtyczką: kWh ładowań między datami początku i końca odcinka.
    Odcinki zaczęte przed `prad_od` (zanim HA zaczął zapisywać ładowania) nie mają
    kWh (None) – inaczej zużycie prądu wyszłoby zaniżone.
    """
    tk = sorted([t for t in tankowania if t.get("przebieg") is not None], key=_klucz)
    out = []
    start = None
    litry = koszt = 0.0
    for t in tk:
        if t.get("pominiete"):
            start, litry, koszt = (t if t.get("pelny") else None), 0.0, 0.0
            continue
        if start is None:
            if t.get("pelny"):
                start, litry, koszt = t, 0.0, 0.0
            continue
        litry += float(t.get("litry") or 0)
        koszt += kwota_tankowania(t)
        if t.get("pelny"):
            km = float(t["przebieg"]) - float(start["przebieg"])
            if km > 0 and litry > 0:
                o = {"od": start["data"], "do": t["data"], "od_km": float(start["przebieg"]),
                     "do_km": float(t["przebieg"]), "km": km, "litry": round(litry, 2),
                     "koszt_paliwa": round(koszt, 2), "l100": round(litry / km * 100, 2),
                     "tankowanie_id": t.get("id")}
                out.append(o)
            start, litry, koszt = t, 0.0, 0.0
    if ladowania is not None:
        for o in out:
            if prad_od and o["od"][:10] < prad_od:
                o.update(kwh=None, kwh100=None, koszt_pradu=None, ladowan=None,
                         zl100=round(o["koszt_paliwa"] / o["km"] * 100, 2))
                continue
            kwh = kw = kwb = 0.0
            ile = 0
            for l in ladowania:
                if l.get("wykluczone"):
                    continue
                cz = czesc_okresu(l, o["od"], o["do"])
                if cz is not None:
                    # ładowanie za okres (np. miesiąc z ekranu auta): część proporcjonalna do dni w odcinku
                    if cz > 0:
                        kwh += float(l.get("kwh") or 0) * cz
                        kw += float(l.get("koszt") or 0) * cz
                        kwb += float(l.get("kwh_bateria") or 0) * cz
                        ile += 1
                    continue
                p = (l.get("poczatek") or "").replace("T", " ")[:16]
                if o["od"][:16] <= p < o["do"][:16] or (len(o["do"]) <= 10 and o["od"][:10] <= p[:10] < o["do"][:10]):
                    kwh += float(l.get("kwh") or 0)
                    kw += float(l.get("koszt") or 0)
                    kwb += float(l.get("kwh_bateria") or 0)
                    ile += 1
            o["kwh"] = round(kwh, 2)
            o["kwh100"] = round(kwh / o["km"] * 100, 2)
            o["koszt_pradu"] = round(kw, 2)
            o["ladowan"] = ile
            o["zl100"] = round((o["koszt_paliwa"] + kw) / o["km"] * 100, 2)
    else:
        for o in out:
            o["zl100"] = round(o["koszt_paliwa"] / o["km"] * 100, 2)
    return out


def srednie(odc, ile=None):
    """Średnie z ostatnich `ile` odcinków (None = wszystkie), ważone kilometrami."""
    o = odc[-ile:] if ile else odc
    km = sum(x["km"] for x in o)
    if km <= 0:
        return {"km": 0, "l100": None, "kwh100": None, "zl100": None}
    litry = sum(x["litry"] for x in o)
    kp = sum(x["koszt_paliwa"] for x in o)
    out = {"km": round(km), "l100": round(litry / km * 100, 2), "litry": round(litry, 2)}
    if o and "kwh" in o[0]:
        # prąd i łączny koszt tylko z odcinków, dla których znamy ładowania
        z = [x for x in o if x.get("kwh") is not None]
        kmz = sum(x["km"] for x in z)
        if kmz > 0:
            kwh = sum(x["kwh"] for x in z)
            kpr = sum(x["koszt_pradu"] for x in z)
            kpz = sum(x["koszt_paliwa"] for x in z)
            out.update(kwh100=round(kwh / kmz * 100, 2), kwh=round(kwh, 2), km_prad=round(kmz),
                       zl100=round((kpz + kpr) / kmz * 100, 2), zl100_paliwo=round(kpz / kmz * 100, 2),
                       zl100_prad=round(kpr / kmz * 100, 2))
        else:
            out.update(kwh100=None, km_prad=0, zl100=round(kp / km * 100, 2), zl100_bez_pradu=True)
    else:
        out.update(kwh100=None, zl100=round(kp / km * 100, 2))
    return out


def miesiac(s):
    return (s or "")[:7]


def koszty_miesieczne(tankowania, ladowania, koszty, od=None, do=None):
    """{"RRRR-MM": {"paliwo": zł, "prad": zł, "inne": zł, "razem": zł}} posortowane."""
    m = {}

    def dodaj(mies, k, v):
        if not mies or (od and mies < od) or (do and mies > do):
            return
        x = m.setdefault(mies, {"paliwo": 0.0, "prad": 0.0, "inne": 0.0})
        x[k] += float(v or 0)

    for t in tankowania:
        dodaj(miesiac(t.get("data")), "paliwo", kwota_tankowania(t))
    for l in ladowania:
        if not l.get("wykluczone"):
            dodaj(miesiac(l.get("poczatek")), "prad", l.get("koszt"))
    for k in koszty:
        dodaj(miesiac(k.get("data")), "inne", k.get("kwota"))
    out = {}
    for k in sorted(m):
        x = {a: round(b, 2) for a, b in m[k].items()}
        x["razem"] = round(sum(m[k].values()), 2)
        out[k] = x
    return out


def przebiegi(tankowania, koszty, odczyty, ladowania=()):
    """Wszystkie znane odczyty licznika: [(data, km)] posortowane po dacie."""
    pts = []
    for src in (tankowania, koszty, odczyty, ladowania):
        for x in src:
            km = x.get("przebieg")
            d = x.get("data") or x.get("poczatek")
            if km not in (None, "") and d:
                pts.append(((d or "").replace("T", " ")[:16], float(km)))
    pts.sort()
    return pts


def przebieg_teraz(pts, z_encji=None):
    vals = [k for _, k in pts]
    if z_encji is not None:
        vals.append(float(z_encji))
    return max(vals) if vals else None


def km_w_okresie(pts, od, do):
    """Przejechane km między datami (od włącznie, do wyłącznie): różnica licznika
    od ostatniego odczytu przed okresem (albo pierwszego w okresie) do ostatniego w okresie."""
    przed = [k for d, k in pts if d[:10] < od]
    w = [k for d, k in pts if od <= d[:10] < do]
    if not w:
        return 0.0
    start = max(przed) if przed else min(w)
    return max(0.0, max(w) - start)


def podsumowanie_okresu(tankowania, ladowania, koszty, odczyty, od, do):
    t = [x for x in tankowania if od <= (x.get("data") or "")[:10] < do]
    l = [x for x in ladowania if not x.get("wykluczone") and od <= (x.get("poczatek") or "")[:10] < do]
    k = [x for x in koszty if od <= (x.get("data") or "")[:10] < do]
    paliwo = sum(kwota_tankowania(x) for x in t)
    prad = sum(float(x.get("koszt") or 0) for x in l)
    inne = sum(float(x.get("kwota") or 0) for x in k)
    km = km_w_okresie(przebiegi(tankowania, koszty, odczyty), od, do)
    razem = paliwo + prad + inne
    return {"od": od, "do": do, "paliwo": round(paliwo, 2), "prad": round(prad, 2), "inne": round(inne, 2),
            "razem": round(razem, 2), "km": round(km), "zl_km": round(razem / km, 3) if km > 0 else None,
            "litry": round(sum(float(x.get("litry") or 0) for x in t), 2),
            "kwh": round(sum(float(x.get("kwh") or 0) for x in l), 2),
            "tankowan": len(t), "ladowan": len(l), "kosztow": len(k)}


def dodaj_miesiace(d, n):
    y, m = d.year, d.month - 1 + int(n)
    y += m // 12
    m = m % 12 + 1
    dni = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(y, m, min(d.day, dni[m - 1]))


def nastepny_termin(t):
    """(data, km) następnego terminu z ostatniego wykonania i okresu."""
    nd = t.get("nastepny_data") or None
    nk = t.get("nastepny_km")
    if t.get("co_mies") and t.get("ostatnio_data"):
        nd = dodaj_miesiace(d10(t["ostatnio_data"]), t["co_mies"]).isoformat()
    if t.get("co_km") and t.get("ostatnio_km") is not None:
        nk = float(t["ostatnio_km"]) + float(t["co_km"])
    return nd, (None if nk in (None, "") else float(nk))


def stan_terminu(t, dzis, km_teraz, prog_dni=30, prog_km=500):
    nd, nk = nastepny_termin(t)
    dni = (d10(nd) - dzis).days if nd else None
    km = (nk - km_teraz) if (nk is not None and km_teraz is not None) else None
    pilne = (dni is not None and dni <= prog_dni) or (km is not None and km <= prog_km)
    po = (dni is not None and dni < 0) or (km is not None and km < 0)
    # postęp 0..1 (ile okresu minęło) – do paska
    postep = None
    if dni is not None and t.get("co_mies"):
        okres = max(1, int(t["co_mies"]) * 30.4)
        postep = min(1.0, max(0.0, 1 - dni / okres))
    if km is not None and t.get("co_km"):
        pk = min(1.0, max(0.0, 1 - km / float(t["co_km"])))
        postep = pk if postep is None else max(postep, pk)
    if postep is None and dni is not None:
        postep = min(1.0, max(0.0, 1 - dni / 365.0))
    return {"nastepny_data": nd, "nastepny_km": nk, "dni": dni, "km": None if km is None else round(km),
            "pilne": bool(pilne), "po_terminie": bool(po), "postep": None if postep is None else round(postep, 3)}


def opis_terminu(s):
    """Krótki tekst: "za 12 dni", "za 460 km", "3 dni po terminie"."""
    cz = []
    if s.get("dni") is not None:
        d = s["dni"]
        cz.append("dziś" if d == 0 else ("za %d dni" % d if d > 1 else ("jutro" if d == 1 else "%d dni po terminie" % -d)))
    if s.get("km") is not None:
        k = s["km"]
        cz.append("za %d km" % k if k >= 0 else "%d km po terminie" % -k)
    if len(cz) == 2:
        # pokazuj to, co bliżej (dni przeliczone ~ km nie mają wspólnej miary – bierzemy pilniejsze)
        if s.get("km") is not None and s["km"] < 0:
            return cz[1]
        if s.get("dni") is not None and s["dni"] < 0:
            return cz[0]
        return cz[0] + " lub " + cz[1]
    return cz[0] if cz else "bez terminu"


def ktore_powiadomienie(s, prog_dni=(30, 7, 1, 0), prog_km=(500, 100, 0)):
    """Najmniejszy przekroczony próg (do jednorazowych powiadomień)."""
    out = None
    if s.get("dni") is not None:
        for p in sorted(prog_dni):
            if s["dni"] <= p:
                out = "d%d" % p
                break
    if s.get("km") is not None:
        for p in sorted(prog_km):
            if s["km"] <= p:
                out = (out + "|" if out else "") + "k%d" % p
                break
    return out


def porownanie_benzyna(odc, l100_bez_pradu, cena_l=None):
    """PHEV: ile kosztowałyby te same km na samej benzynie (spalanie z ustawień)."""
    km = sum(x["km"] for x in odc)
    if not km or not l100_bez_pradu:
        return None
    litry = sum(x["litry"] for x in odc)
    kp = sum(x["koszt_paliwa"] for x in odc)
    kpr = sum(x.get("koszt_pradu") or 0 for x in odc)
    cena = cena_l or (kp / litry if litry else None)
    if not cena:
        return None
    bez = km * float(l100_bez_pradu) / 100 * cena
    return {"km": round(km), "koszt_bez_pradu": round(bez, 2), "koszt": round(kp + kpr, 2),
            "oszczednosc": round(bez - kp - kpr, 2)}
