"""Pojazdy: import i eksport w formacie Fuelio.

Kopia z Fuelio (.fuelio) to ZIP z plikami vehicle-N-local.csv. Każdy plik ma sekcje
zaczynające się wierszem "## Nazwa": Vehicle, Log (tankowania), CostCategories,
Costs, Category, TripLog, FavStations, Pictures. Czytamy Vehicle, Log, CostCategories
i Costs; resztę pomijamy. Eksport tworzy taki sam ZIP (da się go wczytać z powrotem
tutaj i w Fuelio).
"""

import csv
import io
import zipfile

from obliczenia import podejrzana_kwota

LOG_COLS = ["Date", "Odo (km)", "Fuel (l)", "Full", "Price", "l/100km", "latitude", "longitude", "City",
            "Notes", "Missed", "TankNumber", "FuelType", "VolumePrice", "StationID", "ExcludeDistance",
            "UniqueId", "TankCalc", "Weather", "guid", "lastupdated"]
VEH_COLS = ["Name", "Description", "DistUnit", "FuelUnit", "ConsumptionUnit", "ImportCSVDateFormat", "VIN",
            "Insurance", "Plate", "Make", "Model", "Year", "TankCount", "Tank1Type", "Tank2Type", "Active",
            "Tank1Capacity", "Tank2Capacity", "FuelUnitTank2", "FuelConsumptionTank2", "guid", "lastupdated"]
COST_COLS = ["CostTitle", "Date", "Odo", "CostTypeID", "Notes", "Cost", "flag", "idR", "read", "RemindOdo",
             "RemindDate", "isTemplate", "RepeatOdo", "RepeatMonths", "isIncome", "UniqueId", "guid", "lastupdated"]
CAT_COLS = ["CostTypeID", "Name", "priority", "color"]
DOMYSLNE_KATEGORIE = ["Serwis", "Eksploatacja", "Ubezpieczenie", "Rejestracja", "Parking", "Myjnia",
                      "Oplaty za przejazd", "Mandaty", "Tuning"]


def _f(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def sekcje(tekst):
    """CSV Fuelio -> {nazwa sekcji: [słownik wiersza]}."""
    out = {}
    nazwa, naglowek = None, None
    for row in csv.reader(io.StringIO(tekst)):
        if not row:
            continue
        if len(row) == 1 and row[0].startswith("## "):
            nazwa, naglowek = row[0][3:].strip(), None
            out[nazwa] = []
            continue
        if nazwa is None:
            continue
        if naglowek is None:
            naglowek = row
            continue
        out[nazwa].append(dict(zip(naglowek, row)))
    return out


def pliki(dane, nazwa_pliku=""):
    """Bajty .fuelio (ZIP) albo pojedynczy CSV -> [(nazwa pliku, tekst)]."""
    if dane[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(dane)) as z:
            out = []
            for n in sorted(z.namelist()):
                if n.lower().endswith(".csv"):
                    out.append((n, z.read(n).decode("utf-8-sig", "replace")))
            return out
    return [(nazwa_pliku or "fuelio.csv", dane.decode("utf-8-sig", "replace"))]


def czytaj(dane, nazwa_pliku=""):
    """Odczyt kopii Fuelio -> lista pojazdów z tankowaniami i kosztami (bez zapisu)."""
    out = []
    for plik, tekst in pliki(dane, nazwa_pliku):
        s = sekcje(tekst)
        v = (s.get("Vehicle") or [{}])[0]
        nazwa = (v.get("Name") or plik).strip()
        kat = {}
        for c in s.get("CostCategories") or []:
            cid = c.get("Id") or c.get("IdCategory") or c.get("CostTypeID")
            if cid:
                kat[str(cid)] = c.get("Name") or ""
        tank = []
        for r in s.get("Log") or []:
            km = _f(r.get("Odo (km)"))
            litry = _f(r.get("Fuel (l)"))
            if km is None or not r.get("Date"):
                continue
            t = {"data": r["Date"][:16], "przebieg": km, "litry": litry, "kwota": _f(r.get("Price")) or None,
                 "cena_l": _f(r.get("VolumePrice")) or None, "pelny": 1 if str(r.get("Full")) == "1" else 0,
                 "pominiete": 1 if str(r.get("Missed")) == "1" else 0, "stacja": (r.get("City") or "").strip(),
                 "notatka": (r.get("Notes") or "").strip(), "fuelio_typ": r.get("FuelType") or "",
                 "zrodlo": "fuelio"}
            if t["stacja"] in ("Brak nazwy - -", "-"):
                t["stacja"] = ""
            if not t["cena_l"] and t["kwota"] and litry:
                t["cena_l"] = round(t["kwota"] / litry, 3)
            t["uid"] = "fuelio:%s:%s:%s:%s" % (nazwa, t["data"], km, litry)
            t["podejrzana"] = podejrzana_kwota(t)
            tank.append(t)
        koszty, terminy = [], []
        for r in s.get("Costs") or []:
            if str(r.get("isTemplate")) == "1":
                continue
            kw = _f(r.get("Cost"))
            if r.get("Date") and kw is not None and str(r.get("isIncome")) != "1":
                k = {"data": r["Date"][:16], "przebieg": _f(r.get("Odo")) or None,
                     "kategoria": kat.get(str(r.get("CostTypeID")), "") or "Inne",
                     "tytul": (r.get("CostTitle") or "").strip(), "kwota": kw,
                     "notatka": (r.get("Notes") or "").strip(), "zrodlo": "fuelio"}
                k["uid"] = "fuelio:%s:k:%s:%s:%s" % (nazwa, k["data"], k["tytul"], kw)
                koszty.append(k)
            co_km = _f(r.get("RepeatOdo")) or None
            co_m = _f(r.get("RepeatMonths")) or None
            rd = (r.get("RemindDate") or "").strip()
            if co_km or co_m or (rd and rd[:4].isdigit() and rd[:4] != "2000"):
                terminy.append({"nazwa": (r.get("CostTitle") or "Termin").strip(),
                                "kategoria": kat.get(str(r.get("CostTypeID")), "") or "Inne",
                                "co_km": co_km, "co_mies": int(co_m) if co_m else None,
                                "ostatnio_data": (r.get("Date") or "")[:10] or None, "ostatnio_km": _f(r.get("Odo")) or None,
                                "nastepny_data": rd[:10] if (rd and rd[:4].isdigit()) else None,
                                "nastepny_km": _f(r.get("RemindOdo")) or None})
        out.append({"plik": plik, "nazwa": nazwa, "bak_l": _f(v.get("Tank1Capacity")) or None,
                    "tankowania": tank, "koszty": koszty, "terminy": terminy,
                    "od": min([t["data"] for t in tank], default=None), "do": max([t["data"] for t in tank], default=None),
                    "podejrzane": [{"data": t["data"], "kwota": t["kwota"], "wyliczona": t["podejrzana"]}
                                   for t in tank if t["podejrzana"]]})
    return out


def _csv(rows, cols):
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue()


def _num(v, n=2):
    return "" if v is None else ("%.*f" % (n, float(v)))


def eksport_pojazdu(pojazd, tankowania, koszty):
    """Jeden pojazd -> tekst CSV w układzie Fuelio."""
    kat = list(DOMYSLNE_KATEGORIE)
    for k in koszty:
        if k.get("kategoria") and k["kategoria"] not in kat:
            kat.append(k["kategoria"])
    v = {c: "" for c in VEH_COLS}
    v.update({"Name": pojazd.get("nazwa") or "", "DistUnit": "0", "FuelUnit": "0", "ConsumptionUnit": "0",
              "ImportCSVDateFormat": "yyyy-MM-dd", "TankCount": "1", "Tank1Type": "0", "Tank2Type": "0",
              "Active": "1", "Tank1Capacity": _num(pojazd.get("bak_l") or 0, 1), "Tank2Capacity": "0.0",
              "FuelUnitTank2": "0", "FuelConsumptionTank2": "0", "Year": "0", "lastupdated": "0"})
    log = []
    for i, t in enumerate(sorted(tankowania, key=lambda x: (x.get("data") or "", x.get("przebieg") or 0)), 1):
        log.append({"Date": (t.get("data") or "")[:10], "Odo (km)": _num(t.get("przebieg"), 1),
                    "Fuel (l)": _num(t.get("litry")), "Full": "1" if t.get("pelny") else "0",
                    "Price": _num(t.get("kwota")), "l/100km": "0.0", "latitude": "", "longitude": "",
                    "City": t.get("stacja") or "", "Notes": t.get("notatka") or "",
                    "Missed": "1" if t.get("pominiete") else "0", "TankNumber": "1",
                    "FuelType": t.get("fuelio_typ") or "0", "VolumePrice": _num(t.get("cena_l"), 3),
                    "StationID": "0", "ExcludeDistance": "0.0", "UniqueId": str(i), "TankCalc": "0.0",
                    "Weather": "", "guid": "", "lastupdated": "0"})
    cats = [{"CostTypeID": str(i), "Name": n, "priority": "0", "color": ""} for i, n in enumerate(kat, 1)]
    kid = {n: str(i) for i, n in enumerate(kat, 1)}
    cs = []
    for i, k in enumerate(koszty, 1):
        cs.append({"CostTitle": k.get("tytul") or k.get("kategoria") or "", "Date": (k.get("data") or "")[:10],
                   "Odo": _num(k.get("przebieg") or 0, 1), "CostTypeID": kid.get(k.get("kategoria"), "2"),
                   "Notes": k.get("notatka") or "", "Cost": _num(k.get("kwota")), "flag": "0", "idR": "0",
                   "read": "1", "RemindOdo": "0", "RemindDate": "2011-01-01", "isTemplate": "0", "RepeatOdo": "0",
                   "RepeatMonths": "0", "isIncome": "0", "UniqueId": str(i), "guid": "", "lastupdated": "0"})
    parts = ['"## Vehicle"\n', _csv([v], VEH_COLS), '"## Log"\n', _csv(log, LOG_COLS),
             '"## CostCategories"\n', _csv(cats, CAT_COLS), '"## Costs"\n', _csv(cs, COST_COLS)]
    return "".join(parts)


def eksport(pojazdy):
    """[(pojazd, tankowania, koszty)] -> bajty ZIP .fuelio."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (p, t, k) in enumerate(pojazdy, 1):
            z.writestr("vehicle-%d-local.csv" % i, eksport_pojazdu(p, t, k))
    return buf.getvalue()
