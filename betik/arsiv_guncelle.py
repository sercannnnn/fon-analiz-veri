#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gunluk TEFAS fiyat CSV'lerini aylik gzip arsivine isler. Yalnizca standart kutuphane.

Kullanim:
  arsiv_guncelle.py --arsiv <klasor> <csv> [<csv> ...]

Her girdi dosyasi tarih,fonKodu,fiyat,kisiSayisi,portfoyBuyukluk,tedPaySayisi semasindadir.
Girdilerin dokundugu her ay icin <arsiv>/tefas_YYYY-MM.csv.gz yeniden yazilir:
mevcut arsiv + yeni satirlar birlestirilir, (tarih, fonKodu) tekilligi saglanir
(sonra gelen dosya kazanir), tarih ve fon koduna gore siralanir. Dokunulmayan aylar
degismez. gzip zaman damgasi sifirlanir; icerik ayniysa dosya bayt bayt ayni kalir.
"""
import argparse, csv, gzip, io, os, sys
from collections import defaultdict

ALANLAR = ["tarih", "fonKodu", "fiyat", "kisiSayisi", "portfoyBuyukluk", "tedPaySayisi"]
# --tur dagilim: alanlar girdi dosyasinin basligindan alinir (tarih, fonKodu + 56 kod); dosya adi tefas_dagilim_YYYY-MM.csv.gz


def oku(yol, alanlar=None):
    ac = gzip.open if yol.endswith(".gz") else open
    with ac(yol, "rt", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        alanlar = alanlar or ALANLAR
        for s in r:
            t = (s.get("tarih") or "").strip()
            if len(t) != 10 or t == "tarih" or not s.get("fonKodu"):
                continue
            yield t, s["fonKodu"].strip(), [s.get(k, "") or "" for k in alanlar]


def yaz(yol, satirlar, alanlar=None):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(alanlar or ALANLAR)
    for anahtar in sorted(satirlar):
        w.writerow(satirlar[anahtar])
    veri = buf.getvalue().encode("utf-8")
    with open(yol, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(veri)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", required=True)
    ap.add_argument("--tur", default="fiyat", choices=["fiyat", "dagilim"])
    ap.add_argument("csv", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.arsiv, exist_ok=True)
    onek = "tefas" if a.tur == "fiyat" else "tefas_dagilim"
    alanlar = ALANLAR
    if a.tur == "dagilim":
        with open(a.csv[0], encoding="utf-8", newline="") as f:
            alanlar = next(csv.reader(f))

    yeni = defaultdict(dict)                      # ay -> {(tarih, fon): satir}
    for yol in a.csv:
        n = 0
        for t, k, satir in oku(yol, alanlar):
            yeni[t[:7]][(t, k)] = satir
            n += 1
        print(f"  {os.path.basename(yol)}: {n:,} satir", file=sys.stderr)

    for ay in sorted(yeni):
        yol = os.path.join(a.arsiv, f"{onek}_{ay}.csv.gz")
        birlesik = {}
        if os.path.exists(yol):
            for t, k, satir in oku(yol, alanlar):
                birlesik[(t, k)] = satir
        onceki = len(birlesik)
        birlesik.update(yeni[ay])
        yaz(yol, birlesik, alanlar)
        gunler = sorted({t for t, _ in birlesik})
        print(f"{yol}: {len(birlesik):,} satir ({onceki:,} mevcut), {len(gunler)} gun, "
              f"{gunler[0]} .. {gunler[-1]}, {os.path.getsize(yol)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
