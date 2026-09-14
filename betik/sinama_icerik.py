#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Depoda duran, kendi kendine yeten sınama (kural 20): fon içerik hattının M59 kuralları (56 numaralı not, 15 Eylül 2026).
Çalıştırma: python3 betik/sinama_icerik.py (pytest de toplar). fon_icerik_cek pdfplumber ister; yoksa o sınamalar atlanır.

Kanıtlar: sarılan satır üstteki kıymete atanır (Tera'da devam satırı alttaki kıymete yapışıyordu); negatif nominalli satır aynı
kıymetin pozitif satırıyla net okunur (satirTuru); aynı ay için yeniden yayımlanan rapor yeniden işlenir; içerik tazeliği eşiği
aşınca ya da tutulan fon arşivde yokken ölçülemedi; kurucu düzeyinde ihraççı toplamı net ve fon bazında."""
import os, sys, tempfile, gzip
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icerik_kapsam
try:
    import fon_icerik_cek as F
except Exception:      # pdfplumber yok (Mac sistem python'u); ayrıştırıcı sınamaları atlanır
    F = None


def _w(text, x0=20):
    return dict(text=text, x0=x0, x1=x0 + 8 * len(text), top=0)


def test_m59_sarilan_satir_ustteki_kiymete():
    if F is None:
        return
    # satırlar: (top, kelimeler); 0 ve 4 ana satır, 1-3 ilk kıymetin devamı (ad, ISIN, 'VE TİCARET A.Ş.'), 5 ikinci kıymetin devamı
    R = [(82.0, [_w("ASELS")]), (90.0, [_w("ELEKTRON", 118)]), (102.0, [_w("TRAASELS91H2", 224)]), (122.0, [_w("A.Ş.", 130)]),
         (130.0, [_w("ATATR")]), (138.0, [_w("TURİZM", 123)]), (146.0, [_w("GRUP"), _w("TOPLAMI", 60)])]
    anal = [0, 4]
    atama = F._sarilan_atama(R, anal, baslik=set(), tablo_bas=-1, tol=64)
    assert [t for t, _ in atama[0]] == [90.0, 102.0, 122.0], atama[0]      # 'A.Ş.' (122) ATATR'ye (130) daha yakın ama ASELS'e aittir
    assert [t for t, _ in atama[4]] == [138.0]
    # etiket satırı ad değildir; üstünde ana satır olmayan satır atanmaz
    R2 = [(70.0, [_w("Hisse Türk")]), (82.0, [_w("ASELS")]), (90.0, [_w("ELEKTRON", 118)])]
    a2 = F._sarilan_atama(R2, [1], set(), -1, 64, etiket_satir={0})
    assert list(a2) == [1] and len(a2[1]) == 1


def test_m59_negatif_satir_net_okunur():
    if F is None:
        return
    K = [dict(isin="TREALTK00013", kod="ALKLC", ad="", agirlik=7.96), dict(isin="TREALTK00013", kod="ALKLC", ad="", agirlik=-4.05),
         dict(isin="TRAXYZ", kod="XYZ", ad="", agirlik=-1.0), dict(isin="", kod="", ad="VIOP Nakit Teminatı", agirlik=17.93)]
    assert F.satir_turleri(K) == ["pozisyon", "negatif_eslesen", "negatif_tek", "pozisyon"]


def test_m59_ayni_ay_yeniden_yayimlanan_rapor_yeniden_islenir():
    if F is None:
        return
    d = dict(son="2026-08", surum=F.AYRISTIRICI_SURUM, bildirim=1657118)
    assert not F.yeniden_islenmeli(d, dict(disclosureIndex=1657118), "2026-08")      # aynı bildirim: atla
    assert F.yeniden_islenmeli(d, dict(disclosureIndex=1661174), "2026-08")          # aynı ay, yeni bildirim (9 Eylül): yeniden
    assert F.yeniden_islenmeli(dict(son="2026-08", surum=F.AYRISTIRICI_SURUM - 1, bildirim=1657118), dict(disclosureIndex=1657118), "2026-08")  # eski sürüm
    assert F.yeniden_islenmeli(dict(son="2026-07", surum=F.AYRISTIRICI_SURUM), dict(disclosureIndex=1), "2026-08")                          # yeni ay
    assert F.yeniden_islenmeli(dict(son="2026-08", surum=F.AYRISTIRICI_SURUM), dict(disclosureIndex=1), "2026-08")                          # bildirim kaydı yok


def test_m59_icerik_tazeligi_ve_olculemedi():
    S = [dict(fonKodu="AAA", raporTarihi="2026-08", veriGunu="2026-09-01"), dict(fonKodu="AAA", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="BBB", raporTarihi="2026-08", veriGunu="")]           # veriGunu boş: ay sonu (31 Ağustos)
    t = icerik_kapsam.icerik_tazeligi("", ["AAA", "BBB"], bugun=date(2026, 9, 15), satirlar=S)
    assert t["veri_gunu"] == "2026-09-07" and t["yas"] == 8 and t["fon"]["AAA"]["veri_gunu"] == "2026-09-07"
    assert t["fon"]["BBB"]["veri_gunu"] == "2026-08-31" and t["fon"]["BBB"]["yas"] == 15 and not t["olculemedi"]
    t2 = icerik_kapsam.icerik_tazeligi("", ["AAA", "CCC"], bugun=date(2026, 9, 15), satirlar=S)
    assert t2["olculemedi"] and t2["eksik"] == ["CCC"] and "CCC" in t2["sebep"]
    t3 = icerik_kapsam.icerik_tazeligi("", ["BBB"], bugun=date(2026, 10, 20), satirlar=S)
    assert t3["olculemedi"] and t3["eski"] == ["BBB"]                                   # 50 gün > 45
    assert icerik_kapsam.icerik_tazeligi("", ["AAA"], bugun=date(2026, 9, 15), satirlar=[])["olculemedi"]


def test_m62_fon_ihracci_ilk_net_ve_sinir():
    S = [dict(fonKodu="F1", bistKodu="AAA", isin="TRA", agirlik="21.79", veriGunu="2026-09-01", raporTarihi="2026-08"),
         dict(fonKodu="F1", bistKodu="AAA", isin="TRA", agirlik="-1.5", veriGunu="2026-09-01", raporTarihi="2026-08"),
         dict(fonKodu="F1", bistKodu="BBB", isin="TRB", agirlik="20.37", veriGunu="2026-09-01", raporTarihi="2026-08"),
         dict(fonKodu="F1", bistKodu="CCC", isin="TRC", agirlik="5", veriGunu="2026-09-01", raporTarihi="2026-08"),
         dict(fonKodu="F1", bistKodu="DDD", isin="TRD", agirlik="4", veriGunu="2026-09-01", raporTarihi="2026-08"),
         dict(fonKodu="F1", bistKodu="ZZZ", isin="TRZ", agirlik="99", veriGunu="", raporTarihi="2026-07"),      # eski ay: sayılmaz
         dict(fonKodu="F2", bistKodu="", isin="TRYTRPY00036", agirlik="14.01", veriGunu="", raporTarihi="2026-09")]
    o = icerik_kapsam.fon_ihracci_ilk(S, ["F1", "F2", "F9"], n=3)
    assert [x["kod"] for x in o["F1"]] == ["BBB", "AAA", "CCC"] and o["F1"][1]["agirlik"] == 20.29 and o["F1"][0]["veri_gunu"] == "2026-09-01"   # AAA net 21,79 − 1,5
    assert o["F2"][0]["kod"] == "TRYTRPY00036" and o["F2"][0]["veri_gunu"] == "2026-09-30" and "F9" not in o
    assert icerik_kapsam.TEK_KARSI_TARAF_SINIR == 20.0 and o["F1"][0]["agirlik"] > 20.0 and o["F1"][1]["agirlik"] > 20.0


def test_m59_kurucu_duzeyinde_ihracci():
    S = [dict(fonKodu="F1", bistKodu="MNS", nominal="17124756", rayicDeger="566829423.6"), dict(fonKodu="F1", bistKodu="MNS", nominal="-11500000", rayicDeger="-380000000"),
         dict(fonKodu="F2", bistKodu="MNS", nominal="1000000", rayicDeger="33100000"), dict(fonKodu="F3", bistKodu="MNS", nominal="5", rayicDeger="100"),
         dict(fonKodu="F1", bistKodu="", nominal="1", rayicDeger="1"), dict(fonKodu="F1", bistKodu="XXX", nominal="9", rayicDeger="9")]
    kur = {"F1": "K1", "F2": "K1", "F3": "K2"}
    for r in S:
        r["raporTarihi"] = "2026-09"
    S.append(dict(fonKodu="F1", bistKodu="MNS", nominal="99999999", rayicDeger="1", raporTarihi="2026-08"))   # eski ay: sayılmaz
    assert len(icerik_kapsam.son_ay_satirlari(S)) == len(S) - 1
    out = icerik_kapsam.kurucu_ihracci(S, kur, sermaye={"MNS": 40_000_000})
    k1 = next(d for d in out if d["kurucu"] == "K1" and d["bistKodu"] == "MNS")
    assert k1["nominal"] == 17124756 - 11500000 + 1000000 and k1["fonlar"] == ["F1", "F2"] and abs(k1["oran"] - k1["nominal"] / 40e6) < 1e-12
    assert out[0] is k1 and next(d for d in out if d["kurucu"] == "K2")["oran"] is not None
    assert icerik_kapsam.kurucu_ihracci(S, kur)[0]["oran"] is None                       # sermaye yoksa oran ölçülemedi
    assert all(d["kurucu"] == "K2" for d in icerik_kapsam.kurucu_ihracci(S, kur, kurucular={"K2"}))


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f(); print("ok", ad)
    print("bütün sınamalar geçti")
