#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BIST gunluk hisse veri hatti. Kaynak: Is Yatirim HisseTekil ucu. Yalnizca 'requests' ister.

Kullanim:
  hisse_cek.py                      ilk calistirmada son 3 yil, sonra arsivdeki son tarihin 7 gun oncesinden bugune
  hisse_cek.py --bas 01-01-2026     baslangici elle ver (GG-AA-YYYY)
  hisse_cek.py --liste veri/bist100.txt --cikti veri --arsiv arsiv

Kapsam: veri/bist100.txt icindeki kodlar + TSKB, ANHYT, BTCIM.
Ciktilar:
  veri/hisse_son_gunluk.csv      bu calistirmada cekilen satirlar
  veri/hisse_hata.txt            basarisiz kodlar (bos dosya = hata yok)
  arsiv/hisse_YYYY-MM.csv.gz     aylik birikimli arsiv; gzip mtime=0, icerik ayniysa dosya ayni kalir
Sema: tarih,hisse,kapanisDuzeltilmis,kapanisHam,hacim,xu100,usdTry
  kapanisDuzeltilmis = HG_KAPANIS (temettu ve sermaye duzeltmeli; karsilastirma bununla yapilir)
  kapanisHam = HGDG_KAPANIS, hacim = HGDG_HACIM (TL), xu100 = END_DEGER, usdTry = DD_DEGER
"""
import argparse, csv, glob, gzip, io, os, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta
import requests

UC = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil"
BASLIK = {"User-Agent": "Mozilla/5.0 (fon-analiz hisse cekici)", "Accept": "application/json"}
ALANLAR = ["tarih", "hisse", "kapanisDuzeltilmis", "kapanisHam", "hacim", "xu100", "usdTry"]
KAYNAK = {"kapanisDuzeltilmis": "HG_KAPANIS", "kapanisHam": "HGDG_KAPANIS", "hacim": "HGDG_HACIM",
          "xu100": "END_DEGER", "usdTry": "DD_DEGER"}
EK_KODLAR = ["TSKB", "ANHYT", "BTCIM"]
ARA_SANIYE = 1.0               # istekler arasi en az bekleme
GERI_GUN = 7                   # artimli cekimde arsivdeki son tarihten kac gun geriye gidilir
BEKLEME = (2, 4, 8)            # 429 / 5xx / baglanti hatasinda ustel geri cekilme


def liste_oku(yol):
    kod = []
    for satir in open(yol, encoding="utf-8"):
        s = satir.strip()
        if s and not s.startswith("#"):
            kod.append(s.upper())
    for k in EK_KODLAR:
        if k not in kod:
            kod.append(k)
    return kod


def iso(t):
    """'04-09-2026' -> '2026-09-04'."""
    return datetime.strptime(t, "%d-%m-%Y").strftime("%Y-%m-%d")


def cek(kod, bas, bit):
    """Tek hisse icin kayit listesi. 429 ve 5xx'te uc kez dener; basarisizsa None."""
    for i in range(len(BEKLEME) + 1):
        try:
            r = requests.get(UC, params={"hisse": kod, "startdate": bas, "enddate": bit},
                             headers=BASLIK, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            j = r.json()
            if not j.get("ok", True) and j.get("errorDescription"):
                raise RuntimeError(j["errorDescription"])
            return j.get("value") or []
        except Exception as e:
            print(f"  {kod}: deneme {i+1} basarisiz: {e}", file=sys.stderr)
            if i < len(BEKLEME):
                time.sleep(BEKLEME[i])
    return None


def arsiv_oku(yol):
    with gzip.open(yol, "rt", encoding="utf-8", newline="") as f:
        for s in csv.DictReader(f):
            yield s


def arsiv_son_tarih(arsiv):
    son = None
    for yol in sorted(glob.glob(os.path.join(arsiv, "hisse_*.csv.gz")))[-1:]:
        for s in arsiv_oku(yol):
            if son is None or s["tarih"] > son:
                son = s["tarih"]
    return son


def arsiv_yaz(arsiv, satirlar):
    """satirlar: dict (tarih, hisse) -> alan listesi. Dokunulan aylar birlestirilip yeniden yazilir."""
    aylar = defaultdict(dict)
    for (t, h), s in satirlar.items():
        aylar[t[:7]][(t, h)] = s
    for ay in sorted(aylar):
        yol = os.path.join(arsiv, f"hisse_{ay}.csv.gz")
        birlesik = {}
        if os.path.exists(yol):
            for s in arsiv_oku(yol):
                birlesik[(s["tarih"], s["hisse"])] = [s.get(k, "") for k in ALANLAR]
        birlesik.update(aylar[ay])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(ALANLAR)
        for k in sorted(birlesik):
            w.writerow(birlesik[k])
        with open(yol, "wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
                g.write(buf.getvalue().encode("utf-8"))
        print(f"  {yol}: {len(birlesik):,} satir", file=sys.stderr)


def main():
    kok = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", default=os.path.join(kok, "veri", "bist100.txt"))
    ap.add_argument("--cikti", default=os.path.join(kok, "veri"))
    ap.add_argument("--arsiv", default=os.path.join(kok, "arsiv"))
    ap.add_argument("--bas", help="GG-AA-YYYY; varsayilan: arsivdeki son tarih, yoksa bugun - 3 yil")
    ap.add_argument("--bit", help="GG-AA-YYYY; varsayilan bugun")
    a = ap.parse_args()
    os.makedirs(a.cikti, exist_ok=True); os.makedirs(a.arsiv, exist_ok=True)

    bugun = date.today()
    bit = a.bit or bugun.strftime("%d-%m-%Y")
    if a.bas:
        bas = a.bas
    else:
        son = arsiv_son_tarih(a.arsiv)
        # Son tarihten GERI_GUN geriye: Is Yatirim gunun satirini aksam hisse hisse yayimlar,
        # tek gunluk aralik cogu hissede bos doner ve sahte hata uretir. Geriye gitmek ayrica
        # son gunlerin duzeltilmis kapanislarini tazeler; arsiv tekillestirdigi icin zarar yok.
        bas = ((datetime.strptime(son, "%Y-%m-%d") - timedelta(days=GERI_GUN)).strftime("%d-%m-%Y") if son
               else (bugun - timedelta(days=3 * 365)).strftime("%d-%m-%Y"))
    kodlar = liste_oku(a.liste)
    print(f"{len(kodlar)} hisse, {bas} .. {bit}", file=sys.stderr)

    satirlar, hatali, basarili = {}, [], 0
    for i, kod in enumerate(kodlar):
        if i:
            time.sleep(ARA_SANIYE)
        kayit = cek(kod, bas, bit)
        if kayit is None:
            hatali.append(kod)
            continue
        if not kayit:
            # Is Yatirim gecersiz ya da islem gormeyen kod icin hata degil bos liste doner
            hatali.append(f"{kod} (bos yanit)")
            continue
        basarili += 1
        for x in kayit:
            t = iso(x["HGDG_TARIH"])
            satirlar[(t, kod)] = [t, kod] + ["" if x.get(v) is None else x[v] for v in
                                            (KAYNAK[k] for k in ALANLAR[2:])]

    # bu calistirmanin satirlari
    yol = os.path.join(a.cikti, "hisse_son_gunluk.csv")
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(ALANLAR)
        for k in sorted(satirlar):
            w.writerow(satirlar[k])
    with open(os.path.join(a.cikti, "hisse_hata.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(hatali) + ("\n" if hatali else ""))

    if satirlar:
        arsiv_yaz(a.arsiv, satirlar)

    son_tarih = max((t for t, _ in satirlar), default="-")
    xu = next((s[5] for (t, h), s in satirlar.items() if t == son_tarih and s[5] != ""), "-")
    print(f"hisse cekilen: {basarili}/{len(kodlar)}, basarisiz: {len(hatali)}{' (' + ', '.join(hatali) + ')' if hatali else ''}, "
          f"satir: {len(satirlar):,}, son tarih: {son_tarih}, XU100 kapanis: {xu}")
    if basarili == 0:
        sys.exit("hic hisse cekilemedi")


if __name__ == "__main__":
    main()
