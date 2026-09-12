#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KAP acikliklarini gunluk analiz girdisine cevirir.

Iki parca:
  izleme_listesi()  portfoyden ve fon iceriginden IZLEME LISTESI uretir (olculur, elle yazilmaz)
  tara()            gunun TUM KAP bildirimlerini bu listeye karsi tam metin tarar

TASARIM NOTU, 9 Eylul 2026'da ogrenildi
Bugunku Tera-Pusula aciklamasini yapan sirket Katilimevim'di; portfoyumuzde
olmayan, izleme listesinde bulunmayan bir sirket. Onemli olmasinin sebebi
METNINDE "Tera Grubu" gecmesiydi. Bu yuzden tarama, sirket listesiyle
FILTRELENMEZ; gunun butun bildirimleri uzerinde tam metin yapilir. Sirket
filtresi kursaydik bu haberi kacirirdik.

GIZLILIK
Izleme listesi portfoy bilgisidir (hangi fonlari tuttugumuzu ve iclerinde
hangi ismin ne agirlikta oldugunu soyler). Acik depoya YAZILMAZ. Acik depoya
yalnizca KAP'in kendi gunluk bildirim dizini yazilir; o zaten kamuya aciktir.
Eslestirme her zaman ozel tarafta, brifing oturumunda yapilir.
"""
import json, os, re, unicodedata, argparse, csv, sys
from pathlib import Path

# ---------------------------------------------------------------- normalizasyon
def sadelestir(s):
    """Turkce aksanlari ve noktalamayi atar, buyuk harfe cevirir.
    KAP metinlerinde ayni isim 'FAKTORIN', 'Faktoring', 'FAKTORİNG' diye geciyor."""
    s = str(s or "")
    s = s.replace("İ", "I").replace("ı", "i").replace("Ş", "S").replace("ş", "s")
    s = s.replace("Ğ", "G").replace("ğ", "g").replace("Ç", "C").replace("ç", "c")
    s = s.replace("Ö", "O").replace("ö", "o").replace("Ü", "U").replace("ü", "u")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip()

# ---------------------------------------------------------------- izleme listesi
# Kurucu adlari fon kodundan degil kunyeden gelir; grup adi da eklenir cunku bildirim cogu zaman fonu degil grubu anar.
# Tablo PORTFOY BILGISIDIR (hangi kurucularin izlendigini soyler): kodda durmaz, ozel tarafta JSON dosyasindan yuklenir
# (Mac: 03 Veri/Künye/kurucu_grup.json; --kurucu-grup). Dosya yoksa kurucu yalnizca kendi adiyla aranir.
def kurucu_grup_yukle(yol=None):
    """{kurucu: [grup adlari]} sozlugu; yol verilmez ya da dosya yoksa bos sozluk."""
    if yol and os.path.exists(yol):
        return json.load(open(yol, encoding="utf-8"))
    return {}

def izleme_listesi(poz_json, icerik_csv, kunye_csv, esik_kirmizi=10.0, esik_sari=2.0, ek_kurucular=(), kurucu_grup=None):
    """Elde tutulan pozisyonlardan ve fon iceriginden izleme listesi kurar. ek_kurucular: aday fonlarin kuruculari
    (haber kapisi, 12 Eylul 2026 kural metni bolum 5: birinci kademe eslesme adayin giris kapisini kapatir)."""
    kurucu_grup = kurucu_grup or {}
    poz = json.load(open(poz_json, encoding="utf-8")) if isinstance(poz_json, str) else (poz_json or [])
    if isinstance(poz, dict):
        poz = list(poz.values())
    fon = sorted({p["kod"] for p in poz if p.get("tip") == "Fon"})
    his = sorted({p["kod"] for p in poz if p.get("tip") == "Hisse"})

    liste = {}   # anahtar kelime -> {"kademe":1|2, "sebep":str}
    def ekle(kelime, kademe, sebep):
        k = sadelestir(kelime)
        if len(k) < 4:      # cok kisa kelime yanlis eslesme uretir
            return
        onceki = liste.get(k)
        if onceki is None or kademe < onceki["kademe"]:
            liste[k] = {"kademe": kademe, "sebep": sebep}
        elif sebep not in onceki["sebep"]:
            onceki["sebep"] += " · " + sebep

    for h in his:
        ekle(h, 1, f"{h} doğrudan hisse pozisyonu")
    for k in ek_kurucular:
        if isinstance(k, str) and k.strip():
            for g in kurucu_grup.get(k.strip(), [k]):
                ekle(g, 1, f"aday fonun kurucusu {k.strip()}")

    # kurucular
    try:
        import pandas as pd
        kun = pd.read_csv(kunye_csv)
        kur = {r.fonKodu: r.kurucu for _, r in kun.iterrows() if r.fonKodu in fon}
    except Exception:
        kur = {}
    for f in fon:
        ekle(f, 2, f"{f} elde tutulan fon kodu")
        k = kur.get(f)
        if isinstance(k, str):
            for g in kurucu_grup.get(k.strip(), [k]):
                ekle(g, 1, f"{f} fonunun kurucusu")

    # fon icindeki isimler: agirliga gore kademe
    try:
        import pandas as pd
        ic = pd.read_csv(icerik_csv)
    except Exception:
        ic = None
    if ic is not None and len(ic):
        ic = ic[ic.fonKodu.isin(fon)].copy()
        ic["ad"] = ic.kiymetAdi.astype(str)
        ic["k"] = ic.apply(lambda r: r.isin if isinstance(r.isin, str) and r.isin.strip()
                           else r.ad[:30], axis=1)
        g = ic.groupby(["fonKodu", "k"]).agg(a=("agirlik", "sum"), ad=("ad", "first")).reset_index()
        for _, r in g[g.a >= esik_sari].iterrows():
            # BIST kodu: 4-6 harfli, jenerik olmayan
            kodlar = [c for c in re.findall(r"\b([A-ZÇĞİÖŞÜ]{4,6})\b", r.ad)
                      if sadelestir(c) not in JENERIK]
            kademe = 1 if r.a >= esik_kirmizi else 2
            for c in kodlar[:2]:
                ekle(c, kademe, f"{r.fonKodu} içinde %{r.a:.2f}")
            # uzun kurumsal ad parcasi da eklenir (ornek: bir faktoring sirketinin unvaninin ilk iki kelimesi)
            uzun = re.findall(r"\b([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü]{4,})\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü]{4,})", r.ad)
            for a1, a2 in uzun[:1]:
                if sadelestir(a1) not in JENERIK:
                    ekle(f"{a1} {a2}", kademe, f"{r.fonKodu} içinde %{r.a:.2f}")
    return liste

JENERIK = {sadelestir(x) for x in [
    "BORSA","DISI","REPO","HAZINE","YATIRIM","BANKASI","BANKA","VARLIK","PORTFOY","KIRALAMA",
    "SANAYI","TICARET","HOLDING","ANONIM","SIRKET","TURK","TURKIYE","EUROBOND","BONO","TAHVIL",
    "FONU","FON","SERBEST","HISSE","SENEDI","GELISTIRME","ISLETMELERI","HIZMETLERI","FABRIKALARI",
    "GRUP","PROJE","TAAHHUT","DEPOSU","NAKIT","TEMINATI","KATILIM","PARA","PIYASASI","DEGERLER",
    "MENKUL","FINANSAL","GAYRIMENKUL","ELEKTRIK","ENERJI","INSAAT","OTOMOTIV","LIMITED",
    # Asagidakiler ilk kosuda yanlis eslesme uretti: ya kalemin kendisi bir ihracci
    # degil (VIOP nakit teminati), ya da tanidik bir kurumsal adin parcasi
    # ("YAPI VE KREDI", "ING BANK", "PEGASUS HAVA", "TURKIYE SINAI KALKINMA").
    # Ihracciyi bunlarla degil BIST kodu ya da tam unvanla yakalariz.
    "VIOP","BANK","HAVA","KREDI","YAPI","SODA","SINAI","KALKINMA","ZIRAAT","AKBANK",
    "SISECAM","PEGASUS","VAKIFLAR","RONESANS","ALTYAPI"]}

# ---------------------------------------------------------------- konu suzgeci
# Bu konular, ismin kademesi ne olursa olsun her zaman ustteki kademeye cikar.
AGIR_KONU = [
    ("pay devri / birleşme",      ["PAY DEVRI","PAY SAHIPLIGI","DEVRALINMASI","DEVRALMA","BIRLESME",
                                   "HISSE DEVRI","HAKIM ORTAK","YONETIM KONTROLU","CAGRI"]),
    ("düzenleyici işlem",         ["SPK","SERMAYE PIYASASI KURULU","BDDK","IDARI PARA CEZASI",
                                   "YAPTIRIM","SORUSTURMA","TEDBIR","ISLEM SIRASI","SIRA KAPATMA",
                                   "TEDBIRLI","BRUT TAKAS","IZAHNAME"]),
    ("sermaye / temettü",         ["SERMAYE ARTIRIMI","BEDELLI","BEDELSIZ","TEMETTU","KAR PAYI",
                                   "GERI ALIM","PAY GERI ALIM"]),
    ("mali durum",                ["KONKORDATO","IFLAS","ODEME GUCLUGU","TEMERRUT","DEFAULT",
                                   "FAALIYET IZNI","IZIN IPTALI","YENIDEN YAPILANDIRMA"]),
    # 12 Eylul 2026 kural metni, bolum 5: kademe yukselten konulara eklendi
    ("olumsuz denetim görüşü",    ["OLUMSUZ GORUS","GORUS BILDIRMEKTEN KACINMA","SARTLI GORUS","OLUMSUZ DENETIM"]),
    ("yönetim değişikliği",       ["YONETIM KURULU BASKANI","GENEL MUDUR","ISTIFA","GOREVDEN AYRILMA","GOREVDEN ALINMA",
                                   "YONETIM DEGISIKLIGI","ATAMA"]),
    ("ilişkili taraf işlemi",     ["ILISKILI TARAF","ILISKILI TARAFLA","ILISKILI TARAFLARLA"]),
]

# ---------------------------------------------------------------- rutin tur suzgeci ve eksik govde triyaji (12 Eylul 2026)
# Madde 1: eleme yalnizca bildirim TURUNE gore, acik listeyle; sirket adina gore hicbir eleme yapilmaz. Rutin tur kademe
# yukselten konu tasiyorsa haber sayilir. Elenen sayisi her brifingin kapsam satirinda bildirilir; liste genisleyince sayi buyur.
# Liste 12 Eylul 2026'da olcumle genisletildi: fonun standart belgeleri (yatirimci bilgi formu 37, surekli bilgilendirme formu 10,
# izahname 6, risk olcum esaslari, borsa disi ve turev islem ilkeleri, vaad sozlesmesi, finansal tablo) kurucu adini tasidigi icin
# 86 birinci kademe eslesme uretiyordu; hepsi tur adiyla listelendi, Chat'in kural metnine yazmasi istendi.
RUTIN_TURLER = ["Portföy Dağılım Raporu", "Fiyat Raporu", "Gider Raporu", "Repo - Ters Repo Sözleşmesi", "Şirket Genel Bilgi Formu",
                "Yatırımcı Bilgi Formu", "Fon Sürekli Bilgilendirme Formu", "İzahname", "Risk Ölçüm ve Değerleme Esasları",
                "Borsa Dışı Sözleşmelere İlişkin İlkeler", "Türev Araç İşlemlerine İlişkin İlkeler", "Borsa Dışı Vaad Sözleşmesi",
                "Finansal Tablo Bildirimi"]
RUTIN_KONU = re.compile(r"Portföy Dağılım|Fiyat Raporu|Gider Raporu|Toplam Gider|Repo|Şirket Genel Bilgi Formu|Yatırımcı Bilgi Formu|"
                        r"Sürekli Bilgilendirme Formu|İzahname|Risk Ölçüm|Borsa Dışı Sözleşme|Türev Araç İşlemleri|Vaad Sözleşmesi|Finansal Tablo", re.I)


def agir_konu_mu(metin):
    """Metin (konu + ozet) kademe yukselten konu kelimelerinden birini tasiyor mu (AGIR_KONU)."""
    m = sadelestir(metin)
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(sadelestir(k))}(?![A-Z0-9])", m) for _, ks in AGIR_KONU for k in ks)


def rutin_ayir(bildirimler):
    """(rutin olmayanlar, rutin tur olanlar); rutin olanlar yalnizca agir konu tasiyorsa taramada sayilir."""
    rutin = [b for b in bildirimler if RUTIN_KONU.search(b.get("konu") or "")]
    dis = [b for b in bildirimler if not RUTIN_KONU.search(b.get("konu") or "")]
    return dis, rutin


def eksik_triyaj(bildirimler):
    """Madde 3: govdesi cekilemeyen bildirim konusuna gore ikiye ayrilir. Konusu kademe yukselten listedeyse engelleyici
    (adiyla yazilir; o sirketin kurucusunun adaylari icin haber kapisi olculemedi doner); degilse sayilir, tarama 'eksiktir'.
    Donus: (engelleyici liste, engelleyici olmayan sayi)."""
    eng, n = [], 0
    for b in bildirimler:
        if b.get("metinDurumu") != "eksik":
            continue
        if agir_konu_mu(f"{b.get('konu', '')} {b.get('ozet', '')}"):
            eng.append(b)
        else:
            n += 1
    return eng, n


# ---------------------------------------------------------------- tarama
def tara(bildirimler, liste, kendi_fonlarimiz=()):
    """bildirimler: [{'id','tarih','sirket','konu','ozet','metin','url'}]"""
    sonuc = []
    for b in bildirimler:
        gövde = sadelestir(" ".join(str(b.get(k, "")) for k in ("sirket", "konu", "ozet", "metin")))
        vurus = []
        for kelime, bilgi in liste.items():
            if re.search(rf"(?<![A-Z0-9]){re.escape(kelime)}(?![A-Z0-9])", gövde):
                vurus.append((kelime, bilgi))
        if not vurus:
            continue
        kademe = min(v[1]["kademe"] for v in vurus)
        konular = [ad for ad, kelimeler in AGIR_KONU
                   if any(re.search(rf"(?<![A-Z0-9]){re.escape(sadelestir(k))}(?![A-Z0-9])", gövde)
                          for k in kelimeler)]
        if konular and kademe > 1:
            kademe = 1          # agir konu, ismi bir kademe yukari tasir
        sonuc.append({
            "id": b.get("id"), "tarih": b.get("tarih"), "sirket": b.get("sirket"),
            "konu": b.get("konu"), "url": b.get("url"), "ozet": b.get("ozet"),
            "kademe": kademe,
            "eslesen": sorted({v[0] for v in vurus}),
            "sebep": sorted({v[1]["sebep"] for v in vurus}),
            "agir_konu": konular,
        })
    sonuc.sort(key=lambda x: (x["kademe"], x["sirket"] or ""))
    return sonuc

# ---------------------------------------------------------------- brifing bolumu
def brifing_bolumu(vurus, tarama_sayisi):
    """brifing_veri.json icin 'kap' alanini uretir."""
    if not vurus:
        return {"kapsam": f"{tarama_sayisi} KAP bildirimi tarandı, izleme listesiyle eşleşen yok.",
                "kalem": []}
    k1 = [v for v in vurus if v["kademe"] == 1]
    kalem = []
    for v in vurus[:8]:
        gerekce = "; ".join(v["sebep"][:3])
        if v["agir_konu"]:
            gerekce += " · konu: " + ", ".join(v["agir_konu"])
        kalem.append({"sirket": v["sirket"], "konu": v["konu"], "kademe": v["kademe"],
                      "gerekce": gerekce, "url": v.get("url"), "ozet": (v.get("ozet") or "")[:400]})
    return {"kapsam": (f"{tarama_sayisi} KAP bildirimi tarandı; {len(vurus)} tanesi izleme listesiyle "
                       f"eşleşti, {len(k1)} tanesi birinci kademededir."),
            "kalem": kalem}

# ---------------------------------------------------------------- komut satiri
if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--poz", default="poz_yeni.json")
    a.add_argument("--icerik", default="/tmp/ic_fon_icerik_son.csv")
    a.add_argument("--kunye", default="kunye_tam.csv")
    a.add_argument("--bildirim", help="gunun KAP bildirim dizini, JSON dizi")
    a.add_argument("--cikti")
    a.add_argument("--liste-yaz", help="izleme listesini bu dosyaya yaz (portfoy bilgisidir, acik depoya konmaz)")
    a.add_argument("--kurucu-grup", help="kurucu -> grup adlari JSON'u (portfoy bilgisidir, acik depoya konmaz)")
    n = a.parse_args()

    liste = izleme_listesi(n.poz, n.icerik, n.kunye, kurucu_grup=kurucu_grup_yukle(n.kurucu_grup))
    if n.liste_yaz:
        json.dump(liste, open(n.liste_yaz, "w"), ensure_ascii=False, indent=1)
    if not n.bildirim:
        k1 = sorted(k for k, v in liste.items() if v["kademe"] == 1)
        k2 = sorted(k for k, v in liste.items() if v["kademe"] == 2)
        print(f"İzleme listesi: {len(liste)} anahtar kelime "
              f"({len(k1)} birinci kademe, {len(k2)} ikinci kademe)")
        print("\nBirinci kademe:"); [print("  ", k, "→", liste[k]["sebep"]) for k in k1]
        print("\nİkinci kademe:");  [print("  ", k, "→", liste[k]["sebep"]) for k in k2]
        sys.exit(0)
    bild = json.load(open(n.bildirim, encoding="utf-8"))
    v = tara(bild, liste)
    bol = brifing_bolumu(v, len(bild))
    if n.cikti:
        json.dump(bol, open(n.cikti, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(bol, ensure_ascii=False, indent=1))
