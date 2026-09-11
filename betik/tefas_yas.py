#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fon yaşı: TEFAS'ta ilk fiyatlandığı ay (Görev değerlendirmesi 3.2, 11 Eylül 2026). Yalnızca 'requests'; makinede çalışır.

Kuruluş tarihi KAP fon sayfalarında gömülü değildir ve KAP bildirim sorgusu eski dönemleri döndürmez. TEFAS fiyat ucu ise
`fonKod` süzgecini yok sayar ve bir aylık pencere için bütün evreni döndürür (11 Eylül 2026'da ölçüldü: Eylül 2024 penceresi
29.411 satır). Dolayısıyla BAS'tan bugüne aylık pencereler çekilerek her fonun ilk fiyat ayı bulunur; bu, kuruluşun resmî
ve ölçülebilir vekilidir (fon TEFAS'ta fiyatlanmaya başladığı ay). BAS'tan önce de var olan fonlar "<= BAS" olarak işaretlenir.

Çıktı: veri/fon_yas.csv  fonKodu, ilkFiyatAyi (YYYY-MM), sinir (kesin | en_gec), kaynak, olcumTarihi
Artımlı: dosya varsa yalnızca bilinmeyen fonlar için son pencereler çekilir; tam tarama --tam ile.
"""
import argparse, csv, os, sys, time
from datetime import date, datetime, timedelta
import requests

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tefas_cek as T

BAS = "20180101"
ARA = 10             # TEFAS dakikada yaklaşık altı istek


def pencereler(bas, bit):
    b = datetime.strptime(bas, "%Y%m%d").date(); s = datetime.strptime(bit, "%Y%m%d").date()
    while b <= s:
        e = min(b + timedelta(days=27), s)
        yield b.strftime("%Y%m%d"), e.strftime("%Y%m%d")
        b = e + timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", default=os.path.join(KOK, "veri", "fon_yas.csv"))
    ap.add_argument("--bas", default=BAS)
    ap.add_argument("--tam", action="store_true", help="dosyayı yok sayıp bütün pencereleri yeniden çek")
    a = ap.parse_args()
    eski = {}
    if os.path.exists(a.cikti) and not a.tam:
        eski = {r["fonKodu"]: r for r in csv.DictReader(open(a.cikti, encoding="utf-8"))}
    bugun = date.today().strftime("%Y%m%d")
    ilk = {}
    n = 0
    for pb, pe in pencereler(a.bas, bugun):
        satirlar = T.cek("fonGnlBlgSiraliGetir", pb, pe)
        n += 1
        ay = pb[:4] + "-" + pb[4:6]
        for x in satirlar:
            f = x.get("fonKodu")
            if not f or not (T._f(x.get("fiyat")) or 0) > 0:
                continue
            t = (x.get("tarih") or "")[:7]
            if f not in ilk or t < ilk[f]:
                ilk[f] = t
        print(f"  {pb}-{pe}: {len(satirlar):,} satır, bilinen fon {len(ilk):,}", file=sys.stderr)
        time.sleep(ARA)
    bas_ay = a.bas[:4] + "-" + a.bas[4:6]
    bugun_t = date.today().isoformat()
    for f, t in ilk.items():
        eski[f] = dict(fonKodu=f, ilkFiyatAyi=t, sinir=("en_gec" if t == bas_ay else "kesin"), kaynak=f"TEFAS fiyat serisi, {n} aylık pencere {bas_ay}..{bugun_t[:7]}", olcumTarihi=bugun_t)
    with open(a.cikti, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["fonKodu", "ilkFiyatAyi", "sinir", "kaynak", "olcumTarihi"], lineterminator="\n"); w.writeheader()
        for f in sorted(eski):
            w.writerow(eski[f])
    kesin = sum(1 for r in eski.values() if r["sinir"] == "kesin")
    print(f"{a.cikti}: {len(eski):,} fon, ilk ayı kesin {kesin:,}, {bas_ay} öncesinden gelen {len(eski) - kesin:,}; {n} istek")


if __name__ == "__main__":
    main()
