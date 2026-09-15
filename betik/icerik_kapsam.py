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
        o = out.setdefault(f, dict(kesin=0.0, ust_sinir=0.0, kalemler={}, adsiz_satir=0, veri_gunu=(r.get("veriGunu") or "").strip()[:10] or None))
        ih = (r.get("ihracci") or "").strip()
        if ih:
            if eslesir(ih):
                o["kesin"] += a; o["ust_sinir"] += a
                o["kalemler"][ih] = o["kalemler"].get(ih, 0.0) + a
        else:
            o["adsiz_satir"] += 1
            if eslesir(r.get("kiymetAdiHam") or ""):
                o["ust_sinir"] += a
                o["kalemler"]["(ham) " + (r.get("kiymetAdiHam") or "")[:30]] = o["kalemler"].get("(ham) " + (r.get("kiymetAdiHam") or "")[:30], 0.0) + a
    for f, o in out.items():
        o["kesin"] = round(o["kesin"], 2); o["ust_sinir"] = round(o["ust_sinir"], 2)
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
