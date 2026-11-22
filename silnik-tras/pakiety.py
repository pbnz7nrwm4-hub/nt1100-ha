#!/usr/bin/env python3
"""Paczki mapy wybierane przez użytkownika na stronie serwera map (plik pakiety.json obok obszar.env).

    pakiety.py env [PLIK]     wypisuje zmienne dla aktualizuj.sh / kafelki.sh / build_map.py

Brak pliku = ustawienia jak dotąd (komplet punktów, bez budynków, bez ciekawych miejsc)."""
import json
import shlex
import sys

# grupy punktów mapy ekranu, które wolno wyłączyć (stacje paliw, fotoradary i światła są zawsze)
POI_GRUPY = {
    "jedzenie": "Restauracje i kawiarnie",
    "noclegi": "Noclegi",
    "widoki": "Punkty widokowe, przełęcze, miejsca piknikowe",
    "ladowarki": "Ładowarki",
    "moto": "Sklepy i serwisy motocyklowe",
    "parkingi": "Parkingi",
}
MIEJSCA_GRUPY = ("zamki", "muzea", "widoki", "przyroda", "zabytki")
DOMYSLNE = {"poi": sorted(POI_GRUPY), "budynki": False, "miejsca": False, "miejsca_grupy": list(MIEJSCA_GRUPY)}


def popraw(d):
    """Tylko znane pola i wartości; reszta wraca do domyślnych (plik edytuje strona, ale nie ufamy mu)."""
    d = d if isinstance(d, dict) else {}
    out = dict(DOMYSLNE)
    if isinstance(d.get("poi"), list):
        out["poi"] = sorted(g for g in set(d["poi"]) if g in POI_GRUPY)
    out["budynki"] = d.get("budynki") is True
    out["miejsca"] = d.get("miejsca") is True
    if isinstance(d.get("miejsca_grupy"), list):
        out["miejsca_grupy"] = [g for g in MIEJSCA_GRUPY if g in d["miejsca_grupy"]] or list(MIEJSCA_GRUPY)
    return out


def wczytaj(plik):
    try:
        with open(plik) as f:
            return popraw(json.load(f))
    except (OSError, ValueError):
        return dict(DOMYSLNE)


def env(p):
    bez = sorted(set(POI_GRUPY) - set(p["poi"]))
    return {"MAPA_POI_BEZ": ",".join(bez), "MAPA_BUDYNKI": "1" if p["budynki"] else "0",
            "MAPA_MIEJSCA": "1" if p["miejsca"] else "0", "MAPA_MIEJSCA_GRUPY": ",".join(p["miejsca_grupy"])}


if __name__ == "__main__":
    plik = sys.argv[2] if len(sys.argv) > 2 else "/opt/nt1100-trasy/pakiety.json"
    import os
    if not os.path.exists(plik):   # bez pliku nic nie nadpisujemy (zostają ustawienia z obszar.env)
        sys.exit(0)
    for k, v in env(wczytaj(plik)).items():
        print("export %s=%s" % (k, shlex.quote(v)))
