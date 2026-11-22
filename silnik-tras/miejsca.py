#!/usr/bin/env python3
"""Paczka „Ciekawe miejsca”: obiekty z OSM, które mają artykuł w polskiej Wikipedii, z krótkim opisem.

    miejsca.py PLIK.osm.pbf WYJSCIE.json [--cache plik.json] [--grupy zamki,muzea,...]

Źródło: znacznik OSM wikipedia=pl:Tytuł (obiekt jest „znany”, bo ma artykuł). Opis (2 zdania wstępu) pobierany
raz z pl.wikipedia.org i pamiętany w pliku cache – kolejne budowy pytają tylko o nowe tytuły, a wynik działa
bez internetu. Wynik: {"built","n","grupy":{...},"miejsca":[{"n","g","lat","lon","t","o","z","d"}]}
(n nazwa, g grupa, t tytuł artykułu, o opis, z adres miniatury zdjęcia z Wikipedii/Commons albo "", d długość artykułu w bajtach).

Z --ntm powstaje też plik m_miejsca.ntm dla ekranu Tab5 (format NTM1, MIEJSCA_format_ekran.md): nagłówek 14 B, indeks 20 B
na miejsce posortowany po szerokości, sterta tekstów. Waga 0–255 = logarytm długości artykułu względem najdłuższego. Obiekty z artykułem tylko w innym języku są pomijane (liczone).
"""
import json
import math
import os
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

GRUPY = {
    "zamki": "Zamki, pałace, ruiny",
    "muzea": "Muzea",
    "widoki": "Punkty widokowe i wieże",
    "przyroda": "Jaskinie, wodospady, skały",
    "zabytki": "Zabytki i atrakcje",
}
# (klucz, wartość) -> grupa; pierwsza pasująca wygrywa
TAGI = (
    (("historic", "castle"), "zamki"), (("historic", "fort"), "zamki"), (("historic", "ruins"), "zamki"),
    (("historic", "manor"), "zamki"), (("historic", "palace"), "zamki"), (("historic", "fortress"), "zamki"),
    (("tourism", "museum"), "muzea"),
    (("tourism", "viewpoint"), "widoki"), (("man_made", "lighthouse"), "widoki"), (("tower:type", "observation"), "widoki"),
    (("natural", "cave_entrance"), "przyroda"), (("waterway", "waterfall"), "przyroda"), (("natural", "rock"), "przyroda"),
    (("historic", "archaeological_site"), "zabytki"), (("historic", "monument"), "zabytki"),
    (("historic", "monastery"), "zabytki"), (("historic", "mine"), "zabytki"), (("tourism", "attraction"), "zabytki"),
)
FILTR = ["nwr/wikipedia"]
API = "https://pl.wikipedia.org/w/api.php"
OPIS_MAX = 320
MINIATURA = 320   # szerokość miniatury zdjęcia w pikselach


def grupa(tags):
    for (k, v), g in TAGI:
        if tags.get(k) == v:
            return g
    return None


def tytul_pl(tags):
    w = (tags.get("wikipedia") or "").strip()
    if w.lower().startswith("pl:") and len(w) > 3:
        return w[3:].replace("_", " ").strip()
    return None


def punkt(geom):
    """Środek obiektu (punkt albo średnia wierzchołków obrysu)."""
    t, c = geom.get("type"), geom.get("coordinates")
    if not c:
        return None
    if t == "Point":
        pts = [c]
    elif t == "LineString":
        pts = c
    elif t == "Polygon":
        pts = c[0]
    elif t == "MultiPolygon":
        pts = c[0][0]
    else:
        return None
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def wybierz(features, grupy=None):
    """Z obiektów GeoJSON: lista miejsc bez opisów i liczba pominiętych (artykuł tylko w innym języku)."""
    out, seen, inny_jezyk = [], set(), 0
    for f in features:
        tags = f.get("properties") or {}
        g = grupa(tags)
        if g is None or (grupy and g not in grupy):
            continue
        t = tytul_pl(tags)
        if not t:
            inny_jezyk += 1
            continue
        pt = punkt(f.get("geometry") or {})
        if not pt or t in seen:
            continue
        seen.add(t)
        out.append({"n": (tags.get("name:pl") or tags.get("name") or t).strip(), "g": g,
                    "lat": round(pt[0], 5), "lon": round(pt[1], 5), "t": t})
    return out, inny_jezyk


def skroc(tekst):
    tekst = " ".join((tekst or "").split())
    if len(tekst) <= OPIS_MAX:
        return tekst
    ciecie = tekst.rfind(". ", 0, OPIS_MAX)
    return tekst[:ciecie + 1] if ciecie > 80 else tekst[:OPIS_MAX - 1].rstrip() + "…"


def pobierz_wiki(tytuly):
    """Wstępy, miniatury i długości artykułów dla do 20 tytułów: {tytuł podany: (opis, adres miniatury, długość)}. Sieć; w testach podmieniane."""
    q = urllib.parse.urlencode({"action": "query", "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1,
                                "exsentences": 2, "exlimit": 20, "piprop": "thumbnail", "pithumbsize": MINIATURA,
                                "redirects": 1, "format": "json", "titles": "|".join(tytuly)})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": "NT1100-mapa/1 (mapa offline)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read()).get("query", {})
    alias = {}
    for k in ("normalized", "redirects"):
        for e in d.get(k, []):
            alias[e["from"]] = e["to"]
    strony = {p.get("title"): (p.get("extract", ""), (p.get("thumbnail") or {}).get("source", ""), p.get("length", 0))
              for p in d.get("pages", {}).values()}
    out = {}
    for t in tytuly:
        cel = t
        for _ in range(3):
            cel = alias.get(cel, cel)
        out[t] = strony.get(cel, ("", "", 0))
    return out


def opisy(miejsca, cache, pobierz=pobierz_wiki, pauza=0.2, log=print):
    """Dopisuje „o” z cache albo z Wikipedii (po 20 tytułów). Błąd sieci nie przerywa: miejsce zostaje bez opisu."""
    # wpisy z cache sprzed zdjęć (zwykły napis) pobieramy jeszcze raz, żeby mieć miniaturę
    brak = [m["t"] for m in miejsca if not (isinstance(cache.get(m["t"]), dict) and "d" in cache[m["t"]])]
    for i in range(0, len(brak), 20):
        part = brak[i:i + 20]
        try:
            for t, (o, z, d) in pobierz(part).items():
                cache[t] = {"o": skroc(o), "z": z, "d": int(d or 0)}
        except Exception as e:  # noqa: BLE001 - sieć bywa niedostępna, budowa ma się skończyć
            log("Wikipedia: błąd przy %d–%d: %s" % (i, i + len(part), e))
        if pauza:
            time.sleep(pauza)
    for m in miejsca:
        c = cache.get(m["t"], "")
        if isinstance(c, dict):
            m["o"], m["z"], m["d"] = c.get("o", ""), c.get("z", ""), c.get("d", 0)
        else:
            m["o"], m["z"], m["d"] = c, "", 0
    return miejsca


NTM_GRUPA = {"zamki": 1, "muzea": 2, "widoki": 3, "przyroda": 4, "zabytki": 5}
NTM_OPIS_BAJTY = 700   # limit z formatu (długość w u16, ekran czyta do 700 B)


def waga(d, dmax):
    """0–255: logarytm długości artykułu względem najdłuższego; bez długości 0."""
    if d <= 0 or dmax <= 1:
        return 0
    return max(0, min(255, int(round(255 * math.log(d + 1) / math.log(dmax + 1)))))


def ntm(miejsca):
    """Bajty pliku NTM1. Indeks (20 B): lat i32, lon i32, grupa u8, waga u8, nazwa_off u32, opis_off u32, opis_dl u16.
    Sterta, dla każdego miejsca po kolei: nazwa+NUL, opis (opis_dl bajtów, bez NUL), tytuł artykułu+NUL
    (zaczyna się w opis_off + opis_dl)."""
    dmax = max([m.get("d", 0) for m in miejsca] or [0])
    wiersze = sorted(miejsca, key=lambda m: (m["lat"], m["lon"]))
    sterta = bytearray()
    indeks = bytearray()
    for m in wiersze:
        nazwa = m["n"].encode("utf-8")[:120].decode("utf-8", "ignore").encode("utf-8")
        opis = m.get("o", "").encode("utf-8")
        if len(opis) > NTM_OPIS_BAJTY:
            opis = opis[:NTM_OPIS_BAJTY].decode("utf-8", "ignore").encode("utf-8")
        tytul = m["t"].encode("utf-8")[:200].decode("utf-8", "ignore").encode("utf-8")
        n_off = len(sterta)
        sterta += nazwa + b"\0"
        o_off = len(sterta)
        sterta += opis + tytul + b"\0"
        indeks += struct.pack("<iiBBIIH", int(round(m["lat"] * 1e6)), int(round(m["lon"] * 1e6)),
                              NTM_GRUPA.get(m["g"], 5), waga(m.get("d", 0), dmax), n_off, o_off, len(opis))
    return b"NTM1" + struct.pack("<BBII", 1, 0, len(wiersze), len(sterta)) + bytes(indeks) + bytes(sterta)


def czytaj_ntm(dane):
    """Parser do testów (wzorzec dla parsera na ekranie): lista słowników miejsc albo ValueError przy złym pliku."""
    if len(dane) < 14 or dane[:4] != b"NTM1" or dane[4] != 1:
        raise ValueError("zły nagłówek NTM1")
    n, sterta = struct.unpack_from("<II", dane, 6)
    if len(dane) != 14 + 20 * n + sterta:
        raise ValueError("zły rozmiar pliku")
    base = 14 + 20 * n
    out = []
    for i in range(n):
        lat, lon, g, w, no, oo, od = struct.unpack_from("<iiBBIIH", dane, 14 + 20 * i)
        if no >= sterta or oo + od >= sterta:
            raise ValueError("offset poza stertą")
        nazwa = dane[base + no:dane.index(b"\0", base + no)]
        opis = dane[base + oo:base + oo + od]
        tytul = dane[base + oo + od:dane.index(b"\0", base + oo + od)]
        out.append({"lat": lat / 1e6, "lon": lon / 1e6, "g": g, "w": w, "n": nazwa.decode("utf-8"),
                    "o": opis.decode("utf-8"), "t": tytul.decode("utf-8")})
    return out


def czytaj_osm(pbf, work):
    wyc = os.path.join(work, "miejsca-wiki.pbf")
    subprocess.run(["osmium", "tags-filter", pbf] + FILTR + ["-o", wyc, "--overwrite"], check=True)
    with subprocess.Popen(["osmium", "export", wyc, "-f", "geojsonseq"], stdout=subprocess.PIPE, text=True,
                          bufsize=1 << 20) as p:
        for line in p.stdout:
            line = line.lstrip("\x1e")
            if line.startswith("{"):
                yield json.loads(line)
    os.remove(wyc)


def main():
    pbf, wyj = sys.argv[1], sys.argv[2]
    cache_p = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else wyj + ".cache"
    grupy = None
    if "--grupy" in sys.argv:
        grupy = {g for g in sys.argv[sys.argv.index("--grupy") + 1].split(",") if g in GRUPY} or None
    try:
        with open(cache_p) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    miejsca, inny = wybierz(czytaj_osm(pbf, os.path.dirname(os.path.abspath(wyj))), grupy)
    opisy(miejsca, cache)
    with open(cache_p + ".tmp", "w") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(cache_p + ".tmp", cache_p)
    wynik = {"built": time.strftime("%Y-%m-%d"), "n": len(miejsca), "bez_opisu": sum(1 for m in miejsca if not m["o"]),
             "ze_zdjeciem": sum(1 for m in miejsca if m.get("z")),
             "inny_jezyk": inny, "grupy": GRUPY, "miejsca": miejsca}
    with open(wyj + ".tmp", "w") as f:
        json.dump(wynik, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(wyj + ".tmp", wyj)
    if "--ntm" in sys.argv:
        plik = sys.argv[sys.argv.index("--ntm") + 1]
        dane = ntm([m for m in miejsca if m.get("o")])
        with open(plik + ".tmp", "wb") as f:
            f.write(dane)
        os.replace(plik + ".tmp", plik)
        print("m_miejsca.ntm: %d B" % len(dane))
    print("ciekawe miejsca: %d (bez opisu %d, ze zdjęciem %d, pominięte bez polskiego artykułu %d)"
          % (wynik["n"], wynik["bez_opisu"], wynik["ze_zdjeciem"], inny))


if __name__ == "__main__":
    main()
