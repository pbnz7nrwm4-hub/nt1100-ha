#!/usr/bin/env python3
"""Dodatek-pośrednik: panel HA (Ingress) -> aplikacja Zadania dzieci w kontenerze.

Każde żądanie z panelu idzie do aplikacji z kluczem dodatku i identyfikatorem użytkownika HA (nagłówki Ingress),
więc aplikacja wie, kto jest zalogowany w HA. Dodatek nie trzyma żadnych danych. Tylko biblioteka standardowa.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WERSJA = "1.1.0"
OPCJE_PLIK = os.environ.get("ZD_OPCJE", "/data/options.json")
INGRESS = {"172.30.32.2"}            # brama Ingress Supervisora – tylko ona może wołać dodatek
PORT = int(os.environ.get("ZD_PORT_DODATKU", "8099"))
MAX = 10 * 1024 * 1024


def opcje():
    try:
        with open(OPCJE_PLIK, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


O = opcje()
ADRES = (os.environ.get("ZD_APLIKACJA") or O.get("adres_aplikacji") or "").strip().rstrip("/")
KLUCZ = (os.environ.get("ZD_KLUCZ") or O.get("klucz_aplikacji") or "").strip()
TOKEN_HA = (O.get("token_ha") or "").strip()
_PANEL = []

BRAK = """<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;padding:20px;max-width:520px;margin:auto"><h2>Zadania</h2><p>%s</p></body></html>"""


def panel():
    if not _PANEL and os.environ.get("SUPERVISOR_TOKEN"):
        try:
            req = urllib.request.Request("http://supervisor/addons/self/info",
                                         headers={"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]})
            slug = json.loads(urllib.request.urlopen(req, timeout=5).read())["data"]["slug"]
            _PANEL.append("/hassio/ingress/" + slug)
        except Exception:  # noqa: BLE001
            pass
    return _PANEL[0] if _PANEL else ""


def do_aplikacji(metoda, sciezka, body=None, naglowki=None, timeout=300):
    h = {"X-Zadania-Klucz": KLUCZ}
    h.update(naglowki or {})
    req = urllib.request.Request(ADRES + sciezka, data=body, method=metoda, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def wyslij_token():
    """Token HA z opcji dodatku -> aplikacja (powiadomienia). Ponawia, aż aplikacja odpowie."""
    while TOKEN_HA and ADRES and KLUCZ:
        try:
            k, _, _ = do_aplikacji("POST", "/api/dodatek/token", json.dumps({"token": TOKEN_HA}).encode(),
                                   {"Content-Type": "application/json"}, 15)
            if k == 200:
                print("Token HA przekazany do aplikacji.", flush=True)
                return
            print("Aplikacja nie przyjęła tokenu (kod %s) – sprawdź klucz." % k, flush=True)
            return
        except Exception as e:  # noqa: BLE001
            print("Aplikacja nie odpowiada (%s), ponowię za minutę." % e, flush=True)
        time.sleep(60)


class H(BaseHTTPRequestHandler):
    server_version = "ZadaniaDodatek/" + WERSJA

    def log_message(self, *a):
        pass

    def odpowiedz(self, kod, cialo, typ="text/html; charset=utf-8", nag=()):
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(cialo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in nag:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cialo)

    def przekaz(self):
        if self.client_address[0] not in INGRESS and not os.environ.get("ZD_BEZ_INGRESS"):
            return self.odpowiedz(403, (BRAK % "Tylko przez panel Home Assistant.").encode())
        if not (ADRES and KLUCZ):
            return self.odpowiedz(200, (BRAK % "Dodatek nie jest ustawiony: wpisz adres i klucz aplikacji w Konfiguracji "
                                               "dodatku (skopiujesz je w aplikacji: Osoby → Aplikacja Home Assistant).").encode())
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX:
            return self.odpowiedz(413, b'{"blad": "Za duze."}', "application/json")
        body = self.rfile.read(n) if self.command == "POST" else None
        h = {"X-Zadania-HA-User": self.headers.get("X-Remote-User-Id") or "",
             "X-Zadania-HA-Nazwa": self.headers.get("X-Remote-User-Display-Name") or self.headers.get("X-Remote-User-Name") or "",
             "X-Zadania-Panel": panel()}
        if self.headers.get("Content-Type"):
            h["Content-Type"] = self.headers["Content-Type"]
        try:
            kod, nag, tr = do_aplikacji(self.command, self.path, body, h)
        except Exception as e:  # noqa: BLE001
            if self.path.split("?")[0].startswith("/api/"):
                return self.odpowiedz(502, json.dumps({"blad": "Aplikacja Zadania w domu nie odpowiada (%s)." % e},
                                                      ensure_ascii=False).encode(), "application/json")
            return self.odpowiedz(502, (BRAK % ("Aplikacja Zadania w domu nie odpowiada (%s). Sprawdź, czy kontener działa." % e)).encode())
        dod = [("Location", nag["Location"])] if nag.get("Location") else []
        return self.odpowiedz(kod, tr, nag.get("Content-Type") or "application/octet-stream", dod)

    do_GET = przekaz
    do_POST = przekaz


if __name__ == "__main__":
    threading.Thread(target=wyslij_token, daemon=True).start()
    print("Zadania – dodatek %s, aplikacja: %s" % (WERSJA, ADRES or "(nie ustawiona)"), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
