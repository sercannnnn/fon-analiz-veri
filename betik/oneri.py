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
import json, os
from datetime import date, datetime, timedelta

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
    isabet = (f"uygulanan {oz['uygulanan']} önerinin 20 seans ortalama getirisi {_yuzde(g[0])} ({g[1]} ölçüm)" if g[0] is not None else None)
    return o, dict(ay=oz["ay"], verilen=oz["verilen"], uygulanan=oz["uygulanan"], bilinmeyen=oz["bilinmeyen"], isabet=isabet, metin=sicil_satiri(tarih, depo=d))


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


def sicil_guncelle(fiyat, emirler=None, yol=None, depo=None):
    """fiyat: fonKodu -> tarih sıralı (tarih, fiyat) listesi ya da pandas DataFrame(tarih, fonKodu, fiyat).
    Yirmi seansı dolan önerinin sonucu (öneri gününün fiyatından 20 seans sonraki fiyata getiri) yazılır.
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
    n = 0
    for x in s:
        if x.get("sonuc20") is None and x["kod"] in seri:
            L = seri[x["kod"]]
            i = next((j for j, (t, _) in enumerate(L) if t >= x["tarih"]), None)
            if i is not None and i + SONUC_SEANS < len(L):
                p0, (t1, p1) = L[i][1], L[i + SONUC_SEANS]
                if p0 > 0:
                    x["sonuc20"] = p1 / p0 - 1; x["sonucTarihi"] = t1; n += 1
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
    """Ay (YYYY-MM) için: verilen, uygulanan, uygulanan ve uygulanmayanların ortalama 20 seans getirisi. Kaynak: sicil."""
    s = [x for x in _depo(depo, yol).sicil_oku() if x["tarih"][:7] == ay]
    def ort(L):
        v = [x["sonuc20"] for x in L if x.get("sonuc20") is not None]
        return (sum(v) / len(v), len(v)) if v else (None, 0)
    uyg = [x for x in s if x.get("uygulandi") is True]
    uym = [x for x in s if x.get("uygulandi") is not True]
    return dict(ay=ay, verilen=len(s), uygulanan=len(uyg), bilinmeyen=sum(1 for x in s if x.get("uygulandi") is None),
                uygulanan_getiri=ort(uyg), uygulanmayan_getiri=ort(uym))


def sicil_satiri(tarih, yol=None, depo=None):
    """Brifingdeki tek cümlelik sicil satırı (bölüm 8)."""
    d = _depo(depo, yol)
    if not d.sicil_var_mi():
        return "Sicil: öneri sicili henüz yok; ilk öneriyle açılır."
    o = sicil_ozeti(tarih[:7], depo=d)
    if not o["verilen"]:
        return "Sicil: bu ay öneri verilmedi."
    g = o["uygulanan_getiri"]
    isabet = (f"uygulanan {o['uygulanan']} önerinin 20 seans ortalama getirisi {_yuzde(g[0])} ({g[1]} ölçüm)"
              if g[0] is not None else "henüz 20 seansı dolan öneri yok")
    return f"Sicil: bu ay {o['verilen']} öneri verildi, {o['uygulanan']} uygulandı, {o['bilinmeyen']} tanesinin uygulanıp uygulanmadığı işaretlenmedi; {isabet}."


# ---------------------------------------------------------------- brifing bölümü
def brifing_bolumu(oneriler, notlar, tarih, haber_notu, depo=None):
    L = ["## Öneri", ""]
    if not oneriler:
        L.append("Bugün öneri yoktur. Önerisiz gün olağan bir sonuçtur; ölçüm bir öneri üretmediği için bölüm boş bırakılmadı, bu cümle yazıldı (kural 1).")
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
