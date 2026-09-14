#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fon içerik arşivinin tazeliği ve kurucu düzeyinde ihraççı toplamı (M59, 56 numaralı not, 15 Eylül 2026). Yalnızca standart kütüphane.

Tazelik: kıymet kırılımı KAP'ın aylık portföy dağılım raporundan gelir; rapor ay sonu portföyünü izleyen ayın ilk günlerinde yayımlanır.
Bu yüzden kırılım en iyi hâlde iki hafta, en kötü hâlde altı hafta geridedir. Arşivdeki her fonun veri günü (`veriGunu`: raporun
eşleştiği TEFAS dağılım günü; sütun boşsa rapor ayının son günü) ölçülür; ICERIK_YAS_ESIK_GUN'den eskiyse ya da tutulan fon arşivde
yoksa bakış geçirgen ve yoğunlaşma ölçümleri "ölçülemedi" sayılır (kural 14), sayılar yine yazılır.
Kurucu düzeyinde ihraççı: kapılar fon içindeki ağırlığı ölçer; bir kurucunun bütün fonlarıyla bir ihraççıda tuttuğu toplam nominal ve TL
burada toplanır. Sermayeye oran için ihraççının pay sayısı gerekir (`sermaye` sözlüğü); verilmezse oran ölçülemedi.
"""
import csv, glob, gzip, io, os
from datetime import date, timedelta

ICERIK_YAS_ESIK_GUN = 45   # kullanıcı kabulü 15 Eylül 2026 (58 numaralı not)
TEK_KARSI_TARAF_SINIR = 20.0   # puan; kural metni bölüm 5, tek ihraççı sınırı (bizim kuralımız; serbest fonlar mevzuatta muaf, M62)   # varsayım (kullanıcı onayı bekliyor): aylık rapor + yayım gecikmesi; aşılırsa bir ay atlanmış demektir


def _ay_sonu(ay):
    y, m = int(ay[:4]), int(ay[5:7])
    return (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1)) if m else None


def icerik_oku(arsiv, son_n=2):
    """En yeni son_n fon_icerik_YYYY-MM.csv.gz dosyasının satırları (dict), eski dosya önce."""
    L = []
    for f in sorted(glob.glob(os.path.join(arsiv or "", "fon_icerik_20??-??.csv.gz")))[-son_n:]:
        with gzip.open(f, "rt", encoding="utf-8", newline="") as h:
            L += list(csv.DictReader(h))
    return L


def son_ay_satirlari(satirlar):
    """Her fonun yalnızca en yeni raporunun satırları (raporTarihi en büyük olan). Aylık dosyalar birlikte okununca aynı fon iki ayda
    da bulunur ve toplamlar iki kez sayılırdı."""
    son = {}
    for r in satirlar:
        ay = r.get("raporTarihi") or ""
        if ay > son.get(r["fonKodu"], ""):
            son[r["fonKodu"]] = ay
    return [r for r in satirlar if (r.get("raporTarihi") or "") == son.get(r["fonKodu"])]


def icerik_tazeligi(arsiv, fonlar=(), bugun=None, esik=ICERIK_YAS_ESIK_GUN, satirlar=None):
    """Dönüş: dict(dosya, veri_gunu (arşivin en yeni günü), yas, esik, fon{kod: dict(veri_gunu, yas, ay)}, eksik[kod], eski[kod],
    olculemedi, fon_sayisi, sebep)."""
    bugun = bugun or date.today()
    dosyalar = sorted(glob.glob(os.path.join(arsiv or "", "fon_icerik_20??-??.csv.gz")))
    L = satirlar if satirlar is not None else icerik_oku(arsiv)
    gun = {}
    for r in L:
        vg = (r.get("veriGunu") or "").strip()[:10]
        if not vg:
            ay = (r.get("raporTarihi") or "")[:7]
            vg = _ay_sonu(ay).isoformat() if len(ay) == 7 and ay[4] == "-" else ""
        if vg and vg > gun.get(r["fonKodu"], ""):
            gun[r["fonKodu"]] = vg
    def yas(vg):
        try:
            return (bugun - date.fromisoformat(vg)).days
        except ValueError:
            return None
    en_yeni = max(gun.values()) if gun else None
    fon = {k: dict(veri_gunu=gun.get(k), yas=(yas(gun[k]) if k in gun else None)) for k in fonlar}
    eksik = [k for k in fonlar if k not in gun]
    eski = [k for k in fonlar if k in gun and (yas(gun[k]) is None or yas(gun[k]) > esik)]
    olculemedi = (not gun) or bool(eksik) or bool(eski) or (en_yeni is not None and (yas(en_yeni) or 0) > esik)
    sebep = ("içerik arşivi yok" if not gun else "; ".join(s for s in (
        f"arşivde olmayan fon: {', '.join(eksik)}" if eksik else "", f"eşiği aşan fon: {', '.join(eski)}" if eski else "",
        f"arşivin en yeni günü {en_yeni} ({yas(en_yeni)} gün, eşik {esik})" if en_yeni and (yas(en_yeni) or 0) > esik else "") if s))
    return dict(dosya=os.path.basename(dosyalar[-1]) if dosyalar else None, veri_gunu=en_yeni, yas=(yas(en_yeni) if en_yeni else None), esik=esik,
                fon=fon, eksik=eksik, eski=eski, olculemedi=olculemedi, fon_sayisi=len(gun), sebep=sebep)


def fon_ihracci_ilk(satirlar, fonlar, n=3):
    """M62: her fon için en yüksek n NET ihraççı ağırlığı (aynı ISIN ya da BIST kodunun satırları toplanır, negatif satır dahil; yalnızca
    en yeni rapor). Dönüş: {fonKodu: [dict(kod, agirlik(puan), veri_gunu)]}; arşivde olmayan fon sözlükte yoktur."""
    son = son_ay_satirlari(satirlar)
    top = {}
    for r in son:
        f = r.get("fonKodu")
        if f not in fonlar:
            continue
        kod = (r.get("bistKodu") or r.get("isin") or "").strip()
        if not kod:
            continue
        try:
            a = float(r.get("agirlik") or 0)
        except ValueError:
            continue
        d = top.setdefault(f, {})
        e = d.setdefault(kod, dict(kod=kod, agirlik=0.0, veri_gunu=(r.get("veriGunu") or "").strip()[:10] or None, ay=r.get("raporTarihi")))
        e["agirlik"] += a
    out = {}
    for f, d in top.items():
        L = sorted(d.values(), key=lambda e: -e["agirlik"])[:n]
        for e in L:
            e["agirlik"] = round(e["agirlik"], 2)
            if not e["veri_gunu"]:
                e["veri_gunu"] = (_ay_sonu(e["ay"]).isoformat() if e.get("ay") and len(e["ay"]) == 7 else None)
        out[f] = L
    return out


def kurucu_ihracci(satirlar, fon_kurucu, sermaye=None, kurucular=None):
    """Kurucunun bütün fonlarıyla bir ihraççıda tuttuğu toplam: nominal (pay adedi) ve TL, fon listesiyle; aynı fonun aynı kıymetteki
    satırları net toplanır (negatif satır dahil). Yalnızca hisse satırları (bistKodu dolu). sermaye: {bistKodu: paySayisi} verilirse
    oran = nominal / paySayisi, yoksa None. Dönüş: TL'ye göre azalan liste [dict(kurucu, bistKodu, nominal, tl, fonlar, oran)]."""
    top = {}
    for r in son_ay_satirlari(satirlar):
        kod = (r.get("bistKodu") or "").strip(); kur = fon_kurucu.get(r.get("fonKodu"))
        if not kod or not kur or (kurucular and kur not in kurucular):
            continue
        try:
            nom = float(r.get("nominal") or 0); tl = float(r.get("rayicDeger") or 0)
        except ValueError:
            continue
        d = top.setdefault((kur, kod), dict(kurucu=kur, bistKodu=kod, nominal=0.0, tl=0.0, fonlar=set()))
        d["nominal"] += nom; d["tl"] += tl; d["fonlar"].add(r["fonKodu"])
    out = []
    for d in top.values():
        ps = (sermaye or {}).get(d["bistKodu"])
        d["fonlar"] = sorted(d["fonlar"]); d["oran"] = (d["nominal"] / float(ps)) if ps else None
        out.append(d)
    return sorted(out, key=lambda d: -d["tl"])


def sermaye_yukle(yol):
    """03 Veri/Künye/odenmis_sermaye.csv: bistKodu,paySayisi,kaynak (kullanıcı ya da Chat yazar); yoksa boş."""
    if not yol or not os.path.exists(yol):
        return {}
    out = {}
    for r in csv.DictReader(open(yol, encoding="utf-8")):
        try:
            out[r["bistKodu"].strip().upper()] = float(str(r["paySayisi"]).replace(".", "").replace(",", "."))
        except (KeyError, ValueError):
            continue
    return out
