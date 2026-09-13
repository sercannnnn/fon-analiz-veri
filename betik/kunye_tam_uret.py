#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kamuya açık fon künyesini üretir: veri/kunye_tam.csv (M47, 13 Eylül 2026).

Bulut parlayan fon ekranı künyeyi <kok>/veri/kunye_tam.csv yolundan okur; dosya depoda yoktu ve ekran çöküyordu. Künye
betik_esitle.sh ile gönderilemez (bütün fon kodlarını içerir, gizlilik taraması yasak deseni yakalar); sanal makinenin günlük
gönderimiyle taşınır. İçerik TEFAS ve KAP'ın kendi yayımladığı kamuya açık alanlardır, portföy bilgisi taşımaz.

Kaynaklar ve alan sırası:
  fonKodu, fonAd   : veri/son_gunluk.csv (fonUnvan); yoksa önceki kunye_tam.csv
  kategori         : önceki kunye_tam.csv (TEFAS künyesi, yetkili); yoksa KAP künyesi (veri/fon_kunye_kap.csv); yoksa unvandan türetme (kategori.py)
  kurucu           : KAP künyesi; yoksa önceki kunye_tam.csv
  riskDegeri, g1y, g3y, g5y, semsiye : önceki kunye_tam.csv'den taşınır (TEFAS Excel dışa aktarımından gelir; makinede kaynağı yok),
                     yeni fonda boş kalır ve park ölçütü onu risk şartından eler (boş risk kabul edilmez)
Çıktı şeması Mac'teki 'Fon Künyesi Tam' dosyasıyla aynıdır: fonKodu,fonAd,kategori,semsiye,kurucu,riskDegeri,g1y,g3y,g5y.
Yalnızca standart kütüphane.
"""
import argparse, csv, os, sys
try:
    from kategori import kategori_turet
except Exception:   # kategori.py yanında değilse unvandan türetme yapılmaz
    kategori_turet = None

ALANLAR = ["fonKodu", "fonAd", "kategori", "semsiye", "kurucu", "riskDegeri", "g1y", "g3y", "g5y"]


def oku(yol):
    if not yol or not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def uret(son_gunluk, kap_kunye, onceki, cikti):
    eski = {r["fonKodu"]: r for r in oku(onceki) if r.get("fonKodu")}
    kap = {r["fonKodu"]: r for r in oku(kap_kunye) if r.get("fonKodu")}
    unvan = {}
    for r in oku(son_gunluk):
        if r.get("fonKodu") and r.get("fonUnvan"):
            unvan[r["fonKodu"]] = r["fonUnvan"]
    kodlar = sorted(set(eski) | set(unvan))
    satirlar, yeni, turetilen = [], 0, 0
    for kod in kodlar:
        e = eski.get(kod, {}); k = kap.get(kod, {})
        ad = unvan.get(kod) or e.get("fonAd") or k.get("fonUnvan") or ""
        kat = e.get("kategori") or k.get("kategori") or ""
        if not kat and kategori_turet and ad:
            kat = kategori_turet(ad) or ""; turetilen += 1
        satirlar.append(dict(fonKodu=kod, fonAd=ad, kategori=kat, semsiye=e.get("semsiye", ""), kurucu=k.get("kurucu") or e.get("kurucu", ""),
                             riskDegeri=e.get("riskDegeri", ""), g1y=e.get("g1y", ""), g3y=e.get("g3y", ""), g5y=e.get("g5y", "")))
        if kod not in eski:
            yeni += 1
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    with open(cikti, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ALANLAR); w.writeheader(); w.writerows(satirlar)
    return dict(fon=len(satirlar), yeni=yeni, turetilen=turetilen, riskli=sum(1 for s in satirlar if s["riskDegeri"] not in ("", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri")
    ap.add_argument("--cikti", default=None, help="varsayılan <veri>/kunye_tam.csv; önceki sürüm de buradan okunur")
    a = ap.parse_args()
    cikti = a.cikti or os.path.join(a.veri, "kunye_tam.csv")
    oz = uret(os.path.join(a.veri, "son_gunluk.csv"), os.path.join(a.veri, "fon_kunye_kap.csv"), cikti, cikti)
    print(f"kunye_tam.csv: {oz['fon']} fon, yeni {oz['yeni']}, unvandan türetilen kategori {oz['turetilen']}, risk değeri olan {oz['riskli']}")


if __name__ == "__main__":
    main()
