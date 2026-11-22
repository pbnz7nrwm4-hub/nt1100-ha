#!/usr/bin/env python3
"""Kontrola zgodności mapy-kandydata z ekranem (bez ekranu, na serwerze).

    kontrola_zgodnosci.py KATALOG_KANDYDATA ZGODNOSC.json [--json wynik.json]

ZGODNOSC.json (z budowy firmware, gałąź wyniki): ntt_format, flagi_znane (maska), max_terenow_na_kwadrat,
czesci ("c,g,a,n,h"). Sprawdza: format i flagi w nagłówkach c_*.ntt ("NTT1", bajt 4 = format, bajt 5 = flagi),
rodzaje części z manifestu, zgodność crc/rozmiaru plików. Wynik: "ok" true/false i powody po polsku.
Liczby kształtów terenu na kwadrat sprawdza pomiar na urządzeniu (czerwone/żółte/zielone), nie ta kontrola."""
import json
import os
import sys
import zlib

PREFIX_CZESCI = {"c_": "c", "g_": "g", "a_": "a", "n_": "n", "h_": "h"}


def kontrola(kat, caps):
    powody = []
    try:
        with open(os.path.join(kat, "manifest.json")) as f:
            man = json.load(f)
    except (OSError, ValueError) as e:
        return {"ok": False, "powody": ["brak manifestu kandydata: %s" % e]}
    if man.get("format") != caps.get("ntt_format"):
        powody.append("format mapy %s, ekran czyta %s" % (man.get("format"), caps.get("ntt_format")))
    znane = int(caps.get("flagi_znane", 0))
    dozwolone = set(x.strip() for x in str(caps.get("czesci", "")).split(",") if x.strip())
    uzyte_flagi, uzyte_czesci, zle_crc = 0, set(), 0
    for nazwa, bajty, crc in man.get("files", []):
        p = os.path.join(kat, nazwa)
        for pre, c in PREFIX_CZESCI.items():
            if os.path.basename(nazwa).startswith(pre):
                uzyte_czesci.add(c)
        try:
            with open(p, "rb") as f:
                d = f.read()
        except OSError:
            powody.append("brak pliku %s" % nazwa)
            continue
        if len(d) != bajty or (crc and zlib.crc32(d) != crc):
            zle_crc += 1
        if os.path.basename(nazwa).startswith("c_") and d[:4] == b"NTT1" and len(d) > 5:
            uzyte_flagi |= d[5]
    for sekcja, c in (("graph", "g"), ("addr", "a")):
        if man.get(sekcja):
            uzyte_czesci.add(c)
    if zle_crc:
        powody.append("%d plików ma zły rozmiar lub sumę kontrolną" % zle_crc)
    if uzyte_flagi & ~znane:
        powody.append("mapa używa flag 0x%02x, ekran zna 0x%02x" % (uzyte_flagi, znane))
    obce = uzyte_czesci - dozwolone
    if obce:
        powody.append("części nieznane ekranowi: %s" % ",".join(sorted(obce)))
    return {"ok": not powody, "powody": powody, "wersja": man.get("wersja"), "built": man.get("built"),
            "flagi_uzyte": uzyte_flagi, "czesci": sorted(uzyte_czesci)}


if __name__ == "__main__":
    kat, caps_p = sys.argv[1], sys.argv[2]
    with open(caps_p) as f:
        w = kontrola(kat, json.load(f))
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w") as f:
            json.dump(w, f, ensure_ascii=False)
    print(json.dumps(w, ensure_ascii=False))
    sys.exit(0 if w["ok"] else 2)
