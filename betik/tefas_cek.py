#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEFAS gunluk cekici. Tarayici gerektirmez; yalnizca 'requests' kullanir.
Sistem python3 ile calisir, sanal ortam gerekmez.

Kullanim:
  tefas_cek.py                                 son 10 gunu ceker, iki ucu da
  tefas_cek.py --bas 20250227 --bit 20250901   verilen araligi aylik parcalarla ceker
  tefas_cek.py --uc fiyat                      yalnizca fiyat ucu (fiyat | dagilim | hepsi)
  tefas_cek.py --cikti /yol/veri               CSV'lerin yazilacagi klasor

Ciktilar:
  <cikti>/tefas_gunluk_<bit>.csv    tarih,fonKodu,fiyat,kisiSayisi,portfoyBuyukluk,tedPaySayisi
  <cikti>/tefas_dagilim_<bit>.csv   tarih,fonKodu + 56 varlik sinifi agirligi (yuzde)
"""
import argparse, csv, os, sys, time
from datetime import date, datetime, timedelta
import requests

KOK_UC = "https://www.tefas.gov.tr/api/funds/"
BASLIK = {
    "Content-Type": "application/json",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
    "User-Agent": "Mozilla/5.0 (fon-analiz cekici)",
}

# Fiyat ucu
FIYAT_ALAN = ["tarih", "fonKodu", "fiyat", "kisiSayisi", "portfoyBuyukluk", "tedPaySayisi"]

# Dagilim ucu: TEFAS'in 56 varlik sinifi kodu. Sira sabittir, CSV basligi budur.
# Onemli olanlar: hs hisse senedi, tr ters repo, r repo (eksi = borclanma),
# vmtl vadeli mevduat TL, vmd vadeli mevduat doviz, dt devlet tahvili,
# ost ozel sektor tahvili, kh kiymetli maden, yyf yabanci yatirim fonu, yhs yabanci hisse.
DAGILIM_ALAN = ["tarih", "fonKodu",
    "bb", "byf", "d", "db", "bpp", "btaa", "btas", "dt", "dot", "eut", "fb", "fkb",
    "gas", "gsykb", "gsyy", "gykb", "gyy", "hb", "hs", "kba", "kh", "khau", "khd",
    "khtl", "kks", "kksd", "kkstl", "kksyd", "km", "kmbyf", "kmkba", "kmkks", "kibd",
    "osks", "ost", "r", "t", "tpp", "tr", "vdm", "vm", "vmau", "vmd", "vmtl", "vint",
    "yba", "ybkb", "ybosb", "ybyf", "yhs", "ymk", "yyf", "oksyd", "osdb"]

UCLAR = {
    "fiyat":   ("fonGnlBlgSiraliGetir", FIYAT_ALAN,   "tefas_gunluk_{}.csv"),
    "dagilim": ("dagilimSiraliGetirT",  DAGILIM_ALAN, "tefas_dagilim_{}.csv"),
}


def govde(bas, bit):
    return {
        "dil": "TR", "fonTipi": "YAT", "fonKod": None, "fonGrup": None,
        "basTarih": bas, "bitTarih": bit, "fonTurKod": None, "fonUnvanTip": None,
        "kurucuKod": None, "fonTurAciklama": None, "sfonTurKod": None,
        "basSira": 1, "bitSira": 200000, "sira": "tarih", "yon": "ASC",
    }


def cek(uc, bas, bit, deneme=3):
    """Tek aralik icin satirlari dondurur. Hata olursa uc kez dener."""
    for i in range(deneme):
        try:
            r = requests.post(KOK_UC + uc, json=govde(bas, bit), headers=BASLIK, timeout=180)
            r.raise_for_status()
            j = r.json()
            if j.get("errorMessage"):
                raise RuntimeError(j["errorMessage"])
            return j.get("resultList") or []
        except Exception as e:
            print(f"  deneme {i+1}/{deneme} basarisiz ({uc} {bas}-{bit}): {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise SystemExit(f"cekim basarisiz: {uc} {bas}-{bit}")


def aylik_parcalar(bas, bit):
    """TEFAS tek istekte azami bir ay verir; araligi aylik parcalara boler."""
    b = datetime.strptime(bas, "%Y%m%d").date()
    s = datetime.strptime(bit, "%Y%m%d").date()
    while b <= s:
        e = min(b + timedelta(days=30), s)
        yield b.strftime("%Y%m%d"), e.strftime("%Y%m%d")
        b = e + timedelta(days=1)


def uc_calistir(ad, bas, bit, cikti):
    uc, alanlar, dosya = UCLAR[ad]
    satirlar, gorulen = [], set()
    for pb, pe in aylik_parcalar(bas, bit):
        t0 = time.time()
        parca = cek(uc, pb, pe)
        for x in parca:
            anahtar = (x["tarih"], x["fonKodu"])
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            satirlar.append([x.get(k) if x.get(k) is not None else "" for k in alanlar])
        print(f"  {ad} {pb}-{pe}: {len(parca):,} satir, {time.time()-t0:.1f} s", file=sys.stderr)

    if not satirlar:
        raise SystemExit(f"{ad}: hic satir gelmedi; rapor uretilmemeli")

    yol = os.path.join(cikti, dosya.format(bit))
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(alanlar)
        w.writerows(satirlar)

    tarihler = sorted({s[0] for s in satirlar})
    fonlar = {s[1] for s in satirlar}
    print(f"{yol}: {len(satirlar):,} satir, {len(fonlar):,} fon, "
          f"{len(tarihler)} gun ({tarihler[0]} .. {tarihler[-1]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", help="yyyyMMdd, varsayilan: bugun - 10 gun")
    ap.add_argument("--bit", help="yyyyMMdd, varsayilan: bugun")
    ap.add_argument("--uc", default="hepsi", choices=["fiyat", "dagilim", "hepsi"])
    ap.add_argument("--cikti", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "veri"))
    a = ap.parse_args()

    bugun = date.today()
    bit = a.bit or bugun.strftime("%Y%m%d")
    bas = a.bas or (bugun - timedelta(days=10)).strftime("%Y%m%d")
    os.makedirs(a.cikti, exist_ok=True)

    for ad in (["fiyat", "dagilim"] if a.uc == "hepsi" else [a.uc]):
        uc_calistir(ad, bas, bit, a.cikti)


if __name__ == "__main__":
    main()
