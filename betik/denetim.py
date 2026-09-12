#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doğrulama katmanı (Görev 4). Sıfır sapma kapısı bir alışkanlık değil, bir kontroldür.

Dört sınama, tek rapor:
  1 Kimlik: her fonda pay adedi × fiyat = portföy büyüklüğü (çekim anındaki kapsam_son.json kaydından).
  2 Portföy tabanı mutabakatı: pozisyon defterindeki değerlerin toplamı ile brifingin dayandığı taban; fark pozisyon pozisyon.
  3 Bakış geçirgen maruziyet: fon içerik arşivi × pozisyonlar ile hisse maruziyeti ve tek isim maruziyeti; bildirilen değerle fark.
  4 Defter tutarlılığı: emir defterindeki gerçekleşen emirler ile pozisyon adetleri.

Sapma defteri: 03 Veri/sapmalar.json. Sapma ancak sebebi kanıtlandığında kapanır; "yuvarlama", "dönem sınırı", "toplama farkı"
gerekçeleri kapatmaz, kod reddeder. Açık sapmalar brifingin kapsam satırında görünür.

Her sayının künyesi vardır: ölçüm, kayıt, hesaplama, varsayım, projeksiyon.

Kullanım:
  denetim.py [--klasor "04 Günlük Rapor/2026-09-08"] [--icerik <fon_icerik_YYYY-MM.csv.gz>] [--bildirilen anahtar=deger ...]
  denetim.py --kapat <sapmaId> --kanit "<kanıt metni>"
Yalnızca standart kütüphane ve pandas.
"""
import argparse, csv, glob, gzip, io, json, os, re, sys
from datetime import date

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAPOR = os.path.join(KOK, "04 Günlük Rapor")
VERI_KOK = os.environ.get("FON_DENETIM_VERI", os.path.join(KOK, "03 Veri"))   # sinama gecici klasore yazsin diye
KUNYE_KLASOR = os.path.join(VERI_KOK, "Künye")
SAPMA_YOL = os.path.join(VERI_KOK, "sapmalar.json")
OLCUM, KAYIT, HESAP, VARSAYIM = "ölçüm", "kayıt", "hesaplama", "varsayım"
KAPATMA_REDDI = re.compile(r"yuvarlama|dönem sınır|donem sinir|toplama fark|küsurat|kusurat", re.I)
TABAN_TOLERANS_TL = 1.0          # taban mutabakatında bir liranın altı fark sıfır sayılır (kuruş yuvarlaması değil, TL)
HISSE_TUR = re.compile(r"HISSE|HİSSE|ODUNC|ÖDÜNÇ", re.I)


def tl(x, hane=0):
    return f"{x:,.{hane}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def yuzde(x, hane=2):
    return ("-" if x < 0 else "") + "%" + tl(abs(x) * 100, hane)


def json_oku(yol, varsayilan):
    try:
        return json.load(open(yol, encoding="utf-8"))
    except Exception:
        return varsayilan


# ---------------------------------------------------------------- sapma defteri

def sapma_yukle():
    return json_oku(SAPMA_YOL, [])


def sapma_yaz(L):
    os.makedirs(os.path.dirname(SAPMA_YOL), exist_ok=True)
    json.dump(L, open(SAPMA_YOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def sapma_ekle(L, sid, olcum, bildirilen, hesaplanan, kunye, tarih=None, not_=""):
    """Aynı kimlikli açık sapma varsa değerleri günceller, yoksa açar. Fark sıfırsa (tolerans içinde) kayıt açmaz."""
    fark = None if bildirilen is None or hesaplanan is None else round(hesaplanan - bildirilen, 2)
    for s in L:
        if s["id"] == sid and s["durum"] == "acik":
            s.update(bildirilen=bildirilen, hesaplanan=hesaplanan, fark=fark, sonKontrol=(tarih or date.today().isoformat()))
            return s
    if fark is not None and abs(fark) <= TABAN_TOLERANS_TL:
        return None
    s = dict(id=sid, tarih=tarih or date.today().isoformat(), olcum=olcum, bildirilen=bildirilen, hesaplanan=hesaplanan,
             fark=fark, durum="acik", kunye=kunye, **({"not": not_} if not_ else {}))
    L.append(s)
    return s


def sapma_kapat(sid, kanit):
    L = sapma_yukle()
    if not kanit or KAPATMA_REDDI.search(kanit):
        sys.exit("kapatma reddedildi: sapma ancak sebebi kanıtlanınca kapanır; yuvarlama, dönem sınırı ya da toplama farkı gerekçe değildir")
    for s in L:
        if s["id"] == sid:
            if s["durum"] != "acik":
                sys.exit(f"{sid} zaten {s['durum']}")
            s["durum"] = "kapandi"; s["kapanis"] = dict(tarih=date.today().isoformat(), kanit=kanit)
            sapma_yaz(L); print(f"{sid} kapandı; kanıt: {kanit}"); return
    sys.exit(f"{sid} bulunamadı")


# ---------------------------------------------------------------- girdiler

def son_klasor():
    k = sorted(glob.glob(os.path.join(RAPOR, "20??-??-??")))
    return k[-1] if k else None


def icerik_yukle(yol):
    ac = gzip.open if yol.endswith(".gz") else open
    with ac(yol, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def icerik_bul(klasor_arsiv):
    """En yeni fon_icerik_YYYY-MM.csv.gz: önce verilen klasör, sonra 03 Veri/Arşiv, sonra ortam değişkeni FON_ANALIZ_DEPO/arsiv."""
    adaylar = []
    for k in (klasor_arsiv, os.path.join(KOK, "03 Veri", "Arşiv"), os.path.join(os.environ.get("FON_ANALIZ_DEPO", ""), "arsiv")):
        if k:
            adaylar += glob.glob(os.path.join(k, "fon_icerik_20??-??.csv.gz"))
    return sorted(adaylar, key=os.path.basename)[-1] if adaylar else None


# ---------------------------------------------------------------- sınamalar

def sinama_kimlik(L, rapor):
    ks = json_oku(os.path.join(KUNYE_KLASOR, "kapsam_son.json"), {})
    rapor.append("## 1. Kimlik sınaması: pay adedi × fiyat = büyüklük")
    rapor.append("")
    if not ks.get("sonGun"):
        rapor.append("Çekim kaydı (kapsam_son.json) yok; kimlik sınaması yapılamadı. [kayıt]")
        rapor.append(""); return {"durum": "olculemedi"}
    n = ks.get("kimlikSapmaSayisi", 0); sap = ks.get("kimlikSapanlar", [])
    rapor.append(f"Çekim {ks.get('cekimZamaniUtc')} UTC, son gün {ks['sonGun']}: {tl(ks['sonGunKayit'])} kayıt, fiyatsız {tl(ks['sonGunFiyatsiz'])}, "
                 f"tam kapsamlı son gün {ks.get('tamKapsamliSonGun')}. [kayıt, çekim anında ölçüm]")
    rapor.append(f"Kimlik sınamasından sapan fon: {tl(n)}. Tolerans pay adedi × 0,5e-6 + 0,01 TL (fiyat altı ondalıkla basılır). [ölçüm]")
    if sap:
        rapor.append("")
        rapor.append("| Tarih | Fon | Pay × fiyat | Büyüklük | Fark |")
        rapor.append("|---|---|---|---|---|")
        for s in sorted(sap, key=lambda s: -abs(s["payXfiyat"] - s["buyukluk"]))[:25]:
            rapor.append(f"| {s['tarih']} | {s['fonKodu']} | {tl(s['payXfiyat'], 2)} | {tl(s['buyukluk'], 2)} | {tl(s['payXfiyat'] - s['buyukluk'], 2)} |")
        rapor.append("")
        rapor.append("Sapma sıfır çıkmadan bu fonlarda akış hesabı kullanılmaz (beceri bölüm 2).")
    rapor.append("")
    return {"durum": "kirmizi" if n else "yesil", "sapan": n}


def sinama_taban(L, rapor, klasor, tarih):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    bri = json_oku(os.path.join(klasor, "01 Brifing Verisi.json"), None)
    rapor.append("## 2. Portföy tabanı mutabakatı")
    rapor.append("")
    if not poz:
        rapor.append("06 Pozisyonlar.json yok; taban mutabakatı yapılamadı. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    defter = {(v.get("kurum", ""), v["kod"]): float(v.get("deger") or 0) for v in poz.values()}
    taban_defter = round(sum(defter.values()), 2)
    rapor.append(f"Pozisyon defteri ({os.path.basename(klasor)}, {len(defter)} pozisyon): toplam {tl(taban_defter, 2)} TL. [kayıt, 06 Pozisyonlar.json]")
    if not bri or not bri.get("pozisyon"):
        rapor.append("01 Brifing Verisi.json yok; brifingin tabanı karşılaştırılamadı."); rapor.append("")
        return {"durum": "olculemedi", "tabanDefter": taban_defter}
    bpoz = {(x.get("kurum", ""), x["kod"]): float(x.get("deger") or 0) for x in bri["pozisyon"]}
    taban_bri = round(sum(bpoz.values()), 2)
    fark = round(taban_defter - taban_bri, 2)
    rapor.append(f"Brifingin dayandığı taban (pozisyon listesi toplamı): {tl(taban_bri, 2)} TL. [kayıt, 01 Brifing Verisi.json]")
    rapor.append(f"Fark (defter − brifing): {tl(fark, 2)} TL. [hesaplama]")
    # kurum adlari iki kaynakta farkli yazilabilir (kisa ad / tam unvan): kodla eslestir, kurumu ilk alti harfe indirgeyip normalize et
    def norm_k(k):
        k = k.lower().replace("ı", "i").replace("ş", "s").replace("İ", "i")
        return (re.sub(r"bank.*$", "", k).strip()[:6] or k.strip()[:6])
    d2 = {}
    for (k, kod), v in defter.items(): d2[(norm_k(k), kod)] = d2.get((norm_k(k), kod), 0) + v
    b2 = {}
    for (k, kod), v in bpoz.items(): b2[(norm_k(k), kod)] = b2.get((norm_k(k), kod), 0) + v
    satirlar = []
    for a in sorted(set(d2) | set(b2)):
        dv, bv = d2.get(a), b2.get(a)
        if dv is None or bv is None or abs(dv - bv) > TABAN_TOLERANS_TL:
            satirlar.append((a, dv, bv))
    if satirlar:
        rapor.append("")
        rapor.append("| Kurum | Fon | Defter | Brifing | Fark |")
        rapor.append("|---|---|---|---|---|")
        for (k, kod), dv, bv in satirlar:
            rapor.append(f"| {k} | {kod} | {tl(dv, 2) if dv is not None else '-'} | {tl(bv, 2) if bv is not None else '-'} | "
                         f"{tl((dv or 0) - (bv or 0), 2)} |")
    if abs(fark) > TABAN_TOLERANS_TL:
        sapma_ekle(L, f"taban-{tarih}", "portföy tabanı: defter toplamı ile brifing tabanı", taban_bri, taban_defter, KAYIT, tarih,
                   "fark pozisyon pozisyon yukarıdaki tabloda; kapanış için farkı doğuran pozisyonun sebebi kanıtlanmalı")
    rapor.append("")
    return {"durum": "kirmizi" if abs(fark) > TABAN_TOLERANS_TL else "yesil", "tabanDefter": taban_defter, "tabanBrifing": taban_bri, "fark": fark}


def sinama_bakis(L, rapor, klasor, tarih, icerik_yol, isimler, bildirilen):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    rapor.append("## 3. Bakış geçirgen maruziyet")
    rapor.append("")
    if not poz:
        rapor.append("06 Pozisyonlar.json yok. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    if not icerik_yol:
        rapor.append("Fon içerik arşivi (fon_icerik_YYYY-MM.csv.gz) bulunamadı; bakış geçirgen maruziyet hesaplanamadı. [kayıt]")
        rapor.append(""); return {"durum": "olculemedi"}
    ic = icerik_yukle(icerik_yol)
    listeler = {}
    for r in ic:
        listeler.setdefault(r["fonKodu"], []).append(r)
    taban = sum(float(v.get("deger") or 0) for v in poz.values())
    dogrudan = sum(float(v.get("deger") or 0) for v in poz.values() if (v.get("tip") or "").lower().startswith("hisse"))
    ic_hisse = 0.0; ic_tek = {ad: 0.0 for ad in isimler}; eksik = []; liste_eksik = []
    for v in poz.values():
        if (v.get("tip") or "").lower().startswith("hisse"):
            for ad in isimler:
                if any(t.lower() in (v.get("ad") or "").lower() or t.upper() == v["kod"] for t in ad.split("|")):
                    ic_tek[ad] += float(v.get("deger") or 0)
            continue
        Lk = listeler.get(v["kod"])
        if not Lk:
            eksik.append(v["kod"]); continue
        deger = float(v.get("deger") or 0)
        if any((r.get("listeTam") or "true").lower() == "false" for r in Lk):
            liste_eksik.append(v["kod"])
        for r in Lk:
            a = float(r.get("agirlik") or 0) / 100.0
            if HISSE_TUR.search(r.get("tur") or ""):
                ic_hisse += deger * a
            # tek isim: takma adlar '|' ile ayrilir (DESTEK FAKTORİNG|DESTEK FİNANS|DSTKF); ad alanlari ve BIST kodu taranir
            metin = ((r.get("kiymetAdiHam") or "") + " " + (r.get("ihracci") or "") + " " + (r.get("kiymetAdi") or "")).upper()
            for ad in isimler:
                if any(t.upper() in metin or t.upper() == (r.get("bistKodu") or "").upper() for t in ad.split("|")):
                    ic_tek[ad] += deger * a
    hisse_toplam = dogrudan + ic_hisse
    rapor.append(f"İçerik arşivi: {os.path.basename(icerik_yol)} ({len(listeler)} fon). Taban: pozisyon defteri toplamı {tl(taban, 2)} TL. [kayıt]")
    rapor.append(f"Doğrudan hisse {tl(dogrudan, 2)} TL + fon içindeki hisse {tl(ic_hisse, 2)} TL = {tl(hisse_toplam, 2)} TL, "
                 f"tabanın {yuzde(hisse_toplam / taban) if taban else '-'}. [hesaplama; içerik ağırlıkları KAP ay sonu raporundan, kayıt]")
    if eksik:
        rapor.append(f"İçerik listesi olmayan fon: {', '.join(sorted(set(eksik)))}; bu fonların içi bakışta yok, maruziyet eksik sayılır. [kayıt]")
    if liste_eksik:
        rapor.append(f"Listesi eksik işaretli fon (listeTam=false): {', '.join(sorted(set(liste_eksik)))}. [kayıt]")
    for ad, v in ic_tek.items():
        rapor.append(f"Tek isim {ad}: {tl(v, 2)} TL, tabanın {yuzde(v / taban) if taban else '-'}. [hesaplama]")
    durum = "yesil"
    for anah, hes in (("bakisGecirgenHisse", hisse_toplam),) + tuple((f"tekIsim:{ad}", v) for ad, v in ic_tek.items()):
        bil = bildirilen.get(anah)
        if bil is not None:
            fark = round(hes - bil, 2)
            rapor.append(f"Bildirilen {anah}: {tl(bil, 2)} TL; yeniden hesap {tl(hes, 2)} TL; fark {tl(fark, 2)} TL. [hesaplama]")
            if abs(fark) > TABAN_TOLERANS_TL:
                durum = "kirmizi"
                sapma_ekle(L, f"{anah}-{tarih}", f"bakış geçirgen maruziyet: {anah}", bil, round(hes, 2), HESAP, tarih)
        else:
            rapor.append(f"Bildirilen {anah} verilmedi (--bildirilen {anah}=<TL>); karşılaştırma yapılmadı.")
    rapor.append("")
    return {"durum": durum, "hisseToplam": round(hisse_toplam, 2), "tekIsim": {k: round(v, 2) for k, v in ic_tek.items()}}


def sinama_defter(L, rapor, klasor, tarih):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    em = json_oku(os.path.join(klasor, "05 Emirler.json"), None)
    bri = json_oku(os.path.join(klasor, "01 Brifing Verisi.json"), None)
    rapor.append("## 4. Defter tutarlılığı")
    rapor.append("")
    if not poz or not em:
        rapor.append("05 Emirler.json ya da 06 Pozisyonlar.json yok. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    say = {}
    for v in em.values():
        say[v.get("durum")] = say.get(v.get("durum"), 0) + 1
    rapor.append("Emir defteri: " + ", ".join(f"{k} {n}" for k, n in sorted(say.items())) + ". [kayıt]")
    kirmizi = False
    # gerceklesen emirlerde gerceklesen adet ve fiyat yazili mi
    eksik = [k for k, v in em.items() if v.get("durum") == "GERCEKLESTI" and (v.get("gerceklesen_adet") in (None, "") or v.get("gerceklesen_fiyat") in (None, ""))]
    if eksik:
        kirmizi = True
        rapor.append(f"Gerçekleşti yazılmış ama gerçekleşen adet ya da fiyatı olmayan emir: {', '.join(eksik)}. [kayıt]")
    # bankaya girilmis, tarihi gecmis ve hala bekleyen emirler
    gec = [k for k, v in em.items() if v.get("durum") == "BEKLIYOR" and v.get("verildi") and str(v.get("tarih", "")) < tarih]
    if gec:
        rapor.append(f"Tarihi geçmiş ve hâlâ bekleyen emir: {', '.join(gec)}; ertesi sabah brifingin en üstünde görünmeli. [kayıt]")
    # pozisyon adetleri: defter ile brifing pozisyon listesi
    if bri and bri.get("pozisyon"):
        def norm_k(k):
            k = k.lower().replace("ı", "i").replace("ş", "s").replace("İ", "i")
            return (re.sub(r"bank.*$", "", k).strip()[:6] or k.strip()[:6])
        d = {}
        for v in poz.values(): d[(norm_k(v.get("kurum", "")), v["kod"])] = d.get((norm_k(v.get("kurum", "")), v["kod"]), 0) + float(v.get("adet") or 0)
        b = {}
        for x in bri["pozisyon"]: b[(norm_k(x.get("kurum", "")), x["kod"])] = b.get((norm_k(x.get("kurum", "")), x["kod"]), 0) + float(x.get("adet") or 0)
        farkli = [(a, d.get(a), b.get(a)) for a in sorted(set(d) | set(b)) if d.get(a) != b.get(a)]
        if farkli:
            kirmizi = True
            rapor.append("")
            rapor.append("| Kurum | Fon | Defter adet | Brifing adet |")
            rapor.append("|---|---|---|---|")
            for (k, kod), dv, bv in farkli:
                rapor.append(f"| {k} | {kod} | {tl(dv) if dv is not None else '-'} | {tl(bv) if bv is not None else '-'} |")
            sapma_ekle(L, f"defter-adet-{tarih}", "defter pozisyon adetleri ile brifing pozisyon adetleri", None, None, KAYIT, tarih,
                       "; ".join(f"{k}-{kod}: defter {dv}, brifing {bv}" for (k, kod), dv, bv in farkli))
        else:
            rapor.append("Pozisyon adetleri defter ile brifingde birebir. [kayıt]")
    rapor.append("")
    return {"durum": "kirmizi" if kirmizi else "yesil"}


# ---------------------------------------------------------------- ana

def calistir(klasor, icerik_yol, isimler, bildirilen):
    tarih = os.path.basename(klasor) if klasor else date.today().isoformat()
    L = sapma_yukle()
    rapor = [f"# Denetim raporu, {tarih}", "",
             "Her sayının künyesi köşeli ayraç içindedir: ölçüm, kayıt, hesaplama, varsayım, projeksiyon. "
             "Sapma ancak sebebi kanıtlanınca kapanır (denetim.py --kapat <id> --kanit ...).", ""]
    s1 = sinama_kimlik(L, rapor)
    s2 = sinama_taban(L, rapor, klasor, tarih) if klasor else {"durum": "olculemedi"}
    s3 = sinama_bakis(L, rapor, klasor, tarih, icerik_yol, isimler, bildirilen) if klasor else {"durum": "olculemedi"}
    s4 = sinama_defter(L, rapor, klasor, tarih) if klasor else {"durum": "olculemedi"}
    acik = [s for s in L if s["durum"] == "acik"]
    rapor.append("## Açık sapmalar")
    rapor.append("")
    if not acik:
        rapor.append("Açık sapma yok.")
    for s in acik:
        b = tl(s["bildirilen"], 2) if isinstance(s.get("bildirilen"), (int, float)) else "-"
        h = tl(s["hesaplanan"], 2) if isinstance(s.get("hesaplanan"), (int, float)) else "-"
        f = tl(s["fark"], 2) if isinstance(s.get("fark"), (int, float)) else "-"
        rapor.append(f"- `{s['id']}` ({s['tarih']}): {s['olcum']}; bildirilen {b}, hesaplanan {h}, fark {f}. [{s.get('kunye', '')}]"
                     + (f" {s['not']}" if s.get("not") else ""))
    rapor.append("")
    durumlar = {"kimlik": s1["durum"], "taban": s2["durum"], "bakisGecirgen": s3["durum"], "defter": s4["durum"]}
    genel = "kirmizi" if "kirmizi" in durumlar.values() or acik else ("olculemedi" if "olculemedi" in durumlar.values() else "yesil")
    rapor.insert(2, f"**Genel durum: {genel}.** Sınamalar: " + ", ".join(f"{k} {v}" for k, v in durumlar.items()) + f". Açık sapma: {len(acik)}.")
    sapma_yaz(L)
    ozet = dict(tarih=tarih, genel=genel, sinamalar=durumlar, acikSapma=len(acik), kimlikSapan=s1.get("sapan"),
                tabanDefter=s2.get("tabanDefter"), tabanBrifing=s2.get("tabanBrifing"), tabanFark=s2.get("fark"),
                hisseToplam=s3.get("hisseToplam"), tekIsim=s3.get("tekIsim"))
    json.dump(ozet, open(os.path.join(VERI_KOK, "denetim_son.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    metin = "\n".join(rapor)
    if klasor and VERI_KOK == os.path.join(KOK, "03 Veri"):
        open(os.path.join(klasor, "Denetim.md"), "w", encoding="utf-8").write(metin)
    return metin, genel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", help="günlük rapor klasörü; varsayılan en yeni")
    ap.add_argument("--icerik", help="fon_icerik_YYYY-MM.csv.gz; varsayılan bulunan en yeni")
    ap.add_argument("--isim", action="append", default=None, help="tek isim maruziyeti aranacak ad (tekrarlanabilir); varsayılan 03 Veri/Künye/tek_isim.txt")
    ap.add_argument("--bildirilen", action="append", default=[], help="anahtar=TL; örnek bakisGecirgenHisse=1549921")
    ap.add_argument("--kapat", help="kapatılacak sapma kimliği")
    ap.add_argument("--kanit", default="", help="kapatma kanıtı")
    a = ap.parse_args()
    if a.kapat:
        sapma_kapat(a.kapat, a.kanit); return
    klasor = a.klasor or son_klasor()
    isimler = a.isim
    if isimler is None:
        yol = os.path.join(KUNYE_KLASOR, "tek_isim.txt")
        isimler = [l.strip() for l in open(yol, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(yol) else ["DESTEK FAKTORİNG|DSTKF"]
    bildirilen = {}
    for b in a.bildirilen:
        k, v = b.split("=", 1); bildirilen[k] = float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
    icerik = a.icerik or icerik_bul(os.path.join(os.environ.get("FON_ANALIZ_DEPO", ""), "arsiv") if os.environ.get("FON_ANALIZ_DEPO") else None)
    metin, genel = calistir(klasor, icerik, isimler, bildirilen)
    print(metin)
    sys.exit(0 if genel == "yesil" else 1)


if __name__ == "__main__":
    main()
