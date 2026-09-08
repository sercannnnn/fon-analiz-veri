#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KAP portfoy dagilim raporlari: kurucu duzeni sinavi (Asama B), ISIN listesi (Asama C) ve gunluk kuyruk.
Bagimlilik: requests, pdfplumber (makinede ~/fon-analiz/.venv). Kunye: veri/fon_kunye_kap.csv (kap_kunye.py).

Asama B  : raporun 1. sayfasindaki varlik sinifi yuzdeleri, ayni ayin TEFAS dagilim ORTALAMASIYLA
           sinif basina karsilastirilir; sapma 1,0 puani asmiyorsa o kurucunun duzeni gecmis sayilir.
           Sonuc veri/kurucu_duzen.json dosyasina yazilir; kuyruk yalnizca gecen kurucularin fonlarini isler.
Kapi     : (1) agirlik toplami 100 ± 1,0; (2) hicbir satir dusmemis (satir toplami = yaprak grup toplami,
           ISIN'li bolumlerde ISIN ya da fon kodu var); (3) kiymet turu toplamlari, TEFAS'in rapor ayini
           izleyen ilk is gunu dagilimiyla aile duzeyinde ± 1,0 puan icinde (TEFAS dagilimi bir is gunu
           gecikmelidir; T tarihli dagilim T-1 kapanisini yansitir). Sapma her fon icin ozete yazilir.
Kuyruk   : veri/icerik_kuyruk.json fon basina son basarili rapor ayini tutar. Her gun hedef ayin raporu
           alinmamis fonlar sirayla islenir; istekler arasi ARA saniye, gunluk istek butcesi BUTCE.
           429 ustel geri cekilme, uc denemeden sonra fon yarina birakilir ve hata sayilmaz.
Kovalar  : hata (yalnizca ayristirma/kapi), kapsamDisi (ozel fon; dagilim raporu yayimlamayan; duzeni
           B'yi gecmeyen kurucu), ertelendi (ag / butce), beklemede (rapor henuz yayimlanmadi).

Kullanim:
  fon_icerik_cek.py --asama B --kurucu 10            en buyuk 10 kurucuyu sina, kurucu_duzen.json'a yaz
  fon_icerik_cek.py --asama kuyruk                    gunluk kuyruk turu (cron)
  fon_icerik_cek.py --asama kuyruk --kurucu-filtre "İŞ PORTFÖY YÖNETİMİ A.Ş."
  fon_icerik_cek.py --pdf ek_TLY.pdf ...               yerel PDF'lerde ayristirici sinamasi
"""
import argparse, csv, gc, glob, gzip, io, json, os, re, sys, time, unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
import requests
import pdfplumber

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KAP = "https://www.kap.org.tr/tr/api/"
BASLIK = {"User-Agent": "Mozilla/5.0 (fon-analiz icerik)", "Accept": "application/json", "Accept-Language": "tr"}
ARA = 2.5                 # istekler arasi saniye
BUTCE = 400               # gunluk istek butcesi
SAPMA_ESIK = 1.0          # puan; B sinavi ve kapi 3. sart
RAPOR_BEKLEME_GUNU = 20   # ayin bu gununden sonra raporu olmayan fon o ay icin kapsam disi sayilir
DAGILIM_GECIKME_GUN = 1   # TEFAS dagilimi T tarihinde T-1 kapanisini gosterir (07.09.2026, 9 fon, sifir sapma)

AY_AD = {"OCAK": 1, "SUBAT": 2, "MART": 3, "NISAN": 4, "MAYIS": 5, "HAZIRAN": 6, "TEMMUZ": 7,
         "AGUSTOS": 8, "EYLUL": 9, "EKIM": 10, "KASIM": 11, "ARALIK": 12}
SINAV_SURUM = 2           # kurucu sinavi yontemi: kiymet tablosu + kapi, TEFAS ertesi gun (Talimat 7)
SINAV_PAYI = 0.6          # gunluk butcenin sinava ayrilan payi
KAPSAM_AY = 6             # kapsam_disi karari: son 6 ayda hic rapor yok
AYRISTIRICI_SURUM = 3     # artinca kuyruk, eski surumle yayimlanmis fonlari butce dahilinde yeniden isler
# Gunluk dosya (fon_icerik_son.csv) yalnizca o gunun turunu tasir; birikimli hal arsiv/fon_icerik_YYYY-MM.csv.gz.
# kiymetAdi yalnizca tek satirdan okunan (sarilmamis) adlarda doludur; sarilan ad kiymetAdiHam'da ham durur.
ICERIK_ALAN = ["fonKodu", "raporTarihi", "kiymetAdi", "kiymetAdiHam", "bistKodu", "ihracci", "isin", "tur", "nominal", "rayicDeger", "agirlik", "kurucuDuzeni"]
OZET_ALAN = ["fonKodu", "raporTarihi", "kurucu", "kurucuDuzeni", "satir", "agirlikToplam", "tefasGun", "tefasSapma", "hisseSatir", "yabanciHisseSatir", "bistKoduBos", "adTemiz", "durum", "sebep", "not"]
OZET_NOT = "gunluk tur; birikimli hal arsiv/fon_icerik_YYYY-MM.csv.gz"


def norm(s):
    s = str(s).upper().replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("Â", "A")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()).strip()


def sayi(s):
    """'1.234,56' -> 1234.56 ; '1,234.56' -> 1234.56 ; '12,30' -> 12.3 ; '3.52%' -> 3.52"""
    s = s.strip().rstrip("%").strip()
    if "," in s and "." in s:
        return float(s.replace(".", "").replace(",", ".")) if s.rfind(",") > s.rfind(".") else float(s.replace(",", ""))
    if "," in s:
        return float(s.replace(",", "."))
    return float(s)


def json_oku(yol, varsayilan):
    try:
        return json.load(open(yol, encoding="utf-8"))
    except Exception:
        return varsayilan


def json_yaz(yol, veri):
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1, sort_keys=True)


# ================================================================ KAP erisimi ve istek sayaci

class Istek:
    """Istek sayaci ve 429 takibi. butce asilinca Butce istisnasi firlatir."""
    def __init__(self, butce):
        self.butce, self.sayi, self.h429 = butce, 0, 0

    def kullan(self):
        if self.sayi >= self.butce:
            raise ButceBitti()
        self.sayi += 1
        time.sleep(ARA)


class ButceBitti(Exception):
    pass


class Ertelendi(Exception):
    """429 ya da ag hatasi uc denemede gecmedi; fon yarina kalir, hata degildir."""


ISTEK = Istek(BUTCE)


def _istek(metot, url, deneme=3, **kw):
    for i in range(deneme):
        ISTEK.kullan()
        try:
            r = requests.request(metot, url, headers=BASLIK, timeout=120, **kw)
            if r.status_code == 429:
                ISTEK.h429 += 1
                raise RuntimeError("HTTP 429")
            if r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except ButceBitti:
            raise
        except Exception as e:
            print(f"  {url[-48:]}: deneme {i+1} {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(10 * 2 ** i)
    raise Ertelendi(url[-48:])


def kap_get(yol):
    return _istek("GET", KAP + yol).json()


def kap_post(yol, govde):
    return _istek("POST", KAP + yol, json=govde).json()


def kunye_yukle(veri):
    yol = os.path.join(veri, "fon_kunye_kap.csv")
    if not os.path.exists(yol):
        sys.exit("veri/fon_kunye_kap.csv yok; once kap_kunye.py calistir")
    return {s["fonKodu"]: s for s in csv.DictReader(open(yol, encoding="utf-8"))
            if s["fonTipi"] == "YF" and s["durum"] == "faal"}


def raporlar(fund_oids, bas, bit):
    """Verilen fonlarin bas..bit arasindaki 'Portfoy Dagilim Raporu' bildirimleri (fundCode ile)."""
    g = {"fromDate": bas, "toDate": bit, "fundTypeList": ["YF"], "mkkMemberOidList": [],
         "fundOidList": list(fund_oids), "passiveFundOidList": [], "disclosureClass": "", "isLate": "",
         "subjectList": [], "discIndex": [], "fromSrc": False, "srcCategory": ""}
    L = kap_post("disclosure/funds/byCriteria", g) or []
    return [x for x in L if (x.get("subject") or "") == "Portföy Dağılım Raporu"]


def ek_pdf(idx):
    """Bildirim sayfasindan ek kimliklerini alir, PDF olan ilk eki (bayt) dondurur.
    KAP eki 27-29 baytlik Java serilestirme sarmaliyla verir; %PDF imzasindan itibaren kesilir."""
    fids = []
    for i in range(3):
        h = _istek("GET", f"https://www.kap.org.tr/tr/Bildirim/{idx}").text
        fids = list(dict.fromkeys(re.findall(r"/tr/api/file/download/([0-9a-f]{32})", h)))
        if fids:
            break
        time.sleep(5 * (i + 1))      # yuk altinda 200 donup ek baglantisi tasimayan sayfa
    for fid in fids:
        raw = _istek("GET", KAP + f"file/download/{fid}").content
        i = raw.find(b"%PDF")
        if i >= 0:
            return raw[i:]
    return None


# ================================================================ TEFAS dagilimi ve aile eslemesi

# TEFAS dagilim kodlari -> aile (gunluk_analiz.py ile ayni kod sozlugu)
AILE = {
    # kmkba (kiymetli maden cinsinden kamu borclanma araci) TEFAS'ta maden ailesinde durur; KAP standart duzeni
    # bunu 'Devlet Tahvili' bolumunde verir (TTA: 4,19 puan birebir, 08.09.2026). Ayni enstruman, o yuzden dt ailesinde.
    "hisse": ["hs"], "yabanci_hisse": ["yhs"], "dt": ["dt", "kibd", "kmkba"], "hb": ["hb"], "ost": ["ost", "vdm"],
    "dis_borc": ["eut", "kba", "osdb", "yba", "ybkb", "ybosb"], "fb": ["fb", "bb"],
    "kira": ["kks", "kkstl", "kksd", "kksyd", "osks", "oksyd", "kmkks"],
    "tpp": ["tpp", "t", "bpp"], "maden": ["km"],
    "mevduat": ["vm", "vmtl", "vmd", "vmau"], "katilim": ["kh", "khtl", "khd", "khau"],
    "diger": ["d", "dot", "fkb", "gas", "gyy", "gsyy", "ymk", "db"], "teminat": ["vint"],
    "yf": ["yyf", "gykb", "gsykb"], "byf": ["byf", "kmbyf"], "ybyf": ["ybyf"], "repo": ["tr", "r"], "taahhut": ["btaa", "btas"],
}

# KAP sinif / bolum adi -> aile. Sira onemli, ilk eslesen kazanir.
KURAL = [
    (r"TERS REPO|T\.REPO|REPO", "repo"), (r"YABANCI HISSE|YP HISSE|HISSE YABANCI", "yabanci_hisse"), (r"HISSE|\bPAY\b", "hisse"),
    (r"HAZINE BONO", "hb"), (r"DIS BORCLANMA|EUROBOND", "dis_borc"),
    (r"DEVLET TAHVIL|KAMU.*TAHVIL|KAMU BORCLANMA", "dt"), (r"OZEL SEKTOR TAHVIL|OZEL.*BORCLANMA", "ost"),
    (r"FINANSMAN BONO|FINANSMAN BONUSU|\bBONO\b", "fb"), (r"KIRA SERTIFIKA", "kira"),
    (r"TAKASBANK|TPP|\bBPP\b|BORSA PARA", "tpp"), (r"DEGERLI MADEN|KIYMETLI MADEN|D\.MADEN|\bMADEN\b|ALTIN|GUMUS", "maden"),
    (r"(BORSA YATIRIM FONU|\bBYF\b|BORSA Y\.FONU).*(YABANCI|YP)|(YABANCI|\bYP\b).*(BORSA YATIRIM FONU|\bBYF\b)", "ybyf"), (r"BORSA YATIRIM FONU|\bBYF\b|BORSA Y\.FONU", "byf"), (r"YATIRIM FONU|Y\.FONU|YATIRIM FON|FON SEPETI", "yf"),
    (r"KATILIM HESABI|KATILMA HESABI", "katilim"), (r"MEVDUAT", "mevduat"), (r"TEMINAT", "teminat"),
    (r"TAAHHUT", "taahhut"), (r"VDMK|VARLIGA DAYALI", "ost"), (r"DIGER", "diger"),
    (r"^OZEL SEKTOR$|BORSA DISI|BORCLANMA", "ost"), (r"^HAZINE|^DEVLET|^KAMU", "dt"),
    (r"TUREV|FUTURES|OPSIYON|VARANT|\bUZUN\b|\bKISA\b|DOVIZ", "diger"),
]

# ESLEME TABLOSU: ayni enstrumanin KAP ve TEFAS tarafinda farkli adla siniflandigi kanitlanmis durumlar.
# Tablodaki aileler iki tarafta da ust gruba toplanarak karsilastirilir.
# Bu tabloya yalnızca aynı enstrümanın iki tarafta farklı adla sınıflandığı kanıtlanırsa satır eklenir;
# sapmayı kapatmak için eklenmez. Her satir: (aile, ust grup, kanit).
ESLEME_TABLOSU = [
    ("dis_borc", "borclanma", "Standart duzen eurobond'u 'Devlet/Ozel Sektor Tahvili' ya da 'Eurobond' altinda verir; TEFAS eut/kba/osdb kodlarinda ayri tutar (PAL 1. sayfa, 07.09.2026)"),
    ("dt",       "borclanma", "PAL kiymet tablosu: TEFAS'in kksd (kamu kira sertifikasi doviz, 6,20 puan) dedigi TR ISIN'li kagitlar KAP'ta 'Devlet Tahvili' grubunda (13,87 = kibd 7,97 + kksd 5,90); kamu/ozel, TL/doviz, tahvil/kira kirilimi iki tarafta farkli (07.09.2026)"),
    ("ost",      "borclanma", "ayni kanit"),
    ("hb",       "borclanma", "ayni kanit"),
    ("kira",     "borclanma", "ayni kanit; ayrica Yapi Kredi duzeni YP kira sertifikasini dis borclanma icinde verir (YTY, 07.09.2026)"),
    ("fb",       "borclanma", "ayni kanit"),
    ("tpp",      "para_piyasasi", "Takasbank Para Piyasasi ile Borsa Istanbul Para Piyasasi ayni pazarin eski ve yeni adidir; KAP sablonu TPP, TEFAS bpp yazar (TP2, 07.09.2026)"),
    ("repo",     "para_piyasasi", "Garanti duzeni 'TERS REPO' satirinda Takasbank islemlerini de verir (GZE, 07.09.2026)"),
    ("yabanci_hisse", "hisse_toplam", "Standart duzen 'Hisse Yabanci' bolumunu TEFAS yhs koduna, 'Hisse Turk' hs koduna yazar; ikisi de hisse (IED, 07.09.2026)"),
    ("hisse",    "hisse_toplam", "ayni kanit"),
    ("byf",      "maden_byf", "Altin ve gumus BYF'leri (GMSTR TRYFNBK00030, ISGLK TRYISPO01397, ZGOLD TRYZIPO00162, GLDTR) KAP'ta 'Borsa Y.Fonu Turk' bolumunde, TEFAS'ta kmbyf (kiymetli maden BYF) kodunda; GUF 18,30 ve TTA 22,67 puan birebir (08.09.2026)"),
    ("maden",    "maden_byf", "ayni kanit; kmbyf TEFAS'ta kiymetli maden ailesindedir"),
    ("katilim",  "mevduat_katilim", "Ak Portfoy TEFAS'a katilma hesabini vadeli mevduat TL (vmtl) olarak bildirir: ALE KAP mevduat 31,45 + katilim 8,35 = TEFAS vmtl 39,80 birebir; BGP ve PPJ ayni (08.09.2026). Kuveyt Turk khtl ile bildirir; katlama iki tarafta da ayni toplami verir"),
    ("mevduat",  "mevduat_katilim", "ayni kanit"),
    ("diger",    "borclanma", "TEFAS'in kodu olmayan doviz sukuklari (TVF Varlik Kiralama XS2911679004, Vakif Katilim, TT Varlik, Ziraat Katilim; XS ISIN) TEFAS d (diger) sutununa, KAP'ta Devlet Tahvili / Kamu Kesimi Kira / Ozel Sektor Kira bolumlerine yazilir. Kurus sinavi: DBH 2,11, DPB 1,19, DPK 3,60, KPD 15,58, KTT 12,21, TPZ 33,47 puan birebir (08.09.2026). DVS, EDT, FMV, TNK, TRJ'de d baska bir kalemdir, esit degil"),
]
UST_GRUP = {a: g for a, g, _ in ESLEME_TABLOSU}


def aileye(ad):
    n = norm(ad)
    for k, a in KURAL:
        if re.search(k, n):
            return a
    return None


def tefas_dagilim_yukle(veri, arsiv=None):
    """TEFAS dagilimi: once arsiv/tefas_dagilim_YYYY-MM.csv.gz, sonra gunluk dosyalar (gunluk olan ezer)."""
    arsiv = arsiv or os.path.join(os.path.dirname(os.path.abspath(veri)), "arsiv")
    rows = {}
    for f in sorted(glob.glob(os.path.join(arsiv, "tefas_dagilim_*.csv.gz"))):
        with gzip.open(f, "rt", encoding="utf-8", newline="") as fh:
            for s in csv.DictReader(fh):
                rows[(s["tarih"], s["fonKodu"])] = s
    fl = sorted(glob.glob(os.path.join(veri, "tefas_dagilim_*.csv*")) + glob.glob(os.path.join(veri, "son_dagilim.csv")))
    for f in fl:
        for s in csv.DictReader(open(f, encoding="utf-8")):
            rows[(s["tarih"], s["fonKodu"])] = s
    return rows


def tefas_aile(son):
    t = defaultdict(float)
    for a, kod in AILE.items():
        t[a] += sum(float(son.get(k) or 0) for k in kod)
    return t


def tefas_ay_ortalama(rows, fon, ay):
    gunler = [s for (t, k), s in rows.items() if k == fon and t.startswith(ay)]
    if not gunler:
        return None, 0
    top = defaultdict(float)
    for s in gunler:
        for k, v in s.items():
            if k not in ("tarih", "fonKodu") and v not in ("", None):
                top[k] += float(v)
    return {k: v / len(gunler) for k, v in top.items()}, len(gunler)


def tefas_ertesi_gun(rows, fon, ay):
    """Rapor ayindan sonraki ilk TEFAS dagilim gunu (= ay sonu portfoyu, DAGILIM_GECIKME_GUN gecikmeyle)."""
    adaylar = sorted(t for (t, k) in rows if k == fon and t > ay + "-31")
    if not adaylar:
        return None, None
    ilk = datetime.strptime(adaylar[0], "%Y-%m-%d").date()
    ay_sonu = (datetime.strptime(ay + "-01", "%Y-%m-%d").date().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if (ilk - ay_sonu).days > 7:       # izleyen ilk is gunu elde yok (TEFAS dagilim penceresi disinda)
        return None, None
    return adaylar[0], rows[(adaylar[0], fon)]


def katla(k_aile, t_aile):
    """ESLEME_TABLOSU'ndaki aileler iki tarafta da ust gruba toplanir; kalanlar oldugu gibi karsilastirilir."""
    for a in list(set(k_aile) | set(t_aile)):
        g = UST_GRUP.get(a)
        if g:
            k_aile[g] += k_aile.pop(a, 0.0); t_aile[g] += t_aile.pop(a, 0.0)
    return k_aile, t_aile


def sapmalar(k_aile, t_aile):
    out = {}
    for a in set(k_aile) | {a for a, v in t_aile.items() if abs(v) > 0.05}:
        out[a] = round(k_aile.get(a, 0.0) - t_aile.get(a, 0.0), 2)
    return out


# ================================================================ duzen tanima ve 1. sayfa (Asama B)

def duzen(t1, pdf_bayt=None):
    """Duzen tanima. Standart duzen kiymet tablosunun basligiyla ('(FPD' ve '(FTD') taninir; 1. sayfa
    farkli olsa da (Global MD, Aktif/INFINA, Logos) tablo aynidir (08.09.2026)."""
    n = norm(t1)
    if "AYLIK ORTALAMA PORTFOYDEKI MENKUL KIYMETLER YUZDESI" in n and "A-)" in n:
        return "standart"
    if "YATIRIM FONLARI PORTFOY DAGILIM RAPORU" in n and "RAPOR DONEMI" in n:
        return "garanti"
    if "AYLIK RAPORUDUR" in n:
        return "yapikredi"
    if pdf_bayt:
        with pdfplumber.open(io.BytesIO(pdf_bayt)) as p:
            for pg in p.pages[:3]:
                t = pg.extract_text() or ""
                if "(FPD" in t and "(FTD" in t:
                    return "standart"
                pg.flush_cache()
    if "(FPD" in t1 and "(FTD" in t1:
        return "standart"
    return "bilinmiyor"


def rapor_ayi(t1, yayim=None):
    """Rapor ayi: basliktaki 'Agustos-2026' / 'Rapor Donemi 01/08/2026'; okunamazsa yayim tarihinin
    bir onceki ayi (rapor izleyen ayin ilk gunlerinde yayimlanir). Kurulus tarihi gibi eski yillar elenir."""
    n = norm(t1)
    yedek = None
    if yayim:
        d = datetime.strptime(yayim[:10], "%d.%m.%Y").date()
        yedek = f"{d.year}-{d.month-1:02d}" if d.month > 1 else f"{d.year-1}-12"
    for m in re.finditer(r"\b(" + "|".join(AY_AD) + r")\s*-?\s*(20\d\d)\b", n):
        ay = f"{m.group(2)}-{AY_AD[m.group(1)]:02d}"
        if not yedek or abs(int(m.group(2)) - int(yedek[:4])) <= 1:
            return ay
    m = re.search(r"RAPOR DONEMI\s*\d\d/(\d\d)/(20\d\d)", n)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return yedek


def sayfa1_yuzdeler(t1, d):
    out = {}
    if d == "standart":
        blok = t1.split("Menkul Kıymetler Yüzdesi", 1)[1].split("Devir Hızı", 1)[0]
        for m in re.finditer(r"[a-zğ]\d?-\)\s*(.+?)\s*:\s*(-?[\d.]+[,.]\d+|-?\d+)\s*$", blok, re.M):
            out[m.group(1).strip()] = sayi(m.group(2))
    elif d == "garanti":
        n = t1.split("YÜZDESİ", 1)[1] if "YÜZDESİ" in t1 else ""
        n = n.split("AYLIK ORTALAMA TEDAVÜL", 1)[0].split("AYLIK ORTALAMA PORTFÖY DEVİR", 1)[0]
        for m in re.finditer(r"^\s*([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü .()/\-]+?)\s+(-?[\d,]+\.\d+)%\s*$", n, re.M):
            out[m.group(1).strip()] = sayi(m.group(2))
    elif d == "yapikredi":
        n = t1.split("YÜZDESİ", 1)[1] if "YÜZDESİ" in t1 else ""
        n = n.split("F. AYLIK", 1)[0]
        for m in re.finditer(r"^\s*([A-Za-zÇĞİÖŞÜçğıöşü][^\n%]*?)\s+(-?[\d,]+\.\d+)%\s*$", n, re.M):
            out[m.group(1).strip()] = sayi(m.group(2))
    return out


def sayfa1_karsilastir(kap, tefas_ort):
    k_aile, esl = defaultdict(float), []
    for ad, v in kap.items():
        a = aileye(ad)
        if a is None:
            esl.append(ad); continue
        k_aile[a] += v
    k_aile, t_aile = katla(k_aile, tefas_aile(tefas_ort))
    return sapmalar(k_aile, t_aile), esl


# ================================================================ standart duzen kiymet tablosu (Asama C)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
SAYI_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$|^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
PARA = {"TL", "USD", "EUR", "GBP", "CHF", "XAU", "JPY", "TRY"}
TARIH_RE = re.compile(r"^\d{2}/\d{2}/\d{2,4}$|^\d{2}\.\d{2}\.\d{4}$")


def _ad_token(w):
    """Ad ya da ihracci sutununa girebilecek kelime: para birimi, tarih, sayi ve sozlesme numarasi degil."""
    x = w["text"]
    return x not in PARA and not TARIH_RE.match(x) and not SAYI_RE.match(x) and not re.match(r"^\d{6,}$", x)


def _satirlar(pg):
    """Kelimeleri dikey konuma gore satirlara kumeler; 3 puandan yakin ustler ayni satirdir."""
    words = sorted(pg.extract_words(x_tolerance=1.5, y_tolerance=2), key=lambda w: w["top"])
    out, grup, son = [], [], None
    for w in words:
        if son is not None and w["top"] - son > 3:
            out.append(grup); grup = []
        grup.append(w); son = w["top"]
    if grup:
        out.append(grup)
    return [(min(w["top"] for w in g), sorted(g, key=lambda w: w["x0"])) for g in out]


def _kalibre(R):
    """Sayfadaki tablo basligindan sutun sag kenarlarini bulur. Standart ve genis varyant ayni
    basliklari tasir: (%) grup yuzdesi, (FPD ve (FTD toplam yuzdeleri, 'TOPLAM DEGER' toplam deger,
    'NOMINAL DEGER' nominal, 'ISIN' kodu. Bulunamazsa None."""
    k, yuzdeler = {}, []
    for t, r in R:
        for i, w in enumerate(r):
            x = w["text"]
            if x == "(FPD":
                k["fpd"] = w["x1"]
            elif x == "(FTD":
                k["ftd"] = w["x1"]
            elif x == "(%)":
                yuzdeler.append(w["x1"])
            elif x == "DEĞER" and i > 0 and r[i - 1]["text"] == "TOPLAM":
                k["toplam"] = w["x1"]
            elif x == "DEĞER" and i > 0 and r[i - 1]["text"] == "NOMİNAL":
                k["nominal"] = w["x1"]
            elif x == "ISIN":
                k["isin_x0"] = w["x0"]
            elif x == "İHRAÇCI":
                k["ihracci_x0"] = w["x0"]
            elif x == "VADE" and "ihracci_x0" in k and "vade_x0" not in k:
                k["vade_x0"] = w["x0"]
    if "fpd" in k:
        # grup yuzdesi sutunu: FPD basliginin hemen solundaki "(%)"; baslikta baska (%) sutunlari da var
        sol = [x for x in yuzdeler if x < k["fpd"]]
        if sol:
            k["grup"] = max(sol)
    return k if {"fpd", "grup", "toplam"} <= set(k) else None


def _kolon(r, x1, sol=-45, sag=40):
    return [w for w in r if x1 + sol <= w["x1"] <= x1 + sag and SAYI_RE.match(w["text"])]


TOPLAM_SATIR = ("TOPLAM", "FON", "GENEL", "PORTFÖY", "IV-FON", "III-FON")


def _grup_satiri(r):
    return len(r) >= 2 and r[0]["text"] == "GRUP" and r[1]["text"].startswith("TOPLAM")


def _ana(r, k):
    """Kiymet satiri ya da GRUP TOPLAMI. Kiymet satiri: grup %, FPD % ve toplam deger sutunlari dolu.
    GRUP TOPLAMI genis varyantta yuzdesiz gelir, adiyla taninir. Raporun genel toplam satirlari alinmaz."""
    if _grup_satiri(r):
        return True
    if r[0]["text"] in TOPLAM_SATIR:
        return False
    return bool(_kolon(r, k["grup"], -5, 40)) and bool(_kolon(r, k["fpd"], -5, 40)) and bool(_kolon(r, k["toplam"], -45, 12))


def standart_kiymetler(pdf_bayt):
    """Standart duzende (dar ve genis varyant) kiymet satirlarini ve yaprak grup toplamlarini cikarir.
    Tablo 1. sayfanin altinda baslayabilir; grup etiketi sayfalar arasinda tasinir.
    Donus: (kayitlar, gruplar). agirlik = TOPLAM DEGER (FPD'ye gore) yuzdesi."""
    kayit, gruplar = [], []
    etiket, bekleyen, adaylar, kal = None, True, [], None
    son_ana_grup = False          # bir onceki ana satir GRUP TOPLAMI miydi (sayfa sinirini asar)
    with pdfplumber.open(io.BytesIO(pdf_bayt)) as pdf:
        for pi, pg in enumerate(pdf.pages, start=1):
            R = _satirlar(pg)
            pg.flush_cache()
            kal = _kalibre(R) or kal
            if not kal:
                continue
            anal = [i for i, (t, r) in enumerate(R) if _ana(r, kal)]
            if not anal:
                continue
            ilk_ana = anal[0]
            def _baslik(r):
                m = {w["text"] for w in r}
                return (("MENKUL" in m and "KIYMET" in m) or ("CİNSİ" in m and "KURUM" in m) or "VADEYE" in m
                        or ("DÖVİZ" in m and "İHRAÇCI" in m) or ("GÜN" in m and "ORANI" in m) or "(FPD" in m or "(%)" in m)
            baslik = {i for i, (t, r) in enumerate(R) if i not in anal and _baslik(r)}
            etiket_i = {}
            for i, (t, r) in enumerate(R):
                metin = " ".join(w["text"] for w in r)
                if i in anal:
                    if bekleyen and not _grup_satiri(r):
                        esl = [c for c in adaylar if aileye(c)]
                        etiket = esl[-1] if esl else (adaylar[-1] if adaylar else etiket)
                        bekleyen, adaylar = False, []
                    etiket_i[i] = etiket
                    if _grup_satiri(r):
                        bekleyen, adaylar = True, []
                    continue
                if i in baslik or (pi == 1 and i < ilk_ana and not re.search(r"^[A-ZÇĞİÖŞÜa-zçğıöşü.() /-]{3,40}$", metin)):
                    continue
                if pi == 1 and "TABLOSU" in metin:
                    bekleyen, adaylar = True, []
                    continue
                if bekleyen and r[0]["x0"] < 60 and not re.search(r"\d", metin) and len(metin) < 60:
                    adaylar.append(metin)
            # sarilan ihracci satirlari ve ISIN: en yakin ana satira; tolerans satir araligina gore
            # (uzun ihracci adinda ISIN 6-8 satir uzaga dusebilir; BHL, 08.09.2026)
            tops = [t for t, r in R]
            farklar = sorted(b - a for a, b in zip(tops, tops[1:]) if b - a > 0)
            pitch = farklar[len(farklar) // 2] if farklar else 10
            tol = max(40, 8 * pitch)
            atama = defaultdict(list)
            tablo_bas = next((i for i, (t, r) in enumerate(R) if pi == 1 and "TABLOSU" in " ".join(w["text"] for w in r)), -1)
            for i, (t, r) in enumerate(R):
                if i in anal or i in baslik or i <= tablo_bas:
                    continue
                metin = " ".join(w["text"] for w in r)
                if re.search(r"-\)|TOPLAMI|GÖRE\)", metin):
                    continue
                j = min(anal, key=lambda a: abs(R[a][0] - t))
                if abs(R[j][0] - t) <= tol:
                    atama[j].append((t, r))
            ad_sinir = kal.get("isin_x0", 230) - 5
            for i in anal:
                t, r = R[i]
                fpd_l = _kolon(r, kal["fpd"], -5, 40); top_l = _kolon(r, kal["toplam"], -45, 12)
                if _grup_satiri(r):
                    yaprak = not son_ana_grup
                    son_ana_grup = True
                    gruplar.append(dict(sayfa=pi, tur=etiket_i[i], rayic=sayi(top_l[0]["text"]) if top_l else None,
                                        agirlik=sayi(fpd_l[0]["text"]) if fpd_l else None, yaprak=yaprak))
                    continue
                son_ana_grup = False
                fpd, top = fpd_l[0], top_l[0]
                nom = _kolon(r, kal["nominal"], -50, 12) if "nominal" in kal else []
                ad_par = [(t, [w for w in r if w["x0"] < ad_sinir and _ad_token(w)])]
                ad_par += [(tt, [w for w in rr if w["x0"] < ad_sinir and _ad_token(w)]) for tt, rr in atama[i]]
                ad = " ".join(w["text"] for _, ws in sorted(ad_par) for w in ws)
                isinler = {w["text"] for w in r if ISIN_RE.match(w["text"])} | {w["text"] for _, rr in atama[i] for w in rr if ISIN_RE.match(w["text"])}
                # kod sutunu: ana satirin ilk kelimesi (hisse kodu, ISIN ya da kurum adi parcasi)
                kod = r[0]["text"] if r[0]["x0"] < kal.get("ihracci_x0", 110) - 5 else ""
                # ihracci sutunu: baslik İHRAÇCI..VADE araligindaki kelimeler, dikey sirayla; kac satirdan geldigi sayilir
                ih0, ih1 = kal.get("ihracci_x0", 110) - 12, kal.get("vade_x0", kal.get("isin_x0", 230)) - 4
                ih_par = [(t, [w["text"] for w in r if ih0 <= w["x0"] < ih1 and _ad_token(w)])]
                ih_par += [(tt, [w["text"] for w in rr if ih0 <= w["x0"] < ih1 and _ad_token(w)]) for tt, rr in atama[i]]
                ih_satir = [ws for _, ws in sorted(ih_par) if ws]
                ihracci_ham = " ".join(w for ws in ih_satir for w in ws)
                kayit.append(dict(sayfa=pi, ad=re.sub(r"\s+", " ", ad).strip(), isin=sorted(isinler)[0] if isinler else "",
                                  isinSayi=len(isinler), nominal=sayi(nom[-1]["text"]) if nom else None,
                                  rayic=sayi(top["text"]), agirlik=sayi(fpd["text"]), tur=etiket_i[i],
                                  kod=kod, ihracciHam=ihracci_ham, ihracciSatir=len(ih_satir)))
    return kayit, gruplar


# ================================================================ Garanti duzeni

def _yuzde_mi(x):
    return bool(re.match(r"^-?[\d,]+\.\d+%$", x))


def _sayi_mi(x):
    return bool(SAYI_RE.match(x))


def _garanti_kalibre(R):
    """Baslik satirindan sutun sag kenarlari: Grup%, Toplam%, 'Toplam Deger', 'Nominal Deger'; Ihracci x0, Vade x0."""
    k = {}
    for t, r in R:
        m = [w["text"] for w in r]
        if "Grup%" in m and "Toplam%" in m:
            for i, w in enumerate(r):
                x = w["text"]
                if x == "Grup%": k["grup"] = w["x1"]
                elif x == "Toplam%": k["toplam_pct"] = w["x1"]
                elif x == "Değer" and i > 0 and r[i - 1]["text"] == "Toplam": k["toplam"] = w["x1"]
                elif x == "Değer" and i > 0 and r[i - 1]["text"].startswith("Nomi"): k["nominal"] = w["x1"]
                elif x.startswith("İhraç"): k["ihracci_x0"] = w["x0"]
                elif x == "Vade": k["vade_x0"] = w["x0"]
            break
    return k if {"grup", "toplam_pct", "toplam"} <= set(k) else None


def garanti_kiymetler(pdf_bayt):
    """Garanti Portfoy duzeni: genislik 595 (iki olcek), Amerikan sayi bicimi, satir sonunda Toplam Deger, Grup%, Toplam%.
    Toplam% fon toplam degerine (FTD) goredir; agirlik = toplam deger / FON PORTFOY DEGERI olarak yeniden hesaplanir
    (TEFAS ile ayni taban). Bolum basliklari hiyerarsiktir ('B.1.OZEL SEKTOR ...' + 'TAHVIL'); tur = ust + alt.
    Grup toplamlari (Toplam / Ara Grup / Ana Grup) her bolumde bulunmadigindan kapinin 2. sart grup kontrolu atlanir;
    1. sart FON PORTFOY DEGERI ile saglanir."""
    kayit = []
    ust, alt, fpd, kal = "", "", None, None
    with pdfplumber.open(io.BytesIO(pdf_bayt)) as pdf:
        for pi, pg in enumerate(pdf.pages, start=1):
            R = _satirlar(pg); pg.flush_cache()
            kal = _garanti_kalibre(R) or kal
            bitti = False
            for t, r in R:
                metin = " ".join(w["text"] for w in r)
                ilk = r[0]["text"]
                if metin.startswith("FON PORTFOY DEĞERİ") or metin.startswith("FON PORTFÖY DEĞERİ"):
                    sayilar = [w["text"] for w in r if _sayi_mi(w["text"])]
                    if sayilar:
                        fpd = sayi(sayilar[-1])
                    continue
                if metin.startswith("IV-"):
                    bitti = True; break
                if ilk in ("Toplam", "Ara", "Ana"):
                    continue
                if not kal:
                    continue
                yuz = [w for w in r if _yuzde_mi(w["text"]) and w["x1"] >= kal["grup"] - 12]
                deg = sorted([w for w in r if _sayi_mi(w["text"]) and kal["toplam"] - 25 <= w["x1"] <= kal["toplam"] + 16], key=lambda w: w["x1"])
                if len(yuz) >= 2 and deg:
                    nom = [w for w in r if _sayi_mi(w["text"]) and kal.get("nominal", 0) - 30 <= w["x1"] <= kal.get("nominal", 0) + 8] if "nominal" in kal else []
                    isinler = [w["text"] for w in r if ISIN_RE.match(w["text"])]
                    ih0, ih1 = kal.get("ihracci_x0", 97) - 8, kal.get("vade_x0", 189) - 4
                    ad_tok = [w["text"] for w in r if ih0 <= w["x0"] < ih1 and not _sayi_mi(w["text"]) and not TARIH_RE.match(w["text"])]
                    kayit.append(dict(sayfa=pi, ad=" ".join(ad_tok), isin=isinler[0] if isinler else "", isinSayi=len(set(isinler)),
                                      nominal=sayi(nom[-1]["text"]) if nom else None, rayic=sayi(deg[-1]["text"]), agirlik=None,
                                      tur=f"{ust} {alt}".strip(), kod=ilk, ihracciHam=" ".join(ad_tok), ihracciSatir=1 if ad_tok else 0))
                    continue
                if r[0]["x0"] < 25 and not re.search(r"\d\.\d|%", metin) and len(metin) < 70:
                    if re.match(r"^[A-ZÇĞİÖŞÜ]{1,2}(\.\d)?\.", ilk):
                        ust, alt = metin, ""
                    else:
                        alt = metin
            if bitti:
                break
    if fpd is None:
        fpd = sum(k["rayic"] for k in kayit) or None
    if fpd:
        for k in kayit:
            k["agirlik"] = round(100.0 * k["rayic"] / fpd, 4)
    return kayit, []


# ================================================================ Yapi Kredi duzeni

def yapikredi_kiymetler(pdf_bayt):
    """Yapi Kredi Portfoy duzeni: genislik 612; satir = [ISIN] ... vade, ihracci, nominal, rayic, %; bolum
    basliklari 'G) KIRA SERTIFIKALARI :'; ara toplam 'TOPLAM'. % sutunu FPD'ye gore alinir; agirlik
    rayic / (TOPLAM satirlarinin rayic toplami) ile yeniden hesaplanir."""
    kayit, gruplar = [], []
    tur = ""
    with pdfplumber.open(io.BytesIO(pdf_bayt)) as pdf:
        for pi, pg in enumerate(pdf.pages, start=1):
            R = _satirlar(pg); pg.flush_cache()
            for t, r in R:
                metin = " ".join(w["text"] for w in r)
                ilk = r[0]["text"]
                if metin.startswith("IV-") or metin.startswith("IV -"):
                    break
                if re.match(r"^[A-ZÇĞİÖŞÜ]{1,2}\)$", ilk):                 # bolum basligi: 'G) KIRA SERTIFIKALARI :'
                    tur = re.sub(r"\s*:\s*$", "", " ".join(w["text"] for w in r[1:])); continue
                if r[0]["x0"] < 80 and not re.search(r"\d", metin) and len(metin) < 40 and tur and not re.search(r"\d", tur):
                    tur = (tur + " " + metin).strip(); continue        # basligin ikinci satiri
                yuz = [w for w in r if _sayi_mi(w["text"]) and w["x1"] >= 570]
                deg = [w for w in r if _sayi_mi(w["text"]) and 515 <= w["x1"] <= 530]
                if not (yuz and deg):
                    continue
                if ilk == "TOPLAM":
                    gruplar.append(dict(sayfa=pi, tur=tur, rayic=sayi(deg[-1]["text"]), agirlik=None, yaprak=True)); continue
                nom = [w for w in r if _sayi_mi(w["text"]) and 450 <= w["x1"] <= 462]
                isinler = [w["text"] for w in r if ISIN_RE.match(w["text"])]
                ih = [w["text"] for w in r if 320 <= w["x0"] < 400 and not _sayi_mi(w["text"]) and not TARIH_RE.match(w["text"])]
                ad = [w["text"] for w in r if w["x0"] < 300 and not ISIN_RE.match(w["text"]) and not TARIH_RE.match(w["text"])]
                kayit.append(dict(sayfa=pi, ad=" ".join(ad + ih), isin=isinler[0] if isinler else "", isinSayi=len(set(isinler)),
                                  nominal=sayi(nom[-1]["text"]) if nom else None, rayic=sayi(deg[-1]["text"]), agirlik=None,
                                  tur=tur, kod=ilk, ihracciHam=" ".join(ih), ihracciSatir=1 if ih else 0))
            else:
                continue
            break
    fpd = sum(g["rayic"] for g in gruplar) or sum(k["rayic"] for k in kayit) or None
    if fpd:
        for k in kayit:
            k["agirlik"] = round(100.0 * k["rayic"] / fpd, 4)
        for g in gruplar:
            g["agirlik"] = round(100.0 * g["rayic"] / fpd, 4)
    return kayit, gruplar


AYRISTIRICILAR = {"standart": standart_kiymetler, "garanti": garanti_kiymetler, "yapikredi": yapikredi_kiymetler}


def satir_aileleri(kayit):
    sat = defaultdict(float)
    for k in kayit:
        sat[aileye(k["tur"] or "") or "diger"] += k["agirlik"]
    return sat


def bist_evren_yukle(veri):
    yol = os.path.join(veri, "bist_evren.txt")
    return {l.strip().upper() for l in open(yol, encoding="utf-8") if l.strip() and not l.startswith("#")} if os.path.exists(yol) else set()


HISSE_TUR = re.compile(r"HISSE|ODUNC", re.I)
KISA_STOP = {"VE", "A.S.", "A.Ş.", "T.A.S.", "T.A.Ş.", "LTD", "STI", "ŞTİ", "SAN", "TIC", "TİC", "GYO", "BK", "KR", "AG", "SA", "NV", "PLC", "INC", "CO", "LLC", "AŞ", "AS"}


def kimlik_ve_ad(k, evren):
    """bistKodu: hisse satirinda kod sutunu evrende varsa; degilse addaki adaylardan tek olan.
    ihracci: ihracci sutunu tek satirdan geldiyse temiz, yoksa bos. kiymetAdi: tek satir ise dolu, yoksa bos (ham ayrica)."""
    hisse = bool(k["tur"] and HISSE_TUR.search(norm(k["tur"])))
    bist = ""
    if hisse and evren and not re.search(r"YABANCI", norm(k["tur"] or "")):
        if k["kod"].upper() in evren:
            bist = k["kod"].upper()
        else:
            aday = [t for t in re.findall(r"\b[A-Z0-9]{4,6}\b", k["ad"]) if t in evren]
            bist = aday[0] if len(set(aday)) == 1 else ""
    temiz_ad = k["ihracciHam"] if k["ihracciSatir"] == 1 and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2}", k["ihracciHam"]) else ""
    if hisse and bist and not temiz_ad and k["ihracciSatir"] == 0:
        temiz_ad = ""
    ihracci = temiz_ad if not hisse else ""
    return bist, ihracci, temiz_ad


def kapi(kayit, gruplar, tefas_son):
    """Yayimlama kapisi. Donus (gecti, sebep, tefasSapma)."""
    if not kayit:
        return False, "kıymet satırı yok", None
    toplam = sum(k["agirlik"] for k in kayit)
    if abs(toplam - 100.0) > SAPMA_ESIK:
        return False, f"şart 1: ağırlık toplamı {toplam:.2f}", None
    yaprak = [g for g in gruplar if g.get("yaprak", True)]
    grup_toplam = sum(g["agirlik"] for g in yaprak if g["agirlik"] is not None)
    if yaprak and all(g["agirlik"] is not None for g in yaprak) and abs(grup_toplam - toplam) > SAPMA_ESIK:
        return False, f"şart 2: satır toplamı {toplam:.2f}, yaprak grup toplamı {grup_toplam:.2f}; satır düşmüş", None
    isinli_tur = re.compile(r"HISSE|TAHVIL|BONO|KIRA|FON|EUROBOND|VDMK|VARLIGA|OZEL SEKTOR|DEVLET|HAZINE", re.I)
    fon_tur = re.compile(r"FONU|FON SEPETI", re.I)
    eksik = [k for k in kayit if not k["isin"] and k["tur"] and isinli_tur.search(norm(k["tur"]))
             and not (fon_tur.search(norm(k["tur"])) and re.search(r"\b[A-Z0-9]{3}\b", k["ad"]))]
    if eksik:
        return False, f"şart 2: {len(eksik)} satırda ISIN okunamadı ({eksik[0]['tur']}: {eksik[0]['ad'][:30]})", None
    coklu = [k for k in kayit if k["isinSayi"] > 1]
    if coklu:
        return False, f"şart 2: {len(coklu)} satıra birden çok ISIN atandı ({coklu[0]['ad'][:30]})", None
    if tefas_son is None:
        return False, "şart 3: TEFAS izleyen gün dağılımı yok", None
    k_aile, t_aile = katla(defaultdict(float, satir_aileleri(kayit)), tefas_aile(tefas_son))
    sp = sapmalar(k_aile, t_aile)
    enb = max(sp.items(), key=lambda kv: abs(kv[1])) if sp else ("-", 0.0)
    if abs(enb[1]) > SAPMA_ESIK:
        return False, f"şart 3: {enb[0]} satırlarda {k_aile.get(enb[0], 0):.2f}, TEFAS {t_aile.get(enb[0], 0):.2f}", abs(enb[1])
    return True, "", abs(enb[1])


# ================================================================ Asama B

def asama_b(kunye, fonlar, veri):
    rows = tefas_dagilim_yukle(veri)
    bugun = date.today()
    bas = (bugun.replace(day=1) - timedelta(days=7)).isoformat()
    sonuc = []
    oids = {kunye[f]["fundOid"]: f for f in fonlar if f in kunye}
    R = []
    oid_l = list(oids)
    for i in range(0, len(oid_l), 50):
        R += raporlar(oid_l[i:i + 50], bas, bugun.isoformat())
    son = {}
    for x in R:
        f = x.get("fundCode")
        if f in fonlar and f not in son:
            son[f] = x
    for f in fonlar:
        x = son.get(f); kur = kunye.get(f, {}).get("kurucu", "?")
        if not x:
            sonuc.append(dict(fon=f, kurucu=kur, duzen="-", durum="rapor yok")); continue
        try:
            pdf = ek_pdf(x["disclosureIndex"])
        except Ertelendi:
            sonuc.append(dict(fon=f, kurucu=kur, duzen="-", durum="ertelendi (ağ)")); continue
        if not pdf:
            sonuc.append(dict(fon=f, kurucu=kur, duzen="-", durum="ek PDF yok")); continue
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            t1 = p.pages[0].extract_text() or ""; sayfa = len(p.pages)
        d = duzen(t1); ray = rapor_ayi(t1, x.get("publishDate"))
        if d == "bilinmiyor":
            sonuc.append(dict(fon=f, kurucu=kur, duzen=d, ay=ray, durum="düzen tanınmadı", sayfa=sayfa)); continue
        kap = sayfa1_yuzdeler(t1, d)
        tef, gun = tefas_ay_ortalama(rows, f, ray) if ray else (None, 0)
        if not kap or not tef:
            sonuc.append(dict(fon=f, kurucu=kur, duzen=d, ay=ray, durum="1. sayfa okunamadı" if not kap else "TEFAS dağılımı yok")); continue
        sp, esl = sayfa1_karsilastir(kap, tef)
        enb = max(sp.items(), key=lambda kv: abs(kv[1])) if sp else ("-", 0)
        sonuc.append(dict(fon=f, kurucu=kur, duzen=d, ay=ray, tefasGun=gun, kapToplam=round(sum(kap.values()), 2),
                          enBuyukSapma=enb[1], sapmaSinif=enb[0], gecti=abs(enb[1]) <= SAPMA_ESIK, eslesmeyen=esl,
                          sapmalar={k: v for k, v in sp.items() if abs(v) > 0.05}, sayfa=sayfa))
    return sonuc


def kurucu_duzen_yaz(veri, sonuc):
    """B sonuclarini kurucu bazinda veri/kurucu_duzen.json'a isler: bir kurucu, sinanan butun fonlari
    gecerse gecti sayilir. Onceki kayit korunur, yeni sinama ustune yazar."""
    yol = os.path.join(veri, "kurucu_duzen.json")
    kd = json_oku(yol, {})
    by = defaultdict(list)
    for r in sonuc:
        if "gecti" in r:
            by[r["kurucu"]].append(r)
    for kur, L in by.items():
        duzenler = {r["duzen"] for r in L}
        kd[kur] = dict(duzen=sorted(duzenler)[0] if len(duzenler) == 1 else "karisik", sinanan=len(L),
                       gecen=sum(1 for r in L if r["gecti"]), enBuyukSapma=max(abs(r["enBuyukSapma"]) for r in L),
                       gecti=all(r["gecti"] for r in L) and len(duzenler) == 1, tarih=date.today().isoformat(),
                       fonlar={r["fon"]: r["enBuyukSapma"] for r in L})
    json_yaz(yol, kd)
    return kd


# ================================================================ kuyruk (gunluk tur)

def hedef_ay(bugun):
    return f"{bugun.year}-{bugun.month-1:02d}" if bugun.month > 1 else f"{bugun.year-1}-12"


def gz_yaz(yol, satirlar):
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow(ICERIK_ALAN); w.writerows(satirlar)
    with open(yol, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(buf.getvalue().encode("utf-8"))


def gz_oku(yol):
    """Arsiv satirlari; surum 1 (9 sutun) satirlari surum 2 semasina tasir (ham ad korunur, kimlik alanlari bos)."""
    if not os.path.exists(yol):
        return []
    with gzip.open(yol, "rt", encoding="utf-8", newline="") as f:
        r = csv.reader(f); next(r, None); out = []
        for s in r:
            if len(s) == 9:
                s = [s[0], s[1], "", s[2], "", "", s[3], s[4], s[5], s[6], s[7], s[8]]
            out.append(s)
        return out


def arsive_isle(arsiv, yazilan):
    aylar = defaultdict(list)
    for s in yazilan:
        aylar[s[1]].append(s)
    for ay, L in aylar.items():
        if not re.match(r"^\d{4}-\d{2}$", ay):
            continue
        yol = os.path.join(arsiv, f"fon_icerik_{ay}.csv.gz")
        yeni = {s[0] for s in L}
        birlesik = [s for s in gz_oku(yol) if s[0] not in yeni] + L
        birlesik.sort(key=lambda s: (s[0], s[7], s[6], s[3]))
        gz_yaz(yol, birlesik)


def ay_geri(ay, n):
    y, m = int(ay[:4]), int(ay[5:7]); m -= n
    while m <= 0:
        m += 12; y -= 1
    return f"{y}-{m:02d}"


def _tarih(s_):
    """'03.09.2026 11:02:16' -> date"""
    return datetime.strptime(s_[:10], "%d.%m.%Y").date()


def son_raporlar(oids, bas, bit):
    """Fon kodu -> en yeni 'Portfoy Dagilim Raporu' bildirimi (bas..bit). 50'lik kumeler, kume basina 1 istek."""
    out = {}
    oid_l = list(oids)
    for i in range(0, len(oid_l), 50):
        for x in raporlar(oid_l[i:i + 50], bas, bit):
            f = x.get("fundCode")
            if f and (f not in out or _tarih(x["publishDate"]) > _tarih(out[f]["publishDate"])):
                out[f] = x
    return out


def rapor_isle(f, x, kunye, kd, rows, evren, hedef):
    """Tek raporu indirir, ayristirir, kapidan gecirir. Donus: (durum, sebep, satirlar, bilgi)."""
    kur = kunye[f]["kurucu"]
    pdf = ek_pdf(x["disclosureIndex"])
    if not pdf:
        return "hata", "ek PDF yok", [], {}
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        t1 = p.pages[0].extract_text() or ""
    d = duzen(t1, pdf); ray = rapor_ayi(t1, x.get("publishDate")) or hedef
    if d == "bilinmiyor":
        return "duzen_taninmadi", "düzen tanınmadı", [], dict(ray=ray, duzen=d)
    if d not in AYRISTIRICILAR:
        return "duzen_taninmadi", f"düzen {d} için ayrıştırıcı yok", [], dict(ray=ray, duzen=d)
    kayit, gruplar = AYRISTIRICILAR[d](pdf)
    gun, tefas_son = tefas_ertesi_gun(rows, f, ray)
    ok, sebep, sp = kapi(kayit, gruplar, tefas_son)
    bilgi = dict(ray=ray, duzen=d, gun=gun, sapma=sp, satir=len(kayit), toplam=round(sum(k["agirlik"] for k in kayit), 2) if kayit else "")
    pdf = None; gruplar = None; gc.collect()
    if ok:
        satir, hisse_n, yabanci_n, bist_bos, ad_temiz = [], 0, 0, 0, 0
        for k in kayit:
            bist, ihr, temiz = kimlik_ve_ad(k, evren)
            if k["tur"] and HISSE_TUR.search(norm(k["tur"])):
                if re.search(r"YABANCI", norm(k["tur"])):
                    yabanci_n += 1
                else:
                    hisse_n += 1; bist_bos += 0 if bist else 1
            ad_temiz += 1 if temiz else 0
            satir.append([f, ray, temiz, k["ad"], bist, ihr, k["isin"], k["tur"] or "", k["nominal"] if k["nominal"] is not None else "", k["rayic"], k["agirlik"], d])
        bilgi.update(hisse=hisse_n, yabanci=yabanci_n, bistBos=bist_bos, adTemiz=ad_temiz)
        return "yayimlandi", "", satir, bilgi
    if sebep.startswith("şart 3: TEFAS"):
        return "beklemede", sebep, [], bilgi
    if sebep.startswith("şart 3"):
        return "sinif_farki", sebep, [], bilgi
    if sebep == "kıymet satırı yok":
        return "duzen_taninmadi", sebep, [], bilgi
    return "hata", sebep, [], bilgi


def kurucu_sinavi(kunye, kd, rows, evren, hedef, bas, bit, sinav_butce, kurucu_filtre=None):
    """Aşama B, Talimat 7: her kurucu icin rapor yayimlayan en fazla uc fon; kiymet tablosu kapidan
    (TEFAS ertesi gun, sinif basina 1,0 puan) geciyorsa kurucu gecer. Sinanmamis ya da eski yontemle
    sinanmis kurucular alinir. Donus: (sinanan kurucu listesi, fon->rapor onbellegi)."""
    onbellek, sinanan = {}, []
    kurucular = defaultdict(list)
    for f, s_ in kunye.items():
        kurucular[s_["kurucu"]].append(f)
    buy = {}
    fl = [f for f in [os.path.join(os.path.dirname(kd_yol_global), "son_gunluk.csv")] if os.path.exists(f)]  # veri/son_gunluk.csv
    if fl:
        for s_ in csv.DictReader(open(fl[0], encoding="utf-8")):
            buy[s_["fonKodu"]] = float(s_["portfoyBuyukluk"] or 0)
    sira = sorted(kurucular, key=lambda k: -sum(buy.get(f, 0) for f in kurucular[k]))
    for kur in sira:
        if kurucu_filtre and kur != kurucu_filtre:
            continue
        onceki = kd.get(kur, {})
        if onceki.get("sinavSurumu", 0) >= SINAV_SURUM and not (onceki.get("sonuc") == "taninmadi" and onceki.get("duzen") in AYRISTIRICILAR or onceki.get("duzen") == "bilinmiyor" and onceki.get("sonuc") == "taninmadi" and onceki.get("yenidenSina")):
            continue
        if ISTEK.sayi >= sinav_butce:
            break
        fonlar = kurucular[kur]
        try:
            rap = son_raporlar({kunye[f]["fundOid"] for f in fonlar}, bas, bit)
        except (ButceBitti, Ertelendi):
            break
        onbellek.update({f: rap.get(f) for f in fonlar})
        yayimlayan = [f for f in sorted(fonlar, key=lambda f: -buy.get(f, 0)) if f in rap]
        if not yayimlayan:
            kd[kur] = dict(duzen="-", gecti=False, raporYok=True, sinanan=0, gecen=0, fonSayisi=len(fonlar),
                           sinavSurumu=SINAV_SURUM, tarih=date.today().isoformat(), not_="6 ayda hicbir fonu portfoy dagilim raporu yayimlamadi")
            sinanan.append(kur); continue
        sonuc = {}
        for f in yayimlayan[:3]:
            if ISTEK.sayi >= sinav_butce:
                break
            try:
                durum, sebep, _, bilgi = rapor_isle(f, rap[f], kunye, kd, rows, evren, hedef)
            except Ertelendi as e:
                durum, sebep, bilgi = "ertelendi", str(e), {}
            except ButceBitti:
                break
            except Exception as e:
                durum, sebep, bilgi = "hata", f"ayrıştırma hatası: {e}", {}
            sonuc[f] = dict(durum=durum, sebep=sebep[:80], **{k: v for k, v in bilgi.items() if k in ("ray", "duzen", "sapma")})
        if not sonuc:
            break
        duzenler = {v.get("duzen") for v in sonuc.values() if v.get("duzen")}
        gecen = sum(1 for v in sonuc.values() if v["durum"] == "yayimlandi")
        sinif = sum(1 for v in sonuc.values() if v["durum"] == "sinif_farki")
        taninmadi = sum(1 for v in sonuc.values() if v["durum"] in ("duzen_taninmadi", "hata"))
        ertelenen = sum(1 for v in sonuc.values() if v["durum"] in ("ertelendi", "beklemede"))
        if ertelenen == len(sonuc):
            continue                                   # bugun karar verilemedi, yarin yeniden
        # Kurucu, orneklerinden en az biri kapidan gecerse gecer; fon basina kapi zaten koruyor.
        # Karisik duzenli kurucularda (Azimut, Pardus) gecmeyen fonlar tek tek duzen_taninmadi olur.
        gecti = gecen >= 1
        sonuc_kur = "gecti" if gecti else ("sinif_farki" if taninmadi == 0 and sinif > 0 else "taninmadi")
        kd[kur] = dict(duzen=sorted(duzenler)[0] if len(duzenler) == 1 else "karisik", gecti=gecti, sonuc=sonuc_kur, sinanan=len(sonuc),
                       gecen=gecen, sinifFarki=sinif, taninmadi=taninmadi, fonSayisi=len(fonlar), yayimlayan=len(yayimlayan),
                       enBuyukSapma=max((v["sapma"] for v in sonuc.values() if v.get("sapma") is not None), default=None),
                       fonlar=sonuc, sinavSurumu=SINAV_SURUM, sinav="kiymet tablosu + kapi, TEFAS ertesi gun", tarih=date.today().isoformat())
        sinanan.append(kur)
    return sinanan, onbellek


kd_yol_global = ""


def kuyruk_turu(kunye, veri, arsiv, kurucu_filtre=None, fon_filtre=None):
    global kd_yol_global
    bugun = date.today(); hedef = hedef_ay(bugun)
    kd_yol = os.path.join(veri, "kurucu_duzen.json"); kd_yol_global = os.path.join(veri, "x")
    kd = json_oku(kd_yol, {})
    ky_yol = os.path.join(veri, "icerik_kuyruk.json"); ky = json_oku(ky_yol, {})
    for f, d in list(ky.items()):            # eski kova adlarini ve 'ozel fon' varsayimini temizle
        if d.get("durum") == "hata" and d.get("sebep") == "ayrıştırma hatası: ":   # butce bitince yanlis yazilan kayitlar (08.09.2026)
            ky[f] = {k: v for k, v in d.items() if k in ("son", "surum", "sapma", "tefasGun", "satir")}
        if d.get("durum") == "kapsamDisi":
            ky[f] = {k: v for k, v in d.items() if k in ("son", "surum", "sapma", "tefasGun", "satir")}
    rows = tefas_dagilim_yukle(veri, arsiv); evren = bist_evren_yukle(veri)
    kd_yol2 = os.path.join(veri, "kosu_durumu.json")
    kdur = json_oku(kd_yol2, {}); kdur["icerik"] = dict(tarih=bugun.isoformat(), hedefAy=hedef, durum="basladi"); json_yaz(kd_yol2, kdur)
    bas = ay_geri(hedef, KAPSAM_AY - 1) + "-01"; bit = bugun.isoformat()

    # ---- Asama B: kurucu sinavi (butcenin SINAV_PAYI'na kadar), oncelikli
    for kur, v in kd.items():                # kural degisikligi: kayitli sinav sonuclari yeniden yorumlanir, istek harcanmaz
        if not kur.startswith("_") and v.get("sinavSurumu", 0) >= SINAV_SURUM and not v.get("raporYok") and not v.get("gecti") and v.get("gecen", 0) >= 1:
            v["gecti"] = True; v["sonuc"] = "gecti"; v["not_"] = "en az bir ornek gecti; gecmeyen fonlar tek tek duzen_taninmadi (08.09.2026)"
    sinanan, onbellek = kurucu_sinavi(kunye, kd, rows, evren, hedef, bas, bit, int(ISTEK.butce * SINAV_PAYI), kurucu_filtre)
    json_yaz(kd_yol, kd)
    gecen_kurucu = {k for k, v in kd.items() if not k.startswith("_") and v.get("gecti")}
    taninmayan_kurucu = {k for k, v in kd.items() if not k.startswith("_") and v.get("sinavSurumu", 0) >= SINAV_SURUM and v.get("sonuc") == "taninmadi"}
    sinif_farki_kurucu = {k for k, v in kd.items() if not k.startswith("_") and v.get("sinavSurumu", 0) >= SINAV_SURUM and v.get("sonuc") == "sinif_farki"}
    rapor_yok_kurucu = {k for k, v in kd.items() if not k.startswith("_") and v.get("raporYok")}

    yazilan, ozet, hata = [], [], []
    kova = defaultdict(list)
    islenen = 0
    fonlar = [f for f, s_ in sorted(kunye.items()) if (not kurucu_filtre or s_["kurucu"] == kurucu_filtre) and (not fon_filtre or f in fon_filtre)]
    # ---- kurucu durumuna gore dagit
    sorgulanacak = []
    for f in fonlar:
        kur = kunye[f]["kurucu"]
        if kur in rapor_yok_kurucu:
            ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="kapsam_disi", sebep="kurucunun hicbir fonu 6 ayda rapor yayimlamadi", tarih=bit); kova["kapsam_disi"].append(f)
        elif kur in taninmayan_kurucu:
            ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="duzen_taninmadi", sebep=f"kurucu düzeni ({kd[kur].get('duzen')}) ayrıştırılamıyor", tarih=bit); kova["duzen_taninmadi"].append(f)
        elif kur in sinif_farki_kurucu:
            ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="sinif_farki", sebep="kurucunun örnek fonlarında TEFAS sınıf eşleşmesi tutmadı", tarih=bit); kova["sinif_farki"].append(f)
        elif kur not in gecen_kurucu:
            ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="duzen_bekliyor", sebep="kurucu düzeni henüz sınanmadı", tarih=bit); kova["duzen_bekliyor"].append(f)
        else:
            sorgulanacak.append(f)
    # ---- Asama C: gecen kurucularin fonlari
    try:
        eksik = [f for f in sorgulanacak if f not in onbellek]
        if eksik:
            onbellek.update({f: None for f in eksik})
            onbellek.update(son_raporlar({kunye[f]["fundOid"] for f in eksik}, bas, bit))
        for f in sorgulanacak:
            x = onbellek.get(f); d = ky.get(f, {}); kur = kunye[f]["kurucu"]
            if not x:
                ky[f] = dict(**{k: v for k, v in d.items() if k == "son"}, durum="kapsam_disi", sebep=f"son {KAPSAM_AY} ayda portföy dağılım raporu yok (tek tek sorgulandı)", ay=hedef, tarih=bit)
                kova["kapsam_disi"].append(f); continue
            rap_ay = rapor_ayi("", x["publishDate"])          # yayim tarihinin onceki ayi; PDF'ten kesinlesir
            if d.get("son") and d["son"] >= rap_ay and d.get("surum", 1) >= AYRISTIRICI_SURUM:
                # elde olan liste en yeni raporun kendisi
                ky[f]["durum"] = "yayimlandi" if d.get("son") == hedef else "rapor_yok_bu_ay"
                ky[f]["sebep"] = "" if d.get("son") == hedef else f"bu ayın raporu yok; son rapor {d['son']}"
                kova[ky[f]["durum"]].append(f); continue
            islenen += 1
            try:
                durum, sebep, satir, bilgi = rapor_isle(f, x, kunye, kd, rows, evren, hedef)
            except ButceBitti:
                raise
            except Ertelendi as e:
                durum, sebep, satir, bilgi = "ertelendi", f"ağ: {e}", [], {}
            except Exception as e:
                durum, sebep, satir, bilgi = "hata", f"ayrıştırma hatası: {type(e).__name__}: {e}", [], {}
            ray = bilgi.get("ray", rap_ay)
            if durum == "yayimlandi":
                yazilan += satir
                ky[f] = dict(son=ray, durum="yayimlandi" if ray == hedef else "rapor_yok_bu_ay", sapma=bilgi["sapma"], tefasGun=bilgi["gun"], satir=bilgi["satir"], surum=AYRISTIRICI_SURUM, tarih=bit,
                             sebep="" if ray == hedef else f"bu ayın raporu yok; son rapor {ray} kullanıldı")
                kova[ky[f]["durum"]].append(f)
                ozet.append([f, ray, kur, bilgi["duzen"], bilgi["satir"], bilgi["toplam"], bilgi["gun"] or "", bilgi["sapma"], bilgi["hisse"], bilgi["yabanci"], bilgi["bistBos"], bilgi["adTemiz"], "yayimlandi", "", OZET_NOT])
            else:
                ky[f] = dict(**{k: v for k, v in d.items() if k == "son"}, durum=durum, sebep=sebep, ay=ray, tarih=bit)
                kova[durum].append(f)
                if durum == "hata":
                    hata.append((f, ray, sebep))
                ozet.append([f, ray, kur, bilgi.get("duzen", "-"), bilgi.get("satir", 0), bilgi.get("toplam", ""), bilgi.get("gun") or "", bilgi.get("sapma") if bilgi.get("sapma") is not None else "", "", "", "", "", durum, sebep, OZET_NOT])
    except ButceBitti:
        print(f"günlük istek bütçesi ({ISTEK.butce}) bitti; kuyruk yarın devam eder", file=sys.stderr)
    except Ertelendi as e:
        print(f"listeleme ertelendi: {e}", file=sys.stderr)

    # ---- ciktilar
    with open(os.path.join(veri, "fon_icerik_son.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(ICERIK_ALAN); w.writerows(yazilan)
    with open(os.path.join(veri, "fon_icerik_ozet.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(OZET_ALAN); w.writerows(ozet)
    with open(os.path.join(veri, "fon_icerik_hata.txt"), "w", encoding="utf-8") as fh:
        for f, ray, sebep in hata:
            fh.write(f"{f}\t{ray}\t{sebep}\n")
    with open(os.path.join(veri, "fon_icerik_kovalar.txt"), "w", encoding="utf-8") as fh:
        for f in sorted(ky):
            if ky[f].get("durum") and ky[f]["durum"] != "yayimlandi":
                fh.write(f"{f}\t{ky[f]['durum']}\t{ky[f].get('sebep', '')}\n")
    if yazilan:
        os.makedirs(arsiv, exist_ok=True); arsive_isle(arsiv, yazilan)
    json_yaz(ky_yol, ky)
    # ---- kovalar tuketicidir: her faal YF fon tam bir kovada; sirasi gelmeyen 'kuyrukta'
    for f in kunye:
        d = ky.get(f, {})
        if not d.get("durum"):
            ky[f] = dict(**{k: v for k, v in d.items() if k in ("son", "surum", "sapma", "tefasGun", "satir")}, durum="kuyrukta", sebep="sırası gelmedi", tarih=bit)
    json_yaz(ky_yol, ky)
    sayim = defaultdict(int)
    for f in kunye:
        durum_f = ky[f]["durum"]
        sayim["listesi_var" if durum_f == "yayimlandi" else durum_f] += 1
    toplam_fon = len(kunye); kova_toplami = sum(sayim.values())
    # ---- kapsam orani, tek tanim: pay = hedef ay icin arsivde gecerli listesi olan fon;
    #      payda = hedef ay icin rapor yayimlayan fon (KAP listelemesinde en yeni raporu hedef ayda olan)
    arsiv_yol = os.path.join(arsiv, f"fon_icerik_{hedef}.csv.gz")
    kapsam_pay = len({r_[0] for r_ in gz_oku(arsiv_yol)})
    for f, x in onbellek.items():                     # bu turda listelenen fonlarin son rapor ayi
        if x and f in ky:
            ky[f]["sonRaporAy"] = rapor_ayi("", x["publishDate"])
    kapsam_payda = sum(1 for f in kunye if ky[f].get("sonRaporAy") == hedef or ky[f].get("son") == hedef)
    kapsam_orani = round(kapsam_pay / kapsam_payda, 4) if kapsam_payda else None
    json_yaz(ky_yol, ky)
    durum = dict(tarih=bit, hedefAy=hedef, durum="tamamlandi" if kova_toplami == toplam_fon else "denklesmedi",
                 sinananKurucu=sinanan, gecenKurucu=len(gecen_kurucu), taninmayanKurucu=len(taninmayan_kurucu), raporYokKurucu=len(rapor_yok_kurucu),
                 islenen=islenen, yayimlandiBuTur=len({s_[0] for s_ in yazilan}), satirBuTur=len(yazilan),
                 kovalar=dict(sayim), kovaToplami=kova_toplami, toplamFon=toplam_fon,
                 kapsamPay=kapsam_pay, kapsamPayda=kapsam_payda, kapsamOrani=kapsam_orani,
                 kapsamTanimi="pay: hedef ay icin arsivde gecerli kiymet listesi olan fon; payda: KAP'ta en yeni portfoy dagilim raporu hedef ayda olan fon",
                 istek=ISTEK.sayi, h429=ISTEK.h429, ayristiriciSurum=AYRISTIRICI_SURUM, sinavSurumu=SINAV_SURUM, **{"not": OZET_NOT})
    kdur = json_oku(kd_yol2, {}); kdur["icerik"] = durum; json_yaz(kd_yol2, kdur)
    return durum, ozet


# ================================================================ CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asama", default="B", choices=["B", "kuyruk"])
    ap.add_argument("--pdf", nargs="*", help="yerel PDF'lerde ayristiriciyi sina (ad: ek_<FON>*.pdf)")
    ap.add_argument("--veri", default=os.path.join(KOK, "veri"))
    ap.add_argument("--arsiv", default=os.path.join(KOK, "arsiv"))
    ap.add_argument("--fon", help="B ve kuyruk: virgulle fon kodlari (kuyrukta yalniz bu fonlar islenir)")
    ap.add_argument("--kurucu", type=int, default=0, help="B: TEFAS buyuklugune gore en buyuk N kurucu")
    ap.add_argument("--fon-basina", type=int, default=3)
    ap.add_argument("--kurucu-filtre", help="kuyruk: yalnizca bu kurucu")
    ap.add_argument("--butce", type=int, default=BUTCE)
    ap.add_argument("--ay", help="--pdf: rapor ayi (YYYY-MM), TEFAS karsilastirmasi icin")
    ap.add_argument("--goster", type=int, default=0, help="--pdf: en buyuk N hisse satirini bistKodu ile goster")
    a = ap.parse_args()
    ISTEK.butce = a.butce

    if a.pdf:
        rows = tefas_dagilim_yukle(a.veri); evren = bist_evren_yukle(a.veri)
        for yol in a.pdf:
            fon = re.sub(r"^ek_|[_.].*$", "", os.path.basename(yol)); pdf = open(yol, "rb").read()
            with pdfplumber.open(io.BytesIO(pdf)) as p:
                t1 = p.pages[0].extract_text() or ""
            d = duzen(t1, pdf); ray = a.ay or rapor_ayi(t1) or "?"
            kayit, gruplar = AYRISTIRICILAR[d](pdf) if d in AYRISTIRICILAR else ([], [])
            gun, son = tefas_ertesi_gun(rows, fon, ray) if ray != "?" else (None, None)
            ok, sebep, sp = kapi(kayit, gruplar, son)
            print(f"=== {fon} {d} {ray}: satır {len(kayit)}, yaprak grup {sum(1 for g in gruplar if g['yaprak'])}, ISIN'siz {sum(1 for k in kayit if not k['isin'])}, toplam "
                  f"{sum(k['agirlik'] for k in kayit):.2f}, TEFAS {gun} sapma {sp} | {'GEÇTİ' if ok else 'KALDI: ' + sebep}")
            if a.goster:
                hisse = sorted([k for k in kayit if k["tur"] and HISSE_TUR.search(norm(k["tur"]))], key=lambda k: -k["agirlik"])
                bos = sum(1 for k in hisse if not kimlik_ve_ad(k, evren)[0])
                print(f"    hisse satırı {len(hisse)}, bistKodu boş {bos}")
                for k in hisse[:a.goster]:
                    bist, ihr, temiz = kimlik_ve_ad(k, evren)
                    print(f"    {k['agirlik']:6.2f}  bistKodu={bist:6s} isin={k['isin']:13s} kod={k['kod']:8s} temiz={temiz[:30]!r} ham={k['ad'][:55]!r}")
        return

    kunye = kunye_yukle(a.veri)
    if a.asama == "kuyruk":
        durum, ozet = kuyruk_turu(kunye, a.veri, a.arsiv, a.kurucu_filtre, set(f.strip().upper() for f in a.fon.split(",")) if a.fon else None)
        print(json.dumps(durum, ensure_ascii=False))
        return

    fonlar = [f.strip().upper() for f in a.fon.split(",")] if a.fon else []
    if a.kurucu:
        fl = [f for f in sorted(glob.glob(os.path.join(a.veri, "tefas_gunluk_*.csv"))) + [os.path.join(a.veri, "son_gunluk.csv")] if os.path.exists(f)]
        songun, buy = "", {}
        for s in csv.DictReader(open(fl[-1], encoding="utf-8")):
            songun = max(songun, s["tarih"])
        for s in csv.DictReader(open(fl[-1], encoding="utf-8")):
            if s["tarih"] == songun and s["fonKodu"] in kunye:
                buy[s["fonKodu"]] = float(s["portfoyBuyukluk"] or 0)
        kur = defaultdict(list)
        for f, b in buy.items():
            kur[kunye[f]["kurucu"]].append((b, f))
        for k, L in sorted(kur.items(), key=lambda kv: -sum(b for b, _ in kv[1]))[:a.kurucu]:
            fonlar += [f for _, f in sorted(L, reverse=True)[:a.fon_basina]]
    if not fonlar:
        sys.exit("fon verilmedi")
    sonuc = asama_b(kunye, fonlar, a.veri)
    for r in sonuc:
        print(r)
    kd = kurucu_duzen_yaz(a.veri, sonuc)
    for k, v in kd.items():
        print(f"  {k}: {v['duzen']} sınanan {v['sinanan']} geçen {v['gecen']} en büyük sapma {v['enBuyukSapma']} -> {'GEÇTİ' if v['gecti'] else 'kaldı'}")


if __name__ == "__main__":
    main()
