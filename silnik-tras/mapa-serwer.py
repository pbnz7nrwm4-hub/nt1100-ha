"""Serwer plików mapy na kartę (katalog www/mapa) dla dodatku Home Assistant.
Użycie: mapa-serwer.py KATALOG PORT"""
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class H(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


root, port = sys.argv[1], int(sys.argv[2])
os.makedirs(os.path.join(root, "mapa"), exist_ok=True)
ThreadingHTTPServer(("0.0.0.0", port), partial(H, directory=root)).serve_forever()
