"""Pojazdy: baza SQLite (/data/pojazdy.db) – pojazdy, tankowania, ładowania, koszty, terminy."""

import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS pojazdy (
  id INTEGER PRIMARY KEY, nazwa TEXT NOT NULL, rodzaj TEXT NOT NULL DEFAULT 'auto',
  paliwo TEXT DEFAULT 'Pb95', bak_l REAL, bateria_kwh REAL, encja_przebiegu TEXT,
  l100_bez_pradu REAL, aktywny INTEGER DEFAULT 1, kolejnosc INTEGER DEFAULT 0, klucz TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS tankowania (
  id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, data TEXT NOT NULL, przebieg REAL,
  litry REAL, cena_l REAL, kwota REAL, pelny INTEGER DEFAULT 1, pominiete INTEGER DEFAULT 0,
  stacja TEXT, notatka TEXT, fuelio_typ TEXT, zrodlo TEXT DEFAULT 'recznie', uid TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS ladowania (
  id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, poczatek TEXT NOT NULL, koniec TEXT,
  kwh REAL, kwh_pv REAL, kwh_bateria REAL, soc_od REAL, soc_do REAL, koszt REAL, koszt_wartosc REAL,
  strefy TEXT, miejsce TEXT, przebieg REAL, zrodlo TEXT DEFAULT 'recznie', wykluczone INTEGER DEFAULT 0,
  zmienione INTEGER DEFAULT 0, notatka TEXT, uid TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS koszty (
  id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, data TEXT NOT NULL, przebieg REAL,
  kategoria TEXT, tytul TEXT, kwota REAL, notatka TEXT, zrodlo TEXT DEFAULT 'recznie', uid TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS terminy (
  id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, nazwa TEXT NOT NULL, kategoria TEXT,
  co_km REAL, co_mies INTEGER, ostatnio_data TEXT, ostatnio_km REAL, nastepny_data TEXT, nastepny_km REAL,
  aktywny INTEGER DEFAULT 1, powiadomiono TEXT, klucz TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS odczyty (
  id INTEGER PRIMARY KEY, pojazd_id INTEGER NOT NULL, data TEXT NOT NULL, przebieg REAL NOT NULL,
  zrodlo TEXT DEFAULT 'recznie');
CREATE TABLE IF NOT EXISTS ustawienia (klucz TEXT PRIMARY KEY, wartosc TEXT);
"""

POLA = {
    "pojazdy": ["nazwa", "rodzaj", "paliwo", "bak_l", "bateria_kwh", "encja_przebiegu", "l100_bez_pradu",
                "aktywny", "kolejnosc", "klucz"],
    "tankowania": ["pojazd_id", "data", "przebieg", "litry", "cena_l", "kwota", "pelny", "pominiete", "stacja",
                   "notatka", "fuelio_typ", "zrodlo", "uid"],
    "ladowania": ["pojazd_id", "poczatek", "koniec", "kwh", "kwh_pv", "kwh_bateria", "soc_od", "soc_do", "koszt",
                  "koszt_wartosc", "strefy", "miejsce", "przebieg", "zrodlo", "wykluczone", "zmienione", "notatka", "uid"],
    "koszty": ["pojazd_id", "data", "przebieg", "kategoria", "tytul", "kwota", "notatka", "zrodlo", "uid"],
    "terminy": ["pojazd_id", "nazwa", "kategoria", "co_km", "co_mies", "ostatnio_data", "ostatnio_km",
                "nastepny_data", "nastepny_km", "aktywny", "powiadomiono", "klucz"],
    "odczyty": ["pojazd_id", "data", "przebieg", "zrodlo"],
}
SORT = {"pojazdy": "kolejnosc, id", "tankowania": "data DESC, przebieg DESC", "ladowania": "poczatek DESC",
        "koszty": "data DESC", "terminy": "id", "odczyty": "data DESC"}

# Pojazdy na start (Adrian: NT1100 i Eclipse Cross PHEV; bez archiwalnej Hondy).
STARTOWE = [
    {"klucz": "nt1100", "nazwa": "NT1100", "rodzaj": "motocykl", "paliwo": "Pb95", "bak_l": 20.4,
     "encja_przebiegu": "sensor.nt1100_przebieg", "kolejnosc": 2},
    {"klucz": "eclipse", "nazwa": "Eclipse Cross", "rodzaj": "phev", "paliwo": "Pb95", "bak_l": 43,
     "bateria_kwh": 13.8, "l100_bez_pradu": 7.5, "kolejnosc": 1},
]


class Baza:
    def __init__(self, sciezka):
        self.sciezka = sciezka
        self.lock = threading.RLock()
        self.db = sqlite3.connect(sciezka, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            if not self.db.execute("SELECT 1 FROM pojazdy LIMIT 1").fetchone():
                for p in STARTOWE:
                    self.dodaj("pojazdy", p)
            self.db.commit()

    # ---- ogólne
    def lista(self, tabela, **war):
        sql = "SELECT * FROM %s" % tabela
        args = []
        if war:
            sql += " WHERE " + " AND ".join("%s=?" % k for k in war)
            args = list(war.values())
        sql += " ORDER BY " + SORT[tabela]
        with self.lock:
            return [self._wiersz(tabela, r) for r in self.db.execute(sql, args).fetchall()]

    def jeden(self, tabela, id_):
        with self.lock:
            r = self.db.execute("SELECT * FROM %s WHERE id=?" % tabela, (id_,)).fetchone()
        return self._wiersz(tabela, r) if r else None

    def _wiersz(self, tabela, r):
        d = dict(r)
        if tabela == "ladowania" and d.get("strefy"):
            try:
                d["strefy"] = json.loads(d["strefy"])
            except ValueError:
                d["strefy"] = None
        return d

    def _czyste(self, tabela, dane):
        d = {k: dane[k] for k in POLA[tabela] if k in dane}
        if "strefy" in d and isinstance(d["strefy"], dict):
            d["strefy"] = json.dumps(d["strefy"])
        return d

    def dodaj(self, tabela, dane, pomin_istniejace=False):
        """Nowy wiersz -> id (None, gdy uid już jest i pomin_istniejace)."""
        d = self._czyste(tabela, dane)
        sql = "INSERT %sINTO %s (%s) VALUES (%s)" % ("OR IGNORE " if pomin_istniejace else "", tabela,
                                                    ",".join(d), ",".join("?" * len(d)))
        with self.lock:
            c = self.db.execute(sql, list(d.values()))
            self.db.commit()
            return c.lastrowid if c.rowcount else None

    def zmien(self, tabela, id_, dane):
        d = self._czyste(tabela, dane)
        d.pop("uid", None)
        if not d:
            return
        with self.lock:
            self.db.execute("UPDATE %s SET %s WHERE id=?" % (tabela, ",".join("%s=?" % k for k in d)),
                            list(d.values()) + [id_])
            self.db.commit()

    def usun(self, tabela, id_):
        with self.lock:
            self.db.execute("DELETE FROM %s WHERE id=?" % tabela, (id_,))
            self.db.commit()

    def jest_uid(self, tabela, uid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM %s WHERE uid=?" % tabela, (uid,)).fetchone() is not None

    # ---- ustawienia
    def ust(self, klucz, domyslnie=None):
        with self.lock:
            r = self.db.execute("SELECT wartosc FROM ustawienia WHERE klucz=?", (klucz,)).fetchone()
        if not r:
            return domyslnie
        try:
            return json.loads(r[0])
        except ValueError:
            return domyslnie

    def ustaw(self, klucz, wartosc):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO ustawienia (klucz, wartosc) VALUES (?, ?)",
                            (klucz, json.dumps(wartosc, ensure_ascii=False)))
            self.db.commit()

    def kopia(self, cel):
        """Spójna kopia bazy do pliku (działa w trakcie pracy)."""
        with self.lock:
            dst = sqlite3.connect(cel)
            try:
                self.db.backup(dst)
            finally:
                dst.close()
