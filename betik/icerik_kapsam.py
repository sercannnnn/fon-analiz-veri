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
# M67 (62 numaralı not): teminatlı para piyasası işlemi sınıfı; ihraççı ölçüsünün dışında kalır, kendi satırında dayanağının sınıfı ve ihraççısıyla raporlanır
TEMINATLI_PP_TURLER = {"T.REPO", "REPO", "TERS REPO", "G.DİĞER VARLIKLAR TERS REPO", "TAAHHÜT SÖZLEŞMESİ SATIŞ", "TAAHHÜT SÖZLEŞMESİ ALIŞ",
                       "TAAHHÜT SÖZLEŞMESİ", "TPP", "BPP", "KATILIM HESABI"}
REPO_TURLER = TEMINATLI_PP_TURLER      # eski ad
KARSI_TARAF_SABIT = {"TPP": "Takasbank para piyasası (merkezi karşı taraf; piyasa kuralı, raporda yazmaz)",
                     "BPP": "Borsa İstanbul para piyasası (Takasbank merkezi karşı taraf; piyasa kuralı, raporda yazmaz)"}
KAMU_IHRACCILAR = ("HAZİNE", "HAZINE", "T.C. HAZİNE", "TCMB", "MERKEZ BANKASI")   # tek ihraççı sınırından muaf, ağırlığı yine yazılır (62 numaralı not)
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


def _veri_anahtari(r):
    """Satırın veri günü: veriGunu doluysa o, yoksa rapor ayının son günü (70 numaralı not: seçim veriGunu ile; yayımcı etiketi yanıltabilir)."""
    vg = (r.get("veriGunu") or "").strip()[:10]
    if vg:
        return vg
    ay = (r.get("raporTarihi") or "")[:7]
    return _ay_sonu(ay).isoformat() if len(ay) == 7 and ay[4] == "-" else ""


def son_ay_satirlari(satirlar):
    """Her fonun yalnızca en yeni raporunun satırları; seçim veri gününe göre (veriGunu, yoksa rapor ayının son günü). Aylık dosyalar
    birlikte okununca aynı fon iki ayda da bulunur ve toplamlar iki kez sayılırdı."""
    son = {}
    for r in satirlar:
        k = _veri_anahtari(r)
        if k > son.get(r["fonKodu"], ""):
            son[r["fonKodu"]] = k
    return [r for r in satirlar if _veri_anahtari(r) == son.get(r["fonKodu"])]


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


def _norm(s):
    return (s or "").upper().replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")


def kamu_mu(isin, ihracci=""):
    """Hazine ve TCMB: DİBS (TRT…), Hazine kira sertifikası (TRD + rakam), adı Hazine/TCMB olan satır."""
    i = (isin or "").upper()
    if i.startswith("TRT") or (i.startswith("TRD") and len(i) > 3 and i[3].isdigit()):
        return True
    return any(_norm(k) in _norm(ihracci) for k in KAMU_IHRACCILAR)


TEMINATLI_PP_PARCALARI = ("REPO", "TAAHHUT SOZLESMESI", "TPP", "BPP", "PARA PIYASASI", "KATILMA HESAP", "KATILIM HESABI")   # fonbul: "U) PARA PİYASASI", "M) KATILMA HESAPLARI"


def _tur_teminatli(tur):
    n = _norm(tur).strip()
    return n in {_norm(x) for x in TEMINATLI_PP_TURLER} or any(p in n for p in TEMINATLI_PP_PARCALARI)


def _katilim_mu(tur):
    n = _norm(tur)
    return "KATILIM HESABI" in n or "KATILMA HESAP" in n


def _pp_mu(tur):
    n = _norm(tur)
    return n in ("TPP", "BPP") or "PARA PIYASASI" in n


def banka_grup_yukle(yol):
    """banka_grup.json: {grup adı: [ad parçaları]}; ihraççı adında parça geçen banka o gruba sayılır (Ziraat Bankası ile Ziraat Katılım aynı
    karşı taraftır; 64 numaralı not). Kamuya açık şirket yapısıdır; dosya yoksa boş."""
    if not yol or not os.path.exists(yol):
        return {}
    try:
        import json
        return {k: v for k, v in json.load(open(yol, encoding="utf-8")).items() if not k.startswith("_")}
    except Exception:
        return {}


def banka_grubu(ad, tablo):
    n = _norm(ad)
    for grup, parcalar in (tablo or {}).items():
        if any(_norm(p) in n for p in parcalar if p):
            return grup
    return None


GENEL_KOK = {"PORTFOY", "YATIRIM", "MENKUL", "FON", "FONU", "GLOBAL", "CAPITAL", "GOLDEN", "TURK", "TURKIYE", "ATLAS", "HEDEF"}
IHRACCI_OLMAYAN_TURLER = ("VIOP", "NAKIT TEMINAT", "DOVIZ", "TPP", "BPP", "PARA PIYASASI", "VADELI ISLEM", "FUTURES", "UZUN", "KISA")   # M69: yapisi geregi ihracci degil
# 66 numaralı not, bölüm 2 (varsayım, kullanıcı onayı bekliyor): kurucu grubu payı bildirim eşikleri (uyarı, aykırılık), kategoriye göre; fon sepeti muaf ama yazılır
GRUP_PAYI_ESIK = {"Para Piyasası": (5.0, 10.0), "Kısa Vadeli Borçlanma": (5.0, 10.0), "Borçlanma Araçları": (5.0, 10.0), "Katılım": (5.0, 10.0),
                  "Kıymetli Madenler": (5.0, 10.0), "Hisse Senedi": (10.0, 15.0), "Değişken": (10.0, 15.0), "Serbest": (25.0, 40.0), "Fon Sepeti": None}


def grup_payi_esigi(kategori):
    """Kategori adı eşik tablosundaki anahtarla başlıyorsa o eşik; bilinmeyen kategori en sıkı eşik (5, 10). Fon sepeti None (muaf)."""
    k = kategori or ""
    for ad, esik in GRUP_PAYI_ESIK.items():
        if k.startswith(ad):
            return esik
    return (5.0, 10.0)


def grup_payi_durumu(pay, kategori):
    """'aykırı' | 'uyarı' | 'eşik içinde' | 'muaf (fon sepeti)' | 'ölçülemedi'."""
    if pay is None:
        return "ölçülemedi"
    e = grup_payi_esigi(kategori)
    if e is None:
        return "muaf (fon sepeti)"
    return "aykırı" if pay > e[1] else "uyarı" if pay > e[0] else "eşik içinde"


def kurucu_grubu_payi(satirlar, fonlar, fon_kurucu, grup_tablo=None):
    """M68 (64 numaralı not): tutulan fonun kurucu grubuna maruziyeti = kurucu grubunun adı geçen BÜTÜN satırların toplamı, satırın türü ne
    olursa olsun (hisse, tahvil, kira sertifikası, repo dayanağı, kurucunun kendi fonları). Eşleşme: kurucu grup tablosundaki adlar (kurucu_grup.json)
    ve kurucunun kök kelimesi (ilk kelime, dört harften uzun, genel kelime değil) kelime başında; ihraççı alanı doluysa kesin, boşsa ham addan
    üst sınır. Dönüş: {fonKodu: dict(kesin, ust_sinir, kalemler[(ad, puan)], adsiz_satir, veri_gunu)}."""
    import re
    son = son_ay_satirlari(satirlar)
    out = {}
    for r in son:
        f = r.get("fonKodu")
        if f not in fonlar:
            continue
        kur = fon_kurucu.get(f) or ""
        adlar = set(x for x in (grup_tablo or {}).get(kur, [kur]) if x)
        kok = (kur.split() or [""])[0]
        kok_re = re.compile(r"(?<![A-ZÇĞİÖŞÜ0-9])" + re.escape(_norm(kok)) + r"(?![A-ZÇĞİÖŞÜ0-9])") if len(kok) >= 4 and _norm(kok) not in GENEL_KOK else None
        def eslesir(metin):
            n = _norm(metin)
            return any(_norm(a) in n for a in adlar) or bool(kok_re and kok_re.search(n))
        try:
            a = float(r.get("agirlik") or 0)
        except ValueError:
            continue
        vg = (r.get("veriGunu") or "").strip()[:10] or (_ay_sonu(r.get("raporTarihi") or "").isoformat() if len(r.get("raporTarihi") or "") == 7 else None)
        o = out.setdefault(f, dict(kesin=0.0, ust_sinir=0.0, olculemeyen=0.0, olculemeyen_tur={}, kalemler={}, adsiz_satir=0, veri_gunu=vg))
        ih = (r.get("ihracci") or "").strip()
        if ih:
            if eslesir(ih):
                o["kesin"] += a
                o["kalemler"][ih] = o["kalemler"].get(ih, 0.0) + a
        else:
            o["adsiz_satir"] += 1
            tur = (r.get("tur") or "").strip()
            if eslesir(r.get("kiymetAdiHam") or ""):
                o["ust_sinir"] += a          # ham adda grup adı: üst sınıra girer (M68 tanımı)
                o["kalemler"]["(ham) " + (r.get("kiymetAdiHam") or "")[:30]] = o["kalemler"].get("(ham) " + (r.get("kiymetAdiHam") or "")[:30], 0.0) + a
            elif a > 0 and not any(p in _norm(tur) for p in IHRACCI_OLMAYAN_TURLER):
                o["olculemeyen"] += a        # M69 (negatif satır, takas bekleyen satış, bilinmezliğe girmez): adsız satır "grup değil" değil "bilinmiyor"; yapısı gereği ihraççı olmayan türler düşülür
                o["olculemeyen_tur"][tur or "türsüz"] = o["olculemeyen_tur"].get(tur or "türsüz", 0.0) + a
    for f, o in out.items():
        o["kesin"] = round(o["kesin"], 2)
        o["ust_sinir"] = round(o["kesin"] + o["ust_sinir"], 2)                 # ham eşleşen adsız satırlar dahil
        o["olculemeyen"] = round(o["olculemeyen"], 2)
        o["en_kotu"] = round(o["ust_sinir"] + o["olculemeyen"], 2)             # M69: kesin + ham + ölçülemeyen
        o["olculemeyen_tur"] = sorted(((k, round(v, 2)) for k, v in o["olculemeyen_tur"].items()), key=lambda kv: -kv[1])[:3]
        o["kalemler"] = sorted(((k, round(v, 2)) for k, v in o["kalemler"].items()), key=lambda kv: -kv[1])[:4]
    return out


def fon_ihracci_ilk(satirlar, fonlar, n=3, banka_grup=None):
    """M62: her fon için en yüksek n NET ihraççı ağırlığı (aynı ISIN ya da BIST kodunun satırları toplanır, negatif satır dahil; yalnızca
    en yeni rapor; teminatlı para piyasası işlemleri TEMINATLI_PP_TURLER dışarıda). Anahtar: BIST kodu, yoksa ISIN, yoksa ihraççı adı
    (mevduat ve katılım hesabı: banka). Kamu ihraççı (kamu_mu) `muaf` işaretiyle döner, ağırlığı yine yazılır. Adsız ağırlık (anahtarı olmayan
    satırlar) fon başına `adsiz` alanında sözlüğün `_adsiz` girdisinde; fonun ölçüsü ancak adsız pay küçükse tamdır ("kısmen ölçüldü", düzeltme 3).
    Dönüş: {fonKodu: [dict(kod, agirlik(puan), veri_gunu, muaf, ihracci)]} ve {fonKodu: adsız puan} çifti için fon_ihracci_ilk_adsiz."""
    return _fon_ihracci(satirlar, fonlar, n, banka_grup)[0]


def fon_ihracci_ilk_adsiz(satirlar, fonlar):
    """{fonKodu: adsız (anahtarsız) ağırlık, puan}; teminatlı para piyasası satırları hariç."""
    return _fon_ihracci(satirlar, fonlar, 3)[1]


def _fon_ihracci(satirlar, fonlar, n, banka_grup=None):
    son = son_ay_satirlari(satirlar)
    top, adsiz = {}, {}
    for r in son:
        f = r.get("fonKodu")
        if f not in fonlar or _tur_teminatli(r.get("tur")):
            continue
        try:
            a = float(r.get("agirlik") or 0)
        except ValueError:
            continue
        ih = (r.get("ihracci") or "").strip()
        bg = banka_grubu(ih, banka_grup) if ih and not (r.get("bistKodu") or r.get("isin")) else None   # mevduat: banka grubu tek karşı taraf (64 numaralı not)
        kod = (bg or r.get("bistKodu") or r.get("isin") or ih).strip()
        if not kod:
            adsiz[f] = adsiz.get(f, 0.0) + a; continue
        d = top.setdefault(f, {})
        e = d.setdefault(kod, dict(kod=kod, agirlik=0.0, veri_gunu=(r.get("veriGunu") or "").strip()[:10] or None, ay=r.get("raporTarihi"),
                                   muaf=kamu_mu(r.get("isin"), ih), ihracci=ih))
        e["agirlik"] += a
    out = {}
    for f, d in top.items():
        L = sorted(d.values(), key=lambda e: -e["agirlik"])[:n]
        for e in L:
            e["agirlik"] = round(e["agirlik"], 2)
            if not e["veri_gunu"]:
                e["veri_gunu"] = (_ay_sonu(e["ay"]).isoformat() if e.get("ay") and len(e["ay"]) == 7 else None)
        out[f] = L
    return out, {f: round(v, 2) for f, v in adsiz.items()}


TEMINAT_SINIFI = (("TRT", "Hazine"), ("TRD", "kira sertifikası"), ("TRF", "finansman bonosu"), ("TRS", "özel sektör tahvili"),
                  ("TRP", "VDMK ya da ipotekli"), ("TRY", "yatırım fonu"), ("TRA", "hisse"), ("TRE", "hisse"), ("XS", "eurobond"))


def teminat_sinifi(isin, bist=""):
    """Teminat kıymetinin sınıfı ISIN önekinden (Türkiye ISIN yapısı); BIST kodu doluysa hisse."""
    if bist:
        return "hisse"
    for onek, ad in TEMINAT_SINIFI:
        if (isin or "").upper().startswith(onek):
            return ad
    return "diğer"


def repo_ozeti(satirlar, fonlar, grup_adlari=()):
    """M65 ve M67: teminatlı para piyasası işlemleri (TEMINATLI_PP_TURLER) fon başına: toplam, tür dağılımı, dayanağın sınıf dağılımı, en büyük tek
    dayanak, Hazine dışı oran, dayanağın ihraççısına göre toplam (ilk üç; `ihracci` sütunu, M66) ve kurucu grubu adı geçen dayanak toplamı
    (grup_adlari: kurucu grup tablosundaki adlar). Karşı taraf: repo ve taahhüt satırında rapor ad taşımaz (borsa sözleşme numarası) → 'ölçülemedi';
    TPP ve BPP için piyasa kuralı (KARSI_TARAF_SABIT); katılım hesabında karşı taraf ihraççı sütunundaki bankadır."""
    return _repo_ozeti(satirlar, fonlar, grup_adlari)


def _repo_ozeti(satirlar, fonlar, grup_adlari=()):
    """M65 (60 numaralı not): repo satırları ihraççı ölçüsünden çıkarılınca sıfıra dönmesin; fon başına ters repo toplamı, teminatın sınıf
    dağılımı, en büyük tek teminat ve Hazine dışı teminat oranı. Karşı taraf: rapor karşı taraf adı taşımaz (borsa sözleşme numarası taşır),
    bu yüzden 'raporda yok, ölçülemedi' (kural 14). Yalnızca en yeni rapor. Dönüş: {fonKodu: dict(toplam, sinif{ad: puan}, en_buyuk(kod, puan),
    hazine_disi, satir, karsi_taraf, veri_gunu)}; repo satırı olmayan fon sözlükte yoktur."""
    son = son_ay_satirlari(satirlar)
    out = {}
    for r in son:
        f = r.get("fonKodu")
        if f not in fonlar or not _tur_teminatli(r.get("tur")):
            continue
        try:
            a = float(r.get("agirlik") or 0)
        except ValueError:
            continue
        tur = (r.get("tur") or "").strip()
        o = out.setdefault(f, dict(toplam=0.0, tur={}, sinif={}, teminat={}, ihracci={}, grup=0.0, satir=0, karsi_taraf={},
                                   veri_gunu=(r.get("veriGunu") or "").strip()[:10] or None))
        kod = (r.get("bistKodu") or r.get("isin") or "").strip() or "kodsuz"
        ih = (r.get("ihracci") or "").strip()
        s = "Hazine" if kamu_mu(r.get("isin"), ih) else teminat_sinifi(r.get("isin") or "", r.get("bistKodu") or "")
        if _katilim_mu(tur):
            s = "katılım hesabı (teminatsız, banka)"
        o["toplam"] += a; o["satir"] += 1
        o["tur"][tur] = o["tur"].get(tur, 0.0) + a
        o["sinif"][s] = o["sinif"].get(s, 0.0) + a
        o["teminat"][kod] = o["teminat"].get(kod, 0.0) + a
        if ih:
            o["ihracci"][ih] = o["ihracci"].get(ih, 0.0) + a
            if any(_norm(g) in _norm(ih) for g in grup_adlari if g):
                o["grup"] += a
        kt = (KARSI_TARAF_SABIT.get(_norm(tur)) or (KARSI_TARAF_SABIT["TPP"] if _pp_mu(tur) else None)
              or (f"{ih} (banka)" if _katilim_mu(tur) and ih else "raporda yok, ölçülemedi"))
        o["karsi_taraf"][kt] = o["karsi_taraf"].get(kt, 0.0) + a
    for f, o in out.items():
        o["toplam"] = round(o["toplam"], 2)
        o["tur"] = {k: round(v, 2) for k, v in sorted(o["tur"].items(), key=lambda kv: -kv[1])}
        o["sinif"] = {k: round(v, 2) for k, v in sorted(o["sinif"].items(), key=lambda kv: -kv[1])}
        eb = max(o["teminat"].items(), key=lambda kv: kv[1]) if o["teminat"] else None
        o["en_buyuk"] = (eb[0], round(eb[1], 2)) if eb else None
        o["hazine_disi"] = round(o["toplam"] - o["sinif"].get("Hazine", 0.0), 2)
        o["ihracci"] = [(k, round(v, 2)) for k, v in sorted(o["ihracci"].items(), key=lambda kv: -kv[1])[:3]]
        o["grup"] = round(o["grup"], 2)
        o["karsi_taraf"] = {k: round(v, 2) for k, v in sorted(o["karsi_taraf"].items(), key=lambda kv: -kv[1])}
        del o["teminat"]
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


# ---------------------------------------------------------------- hisse katmanı (68 numaralı not, 15 Eylül 2026)
KATILIM_ORANI = 0.20        # varsayım (kullanıcı onayı bekliyor): günlük hacmin bu payı fiyatı bozmadan alınabilir
CIKIS_UYARI_GUN = 5.0       # varsayım
CIKIS_AYKIRI_GUN = 20.0     # varsayım
HACIM_SEANS = 20            # ortanca günlük hacim penceresi


def hisse_fiyat_yukle(arsiv, seans=HACIM_SEANS, son_n=2):
    """arsiv/hisse_YYYY-MM.csv.gz (son son_n dosya): kod -> dict(tarih, kapanis (ham, TL), hacim_ortanca (son `seans` seansın TL hacmi ortancası),
    seans). Ham kapanış kullanılır: nominal pay adedi × bugünkü fiyat = pozisyon değeri; düzeltilmiş kapanış sermaye artırımlarını taşır."""
    seri = {}
    for f in sorted(glob.glob(os.path.join(arsiv or "", "hisse_20??-??.csv.gz")))[-son_n:]:
        with gzip.open(f, "rt", encoding="utf-8", newline="") as h:
            for r in csv.DictReader(h):
                try:
                    k = float(r.get("kapanisHam") or 0); v = float(r.get("hacim") or 0)
                except ValueError:
                    continue
                if k > 0:
                    seri.setdefault(r["hisse"], []).append((r["tarih"][:10], k, v))
    out = {}
    for kod, L in seri.items():
        L.sort()
        son = L[-seans:]
        hac = sorted(v for _, _, v in son if v > 0)
        out[kod] = dict(tarih=L[-1][0], kapanis=L[-1][1], hacim_ortanca=(hac[len(hac) // 2] if hac else None), seans=len(son))
    return out


def cikis_gunu(deger, hacim_ortanca, katilim=KATILIM_ORANI):
    """Pozisyonun çıkış süresi, gün: değer / (ortanca günlük hacim × katılım oranı); hacim yoksa None (ölçülemedi, sıfır değil)."""
    if not hacim_ortanca or hacim_ortanca <= 0 or deger is None:
        return None
    return deger / (hacim_ortanca * katilim)


AKIS_UYARI_ORAN = 0.10        # 72 numaralı not: TEFAS büyüklüğü portföy günündeki büyüklükten bu orandan fazla değiştiyse "varsayım zayıf" (varsayım)
AKIS_OLCULEMEDI_ORAN = 0.25   # bu oranın üstünde yoğunlaşma ve grup payı kapı için "ölçülemedi"; ham rapor ağırlığı yine yazılır (varsayım)
ARTIK_ORAN = 0.10             # M71: rapor satır toplamı / portföy günü TEFAS büyüklüğü bu orandan fazla sapıyorsa artık açıktır, sayılar geçicidir


def akis_durumu(oran):
    if oran is None:
        return "ölçülemedi"
    a = abs(oran)
    return "ölçülemedi (akış)" if a > AKIS_OLCULEMEDI_ORAN else "varsayım zayıf" if a > AKIS_UYARI_ORAN else "tam"


def yeniden_degerle(satirlar, fonlar, fiyat, buyukluk=None, n=5, buyukluk_gun=None):
    """68 numaralı not, bölüm 3: rapor günü nominal pay adedi × bugünkü ham kapanış = bugünkü pozisyon değeri. Güncel ağırlık = değer / fonun
    yalnızca FİYAT değişimiyle taşınmış toplam değeri: rapor toplam değeri (satırların rayiç / ağırlık oranından, FPD) + Σ(bugünkü değer − rapor
    rayici). Alım satım ve akış olmadığı VARSAYIMI açıkça yazılır; TEFAS'ın bugünkü büyüklüğü ayrı verilir ve rapor toplamından AKIS_UYARI_ORAN
    ötesinde sapıyorsa `akis_uyari` işaretlenir (payda olarak kullanılmaz: yeni para raporda yoktur, kullanılsaydı ağırlıklar yapay düşerdi).
    Fiyatı olmayan satır rapor ağırlığını korur ve fiyatsız paya girer. Yalnızca hisse satırları (bistKodu dolu), aynı kodun satırları net toplanır.
    Dönüş: {fon: dict(veri_gunu, fiyat_tarihi, satirlar[...], fiyatsiz_pay, olculen_pay_rapor, olculen_pay_guncel, hisse_sayisi, fiyatli_sayi,
    fpd_rapor, toplam_guncel, buyukluk (TEFAS), akis_orani, akis_uyari)}."""
    son = son_ay_satirlari(satirlar); buyukluk = buyukluk or {}
    top = {}
    for r in son:
        f = r.get("fonKodu"); kod = (r.get("bistKodu") or "").strip()
        if f not in fonlar or not kod:
            continue
        try:
            a = float(r.get("agirlik") or 0); nom = float(r.get("nominal") or 0); ray = float(r.get("rayicDeger") or 0)
        except ValueError:
            continue
        d = top.setdefault(f, dict(veri_gunu=(r.get("veriGunu") or "").strip()[:10] or (_ay_sonu(r.get("raporTarihi") or "").isoformat() if len(r.get("raporTarihi") or "") == 7 else None), kod={}, fpd=[]))
        e = d["kod"].setdefault(kod, dict(kod=kod, nominal=0.0, agirlik_rapor=0.0, rayic=0.0))
        e["nominal"] += nom; e["agirlik_rapor"] += a; e["rayic"] += ray
        if a > 0.05 and ray > 0:
            d["fpd"].append(ray / a * 100.0)
    out = {}
    for f, d in top.items():
        fpd = sorted(d["fpd"])[len(d["fpd"]) // 2] if d["fpd"] else None
        b = float(buyukluk.get(f) or 0)
        L, fiyatsiz, tarih, fark = [], 0.0, None, 0.0
        for e in d["kod"].values():
            p = fiyat.get(e["kod"])
            if p and e["nominal"] > 0:
                deger = e["nominal"] * p["kapanis"]
                e.update(fiyat=p["kapanis"], fiyat_tarihi=p["tarih"], deger=deger, hacim_ortanca=p.get("hacim_ortanca"), cikis_gun=cikis_gunu(deger, p.get("hacim_ortanca")), fiyatsiz=False)
                fark += deger - e["rayic"]; tarih = max(tarih or "", p["tarih"])
            else:
                e.update(fiyat=None, fiyat_tarihi=None, deger=None, hacim_ortanca=None, cikis_gun=None, agirlik_guncel=None, fiyatsiz=True)
                fiyatsiz += max(e["agirlik_rapor"], 0.0)
            L.append(e)
        toplam = (fpd + fark) if fpd else None
        olc_r, olc_g = 0.0, 0.0
        for e in L:
            if not e["fiyatsiz"]:
                e["agirlik_guncel"] = round(e["deger"] / toplam * 100.0, 2) if toplam else None
                olc_r += e["agirlik_rapor"]; olc_g += (e["agirlik_guncel"] or 0.0)
            e["agirlik_rapor"] = round(e["agirlik_rapor"], 2)
        L.sort(key=lambda e: -(e["agirlik_guncel"] if e["agirlik_guncel"] is not None else e["agirlik_rapor"]))
        # 72 numaralı not: akış = TEFAS bugün / TEFAS portföy günü (rapor toplamına değil; rapor toplamı ile TEFAS'ın farkı ayrı bir artıktır, M71)
        bg = float((buyukluk_gun or {}).get(f) or 0)
        akis = (b / bg - 1.0) if (bg > 0 and b > 0) else ((b / fpd - 1.0) if (fpd and b > 0) else None)
        artik = (fpd / bg) if (fpd and bg > 0) else None
        out[f] = dict(veri_gunu=d["veri_gunu"], fiyat_tarihi=tarih, satirlar=L, fiyatsiz_pay=round(fiyatsiz, 2), olculen_pay_rapor=round(olc_r, 2),
                      olculen_pay_guncel=round(olc_g, 2), hisse_sayisi=len(L), fiyatli_sayi=sum(1 for e in L if not e["fiyatsiz"]),
                      fpd_rapor=fpd, toplam_guncel=toplam, buyukluk=b or None, buyukluk_gun=bg or None, akis_orani=akis, akis_durumu=akis_durumu(akis),
                      akis_uyari=(akis is not None and abs(akis) > AKIS_UYARI_ORAN), artik_orani=artik, artik_acik=(artik is not None and abs(artik - 1.0) > ARTIK_ORAN))
    return out


def temel_yukle(yol):
    """veri/temel_veri.csv (temel_cek.py): {bistKodu: dict(...sayılar float ya da None...)}."""
    if not yol or not os.path.exists(yol):
        return {}
    out = {}
    for r in csv.DictReader(open(yol, encoding="utf-8")):
        d = {}
        for k, v in r.items():
            if k in ("bistKodu", "paySayisiKaynak", "donem", "grup", "kaynak", "olcumTarihi"):
                d[k] = v
            else:
                try:
                    d[k] = float(v) if v not in ("", None) else None
                except ValueError:
                    d[k] = None
        out[r["bistKodu"]] = d
    return out


def temel_oranlar(t, kapanis):
    """68 numaralı not, bölüm 4: PD/DD, F/K, net borç/FAVÖK, özkaynak kârlılığı, cari oran. Negatif özkaynak, negatif kâr ve sıfır FAVÖK
    'anlamsız'; veri yoksa 'ölçülemedi' (None). Dönüş: dict(pd_dd, fk, netborc_favok, okk, cari, piyasa_degeri, donem, not)."""
    if not t or kapanis is None:
        return dict(pd_dd=None, fk=None, netborc_favok=None, okk=None, cari=None, piyasa_degeri=None, donem=None, not_="ölçülemedi (temel veri yok)")
    ps, oz, nk, nb, fv, dv, kv = (t.get(k) for k in ("paySayisi", "ozkaynak", "netKar4C", "netBorc", "favok4C", "donenVarlik", "kvYukumluluk"))
    pd_ = ps * kapanis if ps else None
    if (t.get("grup") or "") != "XI_29" and t.get("grup"):
        # 72 numaralı not: banka, faktoring ve sigorta bilançosunda net borç ve cari oran anlamsızdır (borç hammaddedir); boş değil "anlamsız"
        def oran2(pay, payda, anlamsiz):
            if pay is None or payda is None:
                return None
            return "anlamsız" if anlamsiz(payda) else pay / payda
        return dict(piyasa_degeri=pd_, pd_dd=oran2(pd_, oz, lambda x: x <= 0), fk=oran2(pd_, nk, lambda x: x <= 0),
                    netborc_favok="anlamsız (finansal kuruluş bilançosu)", cari="anlamsız (finansal kuruluş bilançosu)",
                    okk=oran2(nk, oz, lambda x: x <= 0), donem=t.get("donem"), not_=(t.get("kaynak") or ""))
    def oran(pay, payda, anlamsiz):
        if pay is None or payda is None:
            return None
        if anlamsiz(payda):
            return "anlamsız"
        return pay / payda
    return dict(piyasa_degeri=pd_, pd_dd=oran(pd_, oz, lambda x: x <= 0), fk=oran(pd_, nk, lambda x: x <= 0), netborc_favok=oran(nb, fv, lambda x: x <= 0),
                okk=oran(nk, oz, lambda x: x <= 0), cari=oran(dv, kv, lambda x: x <= 0), donem=t.get("donem"), not_=(t.get("kaynak") or ""))


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
