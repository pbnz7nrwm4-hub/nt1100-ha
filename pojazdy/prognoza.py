"""Pojazdy: prognoza kosztów na najbliższe 12 miesięcy (bez Home Assistant).

Pewne: niezapłacone raty polis z terminem w okresie.
Szacunek:
  * paliwo i prąd = zł/km z ostatnich 12 miesięcy × km z tego samego miesiąca rok temu (sezon motocyklowy);
    bez odczytów z tamtego miesiąca – średnie km z ostatnich 3 miesięcy;
  * nowa polisa po końcu obecnej (bez następczyni) – ta sama składka i raty;
  * terminy (przegląd, serwis) – ostatni koszt tej samej pozycji; termin tylko w km – data z tempa jazdy;
  * wymiana opon – ta sama wymiana co rok temu, za tyle co wtedy.
"""

from datetime import date, timedelta

import obliczenia as ob

KAT = ("paliwo", "prad", "polisy", "serwis")


def miesiace_okna(dzis, n=12):
    """Najbliższe n pełnych miesięcy od następnego: ["RRRR-MM", ...]."""
    p = ob.dodaj_miesiace(dzis.replace(day=1), 1)
    return [ob.dodaj_miesiace(p, i).isoformat()[:7] for i in range(n)]


def _od_do(mies):
    a = date(int(mies[:4]), int(mies[5:7]), 1)
    return a.isoformat(), ob.dodaj_miesiace(a, 1).isoformat()


def stawki(tankowania, ladowania, koszty, odczyty, dzis):
    """zł/km za paliwo i prąd z ostatnich 12 pełnych miesięcy (+ bieżący)."""
    od = ob.dodaj_miesiace(dzis.replace(day=1), -12).isoformat()
    do = (dzis + timedelta(days=1)).isoformat()
    s = ob.podsumowanie_okresu(tankowania, ladowania, koszty, odczyty, od, do)
    if not s["km"]:
        return None
    return {"paliwo": s["paliwo"] / s["km"], "prad": s["prad"] / s["km"], "km": s["km"], "od": od}


def km_miesiaca(pts, mies, dzis):
    """Szacunek km w przyszłym miesiącu: ten sam miesiąc rok temu, a bez odczytów z niego – średnia z 3 ostatnich."""
    a = date(int(mies[:4]) - 1, int(mies[5:7]), 1)
    od, do = a.isoformat(), ob.dodaj_miesiace(a, 1).isoformat()
    przed = [d for d, _ in pts if d[:10] < od]
    po = [d for d, _ in pts if d[:10] >= do]
    if przed and po:
        # znamy licznik przed i po tamtym miesiącu: różnica licznika na jego początku i końcu, liniowo między
        # najbliższymi odczytami (rzadkie tankowania rozkładają km równo; gęsta telemetria pokaże 0, gdy stał)
        return max(0.0, licznik_w_dniu(pts, do) - licznik_w_dniu(pts, od)), "rok temu"
    od3 = ob.dodaj_miesiace(dzis.replace(day=1), -3).isoformat()
    km3 = ob.km_w_okresie(pts, od3, (dzis + timedelta(days=1)).isoformat())
    dni = max(1, (dzis - ob.d10(od3)).days + 1)
    return km3 / dni * 30.4, "3 ostatnie miesiące"


def licznik_w_dniu(pts, dzien):
    """Licznik na początku dnia: liniowo między ostatnim odczytem przed a pierwszym od tego dnia."""
    a = [(d, k) for d, k in pts if d[:10] < dzien]
    b = [(d, k) for d, k in pts if d[:10] >= dzien]
    if not a:
        return b[0][1]
    if not b:
        return max(k for _, k in a)
    (da, ka), (db, kb) = a[-1], b[0]
    x, y, z = ob.d10(da).toordinal(), ob.d10(db).toordinal(), ob.d10(dzien).toordinal()
    if z <= x or y <= x:
        return ka
    return ka + (kb - ka) * (z - x) / float(y - x)


def prognoza_pojazdu(p, tankowania, ladowania, koszty, odczyty, polisy, terminy, wymiany, dzis, km_teraz=None):
    """{"miesiace": {mies: {kat: zł}}, "pozycje": [...pewne i zaplanowane...], "razem", "opis"}."""
    okno = miesiace_okna(dzis)
    m = {x: {k: 0.0 for k in KAT} for x in okno}
    poz = []
    pts = ob.przebiegi(tankowania, koszty, odczyty, ladowania)
    st = stawki(tankowania, ladowania, koszty, odczyty, dzis)
    zrodla = set()
    if st:
        for x in okno:
            km, zr = km_miesiaca(pts, x, dzis)
            zrodla.add(zr)
            m[x]["paliwo"] += km * st["paliwo"]
            m[x]["prad"] += km * st["prad"]
    pierwszy, ostatni = okno[0] + "-01", _od_do(okno[-1])[1]

    def dodaj(data, kat, kwota, tytul, pewne):
        mies = data[:7]
        if mies not in m:
            return
        if kwota is not None:
            m[mies][kat] += float(kwota)
        poz.append({"data": data[:10], "pojazd": p["nazwa"], "tytul": tytul, "kwota": None if kwota is None else round(float(kwota), 2),
                    "pewne": pewne, "kat": kat})

    # polisy: niezapłacone raty (pewne) i następna polisa po końcu (szacunek)
    for pol in polisy:
        for r in pol.get("raty") or []:
            if not r.get("zaplacono") and pierwszy <= r["termin"][:10] < ostatni:
                dodaj(r["termin"], "polisy", r.get("kwota"), "rata %s" % pol.get("nazwa", "polisy"), True)
        if pol.get("odnowiona"):
            continue
        nast_od = ob.d10(pol["do"]) + timedelta(days=1)
        if not (pierwszy <= nast_od.isoformat() < ostatni):
            continue
        n = max(1, len(pol.get("raty") or []))
        skl = pol.get("skladka")
        if skl is None:
            skl = sum(float(r.get("kwota") or 0) for r in pol.get("raty") or []) or None
        for r in ob.rozloz_raty(nast_od.isoformat(), skl, n):
            dodaj(r["termin"], "polisy", r.get("kwota"), "nowa polisa %s (jak ta)%s" % (pol.get("nazwa", ""), "" if n == 1 else ", rata"), False)

    # terminy: data z terminu, a sam przebieg – data z tempa jazdy
    tempo = None
    od12 = ob.dodaj_miesiace(dzis.replace(day=1), -12).isoformat()
    km12 = ob.km_w_okresie(pts, od12, (dzis + timedelta(days=1)).isoformat())
    if km12 > 0:
        tempo = km12 / max(1, (dzis - ob.d10(od12)).days)
    for t in terminy:
        if not t.get("aktywny", 1):
            continue
        nd, nk = ob.nastepny_termin(t)
        data = nd
        if nk is not None and km_teraz is not None and tempo:
            dk = dzis + timedelta(days=max(0, (nk - km_teraz) / tempo))
            data = min(data, dk.isoformat()) if data else dk.isoformat()
        if not data:
            continue
        if data[:10] < pierwszy:
            data = pierwszy  # zaległy termin – w najbliższym miesiącu
        kw = ostatni_koszt(koszty, t)
        kat = "polisy" if (t.get("kategoria") == "Ubezpieczenie") else "serwis"
        dodaj(data, kat, kw, "%s (%s)" % (t["nazwa"], "jak ostatnio" if kw is not None else "bez ceny"), False)
        # termin co kilka miesięcy może wypaść w oknie drugi raz
        if t.get("co_mies") and nd:
            d2 = ob.dodaj_miesiace(ob.d10(nd), int(t["co_mies"])).isoformat()
            if d2 < ostatni and d2 >= pierwszy:
                dodaj(d2, kat, kw, "%s (%s)" % (t["nazwa"], "jak ostatnio" if kw is not None else "bez ceny"), False)

    # opony: wymiany sprzed roku powtórzone za rok, za tyle co wtedy
    for w in wymiany:
        if not w.get("zdjeta_id"):
            continue  # tylko zamiana kompletów (sezonowa); pierwsze założenie i opony motocykla nie wracają co rok
        d = ob.d10(w["data"])
        nd = ob.dodaj_miesiace(d, 12).isoformat()
        if pierwszy <= nd < ostatni:
            kw = w.get("koszt")
            dodaj(nd[:7] + "-01", "serwis", kw, "wymiana opon (jak ostatnio)", False)

    for x in m:
        m[x] = {k: round(v, 2) for k, v in m[x].items()}
        m[x]["razem"] = round(sum(m[x][k] for k in KAT), 2)
    poz.sort(key=lambda x: x["data"])
    razem = round(sum(v["razem"] for v in m.values()), 2)
    return {"miesiace": m, "pozycje": poz, "razem": razem, "pewne": _pewne(poz),
            "stawki": st, "km_zrodla": sorted(zrodla)}


def ostatni_koszt(koszty, t):
    """Ostatni koszt tej samej pozycji (tytuł jak nazwa terminu), a bez niego – tej samej kategorii z tytułem."""
    zt = [k for k in koszty if (k.get("tytul") or "").strip().lower() == (t.get("nazwa") or "").strip().lower()
          and k.get("kwota") not in (None, "")]
    if zt:
        return float(max(zt, key=lambda k: k.get("data") or "")["kwota"])
    return None


def razem(prognozy):
    """Suma prognoz kilku pojazdów."""
    m = {}
    poz = []
    for pr in prognozy:
        for k, v in pr["miesiace"].items():
            x = m.setdefault(k, {kk: 0.0 for kk in KAT + ("razem",)})
            for kk in x:
                x[kk] += v.get(kk, 0)
        poz += pr["pozycje"]
    for k in m:
        m[k] = {kk: round(vv, 2) for kk, vv in m[k].items()}
    poz.sort(key=lambda x: x["data"])
    r = round(sum(v["razem"] for v in m.values()), 2)
    return {"miesiace": dict(sorted(m.items())), "pozycje": poz, "razem": r, "pewne": _pewne(poz)}


def _pewne(poz):
    return round(sum(x["kwota"] or 0 for x in poz if x["pewne"]), 2)
