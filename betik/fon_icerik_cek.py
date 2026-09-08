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
    (r"(BORSA YATIRIM FONU|\bBYF\b|BORSA Y\.FONU).*(YABANCI|YP)", "ybyf"), (r"BORSA YATIRIM FONU|\bBYF\b|BORSA Y\.FONU", "byf"), (r"YATIRIM FONU|Y\.FONU|YATIRIM FON|FON SEPETI", "yf"),
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
]
UST_GRUP = {a: g for a, g, _ in ESLEME_TABLOSU}


def aileye(ad):
    n = norm(ad)
    for k, a in KURAL:
        if re.search(k, n):
            return a
    return None


def tefas_dagilim_yukle(veri):
    fl = sorted(glob.glob(os.path.join(veri, "tefas_dagilim_*.csv*")) + glob.glob(os.path.join(veri, "son_dagilim.csv")))
    rows = {}
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
    return (adaylar[0], rows[(adaylar[0], fon)]) if adaylar else (None, None)


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

def duzen(t1):
    n = norm(t1)
    if "AYLIK ORTALAMA PORTFOYDEKI MENKUL KIYMETLER YUZDESI" in n and "A-)" in n:
        return "standart"
    if "YATIRIM FONLARI PORTFOY DAGILIM RAPORU" in n and "RAPOR DONEMI" in n:
        return "garanti"
    if "AYLIK RAPORUDUR" in n:
        return "yapikredi"
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


def kuyruk_turu(kunye, veri, arsiv, kurucu_filtre=None, fon_filtre=None):
    bugun = date.today(); hedef = hedef_ay(bugun)
    kd = json_oku(os.path.join(veri, "kurucu_duzen.json"), {})
    ky_yol = os.path.join(veri, "icerik_kuyruk.json"); ky = json_oku(ky_yol, {})
    rows = tefas_dagilim_yukle(veri)
    evren = bist_evren_yukle(veri)
    gecen = {k for k, v in kd.items() if v.get("gecti")}
    yazilan, ozet, hata, kapsam_disi, ertelendi, beklemede = [], [], [], [], [], []
    islenen = 0
    kd_yol = os.path.join(veri, "kosu_durumu.json")
    kdur = json_oku(kd_yol, {}); kdur["icerik"] = dict(tarih=bugun.isoformat(), hedefAy=hedef, durum="basladi"); json_yaz(kd_yol, kdur)

    # kuyruk: hedef ayin raporu alinmamis fonlar
    fonlar = []
    for f, s in sorted(kunye.items()):
        if kurucu_filtre and s["kurucu"] != kurucu_filtre:
            continue
        if fon_filtre and f not in fon_filtre:
            continue
        d = ky.get(f, {})
        if d.get("son") == hedef and d.get("surum", 1) >= AYRISTIRICI_SURUM:
            continue
        if d.get("durum") == "kapsamDisi" and (d.get("kalici") or d.get("ay") == hedef):
            continue
        if "ÖZEL" in s["fonUnvan"].upper():
            ky[f] = dict(durum="kapsamDisi", sebep="özel fon; KAP'ta portföy raporu yayımlanmaz", kalici=True, tarih=bugun.isoformat())
            kapsam_disi.append((f, ky[f]["sebep"])); continue
        if s["kurucu"] not in gecen:
            ky[f] = dict(durum="kapsamDisi", sebep=f"kurucu düzeni B aşamasını geçmedi ya da sınanmadı ({s['kurucu']})", ay=hedef, tarih=bugun.isoformat())
            kapsam_disi.append((f, ky[f]["sebep"])); continue
        fonlar.append(f)
    print(f"hedef ay {hedef}: kuyrukta {len(fonlar)} fon", file=sys.stderr)

    oids = {kunye[f]["fundOid"]: f for f in fonlar}
    bas = (datetime.strptime(hedef + "-01", "%Y-%m-%d").date().replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()
    son = {}
    try:
        oid_l = list(oids)
        for i in range(0, len(oid_l), 50):
            for x in raporlar(oid_l[i:i + 50], bas, bugun.isoformat()):
                f = x.get("fundCode")
                if f in oids.values() and f not in son:
                    son[f] = x
        for f in fonlar:
            x = son.get(f)
            if not x:
                if bugun.day >= RAPOR_BEKLEME_GUNU:
                    ky[f] = dict(durum="kapsamDisi", sebep="dağılım raporu yayımlamıyor", ay=hedef, tarih=bugun.isoformat())
                    kapsam_disi.append((f, ky[f]["sebep"]))
                else:
                    ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="beklemede", sebep="rapor henüz yayımlanmadı", tarih=bugun.isoformat())
                    beklemede.append(f)
                continue
            islenen += 1
            try:
                pdf = ek_pdf(x["disclosureIndex"])
            except Ertelendi as e:
                ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="ertelendi", sebep=f"ağ: {e}", tarih=bugun.isoformat())
                ertelendi.append(f); continue
            kur = kunye[f]["kurucu"]
            if not pdf:
                ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="hata", sebep="ek PDF yok", ay=hedef, tarih=bugun.isoformat())
                hata.append((f, hedef, "ek PDF yok")); ozet.append([f, hedef, kur, "-", 0, "", "", "", "hata", "ek PDF yok"]); continue
            try:
                with pdfplumber.open(io.BytesIO(pdf)) as p:
                    t1 = p.pages[0].extract_text() or ""
                d = duzen(t1); ray = rapor_ayi(t1, x.get("publishDate")) or hedef
                if d != kd[kur].get("duzen"):
                    sebep = f"düzen {d}, kurucunun geçen düzeni {kd[kur].get('duzen')}"
                    ky[f] = dict(durum="kapsamDisi", sebep=sebep, ay=hedef, tarih=bugun.isoformat()); kapsam_disi.append((f, sebep)); continue
                kayit, gruplar = standart_kiymetler(pdf)
                gun, tefas_son = tefas_ertesi_gun(rows, f, ray)
                ok, sebep, sp = kapi(kayit, gruplar, tefas_son)
            except Exception as e:
                ok, sebep, sp, kayit, gun, ray = False, f"ayrıştırma hatası: {e}", None, [], None, hedef
            toplam = round(sum(k["agirlik"] for k in kayit), 2) if kayit else ""
            pdf = None; gruplar = None; gc.collect()      # bir seferde tek rapor bellekte; her fondan sonra serbest birak
            if ok:
                hisse_n = yabanci_n = bist_bos = ad_temiz = 0
                for k in kayit:
                    bist, ihr, temiz = kimlik_ve_ad(k, evren)
                    if k["tur"] and HISSE_TUR.search(norm(k["tur"])):
                        if re.search(r"YABANCI", norm(k["tur"])):
                            yabanci_n += 1          # BIST kodu beklenmez; kimlik ISIN
                        else:
                            hisse_n += 1; bist_bos += 0 if bist else 1
                    ad_temiz += 1 if temiz else 0
                    yazilan.append([f, ray, temiz, k["ad"], bist, ihr, k["isin"], k["tur"] or "", k["nominal"] if k["nominal"] is not None else "", k["rayic"], k["agirlik"], d])
                ky[f] = dict(son=ray, durum="yayimlandi", sapma=sp, tefasGun=gun, satir=len(kayit), surum=AYRISTIRICI_SURUM, tarih=bugun.isoformat())
                ozet.append([f, ray, kur, d, len(kayit), toplam, gun or "", sp, hisse_n, yabanci_n, bist_bos, ad_temiz, "yayimlandi", "", OZET_NOT])
            elif sebep.startswith("şart 3: TEFAS"):
                ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="beklemede", sebep=sebep, tarih=bugun.isoformat())
                beklemede.append(f); ozet.append([f, ray, kur, d, len(kayit), toplam, "", "", "", "", "", "", "beklemede", sebep, OZET_NOT])
            else:
                ky[f] = dict(**{k: v for k, v in ky.get(f, {}).items() if k == "son"}, durum="hata", sebep=sebep, ay=hedef, tarih=bugun.isoformat())
                hata.append((f, ray, sebep)); ozet.append([f, ray, kur, d, len(kayit), toplam, gun or "", sp if sp is not None else "", "", "", "", "", "hata", sebep, OZET_NOT])
    except ButceBitti:
        print(f"günlük istek bütçesi ({BUTCE}) bitti; kuyruk yarın devam eder", file=sys.stderr)
    except Ertelendi as e:
        print(f"listeleme ertelendi: {e}", file=sys.stderr)

    # ciktilar
    with open(os.path.join(veri, "fon_icerik_son.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(ICERIK_ALAN); w.writerows(yazilan)
    with open(os.path.join(veri, "fon_icerik_ozet.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(OZET_ALAN); w.writerows(ozet)
    with open(os.path.join(veri, "fon_icerik_hata.txt"), "w", encoding="utf-8") as fh:
        for f, ray, sebep in hata:
            fh.write(f"{f}\t{ray}\t{sebep}\n")
    with open(os.path.join(veri, "fon_icerik_kapsam_disi.txt"), "w", encoding="utf-8") as fh:
        for f, sebep in sorted(kapsam_disi):
            fh.write(f"{f}\t{sebep}\n")
    if yazilan:
        os.makedirs(arsiv, exist_ok=True); arsive_isle(arsiv, yazilan)
    json_yaz(ky_yol, ky)
    kalan = sum(1 for f in fonlar if ky.get(f, {}).get("son") != hedef and ky.get(f, {}).get("durum") not in ("kapsamDisi", "hata"))
    kova = defaultdict(int)
    for _, sebep in kapsam_disi:
        kova["ozelFon" if sebep.startswith("özel fon") else "kurucuDuzeni" if sebep.startswith("kurucu düzeni") else
             "duzenTaninmadi" if sebep.startswith("düzen") else "raporYayimlamiyor" if sebep.startswith("dağılım raporu") else "diger"] += 1
    durum = dict(tarih=bugun.isoformat(), hedefAy=hedef, durum="tamamlandi", kuyruk=len(fonlar), islenen=islenen, yayimlanan=len({s[0] for s in yazilan}),
                 satir=len(yazilan), hata=len(hata), kapsamDisi=len(kapsam_disi), kapsamDisiKova=dict(kova), ertelendi=len(ertelendi), beklemede=len(beklemede),
                 istek=ISTEK.sayi, h429=ISTEK.h429, kuyrukKalan=kalan, ayristiriciSurum=AYRISTIRICI_SURUM, **{"not": OZET_NOT})
    kdur = json_oku(kd_yol, {}); kdur["icerik"] = durum; json_yaz(kd_yol, kdur)
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
            d = duzen(t1); ray = a.ay or rapor_ayi(t1) or "?"
            kayit, gruplar = standart_kiymetler(pdf) if d == "standart" else ([], [])
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
