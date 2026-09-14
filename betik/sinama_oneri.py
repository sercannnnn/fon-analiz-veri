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


def test_m30_tazelik_dogrulayamadigini_gecirmez():
    """M30: saat dilimsiz ve gelecek tarihli damga eski=True; sebep ayrı alanda; doğrulama gelecek tarihli belgeyi reddeder;
    saat farkı toleransı adıyla (GELECEK_TOLERANS_DK) ve sınamayla."""
    from datetime import datetime, timezone, timedelta
    simdi = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc); bugun = date(2026, 9, 12)
    t = oneri.tazelik("2026-09-11T19:30:00", bugun=bugun, simdi=simdi)
    assert t["eski"] and t["durum"] == "saat_dilimsiz" and t["sebep"]
    for damga in ("2026-09-13T09:00:00+03:00", "2026-09-20T09:00:00+03:00", "2027-01-01T09:00:00+03:00"):
        t = oneri.tazelik(damga, bugun=bugun, simdi=simdi)
        assert t["eski"] and t["durum"] == "gelecek" and t["is_gunu"] is not None and t["is_gunu"] <= 0
    belge = dict(olcumZamani="2026-09-13T09:00:00+03:00", pozisyonlar={"k": dict(kod="AAA", deger=1.0)}, nakit=[])
    assert any("gelecek tarihli" in h for h in oneri.disa_aktarim_dogrula(belge, bugun=bugun, simdi=simdi))
    assert any("saat dilimi" in h for h in oneri.disa_aktarim_dogrula(dict(belge, olcumZamani="2026-09-11T19:30:00"), bugun=bugun, simdi=simdi))
    # tolerans: şimdiden 10 dakika ileri damga taze, 30 dakika ileri damga gelecek
    assert not oneri.tazelik((simdi + timedelta(minutes=10)).isoformat(), bugun=bugun, simdi=simdi)["eski"]
    assert oneri.tazelik((simdi + timedelta(minutes=30)).isoformat(), bugun=bugun, simdi=simdi)["durum"] == "gelecek"
    assert oneri.GELECEK_TOLERANS_DK == 15
    assert oneri.tazelik("dün", bugun=bugun)["durum"] == "gecersiz" and oneri.tazelik(date(2026, 9, 11), bugun=bugun)["durum"] == "taze"


def test_m57_bekleyen_kayit_kural_surumuyle_dogrulanir():
    """Kural 24: sürümü güncel kayıt olduğu gibi; sürümsüz park kaydı park ölçütüyle yeniden doğrulanır, geçmezse iptale çekilmeli ve
    yerine ölçütün seçtiği (haber kapısından kapalı kurucular atlanır); aday kaydı kapı kümesiyle; nakit kısıtı her alımda; satış kapsam dışı."""
    park = dict(kod="PNU", getiri20=0.04, sira={"PNU": 1, "PRY": 2, "QQQ": 3, "PSE": 4}, adaylar=[dict(kod=k) for k in ("PNU", "PRY", "QQQ", "PSE")],
                neden={"HPT": "risk değeri boş (ölçüt 1-3); büyüklük 3,89 milyar TL (taban 5 milyar)"})
    em = {"20260914-01": dict(kod="HPT", yon="AL", tutar=2700000, durum="BEKLIYOR", tur="park"),
          "20260914-02": dict(kod="PNU", yon="AL", tutar=100000, durum="BEKLIYOR", tur="park", kuralSurumu=oneri.KURAL_SURUMU),
          "20260914-03": dict(kod="XXX", yon="AL", tutar=100000, durum="BEKLIYOR", not_="aday"),
          "20260914-04": dict(kod="ZZZ", yon="SAT", tutar=100000, durum="BEKLIYOR"),
          "20260914-05": dict(kod="YYY", yon="AL", tutar=100000, durum="GERCEKLESTI")}
    kur = {"PNU": "A", "PRY": "B", "QQQ": "C", "PSE": "D", "HPT": "E"}
    haber = {"A": False, "B": False, "C": False, "D": True}
    S = {r["kimlik"]: r for r in oneri.bekleyen_dogrula(em, park=park, acik_kodlar={"YYY"}, serbest_nakit=3000000, kurucu_haber=haber, kurucu=kur)}
    assert set(S) == {"20260914-01", "20260914-02", "20260914-03", "20260914-04"}
    r = S["20260914-01"]
    assert r["sonuc"] == "iptale_cekilmeli" and r["surum"] is None and "risk değeri boş" in r["gerekce"] and r["yerine"] == "PSE"
    assert S["20260914-02"]["sonuc"] == "gecerli" and S["20260914-02"]["guncel"]
    assert S["20260914-03"]["sonuc"] == "iptale_cekilmeli" and "kapı kümesi" in S["20260914-03"]["gerekce"]
    assert S["20260914-04"]["sonuc"] == "kapsam_disi"
    # nakit kısıtı: tutar serbest nakdi aşan güncel olmayan park kaydı
    em2 = {"x": dict(kod="PNU", yon="AL", tutar=5000000, durum="BEKLIYOR", tur="park")}
    r2 = oneri.bekleyen_dogrula(em2, park=park, acik_kodlar=set(), serbest_nakit=3000000)[0]
    assert r2["sonuc"] == "iptale_cekilmeli" and "nakit kısıtı" in r2["gerekce"]
    # ölçülemeyen girdi: park ölçütü yok, serbest nakit yok -> ölçülemedi (geçerli değil, kural 14)
    r3 = oneri.bekleyen_dogrula(em2, park={}, acik_kodlar=None, serbest_nakit=None)[0]
    assert r3["sonuc"] == "olculemedi"
    sat = oneri.bekleyen_satirlari(list(S.values()))
    assert any("İPTALE ÇEKİLMELİ" in s and "HPT" in s and "yerine güncel ölçütün seçtiği PSE" in s for s in sat)
    assert "defter değiştirilmedi" in sat[0]


def test_m58_atil_nakit_uc_tutar():
    """Kural 16 genişletmesi: ödemeye bağlı, park edilmiş, atıl; atıl satır tutar, kurum, gün ve günlük maliyet (park getirisi / 20) taşır;
    valörü gelmemiş satış geliri atıl değil; tutarı boş kalem ölçülemedi sayılır."""
    from datetime import date
    bugun = date(2026, 9, 14)
    nakit = [dict(kalem="Hesaptaki serbest nakit", tutar=3371000, kurum="Kurum A", tarih="2026-09-10"),
             dict(kalem="Ödeme: kira", tutar=500000, beklemeSebebi="ödeme", odemeTarihi="2026-09-20"),
             dict(kalem="Park", tutar=200000, beklemeSebebi="park", fon="PNU"),
             dict(kalem="SSS satışı", tutar=2499789, valor="16.09"),
             dict(kalem="Tutarsız", tutar=None)]
    poz = {"k-QQQ": dict(kod="QQQ", deger=1000000, kurum="Kurum B", durum="ACIK"), "k-RRR": dict(kod="RRR", deger=5, durum="ACIK")}
    n = oneri.nakit_ayir(nakit, poz, dict(kod="PNU", getiri20=0.04), bugun, kategori={"QQQ": "Para Piyasası", "RRR": "Hisse"})
    assert n["odeme_toplam"] == 500000 and n["odeme"][0]["tarih"] == "2026-09-20"
    assert n["park_toplam"] == 1200000 and {x["fon"] for x in n["park"]} == {"PNU", "QQQ"}
    assert n["atil_toplam"] == 3371000 and n["atil"][0]["kurum"] == "Kurum A" and n["atil"][0]["gun"] == 4
    assert n["beklenen_giris"] and n["bos"] == 1
    assert abs(n["gunluk_maliyet"] - 3371000 * 0.04 / oneri.PARK_SEANS) < 1e-6
    L = oneri.nakit_satirlari(n)
    assert "atıl 3.371.000 TL" in L[0] and any("Atıl nakit: 3.371.000 TL, Kurum A, 4 gündür" in s and "günlük maliyet 6.742 TL" in s for s in L)
    # park fonu yoksa maliyet ölçülemedi, atıl yine yazılır
    n2 = oneri.nakit_ayir(nakit[:1], {}, {}, bugun)
    assert n2["gunluk_maliyet"] is None and "ölçülemedi" in oneri.nakit_satirlari(n2)[1]


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f(); print("ok", ad)
    print("bütün sınamalar geçti")
