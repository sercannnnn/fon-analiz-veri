#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hisse temel verisi: veri/temel_veri.csv (68 numaralı not, bölüm 4; 15 Eylül 2026). Yalnızca standart kütüphane.

Kaynak İş Yatırım mali tablo ucu (kimliksiz, Mac'ten ve makineden 200 döner; 15 Eylül 2026'da ölçüldü):
  https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo?companyCode=<kod>&exchange=TRY&financialGroup=XI_29&year1=..&period1=..
Dört dönem istenir: son ara dönem (birikimli), önceki yıl sonu, önceki yılın aynı ara dönemi, önceki yıl 9. ay. Son dört çeyrek akış kalemi =
son ara dönem + önceki yıl sonu − önceki yılın aynı ara dönemi. Bilanço kalemleri son dönemden. financialGroup XI_29 sanayi ve hizmet
şirketleri; boş dönerse UFRS (banka) denenir, bankada dönen varlık ve kısa vadeli yükümlülük yoktur (cari oran ölçülemedi).
Pay sayısı = ödenmiş sermaye (nominal 1 TL VARSAYIMI; sütun paySayisiKaynak bunu yazar). Her kalem bulunamadıysa boş kalır ve oran ölçülemedi olur.
Şema: bistKodu,paySayisi,paySayisiKaynak,ozkaynak,netKar4C,netBorc,favok4C,donenVarlik,kvYukumluluk,donem,grup,kaynak,olcumTarihi
Çalıştırma: temel_cek.py --liste veri/hisse_evren_icerik.txt [--liste veri/bist100.txt] --cikti veri --ara 1.2 --butce 600
Kapsam ölçümü (15 Eylül 2026, tutulan fonların 85 hissesi): 76 sanayi tam, 7 banka (UFRS) yalnızca özkaynak ve net kâr, 2 faktoring tablosuz."""
import argparse, csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import date

UC = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo"
ALANLAR = ["bistKodu", "paySayisi", "paySayisiKaynak", "ozkaynak", "netKar4C", "netBorc", "favok4C", "donenVarlik", "kvYukumluluk", "donem", "grup", "kaynak", "olcumTarihi"]
# kalem -> açıklama başlangıçları (İş Yatırım Türkçe açıklaması); banka tablosunda (UFRS) adlar farklıdır
KALEM = {"ozkaynak": ["Özkaynaklar", "ÖZKAYNAKLAR", "Toplam Özkaynaklar"], "donenVarlik": ["Dönen Varlıklar"], "kvYukumluluk": ["Kısa Vadeli Yükümlülükler"],
         "nakit": ["Nakit ve Nakit Benzerleri"], "borcKV": ["Kısa Vadeli Borçlanmalar", "Finansal Borçlar"], "borcUV": ["Uzun Vadeli Borçlanmalar"],
         "netKar": ["Dönem Net Kar/Zararı", "DÖNEM NET KARI", "Net Dönem Karı", "Dönem Karı (Zararı)", "Ana Ortaklık Payları", "DÖNEM NET KAR/ZARARI", "NET DÖNEM KARI/ZARARI", "Dönem Net Karı"],
         "faaliyetKari": ["Esas Faaliyet Karı", "ESAS FAALİYET KARI", "Faaliyet Karı"], "amortisman": ["Amortisman"], "odenmisSermaye": ["Ödenmiş Sermaye"]}
AKIS = {"netKar", "faaliyetKari", "amortisman"}     # son dört çeyrek toplamı hesaplanır


def donemler(bugun):
    """Son ara dönem (yayımlanmış olması beklenen): ay 1-3 → önceki yıl 12; 4-5 → 12; 6-8 → 3; 9-11 → 6; 12 → 9. Dönüş [(yıl, ay)] dört dönem."""
    y, m = bugun.year, bugun.month
    if m <= 5:
        son = (y - 1, 12)
    elif m <= 8:
        son = (y, 3)
    elif m <= 11:
        son = (y, 6)
    else:
        son = (y, 9)
    if son[1] == 12:
        return [son, (son[0] - 1, 12), (son[0] - 1, 9), (son[0] - 1, 6)]
    return [son, (son[0] - 1, 12), (son[0] - 1, son[1]), (son[0] - 1, 9)]


def cek(kod, grup, dl, ara=1.2):
    q = dict(companyCode=kod, exchange="TRY", financialGroup=grup)
    for i, (y, p) in enumerate(dl, start=1):
        q[f"year{i}"] = y; q[f"period{i}"] = p
    req = urllib.request.Request(UC + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "Mozilla/5.0"})
    try:
        j = json.load(urllib.request.urlopen(req, timeout=40))
    except Exception:
        return None
    time.sleep(ara)
    return j.get("value") or []


def _sayi(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


import re as _re
NUMARA = _re.compile(r"^[IVXLC]+\.\s*|^\d+(\.\d+)*\.?\s*")   # banka tablosu (UFRS): "XVI. ÖZKAYNAKLAR", "16.1 Ödenmiş Sermaye"


def ayikla(v):
    """Tablo satırlarından kalem -> [dönem1, dönem2, dönem3, dönem4] değerleri. Numara önekleri atılır (banka tablosu)."""
    out = {}
    for x in v:
        desc = NUMARA.sub("", (x.get("itemDescTr") or "").strip())
        for k, adlar in KALEM.items():
            if k not in out and any(desc.lower().startswith(a.lower()) for a in adlar):
                out[k] = [_sayi(x.get(f"value{i}")) for i in range(1, 5)]
    return out


def dort_ceyrek(vals, dl):
    """Akış kalemi: son ara dönem + önceki yıl sonu − önceki yılın aynı ara dönemi; son dönem yıl sonuysa doğrudan."""
    if not vals or vals[0] is None:
        return None
    if dl[0][1] == 12:
        return vals[0]
    if vals[1] is None or vals[2] is None:
        return None
    return vals[0] + vals[1] - vals[2]


def kayit(kod, v, grup, dl, bugun):
    k = ayikla(v)
    son = lambda ad: (k.get(ad) or [None])[0]
    nakit, bkv, buv = son("nakit"), son("borcKV"), son("borcUV")
    net_borc = ((bkv or 0.0) + (buv or 0.0) - (nakit or 0.0)) if (bkv is not None or buv is not None) and nakit is not None else None
    fk, am = dort_ceyrek(k.get("faaliyetKari"), dl), dort_ceyrek(k.get("amortisman"), dl)
    favok = (fk + abs(am)) if fk is not None and am is not None else None
    ps = son("odenmisSermaye")
    return dict(bistKodu=kod, paySayisi=ps, paySayisiKaynak="ödenmiş sermaye, nominal 1 TL varsayımı" if ps is not None else "",
                ozkaynak=son("ozkaynak"), netKar4C=dort_ceyrek(k.get("netKar"), dl), netBorc=net_borc, favok4C=favok,
                donenVarlik=son("donenVarlik"), kvYukumluluk=son("kvYukumluluk"), donem=f"{dl[0][0]}-{dl[0][1]:02d}", grup=grup,
                kaynak="İş Yatırım MaliTablo", olcumTarihi=bugun.isoformat())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", action="append", default=[])
    ap.add_argument("--kod", help="virgülle kodlar (liste yerine)")
    ap.add_argument("--cikti", default="veri")
    ap.add_argument("--ara", type=float, default=1.2)
    ap.add_argument("--butce", type=int, default=600, help="istek bütçesi; kalan kodlar bir sonraki koşuya (eski kayıt korunur)")
    a = ap.parse_args()
    kodlar = []
    for yol in a.liste:
        if os.path.exists(yol):
            kodlar += [s.strip().split()[0].upper() for s in open(yol, encoding="utf-8") if s.strip() and not s.startswith("#")]
    if a.kod:
        kodlar += [k.strip().upper() for k in a.kod.split(",") if k.strip()]
    kodlar = list(dict.fromkeys(kodlar))
    yol = os.path.join(a.cikti, "temel_veri.csv")
    eski = {r["bistKodu"]: r for r in csv.DictReader(open(yol, encoding="utf-8"))} if os.path.exists(yol) else {}
    bugun = date.today(); dl = donemler(bugun)
    # önce hiç kaydı olmayanlar, sonra en eski ölçüm
    sira = sorted(kodlar, key=lambda k: (k in eski, (eski.get(k) or {}).get("olcumTarihi", "")))
    istek, yeni, tablosuz = 0, 0, []
    for kod in sira:
        if istek >= a.butce:
            break
        v = cek(kod, "XI_29", dl, a.ara); istek += 1; grup = "XI_29"
        if v is not None and not v and istek < a.butce:
            v = cek(kod, "UFRS", dl, a.ara); istek += 1; grup = "UFRS"
        if not v:
            tablosuz.append(kod)
            eski[kod] = dict(bistKodu=kod, paySayisi=None, paySayisiKaynak="", ozkaynak=None, netKar4C=None, netBorc=None, favok4C=None, donenVarlik=None,
                             kvYukumluluk=None, donem="", grup="", kaynak="İş Yatırım MaliTablo: tablo yok", olcumTarihi=bugun.isoformat())
            continue
        eski[kod] = kayit(kod, v, grup, dl, bugun); yeni += 1
    os.makedirs(a.cikti, exist_ok=True)
    with open(yol, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ALANLAR); w.writeheader()
        for kod in sorted(eski):
            w.writerow({k: ("" if eski[kod].get(k) is None else eski[kod].get(k)) for k in ALANLAR})
    print(f"temel_veri.csv: {len(eski)} kod, bu koşuda {yeni} yenilendi, tablosuz {len(tablosuz)} ({', '.join(tablosuz[:8])}), istek {istek}, dönem {dl[0][0]}-{dl[0][1]:02d}")


if __name__ == "__main__":
    main()
