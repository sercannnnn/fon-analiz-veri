#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Veri takvimi (Görev 2.4): veri boşlukları ve doğrulanmış resmî kapanışlar tek yerde.

Kural 7: dört takvim gününden uzun boşluğu aşan getiri sahtedir; oynaklık, azami düşüş ve
Sortino hesabından çıkarılır. Resmî tatil boşluk sayılmaz; doğrulanmış kapanışlar açık listede tutulur.
Kural 15: fiyatı sıfır ya da boş olan kayıt ölçüme girmez, sayısı bildirilir.

Kullanım: oynaklık, yıllık getiri ve düşüş ölçümleri bu modülün maskesini kullanır; betikler kendi
boşluk kuralını yazmaz. Yalnızca numpy ve pandas.
"""
import json, os
from datetime import date, timedelta
import numpy as np
import pandas as pd

BOSLUK_GUN = 4          # iki seans arası bu kadar takvim gününden uzunsa geçiş boşluktur

# Doğrulanmış resmî kapanışlar: (son seans, ilk seans). Aradaki fark boşluk sayılmaz.
# Kaynak: TEFAS takvimi ve Borsa İstanbul tatil duyuruları; her kayıt doğrulandığı tarihle birlikte.
RESMI_KAPANIS = [
    ("2026-05-26", "2026-06-01"),   # Kurban Bayramı 2026; doğrulandı 8 Eylül 2026 (M3 eki)
]

# Bilinen veri boşlukları: ölçüm değil kayıt. Mac arşivinde 7 Eylül 2026'da dolduruldu; Cowork'ün gördüğü
# açık depo arşivinde aynı gün dolduruldu. Kayıt, boşluğun bir daha sessizce geçmemesi içindir.
BILINEN_BOSLUKLAR = [
    ("2025-02-27", "2025-09-01", "TEFAS çekimi yapılmadı; 7 Eylül 2026'da aylık parçalarla dolduruldu"),
]


def bosluk_maskesi(tarihler):
    """Ardışık seanslar arası takvim farkı BOSLUK_GUN'u aşıyorsa o geçiş boşluktur; doğrulanmış resmî
    kapanışlar boşluk sayılmaz. Uzunluğu len(tarihler)-1 olan bool dizisi döndürür (True = boşluk)."""
    t = pd.DatetimeIndex(tarihler).values
    if len(t) < 2:
        return np.zeros(0, dtype=bool)
    fark = np.diff(t).astype("timedelta64[D]").astype(int)
    b = fark > BOSLUK_GUN
    for a, z in RESMI_KAPANIS:
        b[(t[:-1] == np.datetime64(a)) & (t[1:] == np.datetime64(z))] = False
    return b


def dusus_serisi(p, bos):
    """Zirveden düşüş; her boşlukta zirve sıfırlanır, boşluğun kendisi düşüş sayılmaz."""
    p = np.asarray(p, dtype=float)
    dd = np.zeros(len(p))
    if not len(p):
        return dd
    zirve = p[0]
    for i in range(1, len(p)):
        if bos[i - 1]:
            zirve = p[i]
        zirve = max(zirve, p[i])
        dd[i] = p[i] / zirve - 1
    return dd


def gunluk_getiri(p, tarihler):
    """Basit günlük getiri dizisi; boşluk geçişleri NaN. Uzunluk len(p)-1."""
    p = np.asarray(p, dtype=float)
    r = p[1:] / p[:-1] - 1
    r[bosluk_maskesi(tarihler)] = np.nan
    return r


def pencere_getirisi(p, tarihler, k):
    """Son k seansın getirisi; pencere bir boşluk içeriyorsa NaN (kural 7)."""
    p = np.asarray(p, dtype=float)
    if len(p) <= k or bosluk_maskesi(tarihler[-k - 1:]).any():
        return np.nan
    return p[-1] / p[-k - 1] - 1


def gecersiz_fiyat_ayikla(d):
    """Kural 15: fiyatı sıfır ya da boş satır ölçüme girmez. Dönüş: (temiz çerçeve, atılan satır sayısı,
    atılan fon sayısı son günde)."""
    gecersiz = ~(d["fiyat"] > 0)
    son_gun = d["tarih"].max()
    son_gun_fon = int(d.loc[gecersiz & (d["tarih"] == son_gun), "fonKodu"].nunique())
    return d[~gecersiz].copy(), int(gecersiz.sum()), son_gun_fon


VERI_YASI_UYARI_IS_GUNU = 2   # ölçü 13 (21 Eylül 2026, varsayım): depodaki en yeni veri günü ile bugün arasındaki iş günü farkı bunu aşarsa uyarı


def is_gunu_sayisi(bas, bit):
    """bas ile bit (date ya da ISO) arasındaki iş günü sayısı: bas hariç, bit dahil; hafta sonu ve doğrulanmış resmî kapanış günleri
    sayılmaz. Ölçü 13: veri yaşı = is_gunu_sayisi(son veri günü, bugün)."""
    b = bas if isinstance(bas, date) else date.fromisoformat(str(bas)[:10])
    e = bit if isinstance(bit, date) else date.fromisoformat(str(bit)[:10])
    if e <= b:
        return 0
    kapali = set()
    for a, z in RESMI_KAPANIS:
        a_, z_ = date.fromisoformat(a), date.fromisoformat(z)
        x = a_ + timedelta(days=1)
        while x < z_:
            kapali.add(x); x += timedelta(days=1)
    n, g = 0, b
    while g < e:
        g += timedelta(days=1)
        if g.weekday() < 5 and g not in kapali:
            n += 1
    return n


def son_is_gunu(gun):
    """gun (date ya da 'YYYY-AA-GG') tarihine eşit ya da ondan önceki son iş günü: hafta sonu ve doğrulanmış resmî kapanış
    aralığı (RESMI_KAPANIS: son seans ile ilk seans arasındaki günler) atlanır. Köprünün "defter teyit edildi" ölçütü
    arşivin son günü değil bu takvim günüdür (30 numaralı not, madde 4): arşiv eskiyse ölçüt eskimez."""
    g = gun if isinstance(gun, date) else date.fromisoformat(str(gun)[:10])
    kapali = set()
    for a, z in RESMI_KAPANIS:
        a_, z_ = date.fromisoformat(a), date.fromisoformat(z)
        x = a_ + timedelta(days=1)
        while x < z_:
            kapali.add(x); x += timedelta(days=1)
    while g.weekday() >= 5 or g in kapali:
        g -= timedelta(days=1)
    return g


KIMLIK_ARIZA_YONTEMI = "onarim_yoksa_kopruleme"   # M34, M37, M38 (13 Eylül 2026)
# Sıra: (1) imza bozuk alanı gösteriyor ve aritmetik sıfır sapmayla kapanıyorsa o alan onarılır (M38, sıfır sapma kapısı);
# (2) onarım yoksa köprüleme: arızalı günün pay adedi ve büyüklüğü önceki temiz günden taşınır, değişim sonraki temiz güne düşer;
# (3) çöküşteki fonun (tek seansta büyüklük COKUS_ORAN üstünde düşmüş) arızası maskelenmez, adıyla bildirilir (M40).
# Köprüleme yansız değildir (M37): taşınan değişim arıza gününün değil sonraki temiz günün fiyatıyla değerlenir; kaydırmanın üst sınırı
# taramada `kaydirmaUstSinir` olarak yazılır ve köprülenen günün düştüğü hafta kovası üçüncü kapı için ölçülemedi sayılır.


def arsiv_son_gun(arsiv):
    """Arşivdeki (tefas_YYYY-MM.csv.gz) son fiyat günü; dosya yoksa None. Dosya öncelikli maskenin bayatlığını ölçmek için (Chat 34)."""
    import glob, gzip, csv
    dosyalar = sorted(glob.glob(os.path.join(arsiv, "tefas_????-??.csv.gz")))
    if not dosyalar:
        return None
    son = ""
    with gzip.open(dosyalar[-1], "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("tarih", "") > son:
                son = r["tarih"]
    return son or None


def kimlik_arizasi_ayikla(d, yol=None, arsiv=None):
    """Kimlik arızası onarımı ve köprülemesi (30 numaralı not madde 1; M34, M37, M38, M40). Kaynak: `yol` (kimlik_arizalari.json) varsa
    dosya; dosyanın penceresi arşivin son gününden eskiyse ya da dosya yoksa ve `arsiv` verilmişse tarama o arşivde yerinde koşar
    (M33: bulut dosya bağı kurmaz; bayat dosya kullanılmaz). Her arıza kaydı için: `onarim` varsa o alan onarılan değere yazılır;
    `maskele` False ise (çöküş) dokunulmaz; aksi hâlde köprüleme (fon içinde önceki temiz günden ileri doldurma; serinin başı NaN kalır).
    Dönüş: (çerçeve, dokunulan satır sayısı). Ayrıntı `kimlik_arizasi_ayikla.son` sözlüğündedir: kopru {(fon, tarih)}, onarim, cokus, maskesiz."""
    son = dict(kopru=set(), onarim=0, cokus=set(), maskesiz=0, kaynak="yok")
    kimlik_arizasi_ayikla.son = son
    tara = None
    if yol and os.path.exists(yol):
        try:
            tara = json.load(open(yol, encoding="utf-8")) or {}
            son["kaynak"] = "dosya"
        except Exception:
            tara = None
    if tara is not None and arsiv and os.path.isdir(arsiv):
        bit = str((tara.get("pencere") or {}).get("bit") or "")
        asg = arsiv_son_gun(arsiv)
        if asg and bit < asg:
            son["kaynak"] = f"dosya bayat ({bit} < {asg}); tarama yeniden koştu"
            tara = None
    if tara is None and arsiv and os.path.isdir(arsiv):
        try:
            import denetim
            tara = denetim.kimlik_taramasi(arsiv=arsiv)
            son["kaynak"] = son["kaynak"] if "bayat" in son["kaynak"] else "tarama"
        except Exception:
            tara = None
    arizalar = (tara or {}).get("arizalar") or []
    if tara:
        # park fonu dışlama kümesi (39 numaralı not): kimlik arızası, çöküş, kırılma, kesinti, ani düşüş, değer kaybı kaydı olan fon
        # park fonu dışlama kümesi (not 39 madde 1 şart 4, karar not 41): kimlik arızası, çöküş, seviye kırılması, raporlama kesintisi ve
        # değer kaybı (fiyata dayanır) girer; ani düşüş girmez (büyüklüğün tek seansta %20 oynaması olağan akıştır: 52 seansta 279 fon, M48).
        son["dislama"] = (set((tara.get("fonlar") or {}).keys()) | set((tara.get("cokusler") or {}).keys())
                          | {x["fonKodu"] for x in (tara.get("kirilmalar") or [])} | {x["fonKodu"] for x in (tara.get("kesenler") or [])}
                          | {x["fonKodu"] for x in (tara.get("degerKayiplari") or [])})
        son["degerKaybi"] = len(tara.get("degerKayiplari") or []); son["aniDusus"] = len(tara.get("aniDususler") or [])
        son["aniDususFiyat"] = sum(1 for x in (tara.get("aniDususler") or []) if x.get("alan") == "fiyat")   # M48: alarm fiyat tetiğidir
        son["kesen"] = len(tara.get("kesenler") or []); son["cokusSayisi"] = len(tara.get("cokusler") or {})
        son["buyume"] = {x["fonKodu"]: (x.get("payKat") or 0, x.get("buyuklukKat") or 0, x.get("buyuklukSon") or 0) for x in (tara.get("buyumeler") or [])}   # M53
    if not arizalar:
        return d, 0
    onarimlar, kopru, maskesiz = {}, set(), set()
    for a in arizalar:
        k = (a.get("fonKodu"), str(a.get("tarih"))[:10])
        if not k[0] or not k[1]:
            continue
        if a.get("onarim"):
            onarimlar[k] = a["onarim"]
        elif a.get("maskele") is False:
            maskesiz.add(k); son["cokus"].add(k[0])
        else:
            kopru.add(k)
    anahtar = list(zip(d["fonKodu"].astype(str), pd.to_datetime(d["tarih"]).dt.strftime("%Y-%m-%d")))
    m_on = np.array([k in onarimlar for k in anahtar]); m_ko = np.array([k in kopru for k in anahtar])
    son["maskesiz"] = sum(1 for k in anahtar if k in maskesiz)
    if not m_on.any() and not m_ko.any():
        return d, 0
    d = d.copy()
    if m_on.any():
        for i in np.where(m_on)[0]:
            o = onarimlar[anahtar[i]]
            if o.get("alan") in d.columns:
                d.iloc[i, d.columns.get_loc(o["alan"])] = float(o["yeni"])
        son["onarim"] = len({anahtar[i] for i in np.where(m_on)[0]})   # fon-gün sayısı; aynı gün iki dosyada (arşiv + son_gunluk) iki satır olabilir
    if m_ko.any():
        sira = np.lexsort((pd.to_datetime(d["tarih"]).values, d["fonKodu"].astype(str).values))
        for c in ("tedPaySayisi", "portfoyBuyukluk"):
            if c in d.columns:
                d.loc[m_ko, c] = np.nan
                s = d[c].iloc[sira]
                d[c] = s.groupby(d["fonKodu"].iloc[sira].values).ffill().reindex(d.index)   # köprüleme: fon içinde önceki temiz gün
        son["kopru"] = {anahtar[i] for i in np.where(m_ko)[0]}
    return d, int(m_on.sum() + m_ko.sum())


def kopru_olculemedi(kod, tarihler, son=None):
    """M37: fonun son 21 seansına köprülenmiş bir gün düşüyorsa üçüncü kapının hafta kovaları ölçülemedi sayılır (True döner).
    tarihler: fonun tarih sıralı seans tarihleri; son: kimlik_arizasi_ayikla.son (verilmezse son çağrınınki)."""
    son = son if son is not None else getattr(kimlik_arizasi_ayikla, "son", None)
    if not son or not son.get("kopru"):
        return False
    pencere = {pd.Timestamp(t).strftime("%Y-%m-%d") for t in list(tarihler)[-21:]}
    return any((kod, g) in son["kopru"] for g in pencere)
