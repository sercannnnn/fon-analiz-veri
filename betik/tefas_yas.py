#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fon yaşı: TEFAS'ta ilk fiyatlandığı ay (Görev değerlendirmesi 3.2, 11 Eylül 2026). Yalnızca 'requests'; makinede çalışır.

Kuruluş tarihi KAP fon sayfalarında gömülü değildir ve KAP bildirim sorgusu eski dönemleri döndürmez; TEFAS beş yıldan eskiyi vermez. TEFAS fiyat ucu ise
`fonKod` süzgecini yok sayar ve bir aylık pencere için bütün evreni döndürür (11 Eylül 2026'da ölçüldü: Eylül 2024 penceresi
29.411 satır). Dolayısıyla BAS'tan bugüne aylık pencereler çekilerek her fonun ilk fiyat ayı bulunur; bu, kuruluşun resmî
ve ölçülebilir vekilidir (fon TEFAS'ta fiyatlanmaya başladığı ay). BAS'tan önce de var olan fonlar "<= BAS" olarak işaretlenir.

Çıktı: veri/fon_yas.csv  fonKodu, ilkFiyatAyi (YYYY-MM), sinir (kesin | en_gec), kaynak, olcumTarihi
Artımlı: dosya varsa yalnızca bilinmeyen fonlar için son pencereler çekilir; tam tarama --tam ile.
Ara kayıt: her pencereden sonra veri/fon_yas_ara.json yazılır (biten pencereler ve ilk aylar); TEFAS bağlantıyı keserse
(11 Eylül 2026: 33 pencereden sonra 'Connection reset by peer', beş deneme de düştü ve bütün ilerleme kaybedildi) tarama
oradan sürer. Düşen pencere 5 dakika beklenip yeniden denenir; üç kez düşerse betik durur, ara kayıt kalır, sonraki koşu sürdürür.
CSV yalnızca bütün pencereler bittiğinde yazılır; ara kayıt o zaman silinir.
"""
import argparse, csv, json, os, sys, time
from datetime import date, datetime, timedelta
import requests

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tefas_cek as T

# TEFAS başlangıç tarihini beş yıldan eskiye almaz ("Baslangıc Tarihi 5 yıldan eski olamaz", 11 Eylül 2026); pencere bugünden
# beş yıl öncesinin bir hafta sonrasından başlar. O ayda zaten var olan fon "en_gec" (beş yaşından büyük) olarak işaretlenir.
BAS = (date.today() - timedelta(days=5 * 365 - 7)).strftime("%Y%m%d")
ARA = 10             # TEFAS dakikada yaklaşık altı istek
DUSUS_BEKLE = 300    # pencere beş denemede de düşerse (bağlantı sıfırlama) beklenen saniye
DUSUS_AZAMI = 3      # aynı pencere kaç kez düşünce betik durur (ara kayıt kalır)


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
    ara_yol = a.cikti.replace(".csv", "_ara.json")
    ilk, biten = {}, []
    if os.path.exists(ara_yol):
        ara = json.load(open(ara_yol, encoding="utf-8"))
        # yarım kalan tarama kendi başlangıç ve bitiş tarihiyle sürer (BAS her gün kayar; gece yarısını geçen koşu bozulmasın)
        a.bas, bugun, ilk, biten = ara["bas"], ara["bit"], ara["ilk"], ara["biten"]
        print(f"  ara kayıt: {len(biten)} pencere bitmiş, {len(ilk):,} fon; kalan pencereler çekiliyor", file=sys.stderr)
    n = len(biten)
    for pb, pe in pencereler(a.bas, bugun):
        if pb in biten:
            continue
        dusus = 0
        while True:
            try:
                satirlar = T.cek("fonGnlBlgSiraliGetir", pb, pe); break
            except SystemExit as e:
                dusus += 1
                if dusus >= DUSUS_AZAMI:
                    print(f"  {pb}-{pe}: {dusus} kez düştü, betik duruyor; ara kayıt {ara_yol} sonraki koşuda sürdürür", file=sys.stderr)
                    raise SystemExit(str(e))
                print(f"  {pb}-{pe}: düştü ({e}), {DUSUS_BEKLE} sn sonra yeniden", file=sys.stderr)
                time.sleep(DUSUS_BEKLE)
        n += 1
        for x in satirlar:
            f = x.get("fonKodu")
            if not f or not (T._f(x.get("fiyat")) or 0) > 0:
                continue
            t = (x.get("tarih") or "")[:7]
            if f not in ilk or t < ilk[f]:
                ilk[f] = t
        biten.append(pb)
        json.dump(dict(bas=a.bas, bit=bugun, biten=biten, ilk=ilk), open(ara_yol, "w", encoding="utf-8"), ensure_ascii=False)
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
    if os.path.exists(ara_yol):
        os.remove(ara_yol)
    kesin = sum(1 for r in eski.values() if r["sinir"] == "kesin")
    print(f"{a.cikti}: {len(eski):,} fon, ilk ayı kesin {kesin:,}, {bas_ay} öncesinden gelen {len(eski) - kesin:,}; {n} istek")


if __name__ == "__main__":
    main()
