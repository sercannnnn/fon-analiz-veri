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


def kimlik_arizasi_ayikla(d, yol):
    """Tek seanslık kimlik arızası (30 numaralı not, madde 1): denetim.py'nin yazdığı kimlik_arizalari.json içindeki fon-tarih
    çiftlerinde pay adedi ve büyüklük ölçüme girmez (NaN); fiyat kalır. Akış ve itfa ölçümleri o günü atlar, kalıcı tolerans
    doğmaz. Dönüş: (çerçeve, düşülen satır sayısı). Dosya yoksa çerçeve olduğu gibi döner ve sayı sıfırdır."""
    if not yol or not os.path.exists(yol):
        return d, 0
    try:
        j = json.load(open(yol, encoding="utf-8"))
    except Exception:
        return d, 0
    ciftler = {(a["fonKodu"], str(a["tarih"])[:10]) for a in (j.get("arizalar") or []) if a.get("fonKodu") and a.get("tarih")}
    if not ciftler:
        return d, 0
    anahtar = list(zip(d["fonKodu"].astype(str), pd.to_datetime(d["tarih"]).dt.strftime("%Y-%m-%d")))
    maske = np.array([k in ciftler for k in anahtar])
    if not maske.any():
        return d, 0
    d = d.copy()
    for c in ("tedPaySayisi", "portfoyBuyukluk"):
        if c in d.columns:
            d.loc[maske, c] = np.nan
    return d, int(maske.sum())
