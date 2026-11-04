#!/usr/bin/env python3
"""Pusty plik „water polygons” (shapefile w zipie, EPSG:3857) dla Planetilera.

Zapas, gdy osmdata.openstreetmap.de nie odpowiada: mapa buduje się bez
wypełnienia morza na dużych powiększeniach (jeziora i rzeki są z danych OSM).
Użycie: pusta_woda.py WYJSCIE.zip
"""
import struct
import sys
import zipfile

PRJ = ('PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
       'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
       'PROJECTION["Mercator_Auxiliary_Sphere"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
       'PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],'
       'PARAMETER["Auxiliary_Sphere_Type",0.0],UNIT["Meter",1.0]]')


def shp_header():
    # kod pliku 9994, długość w słowach 16-bit (sam nagłówek = 50), wersja 1000, typ 5 = wielokąt
    return struct.pack(">7i", 9994, 0, 0, 0, 0, 0, 50) + struct.pack("<2i8d", 1000, 5, 0, 0, 0, 0, 0, 0, 0, 0)


def dbf():
    field = b"FID".ljust(11, b"\0") + b"N" + b"\0" * 4 + bytes([9, 0]) + b"\0" * 14
    head_len = 32 + 32 + 1
    head = struct.pack("<BBBBIHH20x", 3, 126, 11, 4, 0, head_len, 10)
    return head + field + b"\r" + b"\x1a"


def main(out):
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("water-polygons-split-3857/water_polygons.shp", shp_header())
        z.writestr("water-polygons-split-3857/water_polygons.shx", shp_header())
        z.writestr("water-polygons-split-3857/water_polygons.dbf", dbf())
        z.writestr("water-polygons-split-3857/water_polygons.prj", PRJ)


if __name__ == "__main__":
    main(sys.argv[1])
