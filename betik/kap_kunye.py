#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KAP fon kunyesi. Butun fon tiplerini, faal ve kapanmis fonlari ceker,
veri/fon_kunye_kap.csv yazar. Yalnizca 'requests' ister; kategori icin yanindaki kategori.py.

Sema: fonKodu,fonUnvan,fonTipi,fonSinifi,durum,kurucu,fundOid,kategori,kategoriKaynak
  durum: faal | kapanmis (KAP fundState Y | T)
  kategori: KAP'ta semsiye turu alani yoktur; kategori_turet() unvandan uretir, kaynak 'unvan'.
            KAP ileride verirse kaynak 'kap' yazilir.
"""
import argparse, csv, os, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kategori import kategori_turet

KOK_UC = "https://www.kap.org.tr/tr/api/"
BASLIK = {"User-Agent": "Mozilla/5.0 (fon-analiz kunye)", "Accept": "application/json", "Accept-Language": "tr"}
ALANLAR = ["fonKodu", "fonUnvan", "fonTipi", "fonSinifi", "durum", "kurucu", "fundOid", "kategori", "kategoriKaynak"]


def al(yol, deneme=3):
    for i in range(deneme):
        try:
            r = requests.get(KOK_UC + yol, headers=BASLIK, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  {yol}: deneme {i+1} basarisiz: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise SystemExit(f"KAP'tan alinamadi: {yol}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "veri"))
    a = ap.parse_args()
    os.makedirs(a.cikti, exist_ok=True)

    tipler = [x["value"] for x in al("params/DS_FUNDS_TYPES")]
    satirlar, gorulen = [], set()
    for tip in tipler:
        for durum_kodu, durum in (("Y", "faal"), ("T", "kapanmis")):
            time.sleep(1)
            liste = al(f"fund/criteria/{tip}/{durum_kodu}")
            n = 0
            for f in liste:
                kod = (f.get("fundCode") or "").strip()
                oid = f.get("fundOid") or ""
                if not kod or (kod, oid) in gorulen:
                    continue
                gorulen.add((kod, oid))
                unvan = (f.get("fundName") or "").strip()
                kat = f.get("fundCategory") or f.get("umbrellaType") or ""
                if kat:
                    kaynak = "kap"
                else:
                    kat, kaynak = kategori_turet(unvan), "unvan"
                satirlar.append([kod, unvan, f.get("fundType") or tip, f.get("fundClass") or "",
                                 durum, (f.get("title") or "").strip(), oid, kat, kaynak])
                n += 1
            print(f"  {tip}/{durum}: {n:,} fon", file=sys.stderr)

    satirlar.sort(key=lambda s: (s[4] != "faal", s[0]))
    yol = os.path.join(a.cikti, "fon_kunye_kap.csv")
    with open(yol, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(ALANLAR)
        w.writerows(satirlar)
    faal = sum(1 for s in satirlar if s[4] == "faal")
    kaynaklar = {}
    for s in satirlar:
        kaynaklar[s[8]] = kaynaklar.get(s[8], 0) + 1
    print(f"{yol}: {len(satirlar):,} fon, {faal:,} faal, {len(satirlar)-faal:,} kapanmis, "
          f"kategoriKaynak {kaynaklar}, tipler {tipler}")


if __name__ == "__main__":
    main()
