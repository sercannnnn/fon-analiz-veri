#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emir defterini PDF olarak üretir (fpdf2, gömülü DejaVu; dış araç yok, 12 Eylül 2026).

Kullanım:
  python3 defter_pdf.py --veri defter_veri.json --cikti "Emir Defteri.pdf"

Beklenen JSON anahtarları (sözleşme): tarih, kapsam, verilecek, planli, verilmis, pozisyon, nakit, kapanan, dip.
Brifing günün kararını anlatır; bu belge defterin kendisidir: bekleyen emirler, pozisyonlar, nakit takvimi, son kapananlar.
Kullanıcı bu belgeyi banka ekranıyla karşılaştırarak okur; grafik yoktur, tablo vardır.
"""
import argparse, json
from pdf_temel import Belge, tl, yz, KIRMIZI, YESIL, INK2


def emir_tablosu(b, emirler, gerekce=True, saat=False):
    satir, renk, ger = [], [], []
    for e in emirler:
        satir.append([e.get("kod", ""), e.get("kurum", ""), e.get("portfoy", ""), e.get("yon", ""), tl(e.get("adet")), tl(e.get("tutar")),
                      (e.get("saat") or "—") if saat else (e.get("valor") or "—")])
        renk.append({3: KIRMIZI if e.get("yon") == "SAT" else YESIL})
        ger.append(e.get("gerekce") if gerekce else None)
    b.tablo(["Kod", "Kurum", "Portföy", "Yön", "Adet", "Tutar TL", "Son saat" if saat else "Gerçekleşme"],
            satir, [18, 30, 24, 14, 28, 34, 32], ["L", "L", "L", "L", "R", "R", "L"], renk, gerekceler=ger)


def yaz(v, cikti):
    b = Belge()
    b.ust("Emir defteri", str(v.get("tarih", "")))
    b.kapsam(v.get("kapsam", ""))

    # İki liste ayrı tutulur: birincisi kullanıcıdan işlem bekler, ikincisi beklemez (kullanıcı 8 Eylül 2026'da bildirdi).
    ver = v.get("verilecek", [])
    b.h2("Bugün verilecek emirler")
    if ver:
        t = sum(x.get("tutar") or 0 for x in ver)
        b.p(f"Bankaya girilmesi gereken {len(ver)} emir bulunmaktadır, toplam {tl(t)} TL. Son işlem saatleri aşağıdadır.", 9)
        emir_tablosu(b, ver, saat=True)
    else:
        b.bos("Bugün bankaya girilmesi gereken emir bulunmamaktadır.")

    pln = v.get("planli", [])
    if pln:
        b.h2("İleri tarihe planlanmış emirler")
        t = sum(x.get("tutar") or 0 for x in pln); bilinmez = sum(1 for x in pln if x.get("tutar") is None)
        if bilinmez == len(pln):
            ozet = f"{len(pln)} emir ileri bir tarihe planlanmıştır; tutarları koşula bağlı olduğu için henüz yazılmamıştır. Bugün yapılacak bir işlem yoktur."
        elif bilinmez:
            ozet = f"{len(pln)} emir ileri bir tarihe planlanmıştır; tutarı belli olanların toplamı {tl(t)} TL, {bilinmez} emrin tutarı koşula bağlıdır. Bugün yapılacak bir işlem yoktur."
        else:
            ozet = f"{len(pln)} emir ileri bir tarihe planlanmıştır, toplam {tl(t)} TL. Bugün yapılacak bir işlem yoktur."
        b.p(ozet, 9); emir_tablosu(b, pln, saat=True)

    vms = v.get("verilmis", [])
    b.h2("Verilmiş, gerçekleşmeyi bekleyen emirler")
    if vms:
        t = sum(x.get("tutar") or 0 for x in vms)
        b.p(f"{len(vms)} emir bankada iletilmiş durumdadır, toplam {tl(t)} TL. Bu emirler için yapılacak bir işlem yoktur; gerçekleşme tarihleri aşağıdadır.", 9)
        emir_tablosu(b, vms)
    else:
        b.bos("Bankada bekleyen emir bulunmamaktadır.")

    poz = v.get("pozisyon", []); tp = sum(x["deger"] for x in poz) or 1
    b.h2("Pozisyonlar"); b.p(f"{len(poz)} pozisyon, toplam {tl(tp)} TL.", 9)
    kurumlar = {}
    for x in poz: kurumlar.setdefault((x.get("kurum", ""), x.get("portfoy", "")), []).append(x)
    for (kur, prt), lst in sorted(kurumlar.items(), key=lambda t: -sum(y["deger"] for y in t[1])):
        alt = sum(y["deger"] for y in lst)
        b.h3(f"{kur}, {str(prt).lower()} · {tl(alt)} TL")
        satir, renk = [], []
        for x in sorted(lst, key=lambda t: -t["deger"]):
            kz, gt = x.get("kz"), x.get("getiri")
            satir.append([x["kod"], x.get("tip", ""), tl(x.get("adet")), tl(x["deger"]), yz(x["deger"] / tp), tl(kz), yz(gt)])
            renk.append({5: YESIL if (kz or 0) >= 0 else KIRMIZI, 6: YESIL if (gt or 0) >= 0 else KIRMIZI})
        b.tablo(["Kod", "Tür", "Adet", "Değer TL", "Ağırlık", "K/Z TL", "Girişten"], satir, [18, 22, 30, 34, 22, 32, 22], ["L", "L", "R", "R", "R", "R", "R"], renk)

    nak = v.get("nakit", [])
    b.h2("Nakit ve ödeme takvimi")
    if nak:
        satir = [[n.get("valor") or "—", n.get("kurum") or n.get("kalem") or "", n.get("portfoy", ""), n.get("yon", ""), tl(n.get("tutar")), (n.get("aciklama") or n.get("not") or "")[:90]] for n in nak]
        b.tablo(["Valör", "Kurum / kalem", "Portföy", "Yön", "Tutar TL", "Açıklama"], satir, [16, 40, 22, 12, 30, 60], ["L", "L", "L", "L", "R", "L"], boy=8)
    else:
        b.bos("Ödeme takviminde kalem yok.")

    kap = v.get("kapanan", [])
    if kap:
        b.h2("Son kapanan emirler"); emir_tablosu(b, kap, gerekce=False)
    b.dip(v.get("dip", ""))
    b.output(cikti)
    return cikti


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--veri", required=True); a.add_argument("--cikti", required=True)
    n = a.parse_args()
    print(yaz(json.load(open(n.veri, encoding="utf-8")), n.cikti))
