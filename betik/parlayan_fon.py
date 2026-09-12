#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parlayan fon ekrani. Kural karsiligi: 00_KURALLAR.md bolum 3 ve 3b.

Girdi
  arsiv/tefas_YYYY-MM.csv.gz      GitHub deposundan, tam fiyat gecmisi
  veri/son_gunluk.csv             son gunler
  kunye.csv                       fonKodu,fonAd,kategori,riskDegeri,g1y,g3y
  son_dagilim.csv                 varlik dagilimi, kapi 4 icin

Cikti
  metrik.csv        tum evren, olculen buyuklukler
  parlayan.csv      parlama olcutunu gecen adaylar, kapi sonuclariyla

Kullanim:  python3 parlayan_fon.py [--kok .] [--poz KOD1,KOD2]   (elde tutulan fon kodlari; portfoy bilgisi, komut satirindan verilir)
"""
import argparse, glob, os, sys
from kategori import kategori_turet
import numpy as np, pandas as pd
import kapilar                                   # kapi mantigi tek yerde (Gorev 2, M10)
from kapilar import ASGARI_BUY, ASGARI_KISI
from takvim import bosluk_maskesi as tatil_maskesi, gecersiz_fiyat_ayikla   # bosluk kurali ve resmi kapanislar tek yerde (Gorev 2.4)
import kapsam as kapsam_m                                                    # kismi kapsamli gun korumasi (Gorev 3.3)

ASGARI_SEANS = 120
PARLA_R30    = 0.90       # emsalde 30 seans getirisi ust ondalik
PARLA_GETORI = 0.75       # emsalde risk basina getiri ust ceyrek
GEREKLI_SEANS = 3         # alim talimati icin ardisik seans


def panel(kok):
    fs = sorted(glob.glob(os.path.join(kok, "arsiv", "tefas_*.csv.gz")))
    fs += sorted(glob.glob(os.path.join(kok, "veri", "son_gunluk.csv")))
    if not fs:
        sys.exit("fiyat dosyasi bulunamadi")
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    d["tarih"] = pd.to_datetime(d["tarih"])
    d, panel.gecersiz, panel.gecersiz_son_gun = gecersiz_fiyat_ayikla(d)   # M5 / kural 15: gecersiz fiyat atilir, sayisi tutulur
    return d.drop_duplicates(["tarih", "fonKodu"]).sort_values(["fonKodu", "tarih"])


def olc(d):
    sat = []
    for kod, g in d.groupby("fonKodu"):
        g = g.sort_values("tarih")
        p = g.fiyat.to_numpy(float); t = g.tarih.to_numpy(); u = g.tedPaySayisi.to_numpy(float)
        n = len(p)
        if n < ASGARI_SEANS:
            continue
        def getiri(k):
            if n <= k or tatil_maskesi(t[-k-1:]).any():
                return np.nan
            return p[-1] / p[-k-1] - 1
        r = p[1:] / p[:-1] - 1
        r = r[~tatil_maskesi(t)]
        r60 = r[-60:]
        vol60 = r60.std(ddof=1) * np.sqrt(252) if len(r60) > 30 else np.nan
        ser = pd.Series(p); lr = ser.pct_change()
        lr[np.r_[False, tatil_maskesi(t)]] = np.nan
        volort = (lr.rolling(60, min_periods=40).std() * np.sqrt(252)).median()
        dd = ser / ser.cummax() - 1
        sat.append(dict(fonKodu=kod, seans=n, fiyat=p[-1],
                        buyukluk=g.portfoyBuyukluk.iloc[-1], kisi=g.kisiSayisi.iloc[-1],
                        r30=getiri(30), r63=getiri(63), r126=getiri(126), r250=getiri(250),
                        vol60=vol60, volort=volort,
                        ddsimdi=float(dd.iloc[-1]), ddceyrek=float(dd.quantile(0.25)),
                        dpay20=(u[-1] / u[-21] - 1) if n > 21 else np.nan,
                        akis20=float(np.sum(np.diff(u[-21:]) * p[-20:])) if n > 21 else np.nan,
                        eksigun=int((r60 < 0).sum())))
    m = pd.DataFrame(sat)
    m["hiz30"] = (1 + m.r30) ** (252 / 30) - 1
    m["getori"] = m.hiz30 / m.vol60
    return m


def kurucu_ad(a):
    a = str(a); i = a.upper().find("PORTFÖY")
    return a[:i + 7].strip() if i > 0 else "DİĞER"


# Kapi mantigi kapilar.py icindedir (Gorev 2, M10); burada yalnizca olcumler uretilir.


def kurucu_gecmisi(d, m):
    """Kurucu duzeyinde gecmis (kural metni bolum 6, agresif dilim gerekcesi): fon sayisi, ortanca yas (fon_yas'tan, yoksa NaN),
    ve 60 seans ileriye bakan yuzde 20 dusus gorulme orani (fon-gun; bosluk iceren pencereler ve ilk 20 seans disarida).
    Kaynak: olcum, arsiv fiyat serisi. Bu bir kapi degil, oneri gerekcesidir."""
    fiy = d.pivot_table(index="tarih", columns="fonKodu", values="fiyat").sort_index()
    bos = pd.Series(np.r_[False, tatil_maskesi(fiy.index)], index=fiy.index)
    # ileriye 60 seanslik en dusuk fiyat: ters cevirip yuvarlanan en kucuk
    ileri_min = fiy.iloc[::-1].rolling(60, min_periods=60).min().iloc[::-1]
    ileri_bos = bos.iloc[::-1].rolling(60, min_periods=1).sum().iloc[::-1].gt(0)
    dd = (ileri_min / fiy - 1).mask(ileri_bos, np.nan).iloc[20:]
    oran = pd.DataFrame({"cokus": (dd <= -0.20).sum(), "gun": dd.notna().sum()})
    oran["kurucu"] = m.set_index("fonKodu").kurucu.reindex(oran.index)
    g = oran.dropna(subset=["kurucu"]).groupby("kurucu")[["cokus", "gun"]].sum()
    out = pd.DataFrame({"kurucu_fon": m.groupby("kurucu").fonKodu.count(),
                        "kurucu_yas_ort": m.groupby("kurucu").yas_ay.median(),
                        "kurucu_cokus": (g.cokus / g.gun.where(g.gun > 0)).reindex(m.kurucu.unique())})
    return out


def agresif_adaylar(m, poz):
    """Agresif dilim havuzu (kural metni bolum 6): en az 20 seans, buyukluk ve yatirimci esigi, portfoyde olmayan;
    G2 uygulanmaz, C1 ve C5 gerekceyle askiya alinir; 'yeni' etiketi; buyume kaynagi (20 seansta pay adedi > %1.000)
    boyutlandirmayi yariya indirir. Siralama tek olcuyle: risk basina getiri (getori); vol60 olculemeyen fonda r30 ile."""
    # dilim gecmisi kisa fonlara ayrilmistir: yasi G2 esiginin altinda ya da olculemeyen fonlar; yasli fon ana havuzdadir
    h = m[(m.seans >= kapilar.AGRESIF_ASGARI_SEANS) & (m.buyukluk >= ASGARI_BUY) & (m.kisi >= ASGARI_KISI) & (~m.fonKodu.isin(poz))
          & ((m.yas_ay < kapilar.G2_AY) | m.yas_ay.isna())].copy()
    kayit = []
    for _, r in h.iterrows():
        s_ = kapilar.giris_sonucu(r, dilim="agresif")
        buyume = bool(pd.notna(r.dpay20) and r.dpay20 > kapilar.AGRESIF_PAY_ARTIS)
        kayit.append(dict(fonKodu=r.fonKodu, fonAd=r.fonAd, kategori=r.kategori, kurucu=r.kurucu, etiket="yeni",
                          seans=int(r.seans), yas_ay=r.yas_ay, getori=r.getori, r30=r.r30, vol60=r.vol60,
                          buyukluk=r.buyukluk, kisi=r.kisi, dpay20=r.dpay20, net_giris20=r.net_giris20,
                          kurucu_gecmis=r.kurucu_gecmis, buyume_kaynagi=buyume,
                          kapi_durumu=s_["durum"], kapali=" | ".join(s_["kapali"]), bilinmez=" | ".join(s_["bilinmez"]),
                          askida=" | ".join(s_["askida"]),
                          kapi_raporu="\n".join(kapilar.kapi_raporu(s_["cikis"] + s_["giris"]))))
    o = pd.DataFrame(kayit)
    if not len(o):
        return o
    o["sira_olcusu"] = o.getori.where(o.getori.notna(), o.r30)
    return o.sort_values("sira_olcusu", ascending=False).reset_index(drop=True)


def ekran(kok, poz, haber=None):
    d = panel(kok)
    k = pd.read_csv(os.path.join(kok, "kunye_tam.csv"))
    m = olc(d).merge(k, on="fonKodu", how="left")

    # M9'un ikinci yarisi: kunye dosyasi 07.09 tarihli sabit bir goruntudur ve
    # o gunden sonra acilan fonu icermez. Gunluk cekim artik fonUnvan donuyor;
    # kunyede kategorisi olmayan fonun kategorisi unvandan turetilir. Kunye
    # yetkili kaynaktir, turetme yalnizca yedektir: unvan kategoriyi %98,4
    # dogrulukla veriyor, geri kalani semsiye turunden geliyor ve unvanda yok.
    if "fonUnvan" in m.columns:
        eksik = m.kategori.isna() & m.fonUnvan.notna()
        m.loc[eksik, "kategori"] = m.loc[eksik, "fonUnvan"].map(kategori_turet)
        m.loc[eksik & m.fonAd.isna(), "fonAd"] = m.loc[eksik & m.fonAd.isna(), "fonUnvan"]
        ekran.turetilen = int(eksik.sum())
    else:
        ekran.turetilen = 0
    ekran.kunyesiz = int(m.kategori.isna().sum())
    m = m[m.kategori.notna()].copy()
    if "kurucu" not in m.columns:
        m["kurucu"] = m.fonAd.map(kurucu_ad)

    # Toplam alan olcumler (emsal dilimi, kurucu akisi) kismi kapsamli gunde yapilmaz: tam kapsamli son gune cekilir (Gorev 3.3)
    d_tam, ekran.tam_gun, ekran.atilan_gun = kapsam_m.toplam_alan(d, izin_kismi=False)
    # kapi 2 ve giris kapi 1: son 20 seansta emsal dilimi tarihcesi
    fiy = d_tam.pivot_table(index="tarih", columns="fonKodu", values="fiyat")
    pay = d_tam.pivot_table(index="tarih", columns="fonKodu", values="tedPaySayisi")
    bos = np.r_[False, tatil_maskesi(fiy.index)]
    r63 = (fiy / fiy.shift(63) - 1).mask(
        pd.Series(bos, index=fiy.index).rolling(64, min_periods=1).sum().gt(0), np.nan)
    kat = m.set_index("fonKodu").kategori
    s20 = r63.tail(20)[[c for c in r63.columns if c in kat.index]]
    dil = s20.T.groupby(kat.reindex(s20.columns)).rank(pct=True).T
    m["altceyrek_gun"] = m.fonKodu.map((dil <= 0.25).sum())
    m["olculen_gun"] = m.fonKodu.map(dil.notna().sum())
    m["ustceyrek_gun"] = m.fonKodu.map((dil >= 0.75).sum())

    # kapi 3: dort hafta ust uste net cikis
    akis = (pay.diff() * fiy).fillna(0)
    haf = [akis.tail(20).iloc[i*5:(i+1)*5].sum() for i in range(4)]
    H = pd.concat(haf, axis=1)
    m["neg4hafta"] = m.fonKodu.map((H < 0).all(axis=1))
    m["akis4hafta_o"] = m.fonKodu.map(H.sum(axis=1)) / m.buyukluk

    # kapi 4: dagilim kaymasi
    yol = os.path.join(kok, "son_dagilim.csv")
    if os.path.exists(yol):
        g = pd.read_csv(yol).sort_values("tarih")
        sut = [c for c in g.columns if c not in ("tarih", "fonKodu")]
        kay = (g.groupby("fonKodu").last()[sut].fillna(0)
               - g.groupby("fonKodu").first()[sut].fillna(0)).abs().sum(axis=1) / 2
        m["kayma"] = m.fonKodu.map(kay)
    else:
        m["kayma"] = np.nan

    # G5a: kurucu duzeyinde 20 seanslik net akis
    kk = m.set_index("fonKodu").kurucu
    ort = kk.reindex(pay.columns)
    ak_k = (pay.diff() * fiy).T.groupby(ort).sum().T
    bk_k = (pay * fiy).T.groupby(ort).sum().T
    m["kurucu_akis20"] = m.kurucu.map(ak_k.tail(20).sum() / bk_k.iloc[-21])

    for c in ("r30", "r63", "r126", "getori"):
        m[c + "_d"] = m.groupby("kategori")[c].rank(pct=True)
    # G4: yonetim ucreti kategori icinde dilim (veri/fon_ucret.csv, KAP genel bilgiler, kap_ucret.py); dosya ya da deger yoksa NaN -> olculemedi
    uyol = os.path.join(kok, "veri", "fon_ucret.csv")
    if os.path.exists(uyol):
        u = pd.read_csv(uyol, dtype=str)
        def _o(sut):
            return pd.to_numeric(u[sut].fillna("").str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
        u["ucret"] = _o("yonetimUcretiYillik").fillna(_o("ictuzukYonetimUcretiYillik"))   # uygulanan oran bos ise ictuzukteki oran
        m = m.merge(u[["fonKodu", "ucret"]], on="fonKodu", how="left")
        m["ucret_dilim"] = m.groupby("kategori")["ucret"].rank(pct=True)
        ekran.ucretli = int(m.ucret.notna().sum())
    else:
        m["ucret"] = np.nan; m["ucret_dilim"] = np.nan; ekran.ucretli = 0
    # G2 (12 Eylul 2026 kural metni): fon yasi YALNIZCA TEFAS'ta ilk fiyatlandigi aydan olculur (veri/fon_yas.csv, tefas_yas.py).
    # Arsivdeki seans sayisi arsivin yasidir, fonun degil; kunyedeki uc yillik getiri alani da yas delili degildir (M17).
    # "en_gec" sinirli fon bes yil onceki pencerede zaten vardi, yasi alt sinirdir ve G2_AY'i asar. Dosyada olmayan fon
    # (taramadan sonra acilan) olculemedi kalir ve kural 14 uyarinca gecilmemis sayilir. Esik degismez.
    son = d.tarih.max()
    yyol = os.path.join(kok, "veri", "fon_yas.csv")
    if os.path.exists(yyol):
        y = pd.read_csv(yyol, dtype=str)
        ilk = pd.to_datetime(y.ilkFiyatAyi + "-01", errors="coerce")
        y["yas_ay"] = ((son.year - ilk.dt.year) * 12 + (son.month - ilk.dt.month) + son.day / 30.0).round(1)
        m = m.merge(y[["fonKodu", "yas_ay"]], on="fonKodu", how="left")
        ekran.yasli = int(m.yas_ay.notna().sum())
    else:
        m["yas_ay"] = np.nan; ekran.yasli = 0
    m["gecmis_ay"] = m.yas_ay
    # Haber kapisi G5b: kurucu -> True (temiz) / False (birinci kademe eslesme). Tarama yapilmadiysa NaN -> olculemedi (kural 14).
    m["kurucu_haber"] = m.kurucu.map(haber) if haber is not None else np.nan
    # Agresif dilim gerekceleri (kural metni bolum 6): 20 seanslik net giris orani ve kurucunun diger fonlarinin gecmisi
    m["net_giris20"] = m.akis20 / (m.buyukluk - m.akis20).where(lambda x: x > 0)
    kg = kurucu_gecmisi(d, m)
    m = m.merge(kg, left_on="kurucu", right_index=True, how="left")
    m["kurucu_gecmis"] = m.apply(lambda r: (f"kurucunun {int(r.kurucu_fon)} fonu, ortanca yaş {r.kurucu_yas_ort:.0f} ay, "
                                            f"60 seansta %20 düşüş görülen fon-gün oranı %{100 * r.kurucu_cokus:.1f}")
                                 if pd.notna(r.get("kurucu_fon")) and pd.notna(r.get("kurucu_cokus")) else None, axis=1)
    m.to_csv(os.path.join(kok, "metrik.csv"), index=False)

    h = m[(m.buyukluk >= ASGARI_BUY) & (m.kisi >= ASGARI_KISI) & (~m.fonKodu.isin(poz))]
    p = h[(h.r30_d >= PARLA_R30) & (h.getori_d >= PARLA_GETORI) & (h.akis20 > 0)].copy()
    p = p.sort_values("getori", ascending=False)


    kayit = []
    for _, r in p.iterrows():
        s_ = kapilar.giris_sonucu(r)          # alti cikis kapisi + bes giris kapisi; bilinemeyen gecilmemis sayilir
        kayit.append(dict(fonKodu=r.fonKodu, fonAd=r.fonAd, kategori=r.kategori,
                          kurucu=r.kurucu, getori=r.getori, r30=r.r30, vol60=r.vol60,
                          buyukluk=r.buyukluk, kisi=r.kisi, kurucu_akis20=r.kurucu_akis20,
                          kapi_durumu=s_["durum"],
                          kapali=" | ".join(s_["kapali"]), bilinmez=" | ".join(s_["bilinmez"]),
                          kapi_raporu="\n".join(kapilar.kapi_raporu(s_["cikis"] + s_["giris"]))))
    o = pd.DataFrame(kayit)
    # Liste iki kumeden olusur: kapisi acik olan her aday, ve siralamada
    # en ustteki bes aday. Kesisim tekrarlanmaz.
    acik = o[o.kapi_durumu == "acik"]
    ust  = o.head(5)
    o = pd.concat([acik, ust]).drop_duplicates("fonKodu").reset_index(drop=True)
    o.to_csv(os.path.join(kok, "parlayan.csv"), index=False)
    ag = agresif_adaylar(m, poz)
    ag.to_csv(os.path.join(kok, "agresif.csv"), index=False)
    ekran.agresif = ag
    return o


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kok", default=".")
    ap.add_argument("--poz", default="")
    a = ap.parse_args()
    o = ekran(a.kok, [x for x in a.poz.split(",") if x])
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70)
    print(o.to_string(index=False))
    print("\nAlım talimatı için: kapı durumu açık VE %d ardışık seans." % GEREKLI_SEANS)
