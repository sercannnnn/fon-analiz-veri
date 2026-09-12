#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Günlük fon brifingini grafikli PDF olarak üretir (fpdf2, gömülü DejaVu; dış araç yok, 12 Eylül 2026).

Kullanım:
  python3 brifing_pdf.py --veri brifing_veri.json --cikti "Brifing.pdf"

Beklenen JSON anahtarları (sözleşme, değiştirilmez): tarih, kapsam, dun, pozisyon, talimat, hisse_grafik, hisse_not, tetik,
adaylar, adaylar_bos, kap, acik, haber, dip. 12 Eylül 2026'da kullanıcı onayıyla eklenen iki anahtar: `oneri` (liste; her öğe
kod, yon, tutar, gecilen, askida, sira_olcusu, haber, veri_tarihi, etiket, gerekce) ve `sicil` (nesne: ay, verilen, uygulanan,
isabet, metin). İkisi de yoksa eski veriyle üretilen PDF bozulmaz; `oneri` boşsa "bugün öneri yoktur" yazılır.
"""
import argparse, json
from pdf_temel import Belge, tl, yz, S1, KIRMIZI, YESIL, INK2, INK3


def kap_bolum(b, kap):
    b.kapsam(kap.get("kapsam", ""))
    for k in kap.get("kalem", []):
        renk = KIRMIZI if k.get("kademe") == 1 else INK3
        etiket = "1. kademe" if k.get("kademe") == 1 else "2. kademe"
        b.kutu(f"{k.get('sirket', '')} · {k.get('konu', '')} · {etiket}",
               f"{k.get('ozet', '')}\nİzleme listesine giriş sebebi: {k.get('gerekce', '')}", renk)


def oneri_bolum(b, oneriler, sicil):
    """Kural 1 ve bölüm 8: gerekçeli öneriler ya da 'bugün öneri yoktur'; sicil satırı tek cümle."""
    b.h2("Öneri")
    if not oneriler:
        b.bos("Bugün öneri yoktur. Önerisiz gün olağan bir sonuçtur (kural 1).")
    for o in oneriler:
        et = " [yeni]" if o.get("etiket") else ""
        tutar = f"{tl(o['tutar'])} TL" if o.get("tutar") else "tutar yazılamadı"
        bas = f"{o.get('yon', 'AL')} {o.get('kod', '')}{et} · {tutar}"
        ger = o.get("gerekce") or "; ".join(x for x in [
            "geçilen kapılar: " + ", ".join(o.get("gecilen") or []) if o.get("gecilen") else "",
            "askıda: " + ", ".join(o.get("askida") or []) if o.get("askida") else "",
            f"sıralama ölçüsü {o.get('sira_olcusu')}" if o.get("sira_olcusu") is not None else "",
            f"haber: {o.get('haber', '')}", f"veri tarihi {o.get('veri_tarihi', '')}"] if x)
        b.kutu(bas, ger.rstrip(".") + ". Karar kullanıcınındır.", KIRMIZI if o.get("etiket") else S1)
    if sicil:
        b.p(sicil.get("metin") or f"Sicil: bu ay {sicil.get('verilen', 0)} öneri verildi, {sicil.get('uygulanan', 0)} uygulandı; {sicil.get('isabet') or 'henüz isabet ölçümü yok'}.", 8.5, INK2)


def yaz(v, cikti):
    b = Belge()
    p = v.get("pozisyon", []); tp = sum(x["deger"] for x in p) or 1
    top = {}
    for x in p: top[x["kod"]] = top.get(x["kod"], 0) + x["deger"]      # aynı fon birden çok kurumda durabilir
    agirlik = sorted(top.items(), key=lambda t: -t[1])[:12]
    hisse = [(a, d) for a, d in v.get("hisse_grafik", [])] or [(x["kod"], x["fark"]) for x in p if x.get("fark") is not None]

    b.ust("Fon brifingi", str(v.get("tarih", "")))
    b.kapsam(v.get("kapsam", ""))
    if v.get("dun"):
        b.h2("Dün yapılmayanlar")
        for x in v["dun"]: b.kutu(x.get("bas", ""), x.get("ger", ""), KIRMIZI)

    b.h2("Portföy")
    b.p(f"Toplam {tl(tp)} TL", 9.5, kalin=True, bosluk=0.5)
    b.bar_yatay(agirlik, birim=" TL")
    satir, renk = [], []
    for x in sorted(p, key=lambda t: -t["deger"]):
        kz, gt = x.get("kz"), x.get("getiri")
        satir.append([x["kod"], x.get("kurum", ""), tl(x.get("adet")), tl(x["deger"]), yz(x["deger"] / tp), tl(kz), yz(gt)])
        renk.append({5: YESIL if (kz or 0) >= 0 else KIRMIZI, 6: YESIL if (gt or 0) >= 0 else KIRMIZI})
    b.tablo(["Fon", "Kurum", "Adet", "Değer TL", "Ağırlık", "K/Z TL", "Girişten"], satir, [18, 30, 26, 32, 22, 30, 22], ["L", "L", "R", "R", "R", "R", "R"], renk)

    b.h2("Fon talimatları")
    if v.get("talimat"):
        for x in v["talimat"]: b.kutu(x.get("bas", ""), x.get("ger", ""))
    else:
        b.bos("Bugün fon talimatı yok.")

    if "oneri" in v or "sicil" in v:
        oneri_bolum(b, v.get("oneri") or [], v.get("sicil"))

    if hisse:
        b.h2("Hisse dilimi, endekse göre 12 aylık fark"); b.bar_ayrisan(hisse); b.p(v.get("hisse_not", ""), 8.5, INK2)
    if v.get("tetik"):
        b.h2("Tetikler")
        for t in v["tetik"]: b.mermi(t["deger"], t["esik"], t["enb"], t["etiket"])
    b.h2("Parlayan fonlar")
    if v.get("adaylar"): b.sayac(v["adaylar"])
    else: b.bos(v.get("adaylar_bos") or "Bugün kapısı açık aday yok.")
    if v.get("kap"):
        b.h2("KAP taraması"); kap_bolum(b, v["kap"])
    if v.get("haber"):
        b.h2("Haber")
        for h_ in v["haber"]: b.kutu(h_.get("metin", ""), h_.get("kaynak", ""), INK3)
    if v.get("acik"):
        b.h2("Açık konular")
        for i, x in enumerate(v["acik"], 1): b.p(f"{i}. {x if isinstance(x, str) else x.get('metin', '')}", 9)
    b.dip(v.get("dip", ""))
    b.output(cikti)
    return cikti


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--veri", required=True); a.add_argument("--cikti", required=True)
    n = a.parse_args()
    print(yaz(json.load(open(n.veri, encoding="utf-8")), n.cikti))
