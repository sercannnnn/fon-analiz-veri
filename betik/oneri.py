#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Öneri motoru ve öneri sicili (12 Eylül 2026 kural metni: kural 1, 14, 18, bölüm 6 ve 8).

Kural 1: sistem ölçer, karşılaştırır ve gerekçeli bir emir önerisi yazar; kararı kullanıcı verir. Her öneri dört şeyi taşır:
geçilen ve geçilmeyen kapılar, sıralama ölçüsü, haber ve kaynağı, verinin tarihi. Sıralama tek ölçüyledir (risk başına
getiri), bileşik puan yoktur. Ölçüm öneri üretmiyorsa "bugün öneri yoktur" yazılır.
Kural 14: aday listesi emir değildir; öneri süreklilik şartından (GEREKLI_SEANS ardışık gün kapısı açık) sonra yazılır;
bilinemeyen kapı geçilmemiş sayılır.
Kural 18: her öneri sicile yazılır (tarih, kod, yön, tutar, gerekçe, ölçüm tarihi, sıralama ölçüsü, uygulandı mı); yirmi
seans sonra sonucu ölçülür; ayda bir raporlanır. Sicil üretilmiyorsa öneri rejimi durur.
Bölüm 6: agresif dilim sermayenin %10'u, tek fonda %5 (kullanıcı kararı 12 Eylül 2026, kademesiz); "yeni" etiketi; C1 ve C5
askıya alma her öneride açıkça yazılır; kendi alımıyla fiyat yapan fon (20 seansta pay adedi > %1.000) yarı boyutla.

Gizlilik: sicil ve aday geçmişi portföy bilgisidir, açık depoya yazılmaz (03 Veri altında durur).
"""
import json, os
from datetime import date, datetime, timedelta

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SICIL_YOL = os.path.join(KOK, "03 Veri", "oneri_sicili.json")
ADAY_YOL = os.path.join(KOK, "03 Veri", "aday_gecmisi.json")
GEREKLI_SEANS = 3          # süreklilik şartı: parlayan_fon.GEREKLI_SEANS ile aynı
SONUC_SEANS = 20           # kural 18: öneri sonucu yirmi seans sonra ölçülür
UYGULAMA_GUN = 5           # emir defterinde öneri tarihinden en çok bu kadar gün sonra gerçekleşen aynı yönlü emir "uygulandı" sayılır


def _oku(yol, bos):
    if os.path.exists(yol):
        return json.load(open(yol, encoding="utf-8"))
    return bos


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    json.dump(veri, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _tl(x):
    return f"{x:,.0f}".replace(",", ".") + " TL"


def _yuzde(x, hane=1):
    return ("-" if x < 0 else "") + "%" + f"{abs(x) * 100:,.{hane}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- süreklilik
def ardisik_guncelle(tarih, acik_kodlar, yol=None):
    """Kapısı açık adayların gün gün kaydı; dönüş: kod -> bugün dahil ardışık açık gün sayısı. Aynı gün iki kez çağrılırsa
    günün kaydı üzerine yazılır. Kaynak: ölçüm."""
    yol = yol or ADAY_YOL
    g = _oku(yol, {})
    g[tarih] = sorted(acik_kodlar)
    gunler = sorted(g)[-60:]
    g = {t: g[t] for t in gunler}
    _yaz(yol, g)
    say = {}
    for k in acik_kodlar:
        n = 0
        for t in reversed(gunler):
            if k in g[t]:
                n += 1
            else:
                break
        say[k] = n
    return say


# ---------------------------------------------------------------- öneri
def _gerekce(r, s_askida, haber_notu, veri_tarihi, sira_olcusu):
    gecilen = [x for x in ("C1", "C2", "C3", "C4", "C5", "C6", "G1", "G2", "G3", "G4", "G5a", "G5b") if x not in s_askida]
    parca = [f"kapılar: hepsi geçildi" + (f"; askıda: {', '.join(s_askida)} (agresif dilim, kural 14 istisnası)" if s_askida else ""),
             f"sıralama ölçüsü: risk başına getiri {str(round(sira_olcusu, 2)).replace('.', ',')} (30 seans yıllık hız / 60 seans oynaklık)",
             f"haber: {haber_notu}",
             f"veri tarihi: {veri_tarihi}"]
    return "; ".join(parca)


def oneri_uret(ana, agresif, tarih, veri_tarihi, sermaye, agresif_mevcut, haber_notu, ardisik):
    """ana, agresif: parlayan_fon çıktıları (DataFrame ya da kayıt listesi) — kapi_durumu, getori, askida, kurucu_gecmis,
    net_giris20, buyume_kaynagi, dpay20 alanları. sermaye: portföy tabanı TL (kaynak yazılır). agresif_mevcut: dilimde zaten
    duran tutar. ardisik: kod -> ardışık açık gün. Dönüş: öneri listesi (boş olabilir) ve notlar."""
    def kayitlar(df):
        if df is None:
            return []
        return df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    oneriler, notlar = [], []
    # ana portföy: kapısı açık ve süreklilik şartı; boyut kuralı ana portföy için kural metninde yazılı değil (tutar boş, kullanıcı belirler)
    for r in sorted([x for x in kayitlar(ana) if x.get("kapi_durumu") == "acik"], key=lambda x: -(x.get("getori") or 0)):
        n = ardisik.get(r["fonKodu"], 0)
        if n < GEREKLI_SEANS:
            notlar.append(f"{r['fonKodu']} kapısı açık, süreklilik {n}/{GEREKLI_SEANS} gün; öneri yazılmadı (kural 14)")
            continue
        oneriler.append(dict(kod=r["fonKodu"], ad=r.get("fonAd"), yon="AL", dilim="ana", etiket="", tutar=None,
                             tutar_notu="ana portföy için boyut kuralı yazılı değil; tutarı kullanıcı belirler",
                             sira_olcusu=r.get("getori"), ardisik=n,
                             gerekce=_gerekce(r, [], haber_notu, veri_tarihi, r.get("getori") or 0)))
    # agresif dilim
    kalan = max(0.0, sermaye * 0.10 - (agresif_mevcut or 0)) if sermaye else 0.0
    tek = sermaye * 0.05 if sermaye else 0.0
    for r in sorted([x for x in kayitlar(agresif) if x.get("kapi_durumu") == "acik"], key=lambda x: -(x.get("sira_olcusu") or 0)):
        n = ardisik.get(r["fonKodu"], 0)
        if n < GEREKLI_SEANS:
            notlar.append(f"{r['fonKodu']} (yeni) kapısı açık, süreklilik {n}/{GEREKLI_SEANS} gün; öneri yazılmadı (kural 14)")
            continue
        if kalan <= 0:
            notlar.append(f"{r['fonKodu']} (yeni) süreklilik sağlandı ama agresif dilim dolu (sermayenin %10'u); öneri yazılmadı")
            continue
        ust = min(tek, kalan)
        buyume = bool(r.get("buyume_kaynagi"))
        if buyume:
            ust = ust / 2
        tutar = round(ust, -3)
        kalan -= tutar
        askida = [x for x in str(r.get("askida") or "").split(" | ") if x]
        g = _gerekce(r, [a.split()[0] for a in askida], haber_notu, veri_tarihi, r.get("sira_olcusu") or 0)
        g += (f"; 20 seanslık net giriş oranı {_yuzde(r['net_giris20'])}" if r.get("net_giris20") is not None and r.get("net_giris20") == r.get("net_giris20") else "; net giriş oranı ölçülemedi")
        g += f"; {r.get('kurucu_gecmis') or 'kurucu geçmişi ölçülemedi'}"
        if buyume:
            g += f"; büyüme kaynağı: 20 seansta pay adedi {_yuzde(r['dpay20'], 0)} arttı, fon kendi alımıyla fiyat yapıyor olabilir, boyut yarıya indirildi"
        oneriler.append(dict(kod=r["fonKodu"], ad=r.get("fonAd"), yon="AL", dilim="agresif", etiket="yeni", tutar=tutar,
                             tutar_notu=f"agresif dilim: sermayenin %10'u toplam, tek fonda %5; sermaye {_tl(sermaye)} (kaynak: pozisyonlar)",
                             sira_olcusu=r.get("sira_olcusu"), ardisik=n, askida=askida, gerekce=g))
    return oneriler, notlar


# ---------------------------------------------------------------- sicil
def sicil_yaz(oneriler, tarih, veri_tarihi, yol=None):
    """Kural 18: verilen her öneri sicile yazılır; aynı gün aynı kod tekrar yazılmaz. Dönüş: yazılan kayıt sayısı."""
    yol = yol or SICIL_YOL
    s = _oku(yol, [])
    var = {(x["tarih"], x["kod"]) for x in s}
    n = 0
    for i, o in enumerate(oneriler, 1):
        if (tarih, o["kod"]) in var:
            continue
        s.append(dict(id=f"{tarih.replace('-', '')}-O{i:02d}", tarih=tarih, kod=o["kod"], yon=o["yon"], dilim=o["dilim"], etiket=o.get("etiket", ""),
                      tutar=o.get("tutar"), gerekce=o["gerekce"], olcumTarihi=veri_tarihi, siralamaOlcusu=o.get("sira_olcusu"),
                      uygulandi=None, uygulamaKaynagi=None, sonuc20=None, sonucTarihi=None))
        n += 1
    _yaz(yol, s)
    return n


def sicil_guncelle(fiyat, emirler=None, yol=None):
    """fiyat: fonKodu -> tarih sıralı (tarih, fiyat) listesi ya da pandas DataFrame(tarih, fonKodu, fiyat).
    Yirmi seansı dolan önerinin sonucu (öneri gününün fiyatından 20 seans sonraki fiyata getiri) yazılır.
    emirler: emir defteri sözlüğü; öneri tarihinden en çok UYGULAMA_GUN gün sonra GERCEKLESTI olan aynı yönlü emir
    'uygulandı' sayılır (kaynak: emir defteri). Aksi hâlde alan boş kalır; kullanıcı elle işaretler."""
    yol = yol or SICIL_YOL
    s = _oku(yol, [])
    if not s:
        return 0
    seri = {}
    if hasattr(fiyat, "groupby"):
        for k, g in fiyat.groupby("fonKodu"):
            g = g.sort_values("tarih")
            seri[k] = [(str(t)[:10], float(p)) for t, p in zip(g.tarih, g.fiyat)]
    else:
        seri = fiyat
    n = 0
    for x in s:
        if x.get("sonuc20") is None and x["kod"] in seri:
            L = seri[x["kod"]]
            i = next((j for j, (t, _) in enumerate(L) if t >= x["tarih"]), None)
            if i is not None and i + SONUC_SEANS < len(L):
                p0, (t1, p1) = L[i][1], L[i + SONUC_SEANS]
                if p0 > 0:
                    x["sonuc20"] = p1 / p0 - 1; x["sonucTarihi"] = t1; n += 1
        if x.get("uygulandi") is None and emirler:
            t0 = datetime.strptime(x["tarih"], "%Y-%m-%d").date()
            for eid, e in emirler.items():
                try:
                    te = datetime.strptime(e.get("tarih", ""), "%Y-%m-%d").date()
                except ValueError:
                    continue
                if e.get("kod") == x["kod"] and e.get("yon") == x["yon"] and e.get("durum") == "GERCEKLESTI" and 0 <= (te - t0).days <= UYGULAMA_GUN:
                    x["uygulandi"] = True; x["uygulamaKaynagi"] = f"emir {eid}"; n += 1; break
    _yaz(yol, s)
    return n


def sicil_ozeti(ay, yol=None):
    """Ay (YYYY-MM) için: verilen, uygulanan, uygulanan ve uygulanmayanların ortalama 20 seans getirisi. Kaynak: sicil."""
    yol = yol or SICIL_YOL
    s = [x for x in _oku(yol, []) if x["tarih"][:7] == ay]
    def ort(L):
        v = [x["sonuc20"] for x in L if x.get("sonuc20") is not None]
        return (sum(v) / len(v), len(v)) if v else (None, 0)
    uyg = [x for x in s if x.get("uygulandi") is True]
    uym = [x for x in s if x.get("uygulandi") is not True]
    return dict(ay=ay, verilen=len(s), uygulanan=len(uyg), bilinmeyen=sum(1 for x in s if x.get("uygulandi") is None),
                uygulanan_getiri=ort(uyg), uygulanmayan_getiri=ort(uym))


def sicil_satiri(tarih, yol=None):
    """Brifingdeki tek cümlelik sicil satırı (bölüm 8)."""
    yol = yol or SICIL_YOL
    if not os.path.exists(yol):
        return "Sicil: öneri sicili henüz yok; ilk öneriyle açılır."
    o = sicil_ozeti(tarih[:7], yol)
    if not o["verilen"]:
        return "Sicil: bu ay öneri verilmedi."
    g = o["uygulanan_getiri"]
    isabet = (f"uygulanan {o['uygulanan']} önerinin 20 seans ortalama getirisi {_yuzde(g[0])} ({g[1]} ölçüm)"
              if g[0] is not None else "henüz 20 seansı dolan öneri yok")
    return f"Sicil: bu ay {o['verilen']} öneri verildi, {o['uygulanan']} uygulandı, {o['bilinmeyen']} tanesinin uygulanıp uygulanmadığı işaretlenmedi; {isabet}."


# ---------------------------------------------------------------- brifing bölümü
def brifing_bolumu(oneriler, notlar, tarih, haber_notu):
    L = ["## Öneri", ""]
    if not oneriler:
        L.append("Bugün öneri yoktur. Önerisiz gün olağan bir sonuçtur; ölçüm bir öneri üretmediği için bölüm boş bırakılmadı, bu cümle yazıldı (kural 1).")
    for o in oneriler:
        tutar = _tl(o["tutar"]) if o.get("tutar") else "tutar: kullanıcı belirler"
        et = " [yeni]" if o.get("etiket") else ""
        L.append(f"- **{o['yon']} {o['kod']}{et}**, {o.get('ad') or ''}: {tutar}. {o['gerekce']}. Süreklilik {o['ardisik']} gün. {o['tutar_notu']}. Karar kullanıcınındır.")
    if notlar:
        L.append("")
        L.append("Öneriye dönüşmeyenler: " + "; ".join(notlar[:8]) + ".")
    L.append("")
    L.append(sicil_satiri(tarih))
    L.append(f"Haber kapısı: {haber_notu}")
    L.append("")
    return L
