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
        # M38 (13 Eylül 2026): r.isin pandas'ın Series.isin yöntemidir, sütun değil; öznitelikle okununca ISIN hiç kullanılmıyor ve
        # kıymet adı boş satırda (pandas 3 string dtype'ta eksik değer nan kalır) [:30] patlıyordu. Sütunlar köşeli ayraçla okunur.
        ic["k"] = ic.apply(lambda r: r["isin"] if isinstance(r["isin"], str) and r["isin"].strip()
                           else str(r["ad"])[:30], axis=1)
        g = ic.groupby(["fonKodu", "k"]).agg(a=("agirlik", "sum"), ad=("ad", "first")).reset_index()
        for _, r in g[g.a >= esik_sari].iterrows():
            ad = r.ad if isinstance(r.ad, str) else ""     # adı boş kıymet (M38): ad yok, BIST kodu ve unvan parçası aranmaz
            # BIST kodu: 4-6 harfli, jenerik olmayan
            kodlar = [c for c in re.findall(r"\b([A-ZÇĞİÖŞÜ]{4,6})\b", ad)
                      if sadelestir(c) not in JENERIK]
            kademe = 1 if r.a >= esik_kirmizi else 2
            for c in kodlar[:2]:
                ekle(c, kademe, f"{r.fonKodu} içinde %{r.a:.2f}")
            # uzun kurumsal ad parcasi da eklenir (ornek: bir faktoring sirketinin unvaninin ilk iki kelimesi)
            uzun = re.findall(r"\b([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü]{4,})\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü]{4,})", ad)
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
                                   "TEDBIRLI","BRUT TAKAS"]),   # M55: IZAHNAME cikti; izahname ve bilgi formu aileleri dikkat konusu degildir
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
# M24 (Chat, 12 Eylul 2026): eslesme konu parcasina gore degil TUR ADINA gore, birebir (KAP'in konu alani; bastaki "01285 - " kodu
# ve bosluklar atilir). "Repo Karsi Tarafi Temerrudu" bu yuzden rutin degildir. M25: izahname duzenleyici islem konusudur, listede
# degildir; finansal tablo bildirimi de degildir (hisse cikis kapisi 1 ondan beslenir). Liste Chat'in 12 Eylul kural metnindeki
# on iki addir; "Repo - Ters Repo Sozlesmesi" KAP'ta "Borsa Disi Repo - Ters Repo Sozlesmesi" adiyla gecer, o ad yazildi.
# M55 (13 Eylul 2026, not 49): kapinin tetigi varliktan maddilige. Yalnizca bu olaylar kapiyi kapatir; AGIR_KONU artik dikkat (bilgi) listesidir,
# kapatmaz. Liste dar ve aciktir; genisletmek kural degisikligidir.
KAPATAN_OLAY = [
    ("kontrol veya pay devri, devralma, birleşme, bölünme", ["PAY DEVRI","HISSE DEVRI","DEVRALINMASI","DEVRALMA","DEVRALINMA","BIRLESME","BOLUNME",
                                                             "HAKIM ORTAK","YONETIM KONTROLU","KONTROL DEGISIKLIGI","CAGRI YOLUYLA"]),
    ("faaliyet izninin iptali ya da sınırlandırılması",     ["FAALIYET IZNI","IZIN IPTALI","IZNININ IPTALI","IZNI IPTAL","YETKI BELGESI IPTAL","FAALIYETLERININ DURDURULMASI",
                                                             "FAALIYETININ SINIRLANDIRILMASI","FAALIYET SINIRLAMASI"]),
    ("idari yaptırım, idari para cezası",                   ["IDARI PARA CEZASI","IDARI YAPTIRIM","YAPTIRIM KARARI"]),
    ("iflas, konkordato, temerrüt",                         ["IFLAS","KONKORDATO","TEMERRUT","ODEME GUCLUGU"]),
    ("fonun tasfiyesi ya da işlemlerinin durdurulması",     ["TASFIYE","ISLEMLERININ DURDURULMASI","ISLEM SIRASI KAPATMA","SIRA KAPATMA","ISLEMLERI DURDURULMUS"]),
    ("kurucunun ya da portföy yöneticisinin değişmesi",     ["KURUCU DEGISIKLIGI","KURUCUNUN DEGISMESI","KURUCUSUNUN DEGISMESI","PORTFOY YONETICISI DEGISIKLIGI",
                                                             "PORTFOY YONETICISININ DEGISMESI","PORTFOY YONETIM SIRKETININ DEGISMESI","YONETICI DEGISIKLIGI"]),
]
KAP_TURLERI = {"OZEL DURUM ACIKLAMASI GENEL", "GENEL ACIKLAMA"}   # M55: iceriksiz "kap" turleri; ozeti ve govdesi bos gelirse o kurucu icin kapi olculemedi
# M56 (not 51): tasfiye maddesi adayin kendi fonuna uygulanir. Ozel fon tasfiyesi hic sayilmaz (sureli kurulur), kardes fonun tasfiyesi
# bilgi satiridir; ayni kurucuda TASFIYE_PENCERE_GUN icinde TASFIYE_KURUCU_ESIK ve ustu kamuya acik fon tasfiyesi yonetici isaretidir ve kapatir.
TASFIYE_AD = "fonun tasfiyesi ya da işlemlerinin durdurulması"
TASFIYE_KURUCU_ESIK = 3
TASFIYE_PENCERE_GUN = 28        # takvim gunu, yaklasik yirmi seans


def ozel_fon_mu(sirket):
    return "OZEL FON" in sadelestir(sirket or "")


def kap_gecmisi(arsiv, bugun=None, gun=TASFIYE_PENCERE_GUN):
    """arsiv/kap_YYYY-MM.json.gz icinden son `gun` takvim gunune dusen bildirimler (M56 tasfiye sayimi icin). Arsiv yoksa bos liste."""
    import glob, gzip
    from datetime import date, timedelta
    if not arsiv or not os.path.isdir(arsiv):
        return []
    bugun = bugun or date.today()
    bas = (bugun - timedelta(days=gun)).isoformat()
    L = []
    for f in sorted(glob.glob(os.path.join(arsiv, "kap_*.json.gz")))[-2:]:
        try:
            with gzip.open(f, "rt", encoding="utf-8") as h:
                j = json.load(h)
        except Exception:
            continue
        for b in (j.get("bildirimler") if isinstance(j, dict) else j) or []:
            if str(b.get("tarih", ""))[:10] >= bas:
                L.append(b)
    return L


def kapatan_olaylar(metin):
    """Metindeki kapatan olay adlari (KAPATAN_OLAY, kok deseniyle)."""
    m = sadelestir(metin)
    return [ad for ad, ks in KAPATAN_OLAY if any(re.search(_kok_deseni(k), m) for k in ks)]


def kap_bos_mu(b):
    """Ozel Durum Aciklamasi (Genel) ya da Genel Aciklama olup ozeti ve govdesi bos bildirim: icerigi okunmadan siniflanamaz (M55)."""
    return tur_adi(b.get("konu", "")) in KAP_TURLERI and not str(b.get("ozet") or "").strip() and not str(b.get("metin") or "").strip()


RUTIN_TURLER = ["Portföy Dağılım Raporu", "Fiyat Raporu", "Gider Raporu", "Toplam Gider Oranı Bildirimi",
                "Borsa Dışı Repo - Ters Repo Sözleşmesi", "Şirket Genel Bilgi Formu", "Yatırımcı Bilgi Formu",
                "Fon Sürekli Bilgilendirme Formu", "Risk Ölçüm ve Değerleme Esasları", "Borsa Dışı Sözleşmelere İlişkin İlkeler",
                "Türev Araç İşlemlerine İlişkin İlkeler", "Borsa Dışı Vaad Sözleşmesi"]
_RUTIN_SADE = {sadelestir(t) for t in RUTIN_TURLER}


def tur_adi(konu):
    """KAP konu alanindan tur adi: bastaki sayisal kod ("01285 - ") ve kenar bosluklari atilir, sadelestirilir."""
    return sadelestir(re.sub(r"^\s*\d{3,6}\s*-\s*", "", str(konu or "")))


def rutin_mu(konu):
    return tur_adi(konu) in _RUTIN_SADE


_YUMUSAMA = {"T": "[TD]", "K": "[KG]", "P": "[PB]", "C": "[CÇ]"}


def _kok_deseni(k):
    """Kelime koku deseni: baslangic sinirli, son serbest (ek alabilir); son unsuz yumusayabilir (TEMERRUT -> TEMERRUDU,
    KIRALIK -> KIRALIGI). Sadelestir sonrasi metinde Turkce harfler ASCII'ye inmis olur, C sinifi yine de verilir."""
    sade = sadelestir(k)
    if sade and sade[-1] in _YUMUSAMA:
        sade = re.escape(sade[:-1]) + _YUMUSAMA[sade[-1]]
    else:
        sade = re.escape(sade)
    return rf"(?<![A-Z0-9]){sade}[A-Z]*"


def agir_konu_mu(metin):
    """Metin (konu + ozet) kademe yukselten konu kelimelerinden birini tasiyor mu. Kelime KOKU aranir: Turkce ek alan ve son
    unsuzu yumusayan bicim ("TEMERRUDU", "IFLASI", "BIRLESMESI") de yakalanir (M24)."""
    m = sadelestir(metin)
    return any(re.search(_kok_deseni(k), m) for _, ks in AGIR_KONU for k in ks)


def agir_konular(metin):
    m = sadelestir(metin)
    return [ad for ad, ks in AGIR_KONU if any(re.search(_kok_deseni(k), m) for k in ks)]


def rutin_ayir(bildirimler):
    """(rutin olmayanlar, rutin tur olanlar); rutin olanlar yalnizca agir konu tasiyorsa taramada sayilir."""
    rutin = [b for b in bildirimler if rutin_mu(b.get("konu"))]
    dis = [b for b in bildirimler if not rutin_mu(b.get("konu"))]
    return dis, rutin


def eksik_triyaj(bildirimler):
    """Madde 3: govdesi cekilemeyen bildirim konusuna gore ikiye ayrilir. Konusu kademe yukselten listedeyse engelleyici
    (adiyla yazilir; o sirketin kurucusunun adaylari icin haber kapisi olculemedi doner); degilse sayilir, tarama 'eksiktir'.
    Donus: (engelleyici liste, engelleyici olmayan sayi)."""
    eng, n = [], 0
    for b in bildirimler:
        if b.get("metinDurumu") != "eksik":
            continue
        if kapatan_olaylar(f"{b.get('konu', '')} {b.get('ozet', '')}"):   # M55: engelleyici yalnizca kapatan olay konulu eksik bildirim
            eng.append(b)
        else:
            n += 1
    return eng, n


def haber_kapisi(bildirimler, liste, kurucular, kurucu_grup=None, govde_var=True, gecmis=None):
    """Haber kapisinin TEK giris noktasi (kural 20: her kuralin bir cagirani olur; Mac brifingi ve bulut gorevi bunu cagirir).
    bildirimler: gunun KAP dizini (kap_gunluk.json 'bildirimler'); liste: izleme_listesi(); kurucular: aday fonlarin kuruculari.
    Sira: rutin tur suzgeci (madde 1) -> tam metin tarama -> rutin olup agir konu tasiyanlar eklenir -> eksik govde triyaji (madde 3).
    Donus: dict(haber={kurucu: True/False/None}, notu, k1, engelleyici, elenen, eslesme)."""
    kurucu_grup = kurucu_grup or {}
    dis, rutin = rutin_ayir(bildirimler)
    vurus = tara(dis, liste) + [v for v in tara(rutin, liste) if v["agir_konu"]]
    k1 = [v for v in vurus if v["kademe"] == 1]
    eng, eksik_diger = eksik_triyaj(bildirimler)
    # M56: tasfiye maddesi fon duzeyindedir. Ozel fon tasfiyesi hic sayilmaz; kamuya acik fonun tasfiyesi o fonu kapatir (fon_kapali),
    # kurucu duzeyinde bilgi satiridir; ayni kurucuda pencere icinde TASFIYE_KURUCU_ESIK ve ustu kamu fonu tasfiyesi kurucuyu kapatir.
    fon_kapali, tasfiye_kamu, tasfiye_ozel = set(), [], []
    def _tasfiye_ayikla(vurus_listesi):
        for v in vurus_listesi:
            if TASFIYE_AD not in v["kapatan"]:
                continue
            v["kapatan"] = [x for x in v["kapatan"] if x != TASFIYE_AD]
            if ozel_fon_mu(v["sirket"]):
                v["tasfiye"] = "ozel"; tasfiye_ozel.append(v)
            else:
                v["tasfiye"] = "kamu"; tasfiye_kamu.append(v)
                if v.get("fon"):
                    fon_kapali.add(v["fon"])
    _tasfiye_ayikla(k1)
    gecmis_vurus = [v for v in tara(list(gecmis or []), liste) if v["kademe"] == 1]
    bugun_idler = {v["id"] for v in k1}
    _tasfiye_ayikla([v for v in gecmis_vurus if v["id"] not in bugun_idler])
    kapatan = [v for v in k1 if v["kapatan"]]                       # M55: kapatan olay tasiyan birinci kademe vurus
    kap_bos = [v for v in k1 if v["kap_bos"] and not v["kapatan"]]   # M55: icerigi okunamayan kap bildirimi
    bilgi = [v for v in k1 if not v["kapatan"] and not v["kap_bos"]] # kapatmaz, brifingde bilgi satiri (kardes fon tasfiyesi dahil)
    haber, sebep = {}, {}
    for k in kurucular:
        anahtar = {sadelestir(g) for g in kurucu_grup.get(k, [k])}
        vur = [v for v in kapatan if set(v["eslesen"]) & anahtar]
        kamu_fonlar = {v["fon"] or v["sirket"] for v in tasfiye_kamu if set(v["eslesen"]) & anahtar}
        if vur:
            haber[k] = False; sebep[k] = "; ".join(f"{v['sirket']}: {', '.join(v['kapatan'])}" for v in vur[:3])
        elif len(kamu_fonlar) >= TASFIYE_KURUCU_ESIK:
            haber[k] = False; sebep[k] = f"{TASFIYE_PENCERE_GUN} günde {len(kamu_fonlar)} kamuya açık fon tasfiyesi (eşik {TASFIYE_KURUCU_ESIK}); yönetici işareti"
        elif any(any(a in sadelestir(b.get("sirket") or "") for a in anahtar) for b in eng):
            haber[k] = None; sebep[k] = "gövdesi çekilemeyen kapatan konulu bildirim"   # engelleyici eksik: govde okunana kadar olculemedi
        elif any(set(v["eslesen"]) & anahtar for v in kap_bos):
            haber[k] = None; sebep[k] = "özeti ve gövdesi boş kap bildirimi (Özel Durum Açıklaması / Genel Açıklama); içerik okunmadan sınıflanamaz"
        else:
            haber[k] = True
    b_ = lambda n: f"{n:,}".replace(",", ".")      # binlik ayirici nokta; cumledeki virgullere dokunulmaz
    notu = (f"{b_(len(bildirimler))} bildirim tarandı; rutin tür süzgeciyle elenen {b_(len(rutin))} ({len(RUTIN_TURLER)} tür, kademe yükselten "
            f"konu taşıyanlar sayıldı), {b_(len(vurus))} eşleşme, {b_(len(k1))} birinci kademe; kapatan olay {b_(len(kapatan))}, "
            f"bilgi satırı {b_(len(bilgi))}, içeriksiz kap bildirimi {b_(len(kap_bos))} (M55: yalnızca kapatan olay kapıyı kapatır)"
            + (f"; fon tasfiyesi: özel {b_(len(tasfiye_ozel))} sayılmadı, kamuya açık {b_(len(fon_kapali))} fon kendi kapısı kapalı, kardeş fon bilgi (M56)" if tasfiye_ozel or fon_kapali else "")
            + (f"; gövdesi çekilemeyen {b_(len(eng))} engelleyici bildirim (haber kapısı o kurucularda ölçülemedi)" if eng else "")
            + (f"; gövdesi çekilemeyen {b_(eksik_diger)} rutin dışı bildirim, tarama eksiktir" if eksik_diger else "")
            + ("" if govde_var else "; gövde metni çekilmemiş, tarama özet ve konu üzerinden"))
    return dict(haber=haber, notu=notu, k1=k1, engelleyici=eng, elenen=len(rutin), eslesme=len(vurus), kapatan=kapatan, bilgi=bilgi, kap_bos=kap_bos, sebep=sebep,
                fon_kapali=sorted(fon_kapali), tasfiye_ozel=len(tasfiye_ozel), tasfiye_kamu=len(tasfiye_kamu))


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
        konular = agir_konular(gövde)     # kelime koku: "TEMERRUDU", "IFLASI" gibi ekli bicimler de yakalanir (M24)
        if konular and kademe > 1:
            kademe = 1          # agir konu, ismi bir kademe yukari tasir
        sonuc.append({
            "id": b.get("id"), "tarih": b.get("tarih"), "sirket": b.get("sirket"),
            "konu": b.get("konu"), "url": b.get("url"), "ozet": b.get("ozet"),
            "kademe": kademe,
            "eslesen": sorted({v[0] for v in vurus}),
            "sebep": sorted({v[1]["sebep"] for v in vurus}),
            "agir_konu": konular,
            "kapatan": kapatan_olaylar(gövde),      # M55: yalnizca bu dolu olan birinci kademe vurus kapiyi kapatir
            "kap_bos": kap_bos_mu(b),                 # M55: icerigi okunamayan kap bildirimi -> olculemedi
            "fon": b.get("fon") or "",                # M56: fon bildirimiyse kodu; tasfiye adayin kendi fonuna uygulanir
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
    a.add_argument("--kurucular", help="aday fonlarin kuruculari, | ile ayrilmis (haber kapisi bunlar icin olculur)")
    n = a.parse_args()

    liste = izleme_listesi(n.poz, n.icerik, n.kunye, ek_kurucular=[k for k in (n.kurucular or "").split("|") if k], kurucu_grup=kurucu_grup_yukle(n.kurucu_grup))
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
    kg = json.load(open(n.bildirim, encoding="utf-8"))
    bild = kg["bildirimler"] if isinstance(kg, dict) else kg
    grup = kurucu_grup_yukle(n.kurucu_grup)
    kur = [k for k in (n.kurucular or "").split("|") if k]
    r = haber_kapisi(bild, liste, kur, kurucu_grup=grup, govde_var=(not isinstance(kg, dict) or "govdeTam" in kg))   # tek giris noktasi (kural 20)
    bol = brifing_bolumu([v for v in r["k1"]] + [v for v in tara(bild, liste) if v["kademe"] != 1 and not rutin_mu(v.get("konu"))], len(bild))
    bol["kapsam"] = r["notu"]; bol["haber_kapisi"] = r["haber"]; bol["engelleyici"] = [dict(sirket=b.get("sirket"), konu=b.get("konu")) for b in r["engelleyici"]]
    if n.cikti:
        json.dump(bol, open(n.cikti, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(bol, ensure_ascii=False, indent=1))
