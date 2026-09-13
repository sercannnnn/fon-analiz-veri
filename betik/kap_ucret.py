#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fon yönetim ücreti (giriş kapısı 4 için). Kaynak: KAP fon bilgi sayfası, 'Genel Bilgiler' sekmesi,
https://www.kap.org.tr/tr/fon-bilgileri/genel/<fundOid> (sunucuda üretilir, kabuktan gelir; TEFAS'ın detay sayfası ücreti
göstermez ve F5 korumasındadır, 11 Eylül 2026). Yalnızca 'requests'.

Sayfa verisi gömülüdür: "uygulananYonetimUcretiOranYillikYuzde":"1" gibi. Alanlar:
  uygulanan yıllık yönetim ücreti (%), içtüzükteki yıllık oran (%), performans ücreti oranı, giriş ve çıkış komisyonu.

Artımlı: veri/fon_ucret.csv içinde YENILEME_GUN'den yeni kaydı olan fon atlanır; günde en fazla --butce sayfa çekilir
(sayfa 300 KB, istekler arası ARA saniye). Evren yaklaşık 2.150 fon; 150 sayfa/gün ile iki haftada tamamlanır, sonra aylık yenilenir.

Çekim sırası (M52, 13 Eylül 2026): alfabetik değil ihtiyaca göre. Varsayılan sıra büyüklüğe göredir (veri/son_gunluk.csv son gündeki
portfoyBuyukluk, büyükten küçüğe): tutulan pozisyonlar, park adayları (≥ 5 milyar TL) ve parlayan fon adayları büyük fonlardır ve ilk
turlarda kapsanır; portföy kodları kamuya açık depoya yazılmadan aynı ihtiyaç karşılanır. İsteğe bağlı --oncelik dosyası (satır başına
kod; yerel, depoya girmez) en öne alınır. --sira alfabetik eski davranıştır.

Kullanım: kap_ucret.py [--kunye veri/fon_kunye_kap.csv] [--cikti veri/fon_ucret.csv] [--butce 150] [--fon KOD1,KOD2] [--sira buyukluk|alfabetik] [--oncelik dosya]
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


def buyukluk_oku(yol):
    """veri/son_gunluk.csv: fonKodu -> son gündeki portfoyBuyukluk (TL); dosya yoksa boş sözlük."""
    if not yol or not os.path.exists(yol):
        return {}
    son, buy = {}, {}
    for r in csv.DictReader(open(yol, encoding="utf-8")):
        try:
            b = float(r.get("portfoyBuyukluk") or 0)
        except ValueError:
            continue
        if r.get("tarih", "") >= son.get(r["fonKodu"], ""):
            son[r["fonKodu"]] = r["tarih"]; buy[r["fonKodu"]] = b
    return buy


def sira_belirle(kunye, eski, esik, butce, buyukluk=None, oncelik=(), sira="buyukluk"):
    """Bu turda çekilecek fonlar (M52): yenilemesi dolmuş olanlar arasında önce --oncelik listesi, sonra büyüklüğe göre büyükten küçüğe
    (büyüklüğü bilinmeyen en sona, kendi içinde alfabetik); sira='alfabetik' eski davranış."""
    bekleyen = [f for f in kunye if not eski.get(f) or eski[f]["tarih"] < esik]
    oncelik = [f for f in oncelik if f in kunye]
    if sira == "alfabetik":
        kalan = sorted(f for f in bekleyen if f not in oncelik)
    else:
        buyukluk = buyukluk or {}
        kalan = sorted((f for f in bekleyen if f not in oncelik), key=lambda f: (-(buyukluk.get(f) or 0), f))
    return ([f for f in oncelik if f in bekleyen] + kalan)[:butce]


def main():
    ap = argparse.ArgumentParser()
    kok = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    ap.add_argument("--kunye", default=os.path.join(kok, "veri", "fon_kunye_kap.csv"))
    ap.add_argument("--cikti", default=os.path.join(kok, "veri", "fon_ucret.csv"))
    ap.add_argument("--butce", type=int, default=150)
    ap.add_argument("--fon", help="virgülle fon kodları; yalnızca bunlar, yenileme süresine bakılmaz")
    ap.add_argument("--sira", default="buyukluk", choices=["buyukluk", "alfabetik"], help="çekim sırası (M52): büyüklüğe göre ya da alfabetik")
    ap.add_argument("--oncelik", default=None, help="satır başına fon kodu; en öne alınır (yerel dosya, depoya girmez)")
    ap.add_argument("--son-gunluk", default=os.path.join(kok, "veri", "son_gunluk.csv"), help="büyüklük sırası için günlük çekim dosyası")
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
        onc = [s.strip().split()[0] for s in open(a.oncelik, encoding="utf-8") if s.strip() and not s.startswith("#")] if a.oncelik and os.path.exists(a.oncelik) else []
        sira = sira_belirle(kunye, eski, esik, a.butce, buyukluk=buyukluk_oku(a.son_gunluk), oncelik=onc, sira=a.sira)
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
