#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doğrulama katmanı (Görev 4). Sıfır sapma kapısı bir alışkanlık değil, bir kontroldür.

Dört sınama, tek rapor:
  1 Kimlik: her fonda pay adedi × fiyat = portföy büyüklüğü (çekim anındaki kapsam_son.json kaydından).
  2 Portföy tabanı mutabakatı: pozisyon defterindeki değerlerin toplamı ile brifingin dayandığı taban; fark pozisyon pozisyon.
  3 Bakış geçirgen maruziyet: fon içerik arşivi × pozisyonlar ile hisse maruziyeti ve tek isim maruziyeti; bildirilen değerle fark.
  4 Defter tutarlılığı: emir defterindeki gerçekleşen emirler ile pozisyon adetleri.

  5 Günlük köprü (13 Eylül 2026, finance değerlendirmesi 2.5): dünkü toplam + fiyat etkisi + işlem etkisi = bugünkü toplam; artık sıfır değilse sapma.
     Defter o gün teyit edilmemişse (değerleme tarihi klasör tarihinden eski) köprü hesaplanır ama sapma açılmaz; "defter teyit edilmedi" ayrı hâldir.

Sapma defteri: 03 Veri/sapmalar.json. Sapma ancak sebebi kanıtlandığında kapanır; "yuvarlama", "dönem sınırı", "toplama farkı"
gerekçeleri kapatmaz, kod reddeder. Yeniden üretimle kapanış serbesttir (2.4): defter brifingin fiyat tarihiyle yeniden değerlenip fark
sıfır çıkarsa kayıt hesap çıktısıyla kapanır. Her kayıt sınıf (zamanlama, duzeltme, arastirma, kayit), yaş (iş günü) ve hedef tarih taşır;
SAPMA_YAS_ESIK_IS_GUNU aşılınca brifing ayrı satırda bildirir. Açık sapmalar brifingin kapsam satırında görünür.

Kimlik istisnası (2.2): 03 Veri/Künye/kimlik_istisna.json içindeki fon, listeye alındığı andaki farkı ve adlı toleransı taşır; fark
toleransın ötesine çıkarsa kayıt kendiliğinden kırmızıya döner. İstisna listesi kontrolü durdurmaz, yalnızca bilinen sapmayı sarıya çeker.

Her sayının künyesi vardır: ölçüm, kayıt, hesaplama, varsayım, projeksiyon.

Kullanım:
  denetim.py [--klasor "04 Günlük Rapor/2026-09-08"] [--icerik <fon_icerik_YYYY-MM.csv.gz>] [--bildirilen anahtar=deger ...]
  denetim.py --kapat <sapmaId> --kanit "<kanıt metni>"
Yalnızca standart kütüphane ve pandas.
"""
import argparse, csv, glob, gzip, io, json, os, re, sys
from datetime import date

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAPOR = os.path.join(KOK, "04 Günlük Rapor")
VERI_KOK = os.environ.get("FON_DENETIM_VERI", os.path.join(KOK, "03 Veri"))   # sinama gecici klasore yazsin diye
KUNYE_KLASOR = os.path.join(VERI_KOK, "Künye")
SAPMA_YOL = os.path.join(VERI_KOK, "sapmalar.json")
OLCUM, KAYIT, HESAP, VARSAYIM = "ölçüm", "kayıt", "hesaplama", "varsayım"
KAPATMA_REDDI = re.compile(r"yuvarlama|dönem sınır|donem sinir|toplama fark|küsurat|kusurat", re.I)
TABAN_TOLERANS_TL = 1.0          # taban mutabakatında bir liranın altı fark sıfır sayılır (kuruş yuvarlaması değil, TL)
ARSIV = os.environ.get("FON_DENETIM_ARSIV", os.path.join(KOK, "03 Veri", "Arşiv"))   # tefas_YYYY-MM.csv.gz; yeniden değerleme ve köprü buradan fiyat okur
KIMLIK_ISTISNA_YOL = os.path.join(KUNYE_KLASOR, "kimlik_istisna.json")
SAPMA_YAS_ESIK_IS_GUNU = 5       # açık sapma bu kadar iş gününü aşınca brifing ayrı satırda bildirir (varsayım, 13 Eylül 2026; SOX 30 günlük bantlar günlük döngüye uymaz)
SAPMA_SINIFLAR = ("zamanlama", "duzeltme", "arastirma", "kayit")   # mutabakat kalemi sınıfları (finance değerlendirmesi 2.3)
KIMLIK_ARIZA_YOL = os.path.join(KUNYE_KLASOR, "kimlik_arizalari.json")   # kimlik taramasının çıktısı; akış hesabı bu fon-tarihleri düşer (takvim.kimlik_arizasi_ayikla)
KIMLIK_TARAMA_SEANS = 52         # kimlik taraması penceresi (30 numaralı not: 2.047 fon, 52 seans)
KALICI_ORAN = 0.80               # günlerin bu oranında sapan fon kalıcı kimlik farkıdır; yalnızca kalıcı fon istisna listesine girebilir
BIRIM_HATASI_TOL = 0.01          # oran 1000'e ya da 0,001'e bu göreli payla yakınsa birim hatası (büyüklük bin TL basılmış)
GECIKME_TOL = 0.002              # ardışık iki seansta oranların çarpımı 1'e bu kadar yakınsa bir günlük gecikme imzası (RTH: 1,03 ve 0,97)
SEVIYE_KIRILMA_KAT = 10.0        # M39: büyüklük ya da pay × fiyat iki seans arasında bu kattan fazla değişirse seviye kırılması; kimlik tutsa da bildirilir
COKUS_ORAN = 0.90                # M40: büyüklük tek seansta bu oranın üstünde düşerse çöküş; fonun arızası maskelenmez, adıyla bildirilir
COKUS_KALICI_ORAN = 0.50         # M40: düşüşten sonra pencere boyunca büyüklük önceki seviyenin bu oranına dönmüyorsa çöküş kalıcıdır (tasfiye);
                                 # dönüyorsa besleme sıçramasıdır ve yalnızca kırılma (M39) olarak bildirilir
ONARIM_KATLARI = (1000.0, 0.001)  # M38: birim hatası onarımı pay ya da büyüklük alanında bu katlarla denenir; kimlik sıfır sapmayla kapanmalı ve komşu seansla sürekli olmalı
DISA_AKTARIM = os.path.join(KOK, "03 Veri", "defter_disa_aktarim.json")   # akşam görevinin yazdığı pozisyon fotoğrafı; köprünün yakıtı
FIYAT_ESLESME_TOL = 0.5e-6       # deger/adet ile TEFAS fiyatı bu kadar yakınsa aynı gün sayılır (fiyat altı ondalıkla basılır) + 0,01/adet
HISSE_TUR = re.compile(r"HISSE|HİSSE|ODUNC|ÖDÜNÇ", re.I)


def tl(x, hane=0):
    return f"{x:,.{hane}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def yuzde(x, hane=2):
    return ("-" if x < 0 else "") + "%" + tl(abs(x) * 100, hane)


def json_oku(yol, varsayilan):
    try:
        return json.load(open(yol, encoding="utf-8"))
    except Exception:
        return varsayilan


# ---------------------------------------------------------------- sapma defteri

def sapma_yukle():
    return json_oku(SAPMA_YOL, [])


def sapma_yaz(L):
    os.makedirs(os.path.dirname(SAPMA_YOL), exist_ok=True)
    json.dump(L, open(SAPMA_YOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def is_gunu_ekle(t, n):
    """t tarihine n iş günü ekler (hafta sonu atlanır; resmî tatil sayılmaz, varsayım)."""
    g = t
    while n > 0:
        g = date.fromordinal(g.toordinal() + 1)
        if g.weekday() < 5:
            n -= 1
    return g


def sapma_yasi(s, bugun=None):
    """Açık sapmanın yaşı iş günü olarak (oneri._is_gunu_farki ile aynı sayım)."""
    from oneri import _is_gunu_farki
    bugun = bugun or date.today()
    try:
        t = date.fromisoformat(str(s.get("tarih"))[:10])
    except ValueError:
        return None
    return _is_gunu_farki(t, bugun) if t <= bugun else 0


def sapma_ekle(L, sid, olcum, bildirilen, hesaplanan, kunye, tarih=None, not_="", sinif="arastirma"):
    """Aynı kimlikli açık sapma varsa değerleri günceller, yoksa açar. Fark sıfırsa (tolerans içinde) kayıt açmaz.
    Her yeni kayıt sınıf (SAPMA_SINIFLAR) ve hedef tarih (açılış + SAPMA_YAS_ESIK_IS_GUNU iş günü) taşır."""
    fark = None if bildirilen is None or hesaplanan is None else round(hesaplanan - bildirilen, 2)
    if sinif not in SAPMA_SINIFLAR:
        sinif = "arastirma"
    for s in L:
        if s["id"] == sid and s["durum"] == "acik":
            s.update(bildirilen=bildirilen, hesaplanan=hesaplanan, fark=fark, sonKontrol=(tarih or date.today().isoformat()))
            s.setdefault("sinif", sinif)
            return s
    if fark is not None and abs(fark) <= TABAN_TOLERANS_TL:
        return None
    t0 = tarih or date.today().isoformat()
    s = dict(id=sid, tarih=t0, olcum=olcum, bildirilen=bildirilen, hesaplanan=hesaplanan,
             fark=fark, durum="acik", kunye=kunye, sinif=sinif,
             hedefTarih=is_gunu_ekle(date.fromisoformat(t0[:10]), SAPMA_YAS_ESIK_IS_GUNU).isoformat(),
             **({"not": not_} if not_ else {}))
    L.append(s)
    return s


def sapma_kapat_bellekte(L, sid, kanit, tarih=None):
    """Listede kapatır (dosyaya yazmaz); kanıt boşsa ya da yasak gerekçe içeriyorsa kapatmaz ve False döner. Yeniden üretim
    kanıtı (hesap çıktısı) serbesttir; komut satırındaki sapma_kapat ile aynı ret deseni kullanılır."""
    if not kanit or KAPATMA_REDDI.search(kanit):
        return False
    for s in L:
        if s["id"] == sid and s["durum"] == "acik":
            s["durum"] = "kapandi"; s["kapanis"] = dict(tarih=tarih or date.today().isoformat(), kanit=kanit)
            return True
    return False


def sapma_kapat(sid, kanit):
    L = sapma_yukle()
    if not kanit or KAPATMA_REDDI.search(kanit):
        sys.exit("kapatma reddedildi: sapma ancak sebebi kanıtlanınca kapanır; yuvarlama, dönem sınırı ya da toplama farkı gerekçe değildir")
    for s in L:
        if s["id"] == sid:
            if s["durum"] != "acik":
                sys.exit(f"{sid} zaten {s['durum']}")
            s["durum"] = "kapandi"; s["kapanis"] = dict(tarih=date.today().isoformat(), kanit=kanit)
            sapma_yaz(L); print(f"{sid} kapandı; kanıt: {kanit}"); return
    sys.exit(f"{sid} bulunamadı")


# ---------------------------------------------------------------- fiyat serisi ve değerleme tarihi (2.4, 2.5)

def fiyat_serisi(kodlar, aylar):
    """Arşivden verilen kodların fiyatlarını okur: fonlar tefas_YYYY-MM.csv.gz (fiyat), hisseler hisse_YYYY-MM.csv.gz (kapanisHam;
    banka pozisyonu ham kapanışla değerlenir). Dönüş: {kod: {tarih: fiyat}}; sıfır fiyat atlanır (kural 15)."""
    kodlar = set(kodlar); F = {k: {} for k in kodlar}
    for ay in sorted(set(aylar)):
        for on_ek, kod_alani, fiyat_alani in (("tefas", "fonKodu", "fiyat"), ("hisse", "hisse", "kapanisHam")):
            yol = os.path.join(ARSIV, f"{on_ek}_{ay}.csv.gz")
            if not os.path.exists(yol):
                continue
            with gzip.open(yol, "rt", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get(kod_alani) in kodlar:
                        try:
                            fi = float(r.get(fiyat_alani) or 0)
                        except ValueError:
                            continue
                        if fi > 0 and r["tarih"] not in F[r[kod_alani]]:
                            F[r[kod_alani]][r["tarih"]] = fi
    return F


def _aylar(bas, bit):
    """bas..bit tarihlerini kapsayan YYYY-MM listesi."""
    a = []
    y, m = bas.year, bas.month
    while (y, m) <= (bit.year, bit.month):
        a.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return a


def degerleme_tarihi(poz, F, en_gec):
    """Her pozisyonun deger/adet oranı TEFAS'ta hangi günün fiyatına eşit: dönüş {kimlik: tarih|None}. Tolerans FIYAT_ESLESME_TOL + 0,01/adet
    (fiyat altı ondalıkla basılır, değer kuruşa yuvarlanır). Birden çok gün eşleşirse en_gec'e en yakın gün (fiyat iki gün aynı olabilir)."""
    sonuc = {}
    for k, v in poz.items():
        adet = float(v.get("adet") or 0); deger = float(v.get("deger") or 0)
        if adet <= 0 or deger <= 0 or v.get("kod") not in F:
            sonuc[k] = None; continue
        ima = deger / adet; tol = FIYAT_ESLESME_TOL + 0.01 / adet
        gunler = [g for g, fi in F[v["kod"]].items() if abs(fi - ima) <= tol and g <= en_gec]
        sonuc[k] = max(gunler) if gunler else None
    return sonuc


def en_yakin_gun(v, F, en_gec):
    """Eşleşmeyen pozisyon için deger/adet oranına en yakın TEFAS günü ve pay başına fark (TL); okur sapmanın tarih mi fiyat mı olduğunu görsün."""
    adet = float(v.get("adet") or 0); deger = float(v.get("deger") or 0)
    ser = {g: fi for g, fi in F.get(v.get("kod"), {}).items() if g <= en_gec}
    if adet <= 0 or not ser:
        return None
    ima = deger / adet
    g = min(ser, key=lambda g: abs(ser[g] - ima))
    return g, round(ima - ser[g], 6)


def yeniden_degerle(poz, F, gun):
    """Pozisyonları verilen günün TEFAS fiyatıyla değerler. Dönüş: (toplam, eşleşmeyen kimlikler)."""
    toplam, eksik = 0.0, []
    for k, v in poz.items():
        fi = F.get(v.get("kod"), {}).get(gun)
        if fi is None:
            eksik.append(k); toplam += float(v.get("deger") or 0)
        else:
            toplam += float(v.get("adet") or 0) * fi
    return round(toplam, 2), eksik


def kimlik_istisna_yukle():
    return json_oku(KIMLIK_ISTISNA_YOL, [])


def kimlik_taramasi(seans=KIMLIK_TARAMA_SEANS, son_gun=None, arsiv=None):
    """Arşivdeki son `seans` günde her fonun kimlik farkını (pay × fiyat − büyüklük; tolerans pay × 0,5e-6 + 0,01 TL) ölçer ve
    fonları sınıflar (30 numaralı not, madde 1): kalıcı (günlerin en az KALICI_ORAN'ında sapan), epizodik (tek seans sapan, komşu
    seanslar tolerans içinde), aralıklı (birden çok seans ama kalıcı değil). Epizodik arızalar imzasıyla adlandırılır: birim hatası
    (oran 1000 ya da 0,001'e yakın), bir günlük gecikme (ardışık iki seansta oranlar birbirinin tersi), diğer.
    Dönüş: dict(pencere, fonlar{kod: {sinif, sapanGun, gun, farkOrtanca, farkEnKucuk, farkEnBuyuk}}, arizalar[{fonKodu, tarih, fark, oran, imza}]).
    Liste değil kural: elle bakım istemez; sonuç KIMLIK_ARIZA_YOL dosyasına yazılır, akış hesabı arızalı fon-tarihleri köprüler.
    Arşiv kökü: `arsiv` parametresi, yoksa FON_DENETIM_ARSIV ortam değişkeni, yoksa 03 Veri/Arşiv (M33: bulut kendi klonunun
    arsiv/ klasörünü verir ve taramayı yerinde koşturur; dosya taşınmaz)."""
    dosyalar = sorted(glob.glob(os.path.join(arsiv or ARSIV, "tefas_????-??.csv.gz")))[-4:]
    kayit = {}   # (kod, tarih) -> (pay, fiyat, buyukluk)
    for yol in dosyalar:
        with gzip.open(yol, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    pay, fi, bu = float(r["tedPaySayisi"] or 0), float(r["fiyat"] or 0), float(r["portfoyBuyukluk"] or 0)
                except (ValueError, KeyError):
                    continue
                if fi > 0 and pay > 0:
                    kayit[(r["fonKodu"], r["tarih"])] = (pay, fi, bu)
    gunler = sorted({g for _, g in kayit})
    if son_gun:
        gunler = [g for g in gunler if g <= son_gun]
    gunler = gunler[-seans:]
    gun_ix = {g: i for i, g in enumerate(gunler)}
    seriler = {}
    for (kod, g), (pay, fi, bu) in kayit.items():
        if g in gun_ix:
            seriler.setdefault(kod, {})[g] = (pay * fi - bu, (pay * fi / bu) if bu else None, pay * 0.5e-6 + 0.01)
    fonlar, arizalar, kirilmalar, cokusler = {}, [], [], {}
    # M39 ve M40: kimlikten bağımsız süreklilik; büyüklük ve pay × fiyat seviyesi ardışık iki seansta SEVIYE_KIRILMA_KAT'ı aşarsa kırılma,
    # büyüklük COKUS_ORAN üstünde düşerse çöküş (fon adıyla bildirilir, arızası maskelenmez)
    ham = {}
    for (kod, g), (pay, fi, bu) in kayit.items():
        if g in gun_ix:
            ham.setdefault(kod, {})[g] = (pay, fi, bu)
    for kod, hs in ham.items():
        gs = sorted(hs)
        for g0, g1 in zip(gs, gs[1:]):
            if gun_ix[g1] - gun_ix[g0] != 1:
                continue
            for alan, v0, v1 in (("buyukluk", hs[g0][2], hs[g1][2]), ("payXfiyat", hs[g0][0] * hs[g0][1], hs[g1][0] * hs[g1][1])):
                if v0 > 0 and v1 > 0 and (v1 / v0 >= SEVIYE_KIRILMA_KAT or v0 / v1 >= SEVIYE_KIRILMA_KAT):
                    kirilmalar.append(dict(fonKodu=kod, tarih=g1, alan=alan, oran=round(v1 / v0, 6), onceki=round(v0, 2), sonraki=round(v1, 2)))
            if hs[g0][2] > 0 and hs[g1][2] / hs[g0][2] <= 1 - COKUS_ORAN:
                sonrasi = [hs[x][2] for x in gs if x > g0]
                kalici = all(v <= COKUS_KALICI_ORAN * hs[g0][2] for v in sonrasi)   # pencere boyunca geri dönmedi: tasfiye, sıçrama değil
                if kalici:
                    cokusler.setdefault(kod, []).append(dict(tarih=g1, oran=round(hs[g1][2] / hs[g0][2], 6), onceki=round(hs[g0][2], 2), sonraki=round(hs[g1][2], 2), sonraSeans=len(sonrasi)))
    for kod, s in seriler.items():
        sapan = {g: v for g, v in s.items() if abs(v[0]) > v[2]}
        if not sapan:
            continue
        farklar = [v[0] for v in sapan.values()]
        oran = len(sapan) / len(s)
        if oran >= KALICI_ORAN:
            sinif = "kalici"
        else:
            sinif = "epizodik"
            sg = sorted(sapan)
            # tek seanslık: her sapan günün komşu seansları tolerans içinde ya da ayna imzalı çift; aksi hâlde aralıklı
            for g in sg:
                i = gun_ix[g]
                kom = [gunler[j] for j in (i - 1, i + 1) if 0 <= j < len(gunler)]
                if any(k in sapan for k in kom):
                    # ayna çifti (gecikme) tek arıza sayılır; başka biçimde komşu sapan aralıklıdır
                    eslesen = [k for k in kom if k in sapan and s[k][1] and sapan[g][1] and abs(s[k][1] * sapan[g][1] - 1) <= GECIKME_TOL]
                    if not eslesen:
                        sinif = "aralikli"; break
            if sinif == "epizodik" and len(sapan) > 3:
                sinif = "aralikli"
        fonlar[kod] = dict(sinif=sinif, sapanGun=len(sapan), gun=len(s), farkOrtanca=round(sorted(farklar)[len(farklar) // 2], 2),
                           farkEnKucuk=round(min(farklar), 2), farkEnBuyuk=round(max(farklar), 2))
        if sinif != "kalici":
            for g in sorted(sapan):
                fark, o, _ = sapan[g]
                imza = "diger"
                if o and (abs(o / 1000 - 1) <= BIRIM_HATASI_TOL or abs(o * 1000 - 1) <= BIRIM_HATASI_TOL):
                    imza = "birim_hatasi"
                else:
                    i = gun_ix[g]
                    for j in (i - 1, i + 1):
                        if 0 <= j < len(gunler) and gunler[j] in sapan and o and sapan[gunler[j]][1] and abs(o * sapan[gunler[j]][1] - 1) <= GECIKME_TOL:
                            imza = "bir_gunluk_gecikme"
                kayd = dict(fonKodu=kod, tarih=g, fark=round(fark, 2), oran=(round(o, 6) if o else None), imza=imza, sinif=sinif)
                i = gun_ix[g]
                onc = next((gunler[j] for j in range(i - 1, -1, -1) if gunler[j] in s and gunler[j] not in sapan), None)
                snr = next((gunler[j] for j in range(i + 1, len(gunler)) if gunler[j] in s and gunler[j] not in sapan), None)
                # M38: birim hatası onarımı; tek alan, kat 1000 ya da 0,001; kimlik sıfır sapmayla kapanır ve komşu seansla sürekli olur
                if imza == "birim_hatasi":
                    pay, fi, bu = ham[kod][g]
                    for alan, kat in ((("tedPaySayisi"), k) for k in ONARIM_KATLARI):
                        yeni = pay * kat
                        if abs(yeni * fi - bu) <= yeni * 0.5e-6 + 0.01 and any(k_ and abs(ham[kod][k_][0] - yeni) < 0.5 for k_ in (onc, snr)):
                            kayd["onarim"] = dict(alan=alan, eski=pay, yeni=yeni, kanit=f"pay × {kat:g} kimliği {tl(abs(yeni * fi - bu), 2)} TL sapmayla kapatır ve komşu seansın pay adedine eşittir")
                            break
                    if "onarim" not in kayd:
                        for kat in ONARIM_KATLARI:
                            yeni = bu * kat
                            komsu = [ham[kod][k_][2] for k_ in (onc, snr) if k_]
                            if abs(pay * fi - yeni) <= pay * 0.5e-6 + 0.01 and komsu and all(0.5 <= yeni / kb <= 2.0 for kb in komsu if kb > 0):
                                kayd["onarim"] = dict(alan="portfoyBuyukluk", eski=bu, yeni=yeni, kanit=f"büyüklük × {kat:g} kimliği {tl(abs(pay * fi - yeni), 2)} TL sapmayla kapatır ve komşu seansın büyüklüğüyle süreklidir")
                                break
                # M40: çöküşteki fonun arızası maskelenmez (onarım varsa uygulanır; onarım da bir maske değil ölçümdür)
                if kod in cokusler and "onarim" not in kayd and g >= min(c["tarih"] for c in cokusler[kod]):
                    kayd["maskele"] = False
                # M37: köprülemenin kaydırma üst sınırı: |pay_sonraki − pay_önceki| × |fiyat_sonraki − fiyat_arıza|
                if "onarim" not in kayd and kayd.get("maskele") is not False and onc and snr:
                    kayd["kaydirmaUstSinir"] = round(abs(ham[kod][snr][0] - ham[kod][onc][0]) * abs(ham[kod][snr][1] - ham[kod][g][1]), 2)
                arizalar.append(kayd)
    return dict(pencere=dict(bas=gunler[0] if gunler else None, bit=gunler[-1] if gunler else None, seans=len(gunler), fon=len(seriler)),
                fonlar=fonlar, arizalar=arizalar, kirilmalar=kirilmalar, cokusler=cokusler)


# ---------------------------------------------------------------- girdiler

def son_klasor():
    """Pozisyon defteri taşıyan en yeni günlük klasör; taban, defter ve köprü sınamaları 06 Pozisyonlar.json ister (13 Eylül 2026:
    10 Eylül klasörü yalnızca izleme dosyaları taşıdığı için en yeni klasör seçilince üç sınama ölçülemedi dönüyordu)."""
    k = sorted(glob.glob(os.path.join(RAPOR, "20??-??-??")), reverse=True)
    for x in k:
        if os.path.exists(os.path.join(x, "06 Pozisyonlar.json")):
            return x
    return k[0] if k else None


def icerik_yukle(yol):
    ac = gzip.open if yol.endswith(".gz") else open
    with ac(yol, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def icerik_bul(klasor_arsiv):
    """En yeni fon_icerik_YYYY-MM.csv.gz: önce verilen klasör, sonra 03 Veri/Arşiv, sonra ortam değişkeni FON_ANALIZ_DEPO/arsiv."""
    adaylar = []
    for k in (klasor_arsiv, os.path.join(KOK, "03 Veri", "Arşiv"), os.path.join(os.environ.get("FON_ANALIZ_DEPO", ""), "arsiv")):
        if k:
            adaylar += glob.glob(os.path.join(k, "fon_icerik_20??-??.csv.gz"))
    return sorted(adaylar, key=os.path.basename)[-1] if adaylar else None


# ---------------------------------------------------------------- sınamalar

def sinama_kimlik(L, rapor):
    ks = json_oku(os.path.join(KUNYE_KLASOR, "kapsam_son.json"), {})
    rapor.append("## 1. Kimlik sınaması: pay adedi × fiyat = büyüklük")
    rapor.append("")
    if not ks.get("sonGun"):
        rapor.append("Çekim kaydı (kapsam_son.json) yok; kimlik sınaması yapılamadı. [kayıt]")
        rapor.append(""); return {"durum": "olculemedi"}
    n = ks.get("kimlikSapmaSayisi", 0); sap = ks.get("kimlikSapanlar", [])
    rapor.append(f"Çekim {ks.get('cekimZamaniUtc')} UTC, son gün {ks['sonGun']}: {tl(ks['sonGunKayit'])} kayıt, fiyatsız {tl(ks['sonGunFiyatsiz'])}, "
                 f"tam kapsamlı son gün {ks.get('tamKapsamliSonGun')}. [kayıt, çekim anında ölçüm]")
    rapor.append(f"Kimlik sınamasından sapan fon: {tl(n)}. Tolerans pay adedi × 0,5e-6 + 0,01 TL (fiyat altı ondalıkla basılır). [ölçüm]")
    # tarama (30 numaralı not): son 52 seans, kalıcı / epizodik / aralıklı; epizodik fon-tarihler akış hesabından düşülür
    tara = kimlik_taramasi() if glob.glob(os.path.join(ARSIV, "tefas_????-??.csv.gz")) else dict(pencere={}, fonlar={}, arizalar=[])
    if tara["pencere"]:
        try:
            json.dump(tara, open(KIMLIK_ARIZA_YOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except OSError:
            pass
    fonlar = tara["fonlar"]; ariza_ix = {(a["fonKodu"], a["tarih"]): a for a in tara["arizalar"]}
    kal = sorted(k for k, v in fonlar.items() if v["sinif"] == "kalici")
    ara = sorted(k for k, v in fonlar.items() if v["sinif"] == "aralikli")
    epi = sorted(k for k, v in fonlar.items() if v["sinif"] == "epizodik")
    if tara["pencere"]:
        p = tara["pencere"]
        rapor.append(f"Tarama {p['bas']} ile {p['bit']} arası {tl(p['seans'])} seans, {tl(p['fon'])} fon: kalıcı {tl(len(kal))} ({', '.join(kal) or '-'}), "
                     f"aralıklı {tl(len(ara))} ({', '.join(ara) or '-'}), epizodik {tl(len(epi))}; arızalı fon-gün {tl(len(tara['arizalar']))} "
                     f"(epizodik {tl(len([a for a in tara['arizalar'] if a['sinif'] == 'epizodik']))}, aralıklı {tl(len([a for a in tara['arizalar'] if a['sinif'] == 'aralikli']))}) "
                     f"akış hesabından düşülür (kimlik_arizalari.json); kalıcı fonun günleri düşülmez. [ölçüm]")
        imzalar = {}
        for a in tara["arizalar"]:
            imzalar[a["imza"]] = imzalar.get(a["imza"], 0) + 1
        if imzalar:
            rapor.append("Arıza imzaları: " + ", ".join(f"{k} {tl(v)}" for k, v in sorted(imzalar.items())) + ". [ölçüm]")
        onar = [a for a in tara["arizalar"] if a.get("onarim")]
        kopr = [a for a in tara["arizalar"] if not a.get("onarim") and a.get("maskele") is not False]
        mask = [a for a in tara["arizalar"] if a.get("maskele") is False]
        rapor.append(f"Uygulama: onarılan {tl(len(onar))} (M38, tek alan, kimlik sıfır sapmayla kapanır), köprülenen {tl(len(kopr))} "
                     f"(M34; kaydırma üst sınırı toplam {tl(sum(a.get('kaydirmaUstSinir') or 0 for a in kopr), 2)} TL, M37), maskelenmeyen {tl(len(mask))} (M40, çöküş). [ölçüm]")
        for a in onar:
            o = a["onarim"]
            rapor.append(f"- Onarım {a['fonKodu']} {a['tarih']}: {o['alan']} {tl(o['eski'], 2)} yerine {tl(o['yeni'], 2)}; {o['kanit']}.")
        for kod, L_ in sorted((tara.get("cokusler") or {}).items()):
            for c in L_:
                rapor.append(f"- Çöküş {kod} {c['tarih']}: büyüklük {tl(c['onceki'], 2)} TL'den {tl(c['sonraki'], 2)} TL'ye, oran {c['oran']:.6f}; kimlik ne derse desin bildirilir, maskelenmez (M40).")
        kir = tara.get("kirilmalar") or []
        if kir:
            rapor.append(f"Seviye kırılması (M39, {tl(SEVIYE_KIRILMA_KAT, 0)} kat): {tl(len(kir))} fon-gün; " +
                         "; ".join(f"{k['fonKodu']} {k['tarih']} {k['alan']} ×{k['oran']:.4g}" for k in sorted(kir, key=lambda k: -max(k['oran'], 1 / max(k['oran'], 1e-12)))[:8]) + ". [ölçüm]")
    # istisna listesi (2.2, 30 numaralı not): yalnızca kalıcı fon listede durabilir; satır etiketi satırın kendi farkıyla ölçülür
    ist = {x["fonKodu"]: x for x in kimlik_istisna_yukle() if x.get("fonKodu")}
    kirmizi_sebep = []
    for kod, e in ist.items():
        if tara["pencere"] and fonlar.get(kod, {}).get("sinif") != "kalici":
            kirmizi_sebep.append(f"{kod} listede ama taramada kalıcı değil ({fonlar.get(kod, {}).get('sinif', 'sapmıyor')}); liste kaydı ölçümle çelişiyor")
    for kod in kal:
        if kod not in ist:
            kirmizi_sebep.append(f"{kod} taramada kalıcı ({fonlar[kod]['sapanGun']}/{fonlar[kod]['gun']} gün, ortanca {tl(fonlar[kod]['farkOrtanca'], 2)} TL) ama listede yok")
    def etiket(kod, g, fark):
        e = ist.get(kod)
        if e:
            return "bilinen" if abs(fark - float(e.get("fark") or 0)) <= float(e.get("tolerans") or 0) else "TOLERANS AŞILDI"
        a = ariza_ix.get((kod, g))
        if a:
            return f"besleme arızası ({a['imza']})" if a["sinif"] == "epizodik" else "aralıklı"
        return "yeni"
    sayac = {}
    if sap:
        rapor.append("")
        rapor.append("| Tarih | Fon | Pay × fiyat | Büyüklük | Fark | Etiket |")
        rapor.append("|---|---|---|---|---|---|")
        for s in sorted(sap, key=lambda s: -abs(s["payXfiyat"] - s["buyukluk"]))[:25]:
            f = round(s["payXfiyat"] - s["buyukluk"], 2); et = etiket(s["fonKodu"], s["tarih"], f)
            sayac[et.split(" (")[0]] = sayac.get(et.split(" (")[0], 0) + 1
            rapor.append(f"| {s['tarih']} | {s['fonKodu']} | {tl(s['payXfiyat'], 2)} | {tl(s['buyukluk'], 2)} | {tl(f, 2)} | {et} |")
        rapor.append("")
        rapor.append("Sapma sıfır çıkmadan bu fonlarda akış hesabı kullanılmaz (beceri bölüm 2); epizodik arıza günü akış hesabından düşülmüştür.")
    for kod in ara:
        v = fonlar[kod]
        sapma_ekle(L, f"kimlik-aralikli-{kod}", f"{kod} kimlik farkı aralıklı: {v['sapanGun']}/{v['gun']} günde sapıyor, ne kalıcı ne tek seanslık",
                   None, None, OLCUM, None, f"aralık {tl(v['farkEnKucuk'], 2)} ile {tl(v['farkEnBuyuk'], 2)} TL; sebebi kurucudan ya da TEFAS'tan sorulmalı", sinif="arastirma")
    if kirmizi_sebep:
        for s in kirmizi_sebep:
            rapor.append(f"- {s}.")
    if ist:
        rapor.append(f"İstisna listesi ({os.path.basename(KIMLIK_ISTISNA_YOL)}): {tl(len(ist))} fon ({', '.join(sorted(ist))}); satır etiketleri: "
                     + ", ".join(f"{k} {tl(v)}" for k, v in sorted(sayac.items())) + ". [kayıt]")
    rapor.append("")
    if not n and not kirmizi_sebep:
        durum = "yesil"
    elif kirmizi_sebep or sayac.get("TOLERANS AŞILDI") or sayac.get("yeni"):
        durum = "kirmizi"
    else:
        durum = "sari"
    return {"durum": durum, "sapan": n, "kalici": kal, "aralikli": ara, "epizodik": len(epi), "etiketler": sayac, "celisen": kirmizi_sebep,
            "onarilan": len(onar) if tara["pencere"] else 0, "cokus": sorted((tara.get("cokusler") or {}).keys()), "kirilma": len(tara.get("kirilmalar") or [])}


def sinama_taban(L, rapor, klasor, tarih):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    bri = json_oku(os.path.join(klasor, "01 Brifing Verisi.json"), None)
    rapor.append("## 2. Portföy tabanı mutabakatı")
    rapor.append("")
    if not poz:
        rapor.append("06 Pozisyonlar.json yok; taban mutabakatı yapılamadı. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    defter = {(v.get("kurum", ""), v["kod"]): float(v.get("deger") or 0) for v in poz.values()}
    taban_defter = round(sum(defter.values()), 2)
    rapor.append(f"Pozisyon defteri ({os.path.basename(klasor)}, {len(defter)} pozisyon): toplam {tl(taban_defter, 2)} TL. [kayıt, 06 Pozisyonlar.json]")
    if not bri or not bri.get("pozisyon"):
        rapor.append("01 Brifing Verisi.json yok; brifingin tabanı karşılaştırılamadı."); rapor.append("")
        return {"durum": "olculemedi", "tabanDefter": taban_defter}
    bpoz = {(x.get("kurum", ""), x["kod"]): float(x.get("deger") or 0) for x in bri["pozisyon"]}
    taban_bri = round(sum(bpoz.values()), 2)
    fark = round(taban_defter - taban_bri, 2)
    rapor.append(f"Brifingin dayandığı taban (pozisyon listesi toplamı): {tl(taban_bri, 2)} TL. [kayıt, 01 Brifing Verisi.json]")
    rapor.append(f"Fark (defter − brifing): {tl(fark, 2)} TL. [hesaplama]")
    # kurum adlari iki kaynakta farkli yazilabilir (kisa ad / tam unvan): kodla eslestir, kurumu ilk alti harfe indirgeyip normalize et
    def norm_k(k):
        k = k.lower().replace("ı", "i").replace("ş", "s").replace("İ", "i")
        return (re.sub(r"bank.*$", "", k).strip()[:6] or k.strip()[:6])
    d2 = {}
    for (k, kod), v in defter.items(): d2[(norm_k(k), kod)] = d2.get((norm_k(k), kod), 0) + v
    b2 = {}
    for (k, kod), v in bpoz.items(): b2[(norm_k(k), kod)] = b2.get((norm_k(k), kod), 0) + v
    satirlar = []
    for a in sorted(set(d2) | set(b2)):
        dv, bv = d2.get(a), b2.get(a)
        if dv is None or bv is None or abs(dv - bv) > TABAN_TOLERANS_TL:
            satirlar.append((a, dv, bv))
    if satirlar:
        rapor.append("")
        rapor.append("| Kurum | Fon | Defter | Brifing | Fark |")
        rapor.append("|---|---|---|---|---|")
        for (k, kod), dv, bv in satirlar:
            rapor.append(f"| {k} | {kod} | {tl(dv, 2) if dv is not None else '-'} | {tl(bv, 2) if bv is not None else '-'} | "
                         f"{tl((dv or 0) - (bv or 0), 2)} |")
    sonuc = {"tabanDefter": taban_defter, "tabanBrifing": taban_bri, "fark": fark}
    if abs(fark) <= TABAN_TOLERANS_TL:
        rapor.append(""); return dict(sonuc, durum="yesil")
    # 2. adım (finance değerlendirmesi 2.4): fark bir değerleme tarihi farkı mı? deger/adet oranı TEFAS'ta hangi güne eşit,
    # defter brifingin fiyat gününe çekilince fark sıfır çıkıyor mu. Sıfır çıkarsa kayıt hesap çıktısıyla kapanır; sözle değil.
    try:
        gun = date.fromisoformat(tarih)
    except ValueError:
        gun = date.today()
    kodlar = {v["kod"] for v in poz.values()}
    F = fiyat_serisi(kodlar, _aylar(date.fromordinal(gun.toordinal() - 45), gun))
    bri_poz = {f"b{i}": x for i, x in enumerate(bri["pozisyon"])}
    dt_defter = degerleme_tarihi(poz, F, tarih); dt_bri = degerleme_tarihi(bri_poz, F, tarih)
    g_defter = sorted({g for g in dt_defter.values() if g}); g_bri = sorted({g for g in dt_bri.values() if g})
    rapor.append(f"Değerleme tarihi (deger/adet oranının TEFAS fiyatıyla eşleştiği gün): defter {', '.join(g_defter) or 'eşleşme yok'}; "
                 f"brifing {', '.join(g_bri) or 'eşleşme yok'}. Eşleşmeyen pozisyon: defter {tl(sum(1 for g in dt_defter.values() if not g))}, "
                 f"brifing {tl(sum(1 for g in dt_bri.values() if not g))}. [hesaplama]")
    sonuc.update(degerlemeDefter=g_defter, degerlemeBrifing=g_bri)
    # pozisyon pozisyon: her pozisyonun kendi değerleme tarihi çifti farkını açıklıyor mu (13 Eylül 2026 ölçümü: defter 4 ve 7 Eylül,
    # brifing 7 ve 8 Eylül fiyatlarını karışık taşır; tek tarih çifti yoktur). Açıklanan = adet × (fiyat(brifing günü) − fiyat(defter günü)).
    def anahtar(v):
        return (norm_k(v.get("kurum", "")), v["kod"])
    bd = {anahtar(v): (v, dt_defter[k]) for k, v in poz.items()}
    bb = {anahtar(x): (x, dt_bri[k]) for k, x in bri_poz.items()}
    aciklanan, aciklanamayan, satirlar2 = 0.0, [], []
    for a in sorted(set(bd) | set(bb)):
        vd, gd = bd.get(a, (None, None)); vb, gb = bb.get(a, (None, None))
        f_defter = float(vd.get("deger") or 0) if vd else 0.0
        f_bri = float(vb.get("deger") or 0) if vb else 0.0
        fark_i = round(f_defter - f_bri, 2)
        if abs(fark_i) <= TABAN_TOLERANS_TL:
            continue
        if vd and vb and gd and gb:
            adet = float(vd.get("adet") or 0)
            bekl = round(adet * (F[vd["kod"]][gd] - F[vd["kod"]][gb]), 2)   # defter − brifing yönünde
            kalan = round(fark_i - bekl, 2)
            aciklanan += bekl
            satirlar2.append((a, gd, gb, fark_i, bekl, kalan))
            if abs(kalan) > TABAN_TOLERANS_TL:
                aciklanamayan.append((a, kalan, f"tarih farkı {tl(bekl, 2)} TL açıklıyor, {tl(kalan, 2)} TL açıklamıyor"))
        else:
            sebep = "fiyat eşleşmedi" + ("" if vd and vb else "; pozisyon tek tarafta var")
            yakin = []
            for etiket, v_, g_ in (("defter", vd, gd), ("brifing", vb, gb)):
                if v_ and not g_:
                    y = en_yakin_gun(v_, F, tarih)
                    if y:
                        yakin.append(f"{etiket} en yakın {y[0]}, pay başına {tl(y[1], 4)} TL")
            if yakin:
                sebep += "; " + ", ".join(yakin)
            satirlar2.append((a, gd or "-", gb or "-", fark_i, None, fark_i))
            aciklanamayan.append((a, fark_i, sebep))
    if satirlar2:
        rapor.append("")
        rapor.append("| Kurum | Fon | Defter günü | Brifing günü | Fark | Tarih farkının açıkladığı | Kalan |")
        rapor.append("|---|---|---|---|---|---|---|")
        for (k, kod), gd, gb, fi, bekl, kalan in satirlar2:
            rapor.append(f"| {k} | {kod} | {gd} | {gb} | {tl(fi, 2)} | {tl(bekl, 2) if bekl is not None else '-'} | {tl(kalan, 2)} |")
    kalan_toplam = round(fark - aciklanan, 2)
    rapor.append(f"Değerleme tarihi farklarının açıkladığı toplam {tl(aciklanan, 2)} TL; kalan {tl(kalan_toplam, 2)} TL"
                 f"{' (' + ', '.join(kod for (k, kod), _, _ in aciklanamayan) + ')' if aciklanamayan else ''}. [hesaplama]")
    for (k, kod), kal, s in aciklanamayan:
        rapor.append(f"- {k} {kod}: kalan {tl(kal, 2)} TL; {s}.")
    sonuc.update(tarihFarkiAciklanan=round(aciklanan, 2), kalanFark=kalan_toplam,
                 aciklanamayan=[dict(kurum=k, kod=kod, kalan=kal, sebep=s) for (k, kod), kal, s in aciklanamayan])
    if not aciklanamayan and abs(kalan_toplam) <= TABAN_TOLERANS_TL:
        kanit = (f"değerleme tarihi farkı, pozisyon pozisyon yeniden üretildi: defter günleri {', '.join(g_defter)}, brifing günleri "
                 f"{', '.join(g_bri)}; tarih farklarının açıkladığı {tl(aciklanan, 2)} TL, kalan {tl(kalan_toplam, 2)} TL (denetim.py, {tarih})")
        sapma_ekle(L, f"taban-{tarih}", "portföy tabanı: defter toplamı ile brifing tabanı", taban_bri, taban_defter, KAYIT, tarih,
                   "değerleme tarihi farkı", sinif="zamanlama")
        sapma_kapat_bellekte(L, f"taban-{tarih}", kanit, tarih)
        rapor.append("Sapma kapandı: fark yalnızca değerleme tarihlerinden geliyor, pozisyon pozisyon yeniden üretildi. [hesaplama]")
        rapor.append(""); return dict(sonuc, durum="yesil", kapanis="yeniden_uretildi")
    sapma_ekle(L, f"taban-{tarih}", "portföy tabanı: defter toplamı ile brifing tabanı", taban_bri, taban_defter, KAYIT, tarih,
               f"değerleme tarihi farkları {tl(aciklanan, 2)} TL açıklıyor; kalan {tl(kalan_toplam, 2)} TL şu pozisyonlarda: "
               + "; ".join(f"{k}-{kod} {tl(kal, 2)} TL ({s})" for (k, kod), kal, s in aciklanamayan), sinif="zamanlama" if aciklanan else "arastirma")
    rapor.append("")
    return dict(sonuc, durum="kirmizi")


def sinama_bakis(L, rapor, klasor, tarih, icerik_yol, isimler, bildirilen):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    rapor.append("## 3. Bakış geçirgen maruziyet")
    rapor.append("")
    if not poz:
        rapor.append("06 Pozisyonlar.json yok. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    if not icerik_yol:
        rapor.append("Fon içerik arşivi (fon_icerik_YYYY-MM.csv.gz) bulunamadı; bakış geçirgen maruziyet hesaplanamadı. [kayıt]")
        rapor.append(""); return {"durum": "olculemedi"}
    ic = icerik_yukle(icerik_yol)
    listeler = {}
    for r in ic:
        listeler.setdefault(r["fonKodu"], []).append(r)
    taban = sum(float(v.get("deger") or 0) for v in poz.values())
    dogrudan = sum(float(v.get("deger") or 0) for v in poz.values() if (v.get("tip") or "").lower().startswith("hisse"))
    ic_hisse = 0.0; ic_tek = {ad: 0.0 for ad in isimler}; eksik = []; liste_eksik = []
    for v in poz.values():
        if (v.get("tip") or "").lower().startswith("hisse"):
            for ad in isimler:
                if any(t.lower() in (v.get("ad") or "").lower() or t.upper() == v["kod"] for t in ad.split("|")):
                    ic_tek[ad] += float(v.get("deger") or 0)
            continue
        Lk = listeler.get(v["kod"])
        if not Lk:
            eksik.append(v["kod"]); continue
        deger = float(v.get("deger") or 0)
        if any((r.get("listeTam") or "true").lower() == "false" for r in Lk):
            liste_eksik.append(v["kod"])
        for r in Lk:
            a = float(r.get("agirlik") or 0) / 100.0
            if HISSE_TUR.search(r.get("tur") or ""):
                ic_hisse += deger * a
            # tek isim: takma adlar '|' ile ayrilir (DESTEK FAKTORİNG|DESTEK FİNANS|DSTKF); ad alanlari ve BIST kodu taranir
            metin = ((r.get("kiymetAdiHam") or "") + " " + (r.get("ihracci") or "") + " " + (r.get("kiymetAdi") or "")).upper()
            for ad in isimler:
                if any(t.upper() in metin or t.upper() == (r.get("bistKodu") or "").upper() for t in ad.split("|")):
                    ic_tek[ad] += deger * a
    hisse_toplam = dogrudan + ic_hisse
    rapor.append(f"İçerik arşivi: {os.path.basename(icerik_yol)} ({len(listeler)} fon). Taban: pozisyon defteri toplamı {tl(taban, 2)} TL. [kayıt]")
    rapor.append(f"Doğrudan hisse {tl(dogrudan, 2)} TL + fon içindeki hisse {tl(ic_hisse, 2)} TL = {tl(hisse_toplam, 2)} TL, "
                 f"tabanın {yuzde(hisse_toplam / taban) if taban else '-'}. [hesaplama; içerik ağırlıkları KAP ay sonu raporundan, kayıt]")
    if eksik:
        rapor.append(f"İçerik listesi olmayan fon: {', '.join(sorted(set(eksik)))}; bu fonların içi bakışta yok, maruziyet eksik sayılır. [kayıt]")
    if liste_eksik:
        rapor.append(f"Listesi eksik işaretli fon (listeTam=false): {', '.join(sorted(set(liste_eksik)))}. [kayıt]")
    for ad, v in ic_tek.items():
        rapor.append(f"Tek isim {ad}: {tl(v, 2)} TL, tabanın {yuzde(v / taban) if taban else '-'}. [hesaplama]")
    durum = "yesil"
    for anah, hes in (("bakisGecirgenHisse", hisse_toplam),) + tuple((f"tekIsim:{ad}", v) for ad, v in ic_tek.items()):
        bil = bildirilen.get(anah)
        if bil is not None:
            fark = round(hes - bil, 2)
            rapor.append(f"Bildirilen {anah}: {tl(bil, 2)} TL; yeniden hesap {tl(hes, 2)} TL; fark {tl(fark, 2)} TL. [hesaplama]")
            if abs(fark) > TABAN_TOLERANS_TL:
                durum = "kirmizi"
                sapma_ekle(L, f"{anah}-{tarih}", f"bakış geçirgen maruziyet: {anah}", bil, round(hes, 2), HESAP, tarih)
        else:
            rapor.append(f"Bildirilen {anah} verilmedi (--bildirilen {anah}=<TL>); karşılaştırma yapılmadı.")
    rapor.append("")
    return {"durum": durum, "hisseToplam": round(hisse_toplam, 2), "tekIsim": {k: round(v, 2) for k, v in ic_tek.items()}}


def sinama_defter(L, rapor, klasor, tarih):
    poz = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    em = json_oku(os.path.join(klasor, "05 Emirler.json"), None)
    bri = json_oku(os.path.join(klasor, "01 Brifing Verisi.json"), None)
    rapor.append("## 4. Defter tutarlılığı")
    rapor.append("")
    if not poz or not em:
        rapor.append("05 Emirler.json ya da 06 Pozisyonlar.json yok. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    say = {}
    for v in em.values():
        say[v.get("durum")] = say.get(v.get("durum"), 0) + 1
    rapor.append("Emir defteri: " + ", ".join(f"{k} {n}" for k, n in sorted(say.items())) + ". [kayıt]")
    kirmizi = False
    # gerceklesen emirlerde gerceklesen adet ve fiyat yazili mi
    eksik = [k for k, v in em.items() if v.get("durum") == "GERCEKLESTI" and (v.get("gerceklesen_adet") in (None, "") or v.get("gerceklesen_fiyat") in (None, ""))]
    if eksik:
        kirmizi = True
        rapor.append(f"Gerçekleşti yazılmış ama gerçekleşen adet ya da fiyatı olmayan emir: {', '.join(eksik)}. [kayıt]")
    # bankaya girilmis, tarihi gecmis ve hala bekleyen emirler
    gec = [k for k, v in em.items() if v.get("durum") == "BEKLIYOR" and v.get("verildi") and str(v.get("tarih", "")) < tarih]
    if gec:
        rapor.append(f"Tarihi geçmiş ve hâlâ bekleyen emir: {', '.join(gec)}; ertesi sabah brifingin en üstünde görünmeli. [kayıt]")
    # yinelenme şüphesi (2.7): aynı gün, aynı kurum, aynı fon, aynı yön, aynı adet, iptal değil
    grup = {}
    for k, v in em.items():
        if v.get("durum") == "IPTAL":
            continue
        a = (str(v.get("tarih")), str(v.get("kurum")), str(v.get("kod")), str(v.get("yon")), str(v.get("adet")))
        grup.setdefault(a, []).append(k)
    yinelenen = [ks for ks in grup.values() if len(ks) > 1]
    if yinelenen:
        kirmizi = True
        rapor.append("Yinelenme şüphesi (aynı gün, kurum, fon, yön ve adet): " + "; ".join(", ".join(ks) for ks in yinelenen) + ". [kayıt]")
    # kaynak belge (2.7): alan defterde varsa gerçekleşen emirde boş olamaz; alan hiç yoksa sözleşme kararı beklenir, kırmızı sayılmaz
    if any("kaynakBelge" in v for v in em.values()):
        bos = [k for k, v in em.items() if v.get("durum") == "GERCEKLESTI" and not v.get("kaynakBelge")]
        if bos:
            kirmizi = True
            rapor.append(f"Gerçekleşmiş ama kaynak belgesi (ekran görüntüsü) yazılmamış emir: {', '.join(bos)}. [kayıt]")
    else:
        rapor.append("Emir kaydında kaynakBelge alanı yok; ekran görüntüsü bağı sınanamadı (defter sözleşmesi, kullanıcı kararı bekliyor). [kayıt]")
    # pozisyon adetleri: defter ile brifing pozisyon listesi
    if bri and bri.get("pozisyon"):
        def norm_k(k):
            k = k.lower().replace("ı", "i").replace("ş", "s").replace("İ", "i")
            return (re.sub(r"bank.*$", "", k).strip()[:6] or k.strip()[:6])
        d = {}
        for v in poz.values(): d[(norm_k(v.get("kurum", "")), v["kod"])] = d.get((norm_k(v.get("kurum", "")), v["kod"]), 0) + float(v.get("adet") or 0)
        b = {}
        for x in bri["pozisyon"]: b[(norm_k(x.get("kurum", "")), x["kod"])] = b.get((norm_k(x.get("kurum", "")), x["kod"]), 0) + float(x.get("adet") or 0)
        farkli = [(a, d.get(a), b.get(a)) for a in sorted(set(d) | set(b)) if d.get(a) != b.get(a)]
        if farkli:
            kirmizi = True
            rapor.append("")
            rapor.append("| Kurum | Fon | Defter adet | Brifing adet |")
            rapor.append("|---|---|---|---|")
            for (k, kod), dv, bv in farkli:
                rapor.append(f"| {k} | {kod} | {tl(dv) if dv is not None else '-'} | {tl(bv) if bv is not None else '-'} |")
            sapma_ekle(L, f"defter-adet-{tarih}", "defter pozisyon adetleri ile brifing pozisyon adetleri", None, None, KAYIT, tarih,
                       "; ".join(f"{k}-{kod}: defter {dv}, brifing {bv}" for (k, kod), dv, bv in farkli))
        else:
            rapor.append("Pozisyon adetleri defter ile brifingde birebir. [kayıt]")
    rapor.append("")
    return {"durum": "kirmizi" if kirmizi else "yesil"}


def onceki_klasor(klasor):
    """Verilen günlük klasörden önceki, 06 Pozisyonlar.json taşıyan en yeni klasör."""
    ad = os.path.basename(klasor)
    for k in sorted(glob.glob(os.path.join(os.path.dirname(klasor), "20??-??-??")), reverse=True):
        if os.path.basename(k) < ad and os.path.exists(os.path.join(k, "06 Pozisyonlar.json")):
            return k
    return None


def sinama_kopru(L, rapor, klasor, tarih, disa=None):
    """5. Günlük köprü (2.5): dünkü toplam + fiyat etkisi + işlem etkisi (+ eşleşmeyen pozisyonlar) = bugünkü toplam.
    Fiyat etkisi: dünkü adet × (bugünkü değerleme günü fiyatı − dünkü değerleme günü fiyatı). İşlem etkisi: iki tarih arasında
    gerçekleşen emirlerin gerçekleşen adet × fiyat tutarı (alış +, satış −); gerçekleşen fiyat yoksa bugünkü fiyat varsayılır ve yazılır.
    Defter teyit hâli: bugünkü pozisyonların değerleme günü klasör tarihinden eskiyse "defter teyit edilmedi"; köprü yazılır, sapma açılmaz."""
    rapor.append("## 5. Günlük köprü")
    rapor.append("")
    if disa is None:
        disa = disa_aktarimi_klasore_yaz()
    rapor.append(f"Dışa aktarım yakıtı: {disa['durum']}; {disa['sebep']}. [kayıt]")   # M36: dört hâl ayrı ayrı görünür
    poz1 = json_oku(os.path.join(klasor, "06 Pozisyonlar.json"), None)
    onceki = onceki_klasor(klasor)
    if not poz1 or not onceki:
        rapor.append("Bugünkü ya da önceki günün pozisyon dosyası yok; köprü kurulamadı. [kayıt]"); rapor.append(""); return {"durum": "olculemedi"}
    poz0 = json_oku(os.path.join(onceki, "06 Pozisyonlar.json"), {})
    t0, t1 = os.path.basename(onceki), tarih
    em_yol = os.path.join(klasor, "05 Emirler.json")
    em = json_oku(em_yol, {}) or {}
    try:
        gun = date.fromisoformat(t1)
    except ValueError:
        gun = date.today()
    kodlar = {v["kod"] for v in list(poz0.values()) + list(poz1.values())}
    F = fiyat_serisi(kodlar, _aylar(date.fromordinal(gun.toordinal() - 45), gun))
    d0 = degerleme_tarihi(poz0, F, t0); d1 = degerleme_tarihi(poz1, F, t1)
    g0 = sorted({g for g in d0.values() if g}); g1 = sorted({g for g in d1.values() if g})
    top0 = round(sum(float(v.get("deger") or 0) for v in poz0.values()), 2)
    top1 = round(sum(float(v.get("deger") or 0) for v in poz1.values()), 2)
    rapor.append(f"Önceki gün {t0}: {tl(len(poz0))} pozisyon, toplam {tl(top0, 2)} TL, değerleme günü {', '.join(g0) or 'eşleşme yok'}. [kayıt]")
    rapor.append(f"Bugün {t1}: {tl(len(poz1))} pozisyon, toplam {tl(top1, 2)} TL, değerleme günü {', '.join(g1) or 'eşleşme yok'}. [kayıt]")
    if len(g0) != 1 or len(g1) != 1:
        rapor.append("Değerleme günü tek değil ya da eşleşmedi; köprü kurulamadı, pozisyonlar tek tek incelenmeli. [hesaplama]"); rapor.append("")
        return {"durum": "olculemedi", "toplamOnceki": top0, "toplamBugun": top1}
    if not os.path.exists(em_yol):
        adet_degisti = any(float(poz0[k].get("adet") or 0) != float(poz1[k].get("adet") or 0) for k in poz0 if k in poz1) or set(poz0) != set(poz1)
        if adet_degisti:
            rapor.append("Emir dosyası (05 Emirler.json) yok ve adetler değişmiş; işlem etkisi ölçülemez, köprü kurulamadı. [kayıt]"); rapor.append("")
            return {"durum": "olculemedi", "toplamOnceki": top0, "toplamBugun": top1, "sebep": "emir dosyası yok"}
    from takvim import son_is_gunu
    son_is = son_is_gunu(t1).isoformat()                                          # ölçüt takvimdir, arşivin son günü değil (30 numaralı not, madde 4)
    arsiv_son = max((g for k in F for g in F[k] if g <= t1), default=None)
    teyit = g1[0] >= son_is
    if arsiv_son is not None and arsiv_son < son_is:
        rapor.append(f"Arşivin son fiyat günü {arsiv_son}, takvimin son iş günü {son_is}: arşiv eski; teyit bu yüzden ölçülemez, köprü bilgi amaçlıdır. [ölçüm]")
        teyit = False
    # fiyat etkisi: dünkü adetler, iki değerleme günü arası fiyat farkı
    fiyat_etkisi, eslesmeyen = 0.0, []
    for k, v in poz0.items():
        f0 = F.get(v["kod"], {}).get(g0[0]); f1 = F.get(v["kod"], {}).get(g1[0])
        if f0 is None or f1 is None:
            eslesmeyen.append(k); continue
        fiyat_etkisi += float(v.get("adet") or 0) * (f1 - f0)
    # işlem etkisi: (t0, t1] aralığında gerçekleşen emirler
    islem, varsayim, islemler = 0.0, [], []
    for k, v in em.items():
        if v.get("durum") != "GERCEKLESTI" or not (t0 < str(v.get("tarih", "")) <= t1):
            continue
        adet = float(v.get("gerceklesen_adet") or v.get("adet") or 0)
        fi = v.get("gerceklesen_fiyat")
        if fi in (None, ""):
            fi = F.get(v.get("kod"), {}).get(g1[0]); varsayim.append(k)
        if fi is None:
            eslesmeyen.append(k); continue
        yon = -1.0 if str(v.get("yon", "")).upper().startswith("SAT") else 1.0
        islem += yon * adet * float(fi); islemler.append(k)
    # eşleşmeyen pozisyonların (bugün var dün yok ya da tersi) katkısı
    yeni = round(sum(float(poz1[k].get("deger") or 0) for k in poz1 if k not in poz0), 2)
    giden = round(sum(float(poz0[k].get("deger") or 0) for k in poz0 if k not in poz1), 2)
    artik = round(top1 - (top0 + fiyat_etkisi + islem), 2)
    rapor.append("")
    rapor.append("| Kalem | TL | Künye |")
    rapor.append("|---|---|---|")
    rapor.append(f"| Önceki gün toplamı | {tl(top0, 2)} | kayıt |")
    rapor.append(f"| Fiyat etkisi ({g0[0]} → {g1[0]}) | {tl(fiyat_etkisi, 2)} | hesaplama |")
    rapor.append(f"| İşlem etkisi ({tl(len(islemler))} emir{', gerçekleşen fiyatı olmayan ' + ', '.join(varsayim) + ' bugünkü fiyatla' if varsayim else ''}) | {tl(islem, 2)} | {'varsayım' if varsayim else 'kayıt'} |")
    rapor.append(f"| Bugünkü toplam | {tl(top1, 2)} | kayıt |")
    rapor.append(f"| Artık | {tl(artik, 2)} | hesaplama |")
    if yeni or giden:
        rapor.append(f"| Bugün yeni pozisyon {tl(yeni, 2)}, dün olup bugün olmayan {tl(giden, 2)} | - | kayıt |")
    rapor.append("")
    if eslesmeyen:
        rapor.append(f"Fiyatı bulunamayan pozisyon ya da emir: {', '.join(eslesmeyen)}; köprü bunları açıklamaz. [kayıt]")
    sonuc = dict(toplamOnceki=top0, toplamBugun=top1, fiyatEtkisi=round(fiyat_etkisi, 2), islemEtkisi=round(islem, 2), artik=artik,
                 degerlemeOnceki=g0[0], degerlemeBugun=g1[0], teyit=bool(teyit))
    if not teyit:
        rapor.append(f"Defter bugün teyit edilmedi: bugünkü pozisyonlar {g1[0]} fiyatıyla duruyor, klasör tarihi {t1}. Köprü bilgi amaçlıdır, sapma açılmaz. [kayıt]")
        rapor.append(""); return dict(sonuc, durum="teyitsiz")
    if abs(artik) > TABAN_TOLERANS_TL:
        sapma_ekle(L, f"kopru-{t1}", f"günlük köprü artığı ({t0} → {t1})", round(top0 + fiyat_etkisi + islem, 2), top1, HESAP, t1,
                   "dünkü toplam + fiyat etkisi + işlem etkisi bugünkü toplama eşit değil; kalan tutarın pozisyonu bulunmalı", sinif="arastirma")
        rapor.append(""); return dict(sonuc, durum="kirmizi")
    rapor.append("Artık sıfır: bugünkü değer dünkü değer, fiyat ve işlemlerle açıklanıyor. [hesaplama]")
    rapor.append(""); return dict(sonuc, durum="yesil")


# ---------------------------------------------------------------- ana

def calistir(klasor, icerik_yol, isimler, bildirilen):
    tarih = os.path.basename(klasor) if klasor else date.today().isoformat()
    L = sapma_yukle()
    rapor = [f"# Denetim raporu, {tarih}", "",
             "Her sayının künyesi köşeli ayraç içindedir: ölçüm, kayıt, hesaplama, varsayım, projeksiyon. "
             "Sapma ancak sebebi kanıtlanınca kapanır (denetim.py --kapat <id> --kanit ...).", ""]
    s1 = sinama_kimlik(L, rapor)
    s2 = sinama_taban(L, rapor, klasor, tarih) if klasor else {"durum": "olculemedi"}
    s3 = sinama_bakis(L, rapor, klasor, tarih, icerik_yol, isimler, bildirilen) if klasor else {"durum": "olculemedi"}
    s4 = sinama_defter(L, rapor, klasor, tarih) if klasor else {"durum": "olculemedi"}
    s5 = sinama_kopru(L, rapor, klasor, tarih) if klasor else {"durum": "olculemedi"}
    if s5.get("durum") == "olculemedi" and not klasor:
        s5["disa"] = disa_aktarimi_klasore_yaz()
    bugun = date.today()   # yaş bugüne göre ölçülür; klasör tarihi verinin tarihidir, denetimin değil
    acik = [s for s in L if s["durum"] == "acik"]
    asan = []
    rapor.append("## Açık sapmalar")
    rapor.append("")
    if not acik:
        rapor.append("Açık sapma yok.")
    for s in acik:
        b = tl(s["bildirilen"], 2) if isinstance(s.get("bildirilen"), (int, float)) else "-"
        h = tl(s["hesaplanan"], 2) if isinstance(s.get("hesaplanan"), (int, float)) else "-"
        f = tl(s["fark"], 2) if isinstance(s.get("fark"), (int, float)) else "-"
        yas = sapma_yasi(s, bugun)
        if yas is not None and yas > SAPMA_YAS_ESIK_IS_GUNU:
            asan.append(s["id"])
        rapor.append(f"- `{s['id']}` ({s['tarih']}, {s.get('sinif', 'sınıfsız')}, {tl(yas) if yas is not None else '?'} iş günü"
                     f"{', ESKİ' if yas is not None and yas > SAPMA_YAS_ESIK_IS_GUNU else ''}): {s['olcum']}; bildirilen {b}, hesaplanan {h}, fark {f}. [{s.get('kunye', '')}]"
                     + (f" {s['not']}" if s.get("not") else ""))
    if asan:
        rapor.append("")
        rapor.append(f"Yaş eşiğini ({SAPMA_YAS_ESIK_IS_GUNU} iş günü) aşan açık sapma: {', '.join(asan)}. [hesaplama]")
    rapor.append("")
    durumlar = {"kimlik": s1["durum"], "taban": s2["durum"], "bakisGecirgen": s3["durum"], "defter": s4["durum"], "kopru": s5["durum"]}
    genel = "kirmizi" if "kirmizi" in durumlar.values() or acik else ("olculemedi" if "olculemedi" in durumlar.values() else ("sari" if "sari" in durumlar.values() else "yesil"))
    rapor.insert(2, f"**Genel durum: {genel}.** Sınamalar: " + ", ".join(f"{k} {v}" for k, v in durumlar.items()) + f". Açık sapma: {len(acik)}"
                 + (f", yaş eşiğini aşan {len(asan)}" if asan else "") + ".")
    sapma_yaz(L)
    ozet = dict(tarih=tarih, genel=genel, sinamalar=durumlar, acikSapma=len(acik), yasEsigiAsan=asan, kimlikSapan=s1.get("sapan"),
                kimlikIstisnaBilinen=s1.get("istisnaBilinen"), kimlikIstisnaBozulan=s1.get("istisnaBozulan"), kimlikYeniSapan=s1.get("yeniSapan"),
                tabanDefter=s2.get("tabanDefter"), tabanBrifing=s2.get("tabanBrifing"), tabanFark=s2.get("fark"), tabanKapanis=s2.get("kapanis"),
                kopru={k: s5.get(k) for k in ("durum", "artik", "fiyatEtkisi", "islemEtkisi", "teyit", "degerlemeOnceki", "degerlemeBugun")},
                hisseToplam=s3.get("hisseToplam"), tekIsim=s3.get("tekIsim"))
    json.dump(ozet, open(os.path.join(VERI_KOK, "denetim_son.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    metin = "\n".join(rapor)
    if klasor and VERI_KOK == os.path.join(KOK, "03 Veri"):
        open(os.path.join(klasor, "Denetim.md"), "w", encoding="utf-8").write(metin)
    return metin, genel


def disa_aktarimi_klasore_yaz(disa=None, rapor_kok=None):
    """Akşam görevinin yazdığı defter dışa aktarımı (olcumZamani, pozisyonlar, nakit) o günün klasörüne 06 Pozisyonlar.json olarak
    kopyalanır; köprünün yakıtı budur (30 numaralı not, madde 3). Dört hâl ayrı ayrı bildirilir (M36): dosya yok; belge geçersiz
    (hata listesiyle); yazıldı; hedef zaten var. Hedef varsa yanındaki `06 Pozisyonlar.kaynak.json` damgasına bakılır: dışa aktarım
    daha yeni bir olcumZamani taşıyorsa üstüne yazılır ve eski damga bildirilir (aynı gün düzeltilen defter klasöre ulaşır);
    damga yoksa dosya başka kaynaktan (bulut görevinin klasörü) gelmiştir, üstüne yazılmaz ve içerik farkı bildirilir.
    Dönüş: dict(durum, yol, sebep); durum ∈ yok, gecersiz, yazildi, guncellendi, ayni, farkli_yazilmadi."""
    from oneri import disa_aktarim_dogrula
    disa = disa or DISA_AKTARIM; rapor_kok = rapor_kok or RAPOR
    if not os.path.exists(disa):
        return dict(durum="yok", yol=None, sebep=f"{os.path.basename(disa)} yok; akşam görevi yazmamış")
    j = json_oku(disa, None)
    hata = disa_aktarim_dogrula(j) if j else ["JSON okunamadı"]
    if hata:
        return dict(durum="gecersiz", yol=None, sebep="dışa aktarım doğrulamadan geçmedi: " + "; ".join(hata[:3]))
    gun = str(j.get("olcumZamani"))[:10]
    klasor = os.path.join(rapor_kok, gun); hedef = os.path.join(klasor, "06 Pozisyonlar.json"); damga_yol = os.path.join(klasor, "06 Pozisyonlar.kaynak.json")
    damga = json_oku(damga_yol, None)
    if os.path.exists(hedef):
        mevcut = json_oku(hedef, None)
        if mevcut == j["pozisyonlar"]:
            return dict(durum="ayni", yol=hedef, sebep=f"hedef zaten var ve içerik aynı (damga {damga.get('olcumZamani') if damga else 'yok'})")
        if not damga:
            return dict(durum="farkli_yazilmadi", yol=hedef, sebep="hedef başka kaynaktan yazılmış (damga yok) ve içerik farklı; üstüne yazılmadı")
        if str(damga.get("olcumZamani")) >= str(j.get("olcumZamani")):
            return dict(durum="farkli_yazilmadi", yol=hedef, sebep=f"hedefin damgası ({damga.get('olcumZamani')}) dışa aktarımdan yeni ya da eşit; üstüne yazılmadı")
        eski = damga.get("olcumZamani")
        json.dump(j["pozisyonlar"], open(hedef, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(dict(olcumZamani=j.get("olcumZamani"), yazilma=date.today().isoformat(), onceki=eski), open(damga_yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return dict(durum="guncellendi", yol=hedef, sebep=f"aynı günün daha yeni dışa aktarımı ({eski} yerine {j.get('olcumZamani')}) üstüne yazıldı")
    os.makedirs(klasor, exist_ok=True)
    json.dump(j["pozisyonlar"], open(hedef, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(olcumZamani=j.get("olcumZamani"), yazilma=date.today().isoformat()), open(damga_yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return dict(durum="yazildi", yol=hedef, sebep=f"olcumZamani {j.get('olcumZamani')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", help="günlük rapor klasörü; varsayılan en yeni")
    ap.add_argument("--icerik", help="fon_icerik_YYYY-MM.csv.gz; varsayılan bulunan en yeni")
    ap.add_argument("--isim", action="append", default=None, help="tek isim maruziyeti aranacak ad (tekrarlanabilir); varsayılan 03 Veri/Künye/tek_isim.txt")
    ap.add_argument("--bildirilen", action="append", default=[], help="anahtar=TL; örnek bakisGecirgenHisse=1549921")
    ap.add_argument("--kapat", help="kapatılacak sapma kimliği")
    ap.add_argument("--kanit", default="", help="kapatma kanıtı")
    a = ap.parse_args()
    if a.kapat:
        sapma_kapat(a.kapat, a.kanit); return
    klasor = a.klasor or son_klasor()
    isimler = a.isim
    if isimler is None:
        yol = os.path.join(KUNYE_KLASOR, "tek_isim.txt")
        isimler = [l.strip() for l in open(yol, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(yol) else ["DESTEK FAKTORİNG|DSTKF"]
    bildirilen = {}
    for b in a.bildirilen:
        k, v = b.split("=", 1); bildirilen[k] = float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
    icerik = a.icerik or icerik_bul(os.path.join(os.environ.get("FON_ANALIZ_DEPO", ""), "arsiv") if os.environ.get("FON_ANALIZ_DEPO") else None)
    metin, genel = calistir(klasor, icerik, isimler, bildirilen)
    print(metin)
    sys.exit(0 if genel in ("yesil", "sari") else 1)


if __name__ == "__main__":
    main()
