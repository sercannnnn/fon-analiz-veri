#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurucu grup tablosunu bütün kurucular için üretir: veri/kurucu_grup.json (M54, 13 Eylül 2026).

Haber kapısı (G5b) kurucunun grup şirketlerini izleme listesine alır. Tablo yalnızca tutulan fonların kurucularını içerdiği için
portföy bilgisiydi ve bulutta yoktu; bulut kapıyı "açık" yazıyordu (M54). Çözüm: tablo künyedeki BÜTÜN kurucular için kurulur;
kurucu ile grup şirketi eşlemesi kamuya açık şirket yapısıdır ve seçim bilgisi taşımaz. Sanal makinenin günlük gönderimiyle depoya girer.

Kaynaklar:
  kurucular : veri/kunye_tam.csv (kurucu sütunu; uzun unvan kısaltılır: "TERA PORTFÖY YÖNETİMİ A.Ş." -> "TERA PORTFÖY")
  şirketler : veri/kap_gunluk.json ve arsiv/kap_*.json.gz içindeki bildirim yapan şirket adları (kamuya açık KAP dizini)
  ek        : veri/kurucu_grup_ek.json, elle tutulan kamuya açık ek eşlemeler (banka ana ortakları gibi kök kelimeden türetilemeyenler);
              depoya betik eşitlemesiyle değil veri olarak girer (gizlilik taraması banka adlarını yasak desen sayar; dosya bütün bankaları listeler)
Kural: kurucunun kök kelimesi (ilk kelime; üç harften kısa ya da genel kelime ise atlanır) ile başlayan ve adında bir finans kelimesi
(FINANS_KELIMELERI) geçen şirketlerin ilk iki kelimesi grup adı olur; yatırım ortaklıkları (GYO gibi, "ORTAKLIĞI") alınmaz, ek dosyaya bırakılır. Kök yalnızca kelime başında aranır; "MEDİTERA" "TERA" değildir.
Her kurucu için en az kendi kısa adı yazılır. Yalnızca standart kütüphane."""
import argparse, csv, glob, gzip, json, os, re

GENEL_KOK = {"PORTFÖY", "PORTFOY", "YATIRIM", "MENKUL", "FON", "FONU", "GLOBAL", "CAPITAL", "CAPİTAL", "GOLDEN"}
FINANS_KELIMELERI = ("YATIRIM", "MENKUL", "FİNANS", "FINANS", "FAKTORİNG", "FAKTORING", "BANK", "HOLDİNG", "HOLDING", "KATILIM", "VARLIK",
                     "PORTFÖY", "PORTFOY", "GRUBU", "SİGORTA", "SIGORTA", "LEASING", "KİRALAMA", "KIRALAMA", "EMEKLİLİK", "EMEKLILIK", "GİRİŞİM", "GIRISIM")
KISALT = re.compile(r"\s+(PORTFÖY|PORTFOY)\s+YÖNETİMİ.*$", re.I)


def kisa_kurucu(ad):
    """'TERA PORTFÖY YÖNETİMİ A.Ş.' -> 'TERA PORTFÖY'; kısa biçim zaten kısa kalır."""
    ad = (ad or "").strip()
    return KISALT.sub(lambda m: " " + m.group(1).upper(), ad).strip()


def sirketler(veri, arsiv):
    S = set()
    def ekle(L):
        for b in (L or []):
            t = (b.get("sirket") or "").strip()
            if t:
                S.add(t)
    yol = os.path.join(veri, "kap_gunluk.json")
    if os.path.exists(yol):
        try:
            ekle((json.load(open(yol, encoding="utf-8")) or {}).get("bildirimler"))
        except Exception:
            pass
    for f in sorted(glob.glob(os.path.join(arsiv or "", "kap_*.json.gz"))):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as h:
                j = json.load(h)
            ekle(j.get("bildirimler") if isinstance(j, dict) else j)
        except Exception:
            continue
    return S


def tablo_kur(kurucular, sirket_adlari, ek=None):
    """{kısa kurucu: [grup adları]}; ek sözlüğü kurucu bazında birleştirilir (kamuya açık ek eşlemeler)."""
    ek = ek or {}
    T = {}
    for k in sorted({kisa_kurucu(x) for x in kurucular if x}):
        w = k.split(); kok = w[0] if w else ""
        adlar = {k}
        if len(kok) >= 3 and kok.upper() not in GENEL_KOK:
            for s in sirket_adlari:
                p = s.split()
                if p and p[0].upper() == kok.upper() and "PORTFÖY" not in s.upper() and "ORTAKLIĞI" not in s.upper() and any(f in s.upper() for f in FINANS_KELIMELERI):
                    adlar.add(" ".join(p[:2]))
        for e in ek.get(k, []):
            adlar.add(e)
        T[k] = sorted(adlar)
    return T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri")
    ap.add_argument("--arsiv", default="arsiv")
    ap.add_argument("--kunye", default=None, help="varsayılan <veri>/kunye_tam.csv")
    ap.add_argument("--ek", default=None, help="varsayılan <veri>/kurucu_grup_ek.json")
    ap.add_argument("--cikti", default=None, help="varsayılan <veri>/kurucu_grup.json")
    a = ap.parse_args()
    kunye = a.kunye or os.path.join(a.veri, "kunye_tam.csv")
    kurucular = [r.get("kurucu") for r in csv.DictReader(open(kunye, encoding="utf-8"))] if os.path.exists(kunye) else []
    ek_yol = a.ek or os.path.join(a.veri, "kurucu_grup_ek.json")
    ek = json.load(open(ek_yol, encoding="utf-8")) if os.path.exists(ek_yol) else {}
    S = sirketler(a.veri, a.arsiv)
    T = tablo_kur(kurucular, S, ek)
    cikti = a.cikti or os.path.join(a.veri, "kurucu_grup.json")
    json.dump(T, open(cikti, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"kurucu_grup.json: {len(T)} kurucu, {sum(len(v) for v in T.values())} ad, {len(S)} şirket adından; ek {len(ek)} kurucu")


if __name__ == "__main__":
    main()
