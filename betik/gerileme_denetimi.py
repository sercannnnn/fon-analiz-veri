#!/usr/bin/env python3
"""Satir gerilemesi denetimi, tarih basina (22 Eylul 2026, Chat). Toplam satir sayisi olcu degildir: takvim penceresi degisken sayida is gunu
tasir (yanlis alarm) ve bir gunun icinden dusen satirlari pencere daralmasi gizler (kacirma; eylul basindaki 29 fon, 1.384 satir).

Uc sart, her dosya icin bir onceki kosunun (git HEAD) ayni dosyasiyla, ayni tarih icin:
  a) son tarih geriye gitmemeli
  b) pencere icinde bosluk olmamali (ardisik tarihler arasi BOSLUK_GUN takvim gununden uzun degil; bayramlar takvimde)
  c) bir tarihin satir sayisi, ayni tarih icin bir onceki kosuda olculenin altina dusmemeli
Sonuc: anlik dosyada (veri/*.csv) gerileme UYARI, gonderim surer; kumulatif arsivde (arsiv/*.gz) gerileme HATA, cikis 1, gonderim yapilmaz.
Gunluk pencere dosyalari (tefas_gunluk_<tarih>.csv, tefas_dagilim_<tarih>.csv) ayni ailenin HEAD'deki en yeni dosyasiyla karsilastirilir.
Bulgular 'gerileme=<dosya> <tarih> <eski>-><yeni>' biciminde son_cekim.txt'ye eklenir; brifing bunu aynen aktarir.
Kullanim: python3 betik/gerileme_denetimi.py [--kok .] [--son-cekim son_cekim.txt]
"""
import argparse, csv, glob, gzip, io, os, re, subprocess, sys
from datetime import date

BOSLUK_GUN = 4
AILE = [(re.compile(r"^veri/tefas_gunluk_\d{8}\.csv$"), "veri/tefas_gunluk_*.csv"), (re.compile(r"^veri/tefas_dagilim_\d{8}\.csv$"), "veri/tefas_dagilim_*.csv")]


def _git(kok, *args):
    r = subprocess.run(["git", "-C", kok] + list(args), capture_output=True)
    return r.returncode, r.stdout


def tarih_sayimi(b):
    """CSV (gz olabilir): ilk sutun 'tarih' ise {tarih: satir}, degilse {'_toplam': satir}. JSON gz: {'_toplam': satir}."""
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    t = b.decode("utf-8", "replace")
    ilk = t.split("\n", 1)[0]
    if not ilk.lower().startswith("tarih"):
        return {"_toplam": t.count("\n")}
    say = {}
    for r in csv.reader(io.StringIO(t)):
        if r and r[0] != "tarih":
            say[r[0][:10]] = say.get(r[0][:10], 0) + 1
    return say


def onceki_surum(kok, yol):
    """HEAD'deki karsilik: ayni yol; gunluk pencere ailesinde HEAD'deki en yeni aile uyesi (kendisi haric). Yoksa None."""
    for desen, glob_ in AILE:
        if desen.match(yol):
            kod, out = _git(kok, "ls-files", "--", glob_)
            adaylar = sorted(x for x in out.decode().split() if x != yol)
            return adaylar[-1] if adaylar else None
    kod, _ = _git(kok, "cat-file", "-e", f"HEAD:{yol}")
    return yol if kod == 0 else None


def bosluklar(tarihler):
    t = sorted(x for x in tarihler if len(x) == 10 and x[4] == "-")
    out = []
    for a, b in zip(t, t[1:]):
        try:
            fark = (date.fromisoformat(b) - date.fromisoformat(a)).days
        except ValueError:
            continue
        if fark > BOSLUK_GUN:
            out.append((a, b, fark))
    return out


def denetle(kok, dosyalar=None):
    """Donus: (hatalar, uyarilar) listeleri; metinler 'dosya tarih eski->yeni' ya da 'dosya sebep'."""
    hata, uyari = [], []
    if dosyalar is None:
        dosyalar = sorted(glob.glob(os.path.join(kok, "arsiv", "*.gz")) + glob.glob(os.path.join(kok, "veri", "*.csv")))
        dosyalar = [os.path.relpath(p, kok) for p in dosyalar]
    for yol in dosyalar:
        try:
            yeni = tarih_sayimi(open(os.path.join(kok, yol), "rb").read())
        except Exception:
            continue
        onceki_yol = onceki_surum(kok, yol)
        kova = hata if yol.startswith("arsiv/") else uyari
        if "_toplam" not in yeni:
            for a, b, f in bosluklar(yeni):
                uyari.append(f"{yol} bosluk {a}..{b} ({f} gun)")
        if not onceki_yol:
            continue
        kod, b = _git(kok, "show", f"HEAD:{onceki_yol}")
        if kod != 0:
            continue
        eski = tarih_sayimi(b)
        if "_toplam" in yeni or "_toplam" in eski:
            if yeni.get("_toplam", 0) < eski.get("_toplam", 0):
                kova.append(f"{yol} toplam {eski['_toplam']}->{yeni['_toplam']}")
            continue
        if max(yeni) < max(eski):
            kova.append(f"{yol} son tarih {max(eski)}->{max(yeni)}")
        for t in sorted(set(eski) & set(yeni)):
            if yeni[t] < eski[t]:
                kova.append(f"{yol} {t} {eski[t]}->{yeni[t]}")
    return hata, uyari


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kok", default=".")
    ap.add_argument("--son-cekim", default=None, help="bulgular 'gerileme=' satiri olarak eklenir")
    a = ap.parse_args()
    hata, uyari = denetle(a.kok)
    if uyari:
        print("uyari gerileme (anlik dosya, tarih basina): " + "; ".join(uyari[:12]), file=sys.stderr)
    if hata:
        print("HATA gerileme (kumulatif arsiv, tarih basina): " + "; ".join(hata[:12]), file=sys.stderr)
    if a.son_cekim and (hata or uyari):
        with open(a.son_cekim, "a", encoding="utf-8") as fh:
            for x in hata:
                fh.write(f"gerileme=HATA {x}\n")
            for x in uyari:
                fh.write(f"gerileme={x}\n")
    if not hata and not uyari:
        print("gerileme denetimi temiz (tarih basina)")
    sys.exit(1 if hata else 0)


if __name__ == "__main__":
    main()
