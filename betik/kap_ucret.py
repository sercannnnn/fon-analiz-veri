#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fon yönetim ücreti (giriş kapısı 4 için). Kaynak: KAP fon bilgi sayfası, 'Genel Bilgiler' sekmesi,
https://www.kap.org.tr/tr/fon-bilgileri/genel/<fundOid> (sunucuda üretilir, kabuktan gelir; TEFAS'ın detay sayfası ücreti
göstermez ve F5 korumasındadır, 11 Eylül 2026). Yalnızca 'requests'.

Sayfa verisi gömülüdür: "uygulananYonetimUcretiOranYillikYuzde":"1" gibi. Alanlar:
  uygulanan yıllık yönetim ücreti (%), içtüzükteki yıllık oran (%), performans ücreti oranı, giriş ve çıkış komisyonu.

Artımlı: veri/fon_ucret.csv içinde YENILEME_GUN'den yeni kaydı olan fon atlanır; günde en fazla --butce sayfa çekilir
(sayfa 300 KB, istekler arası ARA saniye). Evren yaklaşık 2.150 fon; 150 sayfa/gün ile iki haftada tamamlanır, sonra aylık yenilenir.

Kullanım: kap_ucret.py [--kunye veri/fon_kunye_kap.csv] [--cikti veri/fon_ucret.csv] [--butce 150] [--fon KOD1,KOD2]
"""
import argparse, csv, os, re, sys, time
from datetime import date, datetime, timedelta
import requests

KAP = "https://www.kap.org.tr/tr/fon-bilgileri/genel/"
BASLIK = {"User-Agent": "Mozilla/5.0 (fon-analiz ucret)", "Accept": "text/html"}
ARA = 2.5
YENILEME_GUN = 30
ALANLAR = ["fonKodu", "yonetimUcretiYillik", "ictuzukYonetimUcretiYillik", "yonetimUcretiGunluk", "performansUcreti",
           "girisKomisyonu", "cikisKomisyonu", "tarih", "kaynak"]
ANAHTAR = {"yonetimUcretiYillik": "uygulananYonetimUcretiOranYillikYuzde", "ictuzukYonetimUcretiYillik": "ictuzukteYerAlanYonetimUcretiOraniYillikYuzde",
           "yonetimUcretiGunluk": "uygulananYonetimUcretiOraniGunlukYuzde", "performansUcreti": "performansUcretiOrani",
           "girisKomisyonu": "girisKomisyonu", "cikisKomisyonu": "cikisKomisyonu"}


def _deger(html, anahtar):
    """Gömülü RSC verisinde \"anahtar\":\"deger\" ya da \"anahtar\":null; ilk değerli geçiş alınır."""
    for m in re.finditer(r'\\"' + anahtar + r'\\":(\\"([^\\"]*)\\"|null)', html):
        if m.group(2) is not None:
            return m.group(2).strip()
    return ""


def sayi(s):
    """'0,00274' -> 0.00274; boş ya da metin ise None."""
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", ".")) if s.count(",") == 1 else float(s)
    except ValueError:
        return None


def cek(oid, deneme=3):
    for i in range(deneme):
        try:
            r = requests.get(KAP + oid, headers=BASLIK, timeout=120)
            if r.status_code == 429:
                raise RuntimeError("HTTP 429")
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  {oid[:8]}: deneme {i+1} {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(10 * (i + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    kok = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    ap.add_argument("--kunye", default=os.path.join(kok, "veri", "fon_kunye_kap.csv"))
    ap.add_argument("--cikti", default=os.path.join(kok, "veri", "fon_ucret.csv"))
    ap.add_argument("--butce", type=int, default=150)
    ap.add_argument("--fon", help="virgülle fon kodları; yalnızca bunlar, yenileme süresine bakılmaz")
    a = ap.parse_args()
    kunye = {r["fonKodu"]: r for r in csv.DictReader(open(a.kunye, encoding="utf-8"))
             if r.get("durum", "faal") == "faal" and r.get("fonTipi", "YF") == "YF"}   # yalnizca yatirim fonlari (2.146); BYF ve digerleri disarida
    eski = {}
    if os.path.exists(a.cikti):
        eski = {r["fonKodu"]: r for r in csv.DictReader(open(a.cikti, encoding="utf-8"))}
    esik = (date.today() - timedelta(days=YENILEME_GUN)).isoformat()
    if a.fon:
        sira = [f for f in a.fon.split(",") if f in kunye]
    else:
        sira = sorted(f for f in kunye if not eski.get(f) or eski[f]["tarih"] < esik)[:a.butce]
    bugun = date.today().isoformat(); n_ok = n_hata = 0
    for f in sira:
        html = cek(kunye[f]["fundOid"])
        time.sleep(ARA)
        if not html or "fon-bilgileri" not in html:
            n_hata += 1; continue
        kayit = {"fonKodu": f, "tarih": bugun, "kaynak": "KAP genel bilgiler"}
        for alan, anah in ANAHTAR.items():
            kayit[alan] = _deger(html, anah)
        eski[f] = kayit; n_ok += 1
    with open(a.cikti, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ALANLAR, lineterminator="\n"); w.writeheader()
        for f in sorted(eski):
            w.writerow({k: eski[f].get(k, "") for k in ALANLAR})
    dolu = sum(1 for r in eski.values() if r.get("yonetimUcretiYillik"))
    print(f"{a.cikti}: bu tur {n_ok} fon çekildi, {n_hata} hata; toplam {len(eski)} kayıt, {dolu} fonda yıllık ücret dolu; "
          f"kalan {len([f for f in kunye if not eski.get(f) or eski[f]['tarih'] < esik])}")


if __name__ == "__main__":
    main()
