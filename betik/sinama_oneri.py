#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Depoda duran, kendi kendine yeten sınama (kural 20): bulutun davranışını belirleyen öneri kurallarının kanıtı.
Çalıştırma: python3 betik/sinama_oneri.py (pytest de toplar). Yalnızca standart kütüphane ve oneri.

Kanıtlar: M29 sicil kimliği YYYYAAGG-KOD ve koşular arası tekillik; dışa aktarım sözleşmesi (alanlar, ISO ve saat dilimli
olcumZamani, pozisyon biçimi) ve tazelik kuralı (bir iş günü; cuma akşamı ölçümü pazartesi sabahı doğrulanmış); M28 defter
üzerinden süreklilik; bölüm 4 boyutlandırma (nakit kısıtı, yeni fona %5, haftada bir yeni fon)."""
import os, sys, tempfile
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oneri


def _o(kod):
    return dict(kod=kod, ad=kod, yon="AL", dilim="ana", etiket="", tutar=100000, yeni_fon=True, tutar_notu="", sira_olcusu=1.0, ardisik=3, gerekce="g")


def test_m29_sicil_kimligi_tarih_kod():
    b = oneri.BellekDeposu()
    assert oneri.sicil_yaz([_o("AAA"), _o("BBB")], "2026-09-14", "2026-09-13", depo=b) == 2
    assert oneri.sicil_yaz([_o("CCC"), _o("AAA"), _o("BBB")], "2026-09-14", "2026-09-13", depo=b) == 1
    ids = [x["id"] for x in b.sicil_oku()]
    assert ids == ["20260914-AAA", "20260914-BBB", "20260914-CCC"] and len(set(ids)) == 3
    _, belgeler = b.belgeler(yalniz_degisen=False)
    assert len(belgeler) == len(b.sicil_oku()) == 3
    assert oneri.sicil_yaz([_o("AAA")], "2026-09-15", "2026-09-14", depo=b) == 1 and "20260915-AAA" in {x["id"] for x in b.sicil_oku()}


def test_disa_aktarim_sozlesmesi_ve_tazelik():
    belge = dict(olcumZamani="2026-09-11T18:30:00+03:00", pozisyonlar={"k1": dict(kod="AAA", adet=1, deger=10.0, dilim="ana")}, nakit=[dict(kalem="serbest", tutar=5.0)])
    assert oneri.disa_aktarim_dogrula(belge) == []
    assert "olcumZamani saat dilimi taşımıyor" in oneri.disa_aktarim_dogrula(dict(belge, olcumZamani="2026-09-11T18:30:00"))
    assert any("nakit" in h for h in oneri.disa_aktarim_dogrula(dict(belge, nakit={})))
    assert any("pozisyon k1" in h for h in oneri.disa_aktarim_dogrula(dict(belge, pozisyonlar={"k1": dict(adet=1)})))
    assert any("alanı yok" in h for h in oneri.disa_aktarim_dogrula({}))
    t = oneri.tazelik(belge["olcumZamani"], bugun=date(2026, 9, 14))     # cuma akşamı ölçüm, pazartesi sabahı
    assert t["is_gunu"] == 1 and not t["eski"]
    assert oneri.tazelik(belge["olcumZamani"], bugun=date(2026, 9, 15))["eski"]
    assert oneri.tazelik(None)["eski"] and oneri.tazelik("dün")["eski"]
    sh = oneri.sermaye_hesapla(belge["pozisyonlar"], sum(x["tutar"] for x in belge["nakit"]))
    assert sh["sermaye"] == 15.0


def test_m28_defter_uzerinden_sureklilik():
    b1 = oneri.BellekDeposu(); assert oneri.ardisik_guncelle("2026-09-14", ["AAA"], depo=b1)["AAA"] == 1
    a, s = b1.belgeler()
    assert oneri.ardisik_guncelle("2026-09-15", ["AAA"], depo=oneri.BellekDeposu.defterden(a, s))["AAA"] == 2
    d = tempfile.mkdtemp()
    assert oneri.ardisik_guncelle("2026-09-15", ["AAA"], depo=oneri.DosyaDeposu(os.path.join(d, "a.json"), os.path.join(d, "s.json")))["AAA"] == 1


def test_bolum4_boyutlandirma():
    b = oneri.BellekDeposu()
    ardisik = {"AAA": 3, "BBB": 3}
    ana = [dict(fonKodu="AAA", fonAd="A", kapi_durumu="acik", getori=30.0), dict(fonKodu="BBB", fonAd="B", kapi_durumu="acik", getori=20.0)]
    o, n = oneri.oneri_uret(ana, [], "2026-09-14", "2026-09-13", 10_000_000, 0, "t", ardisik, serbest_nakit=None, depo=b)
    assert o == [] and "nakit ölçülemedi" in n[0]
    o, n = oneri.oneri_uret(ana, [], "2026-09-14", "2026-09-13", 10_000_000, 0, "t", ardisik, serbest_nakit=2_000_000, depo=b)
    assert [x["kod"] for x in o] == ["AAA"] and o[0]["tutar"] == 500_000 and any("haftada bir yeni fon" in x for x in n)
    o, _ = oneri.oneri_uret(ana[:1], [], "2026-09-14", "2026-09-13", 10_000_000, 0, "t", ardisik, serbest_nakit=120_000, depo=b)
    assert o[0]["tutar"] == 120_000


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f(); print("ok", ad)
    print("bütün sınamalar geçti")
