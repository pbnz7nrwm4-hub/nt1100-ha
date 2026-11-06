#!/usr/bin/env python3
"""Diagnoza wariantów krętości: liczy te same trasy w każdym wariancie i porównuje, jak kręte wyszły.

Uruchom tam, gdzie widać silnik tras (np. kontener Claude):
    NT1100_START=lat,lon python3 narzedzia/kretosc_diag.py http://ADRES-SILNIKA:8989 [--kandydaci] [--kreto]

Dla każdej trasy i wariantu: km, minuty, °/km tak jak w dodatku („deg_km”), °/km bez skrętów
na skrzyżowaniach („zakręty”), udział klas dróg. --kandydaci dokłada próbne ustawienia modelu.
Wynik: tabela na ekran i plik kretosc_diag.json obok bieżącego katalogu.
"""
import json
import os
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nt1100_jazdy"))
import nav  # noqa: E402
import ntt  # noqa: E402

# Punkt startu z NT1100_START="lat,lon" (repo jest publiczne – bez adresu domowego); domyślnie rynek w Katowicach.
DOM = tuple(float(x) for x in (os.environ.get("NT1100_START") or "50.2590,19.0220").split(",")[:2])
TRASY = [("Dom → Szczyrk", DOM, (49.7186, 19.0317)),
         ("Dom → Wisła", DOM, (49.6495, 18.8590)),
         ("Dom → Żywiec", DOM, (49.6857, 19.1925)),
         ("Dom → Wadowice", DOM, (49.8833, 19.4931)),
         ("Dom → Ojców", DOM, (50.2117, 19.8297)),
         ("Dom → Ustroń", DOM, (49.7210, 18.8120))]


def post(url, body):
    r = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as f:
        return json.loads(f.read())


def metrics(path):
    pts = [(c[1], c[0]) for c in path["points"]["coordinates"]]
    cum = nav.cum_dist(pts)
    cv = nav.curviness(pts, cum) or {}
    # skręty na skrzyżowaniach: punkty instrukcji ze znakiem != 0 (±40 m wokół)
    turn_d = [cum[ins["interval"][0]] for ins in path.get("instructions", []) if ins.get("sign", 0) not in (0, 4, 5)]
    samples, want = [], 0.0
    for i, c in enumerate(cum):
        if c >= want:
            samples.append((pts[i], c))
            want = c + 50.0
    tot = junc = 0.0
    for i in range(2, len(samples)):
        d = abs(ntt.angle_diff(ntt.bearing(samples[i - 2][0], samples[i - 1][0]), ntt.bearing(samples[i - 1][0], samples[i][0])))
        if d < 4:
            continue
        if any(abs(samples[i - 1][1] - t) < 40 for t in turn_d):
            junc += d
        else:
            tot += d
    km = cum[-1] / 1000.0
    rc = {}
    for a, b, v in path.get("details", {}).get("road_class", []):
        rc[v] = rc.get(v, 0) + cum[min(b, len(cum) - 1)] - cum[a]
    share = {k: round(100 * v / max(1, cum[-1])) for k, v in sorted(rc.items(), key=lambda x: -x[1]) if v / max(1, cum[-1]) >= 0.03}
    return {"km": round(km, 1), "min": round(path["time"] / 60000), "deg_km": cv.get("deg_km"),
            "zakrety_km": int(tot / km) if km else None, "skrzyzowania_km": int(junc / km) if km else None, "klasy": share}


def kandydaci(n, variant, avoid):
    """Próbne modele: K1 = stopniowana kara za proste drogi, K2 = K1 + kara za drogi w zabudowie."""
    base = n.gh_custom_model(variant, avoid)
    if variant == "szybko":
        return {}
    pr = [x for x in base["priority"] if "curvature" not in (x.get("if") or x.get("else_if") or "")]
    z = n.settings()["curvy"][variant]["zakrety"] / 100.0
    st = 1 - 0.75 * z
    k1 = pr + [{"if": "curvature > 0.97", "multiply_by": str(round(st, 3))},
               {"else_if": "curvature > 0.92", "multiply_by": str(round(min(1, st + 0.15), 3))},
               {"else_if": "curvature > 0.85", "multiply_by": str(round(min(1, st + 0.3), 3))}]
    k2 = k1 + [{"if": "road_class == RESIDENTIAL || road_class == LIVING_STREET || road_class == UNCLASSIFIED",
                "multiply_by": str(round(1 - 0.5 * z, 3))}]
    return {"K1": dict(base, priority=k1), "K2": dict(base, priority=k2)}


def main():
    url = sys.argv[1].rstrip("/")
    cand = "--kandydaci" in sys.argv
    tmp = tempfile.mkdtemp()
    n = nav.Nav(tmp, tmp, lambda: {"engine_url": url})
    out = []
    for name, a, b in TRASY:
        print("\n" + name)
        for v, _ in nav.VARIANTS:
            models = {"teraz": n.gh_custom_model(v, [])}
            if cand:
                models.update(kandydaci(n, v, []))
            if "--kreto" in sys.argv and v == "kreto":
                # próbne suwaki „kręto” (glowne/zakrety/dluzej), reszta jak dziś
                for g, z, dl in ((90, 80, 60), (95, 80, 70), (90, 100, 60)):
                    nk = nav.Nav(tmp, tmp, lambda g=g, z=z, dl=dl: {"engine_url": url, "curvy": {"kreto": {"glowne": g, "zakrety": z, "dluzej": dl}}})
                    models["k%d/%d/%d" % (g, z, dl)] = nk.gh_custom_model(v, [])
            for mname, cm in models.items():
                body = {"points": [[a[1], a[0]], [b[1], b[0]]], "profile": "motocykl", "locale": "pl",
                        "instructions": True, "points_encoded": False, "calc_points": True,
                        "details": ["road_class"], "ch.disable": True, "custom_model": cm}
                try:
                    m = metrics(post(url + "/route", body)["paths"][0])
                except Exception as e:  # noqa: BLE001
                    m = {"blad": str(e)[:120]}
                m.update(trasa=name, wariant=v, model=mname)
                out.append(m)
                print("  %-7s %-10s %6s km %4s min  °/km %4s  zakręty %4s  skrzyż. %4s  %s" % (
                    v, mname, m.get("km"), m.get("min"), m.get("deg_km"), m.get("zakrety_km"),
                    m.get("skrzyzowania_km"), m.get("klasy", m.get("blad"))))
    with open("kretosc_diag.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
