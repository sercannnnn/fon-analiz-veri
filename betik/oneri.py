#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Öneri motoru ve öneri sicili (12 Eylül 2026 kural metni: kural 1, 14, 18, bölüm 6 ve 8).

Kural 1: sistem ölçer, karşılaştırır ve gerekçeli bir emir önerisi yazar; kararı kullanıcı verir. Her öneri dört şeyi taşır:
geçilen ve geçilmeyen kapılar, sıralama ölçüsü, haber ve kaynağı, verinin tarihi. Sıralama tek ölçüyledir (risk başına
getiri), bileşik puan yoktur. Ölçüm öneri üretmiyorsa "bugün öneri yoktur" yazılır.
Kural 14: aday listesi emir değildir; öneri süreklilik şartından (GEREKLI_SEANS ardışık gün kapısı açık) sonra yazılır;
bilinemeyen kapı geçilmemiş sayılır.
Kural 18: her öneri sicile yazılır (tarih, kod, yön, tutar, gerekçe, ölçüm tarihi, sıralama ölçüsü, uygulandı mı); yirmi
seans sonra sonucu ölçülür; ayda bir raporlanır. Sicil üretilmiyorsa öneri rejimi durur.
Bölüm 6: agresif dilim sermayenin %10'u, tek fonda %5 (kullanıcı kararı 12 Eylül 2026, kademesiz); "yeni" etiketi; C1 ve C5
askıya alma her öneride açıkça yazılır; kendi alımıyla fiyat yapan fon (20 seansta pay adedi > %1.000) yarı boyutla.

Gizlilik: sicil ve aday geçmişi portföy bilgisidir, açık depoya yazılmaz (03 Veri altında durur).
"""
import json, os, re
from datetime import date, datetime, timedelta, timezone

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SICIL_YOL = os.path.join(KOK, "03 Veri", "oneri_sicili.json")
ADAY_YOL = os.path.join(KOK, "03 Veri", "aday_gecmisi.json")
GEREKLI_SEANS = 3          # süreklilik şartı: parlayan_fon.GEREKLI_SEANS ile aynı
SONUC_SEANS = 20           # kural 18: öneri sonucu yirmi seans sonra ölçülür
UYGULAMA_GUN = 5           # emir defterinde öneri tarihinden en çok bu kadar gün sonra gerçekleşen aynı yönlü emir "uygulandı" sayılır


def _oku(yol, bos):
    if os.path.exists(yol):
        return json.load(open(yol, encoding="utf-8"))
    return bos


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    json.dump(veri, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- durum deposu (M28, 12 Eylül 2026)
# Süreklilik sayacı ve sicil DURUMDUR; nerede tutulduğu koda değil çağırana aittir. Bulut kabı her sabah sıfırdan kurulur ve
# 03 Veri klasörü orada yoktur: dosya yoluna bağlı sayaç her gün 1 döner, "süreklilik 1/3, öneri yazılmadı" kurala uygun görünür ve
# öneri rejimi hiç çalışmamış olur. Bu yüzden okuma ve yazma bir arayüzün arkasındadır: Mac dosyayla (DosyaDeposu), bulut emir
# defteriyle (BellekDeposu: görev defterin `adaylar` ve `sicil` koleksiyonlarını okuyup verir, koşu sonunda `belgeler()` ile geri yazar)
# aynı kodu koşar. Sicil ve aday geçmişi portföy bilgisidir, açık depoya konmaz.
class DosyaDeposu:
    """Mac: 03 Veri/aday_gecmisi.json ve 03 Veri/oneri_sicili.json."""
    def __init__(self, aday_yol=None, sicil_yol=None):
        self.aday_yol = aday_yol or ADAY_YOL; self.sicil_yol = sicil_yol or SICIL_YOL

    def aday_oku(self): return _oku(self.aday_yol, {})
    def aday_yaz(self, g): _yaz(self.aday_yol, g)
    def sicil_oku(self): return _oku(self.sicil_yol, [])
    def sicil_yaz(self, s): _yaz(self.sicil_yol, s)
    def sicil_var_mi(self): return os.path.exists(self.sicil_yol)


class BellekDeposu:
    """Bulut: durum çağıranın verdiği sözlüklerde tutulur. aday: {tarih: [kodlar]} (defterin `adaylar` koleksiyonu, belge kimliği
    tarih); sicil: kayıt listesi (defterin `sicil` koleksiyonu, belge kimliği YYYYAAGG-KOD). Koşu sonunda `belgeler()` deftere
    yazılacak belgeleri verir; görev bunları koleksiyonlara yazar. Kap silinse de durum defterde kalır."""
    def __init__(self, aday=None, sicil=None):
        self.aday = dict(aday or {}); self.sicil = list(sicil or []); self.degisen_aday, self.degisen_sicil = set(), set()

    def aday_oku(self): return dict(self.aday)
    def aday_yaz(self, g):
        self.degisen_aday |= {t for t in g if g[t] != self.aday.get(t)}; self.aday = dict(g)
    def sicil_oku(self): return list(self.sicil)
    def sicil_yaz(self, s):
        eski = {x["id"]: x for x in self.sicil}
        self.degisen_sicil |= {x["id"] for x in s if eski.get(x["id"]) != x}; self.sicil = list(s)
    def sicil_var_mi(self): return bool(self.sicil)

    def belgeler(self, yalniz_degisen=True):
        """(adaylar belgeleri, sicil belgeleri): {kimlik: belge}. Defterin belge kimliği biçimi: adaylar için tarih, sicil için kaydın id'si."""
        a = {t: dict(tarih=t, kodlar=k) for t, k in self.aday.items() if not yalniz_degisen or t in self.degisen_aday}
        s = {x["id"]: dict(x) for x in self.sicil if not yalniz_degisen or x["id"] in self.degisen_sicil}
        return a, s

    @classmethod
    def defterden(cls, aday_belgeleri, sicil_belgeleri):
        """Defter koleksiyonlarından kur: aday_belgeleri {tarih: {"tarih","kodlar"}} ya da liste; sicil_belgeleri {id: kayıt} ya da liste."""
        ab = aday_belgeleri.values() if isinstance(aday_belgeleri, dict) else (aday_belgeleri or [])
        sb = sicil_belgeleri.values() if isinstance(sicil_belgeleri, dict) else (sicil_belgeleri or [])
        return cls(aday={b["tarih"]: list(b.get("kodlar") or []) for b in ab}, sicil=sorted(sb, key=lambda x: (x.get("tarih", ""), x.get("id", ""))))


def _depo(depo, yol=None, tur="sicil"):
    """Geriye uyumluluk: depo verilmemişse dosya deposu; yol verilmişse o yol (eski sınamalar)."""
    if depo is not None:
        return depo
    return DosyaDeposu(aday_yol=yol if tur == "aday" else None, sicil_yol=yol if tur == "sicil" else None)


def _tl(x):
    return f"{x:,.0f}".replace(",", ".") + " TL"


def _yuzde(x, hane=1):
    return ("-" if x < 0 else "") + "%" + f"{abs(x) * 100:,.{hane}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- defter dışa aktarımı sözleşmesi (Chat 19 ve 21, 13 Eylül 2026)
# Akşam teyit görevi defteri okuyup Mac'e tek dosya yazar: 03 Veri/defter_disa_aktarim.json. Alanlar: olcumZamani (ISO 8601, saat
# dilimli), pozisyonlar (defterin pozisyon koleksiyonu, {kimlik: kayıt}), nakit (defterin nakit koleksiyonu, liste). Tazelik yalnızca
# olcumZamani alanından ölçülür; bir iş gününden eski ölçümle üretilen ağırlık "doğrulanmadı" etiketi alır. Dosya portföy bilgisidir.
DISA_AKTARIM_ALANLARI = ("olcumZamani", "pozisyonlar", "nakit")
TAZELIK_ESIK_IS_GUNU = 1


GELECEK_TOLERANS_DK = 15    # kap ile Mac arasındaki saat farkı payı (M30): damga şimdiden en çok bu kadar ileri olabilir, adı konmuş tolerans


def disa_aktarim_dogrula(belge, bugun=None, simdi=None):
    """Dışa aktarım belgesinin biçimini sınar. Dönüş: hata listesi (boşsa geçerli). Gelecek tarihli olcumZamani da hatadır (M30)."""
    h = []
    if not isinstance(belge, dict):
        return ["belge sözlük değil"]
    for a in DISA_AKTARIM_ALANLARI:
        if a not in belge:
            h.append(f"{a} alanı yok")
    t = tazelik(belge.get("olcumZamani"), bugun=bugun, simdi=simdi)
    if t["durum"] == "gecersiz":
        h.append("olcumZamani ISO 8601 değil")
    elif t["durum"] == "saat_dilimsiz":
        h.append("olcumZamani saat dilimi taşımıyor")
    elif t["durum"] == "gelecek":
        h.append(f"olcumZamani gelecek tarihli ({t['sebep']})")
    poz = belge.get("pozisyonlar")
    if not isinstance(poz, dict):
        h.append("pozisyonlar sözlük değil ({kimlik: kayıt})")
    else:
        for k, v in poz.items():
            if not isinstance(v, dict) or not v.get("kod") or "deger" not in v:
                h.append(f"pozisyon {k}: kod ya da deger yok")
    if not isinstance(belge.get("nakit"), list):
        h.append("nakit liste değil")
    return h


def _is_gunu_farki(bas, bit):
    n, g = 0, bas
    while g < bit:
        g = date.fromordinal(g.toordinal() + 1)
        if g.weekday() < 5:
            n += 1
    return n


def tazelik(olcum_zamani, bugun=None, esik=TAZELIK_ESIK_IS_GUNU, simdi=None):
    """olcumZamani'ndan bugüne iş günü. Dönüş: dict(is_gunu, eski, durum, sebep, tarih); durum: taze | eski | saat_dilimsiz |
    gelecek | gecersiz. Doğrulanamayan damga en iyi durumda değil en kötü durumda sayılır (M30): saat dilimsiz, gelecek tarihli
    (GELECEK_TOLERANS_DK ötesinde) ya da okunamayan damgada eski=True. Klasör tarihinden gelen çıplak `date` de kabul edilir.
    Kopyalama zamanı değil, ölçüm zamanı esastır."""
    bugun = bugun or date.today()
    if isinstance(olcum_zamani, date) and not isinstance(olcum_zamani, datetime):
        t = olcum_zamani
    else:
        try:
            dt = datetime.fromisoformat(str(olcum_zamani))
        except (TypeError, ValueError):
            return dict(is_gunu=None, eski=True, durum="gecersiz", sebep="olcumZamani ISO 8601 değil", tarih=None)
        if dt.tzinfo is None:
            return dict(is_gunu=None, eski=True, durum="saat_dilimsiz", sebep="olcumZamani saat dilimi taşımıyor", tarih=dt.date())
        simdi_ = simdi or datetime.now(timezone.utc)
        if simdi_.tzinfo is None:
            simdi_ = simdi_.replace(tzinfo=timezone.utc)
        if dt - simdi_ > timedelta(minutes=GELECEK_TOLERANS_DK):
            ileri = -_is_gunu_farki(bugun, dt.date()) if dt.date() > bugun else 0
            return dict(is_gunu=ileri, eski=True, durum="gelecek", sebep=f"damga şimdiden {int((dt - simdi_).total_seconds() // 60)} dakika ileride, tolerans {GELECEK_TOLERANS_DK} dakika", tarih=dt.date())
        t = dt.date()
    if t > bugun:
        return dict(is_gunu=-_is_gunu_farki(bugun, t), eski=True, durum="gelecek", sebep="ölçüm tarihi bugünden ileri", tarih=t)
    n = _is_gunu_farki(t, bugun)
    return dict(is_gunu=n, eski=n > esik, durum=("eski" if n > esik else "taze"), sebep=None, tarih=t)


# ---------------------------------------------------------------- sermaye (M27, 12 Eylül 2026)
def acik_pozisyonlar(pozisyonlar):
    """Kapanmış pozisyon sermayeye katılmaz (M27): `durum` alanı KAPANDI olan ya da adedi sıfır olan kayıt çıkarılır.
    Satılan pozisyonun karşılığı nakit kaleminde zaten sayılır; canlı bırakılırsa aynı para iki kez toplanır ve bütün ağırlık
    oranları küçük görünür (12 Eylül: en ağır fon %38 yerine %52,7 çıktı). Girdi sözlük (kimlik -> kayıt) ya da liste olabilir."""
    L = list(pozisyonlar.values()) if isinstance(pozisyonlar, dict) else list(pozisyonlar or [])
    acik = []
    for v in L:
        if str(v.get("durum") or "").upper() == "KAPANDI":
            continue
        if v.get("adet") is not None and float(v.get("adet") or 0) == 0:
            continue
        acik.append(v)
    return acik


def sermaye_hesapla(pozisyonlar, nakit):
    """Sermaye = açık pozisyonların değeri + nakit (madde 5). Dönüş: dict(sermaye, pozisyon, nakit, acik, kapanan, kodlar).
    kodlar: kod -> açık değer toplamı (aynı fon birden çok kurumda durabilir)."""
    L = list(pozisyonlar.values()) if isinstance(pozisyonlar, dict) else list(pozisyonlar or [])
    acik = acik_pozisyonlar(L)
    poz = sum(float(v.get("deger") or 0) for v in acik)
    kodlar = {}
    for v in acik:
        if v.get("kod"):
            kodlar[v["kod"]] = kodlar.get(v["kod"], 0) + float(v.get("deger") or 0)
    return dict(sermaye=poz + float(nakit or 0), pozisyon=poz, nakit=float(nakit or 0), acik=len(acik), kapanan=len(L) - len(acik), kodlar=kodlar)


# ---------------------------------------------------------------- süreklilik
def ardisik_guncelle(tarih, acik_kodlar, yol=None, depo=None):
    """Kapısı açık adayların gün gün kaydı; dönüş: kod -> bugün dahil ardışık açık gün sayısı. Aynı gün iki kez çağrılırsa
    günün kaydı üzerine yazılır. Durum `depo` üzerinden okunur ve yazılır (M28). Kaynak: ölçüm."""
    d = _depo(depo, yol, "aday")
    g = d.aday_oku()
    g[tarih] = sorted(acik_kodlar)
    gunler = sorted(g)[-60:]
    g = {t: g[t] for t in gunler}
    d.aday_yaz(g)
    say = {}
    for k in acik_kodlar:
        n = 0
        for t in reversed(gunler):
            if k in g[t]:
                n += 1
            else:
                break
        say[k] = n
    return say


# ---------------------------------------------------------------- öneri
def _gerekce(r, s_askida, haber_notu, veri_tarihi, sira_olcusu):
    gecilen = [x for x in ("C1", "C2", "C3", "C4", "C5", "C6", "G1", "G2", "G3", "G4", "G5a", "G5b") if x not in s_askida]
    parca = [f"kapılar: hepsi geçildi" + (f"; askıda: {', '.join(s_askida)} (agresif dilim, kural 14 istisnası)" if s_askida else ""),
             f"sıralama ölçüsü: risk başına getiri {str(round(sira_olcusu, 2)).replace('.', ',')} (30 seans yıllık hız / 60 seans oynaklık)",
             f"haber: {haber_notu}",
             f"veri tarihi: {veri_tarihi}"]
    return "; ".join(parca)


YENI_FON_HAFTA_GUN = 7     # bölüm 4: haftada en çok bir yeni fona girilir
IKINCI_DILIM_SEANS = 20    # bölüm 4: ikinci dilim kapılar dört hafta açık kaldıktan sonra
ILK_DILIM = 0.05           # yeni fona ilk dilim: sermayenin %5'i
FON_USTU = 0.10            # bir fonda toplam: sermayenin %10'u (mevcut pozisyonun artırılması da bu sınıra tabidir)


def son_yeni_fon_onerisi(tarih, gun=YENI_FON_HAFTA_GUN, yol=None, depo=None):
    """Son `gun` gün içinde verilen yeni fon (portföyde olmayan) önerisi var mı; varsa (tarih, kod)."""
    t0 = datetime.strptime(tarih, "%Y-%m-%d").date()
    for x in reversed(_depo(depo, yol).sicil_oku()):
        if x.get("yeniFon") and 0 < (t0 - datetime.strptime(x["tarih"], "%Y-%m-%d").date()).days <= gun:
            return x["tarih"], x["kod"]
    return None


def oneri_uret(ana, agresif, tarih, veri_tarihi, sermaye, agresif_mevcut, haber_notu, ardisik, serbest_nakit=None, pozisyonlar=None, sicil_yol=None, depo=None):
    """ana, agresif: parlayan_fon çıktıları (DataFrame ya da kayıt listesi). sermaye: pozisyon + nakit, TL. agresif_mevcut: dilimi
    'agresif' olan pozisyonların değeri. serbest_nakit: serbest nakit ile karşılanmış satışların toplamı (None: ölçülemedi).
    pozisyonlar: kod -> elde tutulan değer. Dönüş: öneri listesi ve öneriye dönüşmeyenlerin notları.

    Boyutlandırma (12 Eylül 2026 kural metni, bölüm 4): her öneri tutar taşır, tutar ölçülemiyorsa öneri yazılmaz; yeni fona ilk
    dilim sermayenin %5'i, haftada en çok bir yeni fon; mevcut pozisyon ancak kapılar 20 seans açık kaldıysa artırılır ve fonun toplamı
    %10'u aşamaz; önerilen tutar serbest nakit ile karşılanmış satışların toplamını aşamaz, ikisi de yoksa öneri yazılmaz.
    Agresif dilim (bölüm 6): toplam sermayenin %10'u eksi dilimde duran, tek fon %5, büyüme kaynağı yarıya; nakit kısıtı aynen."""
    def kayitlar(df):
        if df is None:
            return []
        return df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    pozisyonlar = pozisyonlar or {}
    oneriler, notlar = [], []
    if not sermaye:
        return [], ["sermaye ölçülemedi (pozisyon dosyası yok); öneri yazılmadı (bölüm 4: tutar zorunlu)"]
    if serbest_nakit is None:
        return [], ["serbest nakit ölçülemedi (nakit kaydı yok); öneri yazılmadı (bölüm 4: nakit kısıtı)"]
    nakit = float(serbest_nakit)
    if nakit <= 0:
        return [], [f"serbest nakit {_tl(nakit)}; öneri yazılmadı (bölüm 4: nakit kısıtı)"]
    yeni_verildi = son_yeni_fon_onerisi(tarih, yol=sicil_yol, depo=depo)
    yeni_bu_koşu = False
    ortak = dict(haber=haber_notu, veri_tarihi=veri_tarihi)

    # ana portföy
    for r in sorted([x for x in kayitlar(ana) if x.get("kapi_durumu") == "acik"], key=lambda x: -(x.get("getori") or 0)):
        kod = r["fonKodu"]; n = ardisik.get(kod, 0)
        if n < GEREKLI_SEANS:
            notlar.append(f"{kod} kapısı açık, süreklilik {n}/{GEREKLI_SEANS} gün; öneri yazılmadı (kural 14)"); continue
        mevcut = float(pozisyonlar.get(kod, 0) or 0)
        if mevcut > 0:
            if n < IKINCI_DILIM_SEANS:
                notlar.append(f"{kod} portföyde; ikinci dilim için kapılar {IKINCI_DILIM_SEANS} seans açık kalmalı, bugün {n}; öneri yazılmadı (bölüm 4)"); continue
            ust = sermaye * FON_USTU - mevcut; tur = "mevcut pozisyonun artırılması"
            if ust <= 0:
                notlar.append(f"{kod} portföyde ve fonun toplamı sermayenin %10'una ulaşmış ({_tl(mevcut)}); öneri yazılmadı (bölüm 4)"); continue
        else:
            if yeni_verildi:
                notlar.append(f"{kod} yeni fon; bu hafta {yeni_verildi[1]} için {yeni_verildi[0]} tarihinde öneri verildi, haftada bir yeni fon (bölüm 4)"); continue
            if yeni_bu_koşu:
                notlar.append(f"{kod} yeni fon; bugün başka bir yeni fon önerildi, haftada bir yeni fon (bölüm 4)"); continue
            ust = sermaye * ILK_DILIM; tur = "yeni fona ilk dilim"
        tutar = round(min(ust, nakit), -3)
        if tutar <= 0:
            notlar.append(f"{kod} için nakit kalmadı; öneri yazılmadı (bölüm 4: nakit kısıtı)"); continue
        nakit -= tutar
        if mevcut == 0:
            yeni_bu_koşu = True
        oneriler.append(dict(kod=kod, ad=r.get("fonAd"), yon="AL", dilim="ana", etiket="", tutar=tutar, yeni_fon=(mevcut == 0),
                             tutar_notu=f"{tur}: sermayenin {'%5' if mevcut == 0 else '%10 tavanına kadar'}'i, sermaye {_tl(sermaye)}, serbest nakit sınırı uygulandı",
                             sira_olcusu=r.get("getori"), ardisik=n, askida=[], gecilen=_gecilen([]), **ortak,
                             gerekce=_gerekce(r, [], haber_notu, veri_tarihi, r.get("getori") or 0)))

    # agresif dilim
    kalan = max(0.0, sermaye * 0.10 - (agresif_mevcut or 0)); tek = sermaye * 0.05
    for r in sorted([x for x in kayitlar(agresif) if x.get("kapi_durumu") == "acik"], key=lambda x: -(x.get("sira_olcusu") or 0)):
        kod = r["fonKodu"]; n = ardisik.get(kod, 0)
        if n < GEREKLI_SEANS:
            notlar.append(f"{kod} (yeni) kapısı açık, süreklilik {n}/{GEREKLI_SEANS} gün; öneri yazılmadı (kural 14)"); continue
        if kalan <= 0:
            notlar.append(f"{kod} (yeni) süreklilik sağlandı ama agresif dilim dolu (sermayenin %10'u); öneri yazılmadı"); continue
        ust = min(tek, kalan)
        buyume = bool(r.get("buyume_kaynagi"))
        if buyume:
            ust = ust / 2
        tutar = round(min(ust, nakit), -3)
        if tutar <= 0:
            notlar.append(f"{kod} (yeni) için nakit kalmadı; öneri yazılmadı (bölüm 4: nakit kısıtı)"); continue
        kalan -= tutar; nakit -= tutar
        askida = [x for x in str(r.get("askida") or "").split(" | ") if x]
        g = _gerekce(r, [a.split()[0] for a in askida], haber_notu, veri_tarihi, r.get("sira_olcusu") or 0)
        g += (f"; 20 seanslık net giriş oranı {_yuzde(r['net_giris20'])}" if r.get("net_giris20") is not None and r.get("net_giris20") == r.get("net_giris20") else "; net giriş oranı ölçülemedi")
        g += f"; {r.get('kurucu_gecmis') or 'kurucu geçmişi ölçülemedi'}"
        if buyume:
            g += f"; büyüme kaynağı: 20 seansta pay adedi {_yuzde(r['dpay20'], 0)} arttı, fon kendi alımıyla fiyat yapıyor olabilir, boyut yarıya indirildi"
        oneriler.append(dict(kod=kod, ad=r.get("fonAd"), yon="AL", dilim="agresif", etiket="yeni", tutar=tutar, yeni_fon=True,
                             tutar_notu=f"agresif dilim: sermayenin %10'u toplam, tek fonda %5, dilimde duran {_tl(agresif_mevcut or 0)}; sermaye {_tl(sermaye)}; serbest nakit sınırı uygulandı",
                             sira_olcusu=r.get("sira_olcusu"), ardisik=n, askida=askida, gecilen=_gecilen([a.split()[0] for a in askida]), **ortak, gerekce=g))
    return oneriler, notlar


def _gecilen(askida):
    return [x for x in ("C1", "C2", "C3", "C4", "C5", "C6", "G1", "G2", "G3", "G4", "G5a", "G5b") if x not in askida]


def oneri_json(oneriler, tarih, yol=None, depo=None):
    """Brifing JSON'unun 12 Eylül 2026'da eklenen iki anahtarı: `oneri` (liste) ve `sicil` (nesne). Mevcut on dört anahtar değişmez."""
    o = [dict(kod=x["kod"], ad=x.get("ad"), yon=x["yon"], tutar=x.get("tutar"), dilim=x.get("dilim"), etiket=x.get("etiket", ""),
              gecilen=x.get("gecilen", []), askida=x.get("askida", []), sira_olcusu=x.get("sira_olcusu"), haber=x.get("haber"),
              veri_tarihi=x.get("veri_tarihi"), gerekce=x.get("gerekce"), tutar_notu=x.get("tutar_notu")) for x in oneriler]
    d = _depo(depo, yol)
    oz = sicil_ozeti(tarih[:7], depo=d)
    g = oz["uygulanan_getiri"]
    isabet = (f"uygulanan {oz['uygulanan']} önerinin 20 seans ortalama getirisi {_yuzde(g[0])} ({g[1]} ölçüm); {kiyas_cumlesi(oz)}" if g[0] is not None else None)
    return o, dict(ay=oz["ay"], verilen=oz["verilen"], uygulanan=oz["uygulanan"], bilinmeyen=oz["bilinmeyen"], isabet=isabet, metin=sicil_satiri(tarih, depo=d))


# ---------------------------------------------------------------- park fonu (39 numaralı not, madde 1)
PARK_KATEGORILER = ("Para Piyasası", "Kısa Vadeli Borçlanma")   # hisse, serbest, fon sepeti park olamaz
PARK_RISK_ARALIGI = (1, 3)              # künyedeki riskDegeri; sıfır ve boş kabul edilmez (2.033 fonun 1.091'inde bildirilmemiş)
PARK_ASGARI_BUYUKLUK = 5_000_000_000.0  # TL; "görece büyük" için varsayım (Chat 39), adlı sabit, değiştirilebilir
PARK_SEANS = 20                         # sıralama ölçüsü: son 20 seans getirisi
# PARK_GECIKME_SEANS kaldırıldı (60 numaralı not): pencere evrenin son tam gününde biter, tam güne yetişemeyen fon aday değildir (M61)


PARK_MEVCUT_RISK_ESIT_KABUL = False   # kullanıcı kuralı (15 Eylül 2026): mevcut park fonu ancak en az onun kadar kazandıran ve DAHA AZ riskli aday varsa
                                      # değişir; True yapılırsa eşit risk de kabul edilir (risk 1 taban olduğu için eşitlik kabulü kullanıcı kararıdır)


OLAY_PENCERE_GUN = 5   # 78 numaralı not, bölüm 2: olay etki ölçüsü olayın piyasa gününden sonraki beş piyasa günü boyunca her sabah yenilenir


def olay_etkisi(d, kategori, kurucu_map, kurucu, olay_gunu, pencere=OLAY_PENCERE_GUN):
    """Olay etki ölçüsü (78 numaralı not, bölüm 2). d: tarih, fonKodu, fiyat, tedPaySayisi; kategori ve kurucu_map: fon -> ad; olay_gunu: KAP
    yayım günü (piyasa günü D, ISO). Taban TEFAS günü D'den sonraki ilk TEFAS günü (D kapanışı, M73), bitiş taban artı `pencere` TEFAS günü ya da
    son gün. Kurucunun her fonu için getiri, pay adedi değişimi, kategorideki getiri sırası; kategori ortancaları aynı pencerede. İşlev yalnızca
    ölçer; yorum kuralı kural metnindedir (fiyat iyi ve pay adedi kötü kapıyı kapatır, ikisi iyi kapıyı açmaz: kapı devir riskini ölçer)."""
    import pandas as pd
    x = d[d.fiyat > 0][["tarih", "fonKodu", "fiyat", "tedPaySayisi"]].copy(); x["tarih"] = pd.to_datetime(x.tarih)
    D = pd.Timestamp(olay_gunu); sonra = [g for g in sorted(x.tarih.unique()) if g > D]
    if not sonra:
        return dict(olay_gunu=olay_gunu, fonlar=[], olculemedi="olaydan sonra TEFAS günü yok")
    bas = sonra[0]; bit = sonra[min(pencere, len(sonra) - 1)]
    a = x[x.tarih == bas].drop_duplicates("fonKodu").set_index("fonKodu"); b = x[x.tarih == bit].drop_duplicates("fonKodu").set_index("fonKodu")
    ort = a.index.intersection(b.index)
    g = b.loc[ort, "fiyat"] / a.loc[ort, "fiyat"] - 1
    p = (b.loc[ort, "tedPaySayisi"] / a.loc[ort, "tedPaySayisi"] - 1).replace([float("inf"), -float("inf")], float("nan"))
    kat = pd.Series({f: kategori.get(f) for f in ort}, dtype=object)
    out = []
    kur_fon = sorted(f for f in a.index if kurucu_map.get(f) == kurucu)
    for f in kur_fon:
        k = kat.get(f) if f in ort else kategori.get(f); ayni = list(kat[kat == k].index) if k else []
        gk = g.loc[ayni] if ayni else g.iloc[0:0]; pk = p.loc[ayni].dropna() if ayni else p.iloc[0:0]
        if f in ort:
            gf, pf, bit_f = float(g[f]), (None if pd.isna(p[f]) else float(p[f])), None
        else:
            # bitiş günü fonun fiyatı yok (kısmi kapsamlı gün, kural 15): fonun kendi son fiyatlı günü alınır ve yazılır; sıra ortak günde ölçülemez
            xf = x[(x.fonKodu == f) & (x.tarih > bas) & (x.tarih <= bit)].sort_values("tarih")
            if xf.empty:
                out.append(dict(fon=f, kategori=k, getiri=None, pay=None, sira=None, n=len(ayni), kat_getiri=(float(gk.median()) if ayni else None),
                                kat_pay=(float(pk.median()) if len(pk) else None), bit_fon=None)); continue
            son = xf.iloc[-1]; gf = float(son.fiyat / a.loc[f, "fiyat"] - 1)
            pf = (float(son.tedPaySayisi / a.loc[f, "tedPaySayisi"] - 1) if a.loc[f, "tedPaySayisi"] else None); bit_f = son.tarih.date().isoformat()
        out.append(dict(fon=f, kategori=k, getiri=gf, pay=pf, sira=((int((gk > gf).sum()) + 1) if (ayni and f in ort) else None), n=len(ayni),
                        kat_getiri=(float(gk.median()) if ayni else None), kat_pay=(float(pk.median()) if len(pk) else None), bit_fon=bit_f))
    out.sort(key=lambda e: (e["pay"] if e["pay"] is not None else 0.0, e["fon"]))
    try:
        import icerik_kapsam as _ik
        pb, pe = _ik.piyasa_gunu(bas.date().isoformat()), _ik.piyasa_gunu(bit.date().isoformat())
    except Exception:
        pb, pe = None, None
    return dict(olay_gunu=olay_gunu, bas=bas.date().isoformat(), bit=bit.date().isoformat(), piyasa_bas=pb, piyasa_bit=pe,
                gun=sum(1 for g_ in sonra if g_ <= bit) - 1, fonlar=out, olculemedi="")


def olay_satiri(o, kurucu, sebep="", en_fazla=6):
    """Brifing satırı: olay, pencere piyasa günüyle, fon başına getiri / kategori ortancası / sıra ve pay adedi / ortanca; fiyat iyi ve pay adedi
    kötü olan fon kalın. Yalnızca ölçüm; kapının kararı olay listesindedir."""
    def _y(x):
        return "-" if x is None else (("+" if x >= 0 else "-") + f"%{abs(x) * 100:.2f}".replace(".", ","))
    if o.get("olculemedi"):
        return f"Olay etki ölçüsü ({kurucu}, olay {o.get('olay_gunu')}): ölçülemedi ({o['olculemedi']})."
    parca = []
    for e in o["fonlar"][:en_fazla]:
        if e["getiri"] is None:
            parca.append(f"{e['fon']} pencerede fiyatı yok, ölçülemedi"); continue
        kotu = (e["kat_getiri"] is not None and e["getiri"] > e["kat_getiri"] and e["pay"] is not None and e["kat_pay"] is not None and e["pay"] < e["kat_pay"])
        ek = f" (son fiyat {e['bit_fon']}, bitiş günü fiyatsız, sıra ölçülemedi)" if e.get("bit_fon") else ""
        s = (f"{e['fon']} getiri {_y(e['getiri'])} (kategori ortancası {_y(e['kat_getiri'])}, sıra {e['sira']}/{e['n']}), pay adedi {_y(e['pay'])} (ortanca {_y(e['kat_pay'])})"
             if e["sira"] else f"{e['fon']} getiri {_y(e['getiri'])} (kategori ortancası {_y(e['kat_getiri'])}), pay adedi {_y(e['pay'])} (ortanca {_y(e['kat_pay'])}){ek}")
        parca.append(f"**{s}**" if kotu else s)
    kalan = len(o["fonlar"]) - en_fazla
    return (f"Olay etki ölçüsü (78 numaralı not, bölüm 2; yalnızca ölçüm, karar olay listesinde): {kurucu}, olay {o['olay_gunu']}"
            + (f" ({sebep})" if sebep else "") + f", pencere piyasa günü {o['piyasa_bas']} → {o['piyasa_bit']} (TEFAS {o['bas']} → {o['bit']}, {o['gun']}/{OLAY_PENCERE_GUN} gün): "
            + ("; ".join(parca) if parca else "kurucunun fonu evrende yok") + (f"; {kalan} fon daha" if kalan > 0 else "")
            + ". Yorum kuralı: fiyat iyi, pay adedi kötü kapıyı kapatır (kalın); ikisi birlikte iyi kapıyı açmaz, kapı devir riskini ölçer.")


def park_fonu_sec(d, kunye, dislama=(), disla_yol=None, mevcut=None):
    """Park fonu sabit kod değil ölçüttür (39 numaralı not): kategori PARK_KATEGORILER, risk değeri PARK_RISK_ARALIGI içinde (sıfır
    ve boş kabul edilmez), büyüklük PARK_ASGARI_BUYUKLUK üstünde, kimlik arızası / çöküş / kırılma / kesinti / değer kaybı kaydı olan
    fon ve park_disla.txt listesindekiler dışarıda; kalanlar arasında son PARK_SEANS seans getirisi en yüksek olan seçilir, her gün yeniden.
    M61 (58 numaralı not): getiri ORTAK pencerede ölçülür: evrenin son tam kapsamlı günü (kapsam.son_tam_gun) pencerenin sonu, PARK_SEANS
    seans öncesi başıdır; tam güne yetişemeyen fon aday değildir (sebep tam_gun). M60: risk değeri boş olup öbür şartları geçen fonlar
    adıyla `risk_olculemedi` listesinde döner (kural 14: ölçülemeyen geçmiş sayılmaz, ama sessizce de elenmez).
    Kullanıcı kuralı (15 Eylül 2026): `mevcut` (tutulan park fonu) verilirse ölçütün ilk sırası ancak mevcuttan az kazandırmıyor VE daha az
    riskliyse (PARK_MEVCUT_RISK_ESIT_KABUL) seçilir; yoksa mevcut kalır ve fark yazılır.
    d: tarih, fonKodu, fiyat, portfoyBuyukluk çerçevesi (fiyatı sıfır satırlar kapsam ölçümüne girer); kunye: fonKodu, kategori, riskDegeri.
    Dönüş: dict(kod (seçilen), ilk (ölçütün ilk sırası), kategori, risk, buyukluk, getiri20, pencere(bas, bit), aday, sira, adaylar, gerekce,
    elenen{sebep: sayı}, neden{kod: sebep}, risk_olculemedi[list], mevcut{...} ya da None, karar); aday yoksa kod None ve sebep."""
    import pandas as pd
    import kapsam as _kapsam
    elle = set()
    if disla_yol and os.path.exists(disla_yol):
        elle = {s.strip().split()[0] for s in open(disla_yol, encoding="utf-8") if s.strip() and not s.startswith("#")}
    k = kunye[["fonKodu", "kategori", "riskDegeri"]].drop_duplicates("fonKodu").set_index("fonKodu")
    tam = _kapsam.son_tam_gun(d[["tarih", "fonKodu", "fiyat"]])
    d = d[d["fiyat"] > 0].sort_values(["fonKodu", "tarih"])
    if tam is not None:
        d = d[d["tarih"] <= tam]
    gunler = sorted(d["tarih"].unique())
    if len(gunler) <= PARK_SEANS:
        return dict(kod=None, sebep=f"evrende {len(gunler)} seans var, {PARK_SEANS + 1} gerekir", aday=0, elenen={}, neden={}, sira={}, adaylar=[], risk_olculemedi=[], mevcut=None, karar="")
    bit_gun = gunler[-1]; bas_gun = gunler[-1 - PARK_SEANS]
    pencere = (str(bas_gun)[:10], str(bit_gun)[:10])
    try:
        import icerik_kapsam as _ik
        pencere_piyasa = (_ik.piyasa_gunu(pencere[0]), _ik.piyasa_gunu(pencere[1]))   # M73: TEFAS günü bir önceki işlem gününün kapanışıdır
    except Exception:
        pencere_piyasa = (None, None)
    elenen = {"kategori": 0, "risk": 0, "buyukluk": 0, "dislama": 0, "seans": 0, "tam_gun": 0}
    neden = {}      # M57: kod -> eleme sebebi; bütün şartlar sınanır, ilk sebepte durulmaz
    adaylar, risk_olculemedi, olcum = [], [], {}
    for kod, g in d.groupby("fonKodu"):
        kat = k["kategori"].get(kod); risk = k["riskDegeri"].get(kod)
        fiy = dict(zip(g["tarih"], g["fiyat"].astype(float))); b = float(g["portfoyBuyukluk"].iloc[-1] or 0)
        son_f = fiy.get(bit_gun)
        bas_adaylar = [t for t in fiy if t <= bas_gun]
        bas_f = fiy[max(bas_adaylar)] if bas_adaylar else None
        getiri = (son_f / bas_f - 1) if (son_f and bas_f) else None
        olcum[kod] = dict(getiri20=getiri, buyukluk=b, risk=risk)
        seb = []; risk_bos = risk is None or pd.isna(risk)
        if kat not in PARK_KATEGORILER:
            seb.append(f"kategori {kat or 'boş'} park kategorisi değil")
        if risk_bos or not (PARK_RISK_ARALIGI[0] <= float(risk) <= PARK_RISK_ARALIGI[1]):
            seb.append("risk değeri " + ("boş (ölçülemedi)" if risk_bos else str(int(risk))) + f" (ölçüt {PARK_RISK_ARALIGI[0]}-{PARK_RISK_ARALIGI[1]})")
        if kod in dislama or kod in elle:
            seb.append("dışlama listesinde (arıza/çöküş/kırılma/kesinti/değer kaybı ya da park_disla.txt)")
        if son_f is None:
            seb.append(f"tam güne yetişemedi (evrenin son tam günü {pencere[1]}, fonun son fiyatı {str(g['tarih'].iloc[-1])[:10]}; kısmi gün)")
        elif bas_f is None:
            seb.append(f"seans yetersiz ({len(fiy)} seans, pencere başı {pencere[0]} öncesi fiyat yok)")
        if b < PARK_ASGARI_BUYUKLUK:
            seb.append(f"büyüklük {b / 1e9:.2f} milyar TL (taban {PARK_ASGARI_BUYUKLUK / 1e9:.0f} milyar)")
        if seb:
            neden[kod] = "; ".join(seb)
            anahtar = ("kategori" if "kategori" in seb[0] else "risk" if seb[0].startswith("risk") else "dislama" if "dışlama" in seb[0]
                       else "tam_gun" if seb[0].startswith("tam güne") else "seans" if seb[0].startswith("seans") else "buyukluk")
            elenen[anahtar] += 1
            if len(seb) == 1 and risk_bos:      # M60: yalnızca risk hanesi boş; adıyla raporlanır
                risk_olculemedi.append(dict(kod=kod, kategori=kat, buyukluk=b, getiri20=getiri))
            continue
        adaylar.append(dict(kod=kod, kategori=kat, risk=int(risk), buyukluk=b, getiri20=getiri, sonGun=str(g["tarih"].iloc[-1])[:10]))
    risk_olculemedi.sort(key=lambda a: -(a["getiri20"] or -9))
    if not adaylar:
        return dict(kod=None, sebep="dört şartı geçen fon yok", aday=0, elenen=elenen, neden=neden, sira={}, adaylar=[], pencere=pencere,
                    risk_olculemedi=risk_olculemedi, mevcut=None, karar="")
    adaylar.sort(key=lambda a: -a["getiri20"])
    ilk = adaylar[0]; s = ilk; karar = ""; mev = None
    if mevcut:
        m_ad = next((a for a in adaylar if a["kod"] == mevcut), None)
        o = olcum.get(mevcut) or {}
        mev = dict(kod=mevcut, getiri20=o.get("getiri20"), risk=(None if o.get("risk") is None or pd.isna(o.get("risk")) else int(o["risk"])),
                   sira=next((i + 1 for i, a in enumerate(adaylar) if a["kod"] == mevcut), None), aday=m_ad is not None, neden=neden.get(mevcut, ""))
        if m_ad is None:
            karar = f"mevcut {mevcut} ölçütten elendi ({neden.get(mevcut, 'evrende yok')}); ölçütün ilk sırası {ilk['kod']} seçildi"
        elif ilk["kod"] == mevcut:
            karar = f"mevcut {mevcut} ölçütün ilk sırası, kalır"
        else:
            daha_az_riskli = (ilk["risk"] <= m_ad["risk"]) if PARK_MEVCUT_RISK_ESIT_KABUL else (ilk["risk"] < m_ad["risk"])
            uygun = [a for a in adaylar if a["getiri20"] >= m_ad["getiri20"] and ((a["risk"] <= m_ad["risk"]) if PARK_MEVCUT_RISK_ESIT_KABUL else (a["risk"] < m_ad["risk"]))]
            if uygun:
                s = uygun[0]
                karar = (f"{s['kod']} seçildi: en az {mevcut} kadar kazandırıyor ({_yuzde(s['getiri20'], 2)} ≥ {_yuzde(m_ad['getiri20'], 2)}) ve daha az riskli "
                         f"(risk {s['risk']} < {m_ad['risk']}); kural 15 Eylül 2026, kullanıcı")
            else:
                s = m_ad
                karar = (f"mevcut {mevcut} kalır: en az onun kadar kazandıran ({_yuzde(m_ad['getiri20'], 2)}) ve daha az riskli (risk < {m_ad['risk']}) aday yok; "
                         f"ölçütün ilk sırası {ilk['kod']} ({_yuzde(ilk['getiri20'], 2)}, risk {ilk['risk']}), fark {_yuzde(ilk['getiri20'] - m_ad['getiri20'], 2)}; kural 15 Eylül 2026, kullanıcı")
    gerekce = (f"{s['kod']} ({s['kategori']}, risk {s['risk']}, {s['buyukluk'] / 1e9:.1f} milyar TL, {PARK_SEANS} seans {_yuzde(s['getiri20'])}, pencere piyasa günü {pencere_piyasa[0]} → {pencere_piyasa[1]}, TEFAS günü {pencere[0]} → {pencere[1]}); "
               f"{len(adaylar)} aday; ölçüt: kategori {', '.join(PARK_KATEGORILER)}, risk {PARK_RISK_ARALIGI[0]}-{PARK_RISK_ARALIGI[1]}, "
               f"büyüklük ≥ {PARK_ASGARI_BUYUKLUK / 1e9:.0f} milyar TL (varsayım), arıza/çöküş/kırılma/kesinti/değer kaybı ve park_disla.txt dışarıda, ortak pencere (M61)")
    return dict(kod=s["kod"], ilk=ilk["kod"], kategori=s["kategori"], risk=s["risk"], buyukluk=s["buyukluk"], getiri20=s["getiri20"], pencere=pencere, pencere_piyasa=pencere_piyasa, aday=len(adaylar),
                sira={a["kod"]: i + 1 for i, a in enumerate(adaylar)}, adaylar=adaylar[:5], gerekce=gerekce, elenen=elenen, neden=neden,
                risk_olculemedi=risk_olculemedi, mevcut=mev, karar=karar)


def park_eleme_satiri(p):
    """M60: park ölçütünün eleme sayacı brifingde her sabah; risk hanesi boş olup öbür şartları geçen fonlar adıyla (ölçülemedi, elenmedi)."""
    e = p.get("elenen") or {}
    ro = p.get("risk_olculemedi") or []
    return (f"Park ölçütü eleme sayacı (M60): kategori dışı {e.get('kategori', 0)}, risk hanesi boş ya da aralık dışı {e.get('risk', 0)}, "
            f"büyüklük {e.get('buyukluk', 0)}, dışlama {e.get('dislama', 0)}, seans {e.get('seans', 0)}, tam güne yetişemeyen {e.get('tam_gun', 0)}. "
            + (f"Risk değeri ÖLÇÜLEMEDİ ama öbür şartları geçen {len(ro)} fon (kaynak: TEFAS künyesi boş; KAP künyesi ve KAP fon sayfası risk taşımaz): "
               + ", ".join(f"{a['kod']} {_yuzde(a['getiri20']) if a['getiri20'] is not None else '-'} {a['buyukluk'] / 1e9:.1f} mrd" for a in ro[:6]) + "." if ro else ""))


# ---------------------------------------------------------------- kural sürümü ve bekleyen defter kaydı (M57, kural 24; 53 numaralı not, 14 Eylül 2026)
KURAL_SURUMU = "2026-09-14.M58"   # defter kaydının üretildiği kural seti; bekleyen kayıt `kuralSurumu` alanında bunu taşır. Kural değişince damga ilerler.


def kayit_turu(k):
    """Bekleyen kaydın türü: `tur` alanı varsa o (park, aday, satis); yoksa SAT yönlü kayıt satış, notunda 'park' geçen alım park, kalan alım aday."""
    t = str(k.get("tur") or "").strip().lower()
    if t:
        return t
    if str(k.get("yon") or "").upper() == "SAT":
        return "satis"
    return "park" if "park" in str(k.get("not") or "").lower() else "aday"


def bekleyen_dogrula(emirler, park=None, acik_kodlar=None, serbest_nakit=None, kurucu_haber=None, kurucu=None, surum=KURAL_SURUMU):
    """Kural 24 (M57): brifing bekleyen bir defter kaydını yazmadan önce kaydın `kuralSurumu` damgasını günceliyle karşılaştırır.
    Güncelse olduğu gibi yazılır. Eski ya da yoksa yeniden doğrulanır: park kaydı park ölçütüyle (park_fonu_sec çıktısı), aday kaydı
    kapı kümesiyle (bugün kapısı açık kodlar), her alım nakit kısıtıyla (serbest nakit). Geçmezse "iptale çekilmeli" ve gerekçe;
    yerine güncel ölçütün seçtiği kod (park: sıradaki ilk aday, kurucusu haber kapısından kapalı olan atlanır). Satış kaydı yeniden
    doğrulama kapsamı dışıdır (çıkış kararı kullanıcınındır). Defter burada değiştirilmez; karar kullanıcınındır.
    Dönüş: [dict(kimlik, kod, tur, tutar, surum, guncel, sonuc(gecerli|iptale_cekilmeli|olculemedi|kapsam_disi), gerekce, yerine)]."""
    park = park or {}; kurucu_haber = kurucu_haber or {}; kurucu = kurucu or {}
    def yerine_park():
        for a in park.get("adaylar") or []:
            if kurucu_haber.get(kurucu.get(a["kod"]), True) is not False:
                return a["kod"]
        return park.get("kod")
    S = []
    for kimlik, k in sorted((emirler or {}).items()):
        if str(k.get("durum") or "").upper() != "BEKLIYOR":
            continue
        tur = kayit_turu(k); ks = k.get("kuralSurumu"); guncel = (ks == surum)
        r = dict(kimlik=kimlik, kod=k.get("kod"), tur=tur, tutar=k.get("tutar"), surum=ks, guncel=guncel, yerine=None)
        if guncel:
            r.update(sonuc="gecerli", gerekce="kural sürümü güncel, olduğu gibi yazıldı")
        elif tur == "satis":
            r.update(sonuc="kapsam_disi", gerekce="satış kaydı yeniden doğrulama kapsamı dışında (çıkış kararı kullanıcının)")
        else:
            seb = []; olculemedi = []
            if tur == "park":
                if not park.get("sira") and not park.get("neden"):
                    olculemedi.append("park ölçütü ölçülemedi")
                elif k.get("kod") not in park.get("sira", {}):
                    seb.append("park ölçütü: " + park.get("neden", {}).get(k.get("kod"), "fon evrende yok"))
                elif park.get("kod") and k.get("kod") != park.get("kod"):
                    seb.append(f"park ölçütü: dört şartı geçiyor ama {park['sira'][k['kod']]}. sırada, ölçütün seçtiği {park['kod']}")
            else:
                if acik_kodlar is None:
                    olculemedi.append("kapı kümesi ölçülemedi")
                elif k.get("kod") not in set(acik_kodlar):
                    seb.append("kapı kümesi: bugün kapısı açık aday değil")
            tutar = k.get("tutar")
            if serbest_nakit is None:
                olculemedi.append("nakit kısıtı ölçülemedi (serbest nakit yok)")
            elif tutar is not None and float(tutar) > float(serbest_nakit):
                seb.append(f"nakit kısıtı: tutar {_tl(float(tutar))} > serbest nakit {_tl(float(serbest_nakit))}")
            if seb:
                r.update(sonuc="iptale_cekilmeli", gerekce="; ".join(seb + olculemedi), yerine=(yerine_park() if tur == "park" else None))
            elif olculemedi:
                r.update(sonuc="olculemedi", gerekce="; ".join(olculemedi))
            else:
                r.update(sonuc="gecerli", gerekce="yeniden doğrulandı, güncel ölçütü geçiyor")
        S.append(r)
    return S


def bekleyen_satirlari(sonuclar, kaynak=None, surum=KURAL_SURUMU):
    """Brifing satırları (kural 24). Kayıt yoksa tek cümle."""
    if not sonuclar:
        return [f"Bekleyen defter kaydı yok (kural 24, M57; kaynak {kaynak or 'emir defteri'}; güncel kural sürümü {surum})."]
    ad = {"gecerli": "geçerli", "iptale_cekilmeli": "İPTALE ÇEKİLMELİ", "olculemedi": "ölçülemedi", "kapsam_disi": "kapsam dışı"}
    L = [f"Bekleyen defter kayıtları (kural 24, M57; güncel kural sürümü {surum}; defter değiştirilmedi, karar kullanıcınındır):"]
    for r in sonuclar:
        s = (f"- {r['kimlik']} {r['kod']} ({r['tur']}" + (f", {_tl(float(r['tutar']))}" if r.get("tutar") is not None else "") + "): kural sürümü "
             + (r["surum"] if r["surum"] else "yok") + ", " + ad.get(r["sonuc"], r["sonuc"]) + "; " + r["gerekce"]
             + (f"; yerine güncel ölçütün seçtiği {r['yerine']}" if r.get("yerine") else "") + ".")
        L.append(s)
    return L


# ---------------------------------------------------------------- nakit ayrımı ve atıl nakit (M58, kural 16 genişletmesi; 53 numaralı not)
def _tarih_coz(s, bugun):
    """'2026-09-09', '09.09' (yıl bugünün yılı) ya da '09.09.2026' -> date; çözülemezse None."""
    s = str(s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$", s)
    if m:
        try:
            return date(int(m.group(3) or bugun.year), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _sebep(k):
    """`beklemeSebebi` sadeleştirilmiş; alan yoksa kalem adı 'Ödeme' ile başlıyorsa ödeme sayılır (eski kayıtlar için yedek, sözleşme alanı beklemeSebebi)."""
    s = str(k.get("beklemeSebebi") or "").strip().lower()
    if not s and str(k.get("kalem") or "").strip().lower().startswith(("ödeme", "odeme")):
        s = "odeme"
    return s.replace("ö", "o").replace("ı", "i").replace("ş", "s").replace("ç", "c").replace("ü", "u").replace("ğ", "g")


def nakit_ayir(nakit_listesi, pozisyonlar=None, park=None, bugun=None, kategori=None):
    """Kural 16 genişletmesi (M58): nakit koleksiyonu üç tutara ayrılır. Ödemeye bağlı: `beklemeSebebi` 'ödeme' ile başlayan kalem
    (tarihi `odemeTarihi` ya da `valor`). Park edilmiş: park kategorisindeki açık pozisyonlar (fon koduyla) ve `beklemeSebebi` 'park'
    kalemler. Atıl: `beklemeSebebi` taşımayan, tutarı dolu, valörü geçmiş ya da yazılmamış kalem; başka bir sebep taşıyan kalem
    'ayrılmış' sayılır. Valörü gelecekte olan kalem beklenen giriştir, atıl değildir. Atıl satır: tutar, kurum, kaç gündür (kaydın
    `tarih` ya da `valor` alanından), günlük maliyet = tutar × park fonunun günlük getirisi (PARK_SEANS getirisi / PARK_SEANS).
    Dönüş: dict(odeme[list], park[list], atil[list], ayrilmis[list], beklenen_giris[list], bos(int), toplamlar, gunluk_getiri, gunluk_maliyet)."""
    bugun = bugun or date.today(); kategori = kategori or {}; park = park or {}
    odeme, parkl, atil, ayrilmis, giris = [], [], [], [], []
    bos = 0
    for k in nakit_listesi or []:
        tutar = k.get("tutar")
        if tutar is None:
            bos += 1; continue
        tutar = float(tutar); s = _sebep(k)
        valor = _tarih_coz(k.get("valor"), bugun); tarih = _tarih_coz(k.get("tarih"), bugun) or valor
        kayit = dict(kalem=k.get("kalem"), tutar=tutar, kurum=k.get("kurum") or "kurum yazılmamış", tarih=(tarih.isoformat() if tarih else None),
                     gun=((bugun - tarih).days if tarih else None))
        if s.startswith("odeme"):
            odeme.append(dict(kayit, tarih=str(k.get("odemeTarihi") or k.get("valor") or "tarih yazılmamış")))
        elif s.startswith("park"):
            parkl.append(dict(kayit, fon=k.get("fon") or "fon yazılmamış"))
        elif s:
            ayrilmis.append(dict(kayit, sebep=k.get("beklemeSebebi")))
        elif valor and valor > bugun:
            giris.append(dict(kayit, valor=valor.isoformat()))
        else:
            atil.append(kayit)
    for v in acik_pozisyonlar(pozisyonlar or {}):
        if kategori.get(v.get("kod")) in PARK_KATEGORILER:
            parkl.append(dict(kalem=f"pozisyon {v.get('kurum') or ''} {v.get('kod')}", tutar=float(v.get("deger") or 0), kurum=v.get("kurum") or "", fon=v.get("kod")))
    gg = (float(park["getiri20"]) / PARK_SEANS) if park.get("getiri20") is not None else None
    at = sum(x["tutar"] for x in atil)
    return dict(odeme=odeme, park=parkl, atil=atil, ayrilmis=ayrilmis, beklenen_giris=giris, bos=bos,
                odeme_toplam=sum(x["tutar"] for x in odeme), park_toplam=sum(x["tutar"] for x in parkl), atil_toplam=at,
                gunluk_getiri=gg, gunluk_maliyet=(at * gg if gg is not None else None), park_kod=park.get("kod"))


def nakit_satirlari(n, kaynak=None):
    """Brifingin nakit ve ödeme takvimi satırları (M58)."""
    L = [f"Nakit ve ödeme takvimi (kural 16, M58; kaynak {kaynak or 'emir defteri nakit koleksiyonu'}): "
         f"ödemeye bağlı {_tl(n['odeme_toplam'])}" + (" (" + "; ".join(f"{x['kalem']} {x['tarih']}" for x in n["odeme"][:4]) + ")" if n["odeme"] else "")
         + f", park edilmiş {_tl(n['park_toplam'])}" + (" (" + "; ".join(f"{x['fon']} {_tl(x['tutar'])}" for x in n["park"][:4]) + ")" if n["park"] else "")
         + f", atıl {_tl(n['atil_toplam'])}"
         + (f", ayrılmış {_tl(sum(x['tutar'] for x in n['ayrilmis']))}" if n["ayrilmis"] else "")
         + (f", valörü gelmemiş giriş {_tl(sum(x['tutar'] for x in n['beklenen_giris']))}" if n["beklenen_giris"] else "")
         + (f"; tutarı boş {n['bos']} kalem ölçülemedi" if n["bos"] else "") + "."]
    if n["atil"]:
        for x in n["atil"]:
            L.append(f"- **Atıl nakit: {_tl(x['tutar'])}, {x['kurum']}, " + (f"{x['gun']} gündür bekliyor" if x.get("gun") is not None else "bekleme süresi ölçülemedi (tarih yok)")
                     + (f", günlük maliyet {_tl(x['tutar'] * n['gunluk_getiri'])} ({n['park_kod']} günlük getirisi {_yuzde(n['gunluk_getiri'], 3)})" if n["gunluk_getiri"] is not None else ", günlük maliyet ölçülemedi (park fonu yok)")
                     + ".** Karar kullanıcınındır.")
    return L


# ---------------------------------------------------------------- sicil
def sicil_yaz(oneriler, tarih, veri_tarihi, yol=None, depo=None):
    """Kural 18: verilen her öneri sicile yazılır; aynı gün aynı kod tekrar yazılmaz. Kimlik YYYYAAGG-KOD (M29): kural 18'in
    değişmezi kimliğe taşınır, ikinci yazma sessizce çoğalamaz. Dönüş: yazılan kayıt sayısı."""
    d = _depo(depo, yol)
    s = d.sicil_oku()
    var = {(x["tarih"], x["kod"]) for x in s}
    n = 0
    for o in oneriler:
        if (tarih, o["kod"]) in var:
            continue
        # M29: kimlik kaydı tekilleştiren alandan kurulur (tarih, kod); sıra numarası koşular arasında kayıp çakışıyordu
        s.append(dict(id=f"{tarih.replace('-', '')}-{o['kod']}", tarih=tarih, kod=o["kod"], yon=o["yon"], dilim=o["dilim"], etiket=o.get("etiket", ""),
                      tutar=o.get("tutar"), gerekce=o["gerekce"], olcumTarihi=veri_tarihi, siralamaOlcusu=o.get("sira_olcusu"), yeniFon=bool(o.get("yeni_fon")),
                      uygulandi=None, uygulamaKaynagi=None, sonuc20=None, sonucTarihi=None))
        n += 1
    d.sicil_yaz(s)
    return n


def _pencere_getirisi(L, t0, k=SONUC_SEANS):
    """Tarih sıralı (tarih, fiyat) listesinde t0'dan (ilk seans >= t0) k seans sonraya getiri; yoksa None."""
    i = next((j for j, (t, _) in enumerate(L) if t >= t0), None)
    if i is None or i + k >= len(L) or L[i][1] <= 0:
        return None
    return L[i + k][1] / L[i][1] - 1, L[i + k][0]


def sicil_guncelle(fiyat, emirler=None, yol=None, depo=None, kategori=None, park=None):
    """fiyat: fonKodu -> tarih sıralı (tarih, fiyat) listesi ya da pandas DataFrame(tarih, fonKodu, fiyat).
    Yirmi seansı dolan önerinin sonucu (öneri gününün fiyatından 20 seans sonraki fiyata getiri) yazılır.
    Kural 18 kıyası (30 numaralı not, madde 5): aynı pencerede fonun kendi kategorisindeki fonların ortanca getirisi
    (`kiyas20`, `kiyasKategori`, `kiyasFon` sayısı) ve park fonunun getirisi (`park20`) ayrıca yazılır; kategori: kod -> kategori,
    park: park fonunun kodu. Yükselen piyasada ham getiri her öneriyi isabetli gösterir; isabet kıyasa göre ölçülür.
    emirler: emir defteri sözlüğü; öneri tarihinden en çok UYGULAMA_GUN gün sonra GERCEKLESTI olan aynı yönlü emir
    'uygulandı' sayılır (kaynak: emir defteri). Aksi hâlde alan boş kalır; kullanıcı elle işaretler."""
    d = _depo(depo, yol)
    s = d.sicil_oku()
    if not s:
        return 0
    seri = {}
    if hasattr(fiyat, "groupby"):
        for k, g in fiyat.groupby("fonKodu"):
            g = g.sort_values("tarih")
            seri[k] = [(str(t)[:10], float(p)) for t, p in zip(g.tarih, g.fiyat)]
    else:
        seri = fiyat
    kategori = kategori or {}
    n = 0
    for x in s:
        if x.get("sonuc20") is None and x["kod"] in seri:
            r = _pencere_getirisi(seri[x["kod"]], x["tarih"])
            if r is not None:
                x["sonuc20"], x["sonucTarihi"] = r; n += 1
                kat = kategori.get(x["kod"])
                if kat:
                    emsal = [v[0] for k, L in seri.items() if k != x["kod"] and kategori.get(k) == kat
                             for v in [_pencere_getirisi(L, x["tarih"])] if v is not None]
                    if emsal:
                        emsal.sort(); x["kiyas20"] = emsal[len(emsal) // 2]; x["kiyasKategori"] = kat; x["kiyasFon"] = len(emsal)
                if park and park in seri:
                    rp = _pencere_getirisi(seri[park], x["tarih"])
                    if rp is not None:
                        x["park20"] = rp[0]; x["parkKod"] = park
        if x.get("uygulandi") is None and emirler:
            t0 = datetime.strptime(x["tarih"], "%Y-%m-%d").date()
            for eid, e in emirler.items():
                try:
                    te = datetime.strptime(e.get("tarih", ""), "%Y-%m-%d").date()
                except ValueError:
                    continue
                if e.get("kod") == x["kod"] and e.get("yon") == x["yon"] and e.get("durum") == "GERCEKLESTI" and 0 <= (te - t0).days <= UYGULAMA_GUN:
                    x["uygulandi"] = True; x["uygulamaKaynagi"] = f"emir {eid}"; n += 1; break
    d.sicil_yaz(s)
    return n


def sicil_ozeti(ay, yol=None, depo=None):
    """Ay (YYYY-MM) için: verilen, uygulanan, uygulanan ve uygulanmayanların ortalama 20 seans getirisi; kural 18 kıyası:
    kategori ortancasına göre üstte ve altta kalan öneri sayısı, ortalama fark (yanlılık: her öneri aynı yönde sapıyorsa
    ölçü kendini doğrulamaktadır), park fonuna göre üstte kalan sayısı. Kaynak: sicil."""
    s = [x for x in _depo(depo, yol).sicil_oku() if x["tarih"][:7] == ay]
    def ort(L):
        v = [x["sonuc20"] for x in L if x.get("sonuc20") is not None]
        return (sum(v) / len(v), len(v)) if v else (None, 0)
    uyg = [x for x in s if x.get("uygulandi") is True]
    uym = [x for x in s if x.get("uygulandi") is not True]
    k = [x for x in s if x.get("sonuc20") is not None and x.get("kiyas20") is not None]
    farklar = [x["sonuc20"] - x["kiyas20"] for x in k]
    pk = [x for x in s if x.get("sonuc20") is not None and x.get("park20") is not None]
    return dict(ay=ay, verilen=len(s), uygulanan=len(uyg), bilinmeyen=sum(1 for x in s if x.get("uygulandi") is None),
                uygulanan_getiri=ort(uyg), uygulanmayan_getiri=ort(uym),
                kiyas_olculen=len(k), kiyas_ustu=sum(1 for f in farklar if f > 0), kiyas_alti=sum(1 for f in farklar if f < 0),
                kiyas_fark_ort=(sum(farklar) / len(farklar) if farklar else None),
                park_olculen=len(pk), park_ustu=sum(1 for x in pk if x["sonuc20"] > x["park20"]))


def kiyas_cumlesi(o):
    """Sicil satırının kıyas parçası; kıyas ölçülmemişse bunu söyler (kural 18: kıyassız isabet yazılmaz)."""
    if not o.get("kiyas_olculen"):
        return "kategori kıyası henüz ölçülmedi"
    c = (f"kategori ortancasının üstünde {o['kiyas_ustu']}, altında {o['kiyas_alti']} öneri, ortalama fark {_yuzde(o['kiyas_fark_ort'])}")
    if o.get("park_olculen"):
        c += f"; park fonunu geçen {o['park_ustu']}/{o['park_olculen']}"
    return c


def sicil_satiri(tarih, yol=None, depo=None):
    """Brifingdeki tek cümlelik sicil satırı (bölüm 8)."""
    d = _depo(depo, yol)
    if not d.sicil_var_mi():
        return "Sicil: öneri sicili henüz yok; ilk öneriyle açılır."
    o = sicil_ozeti(tarih[:7], depo=d)
    if not o["verilen"]:
        return "Sicil: bu ay öneri verilmedi."
    g = o["uygulanan_getiri"]
    isabet = (f"uygulanan {o['uygulanan']} önerinin 20 seans ortalama getirisi {_yuzde(g[0])} ({g[1]} ölçüm); {kiyas_cumlesi(o)}"
              if g[0] is not None else "henüz 20 seansı dolan öneri yok")
    return f"Sicil: bu ay {o['verilen']} öneri verildi, {o['uygulanan']} uygulandı, {o['bilinmeyen']} tanesinin uygulanıp uygulanmadığı işaretlenmedi; {isabet}."


# ---------------------------------------------------------------- brifing bölümü
def brifing_bolumu(oneriler, notlar, tarih, haber_notu, depo=None, olculemeyen=None, bekleyen=None):
    """olculemeyen: her adayda ölçülemeyen giriş kapıları (M50). bekleyen: kapatan kapısı olmayan ama ölçülemeyen kapısı olan adayların
    cümleleri (M51; kesişim değil aday bazında). İkisi de doluysa "öneri yoktur" yanıltıcıdır; eksik girdi adıyla yazılır."""
    L = ["## Öneri", ""]
    if not oneriler and olculemeyen:
        L.append("Giriş kapısı ölçülemiyor: " + "; ".join(olculemeyen) + ". Bu kapılar hiçbir adayda ölçülemediği için kapısı açık aday olamaz ve "
                 "öneri üretilemez; bu bir sonuç değil, girdi eksiğidir (M50, kural 14).")
    elif not oneriler and bekleyen:
        L.append("Bugün öneri yoktur, ama bu bir sonuç değil girdi eksiğidir (M51): " + " ".join(c + "." for c in bekleyen))
    elif not oneriler:
        L.append("Bugün öneri yoktur. Önerisiz gün olağan bir sonuçtur; ölçüm bir öneri üretmediği için bölüm boş bırakılmadı, bu cümle yazıldı (kural 1).")
    elif bekleyen:
        L.append("Bekleyen aday (M51): " + " ".join(c + "." for c in bekleyen))
    for o in oneriler:
        tutar = _tl(o["tutar"])
        et = " [yeni]" if o.get("etiket") else ""
        L.append(f"- **{o['yon']} {o['kod']}{et}**, {o.get('ad') or ''}: {tutar}. {o['gerekce']}. Süreklilik {o['ardisik']} gün. {o['tutar_notu']}. Karar kullanıcınındır.")
    if notlar:
        L.append("")
        L.append("Öneriye dönüşmeyenler: " + "; ".join(notlar[:8]) + ".")
    L.append("")
    L.append(sicil_satiri(tarih, depo=depo))
    L.append(f"Haber kapısı: {haber_notu}")
    L.append("")
    return L
