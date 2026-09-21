#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Depoda duran, kendi kendine yeten sınama (kural 20): fon içerik hattının M59 kuralları (56 numaralı not, 15 Eylül 2026).
Çalıştırma: python3 betik/sinama_icerik.py (pytest de toplar). fon_icerik_cek pdfplumber ister; yoksa o sınamalar atlanır.

Kanıtlar: sarılan satır üstteki kıymete atanır (Tera'da devam satırı alttaki kıymete yapışıyordu); negatif nominalli satır aynı
kıymetin pozitif satırıyla net okunur (satirTuru); aynı ay için yeniden yayımlanan rapor yeniden işlenir; içerik tazeliği eşiği
aşınca ya da tutulan fon arşivde yokken ölçülemedi; kurucu düzeyinde ihraççı toplamı net ve fon bazında."""
import os, sys, tempfile, gzip, json
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
         dict(fonKodu="F2", bistKodu="", isin="TRYTRPY00036", agirlik="14.01", veriGunu="", raporTarihi="2026-09"),
         dict(fonKodu="F2", bistKodu="", isin="TREXXX", tur="T.REPO", agirlik="30", veriGunu="", raporTarihi="2026-09")]   # repo teminatı: sayılmaz
    o = icerik_kapsam.fon_ihracci_ilk(S, ["F1", "F2", "F9"], n=3)
    assert [x["kod"] for x in o["F1"]] == ["BBB", "AAA", "CCC"] and o["F1"][1]["agirlik"] == 20.29 and o["F1"][0]["veri_gunu"] == "2026-09-01"   # AAA net 21,79 − 1,5
    assert o["F2"][0]["kod"] == "TRYTRPY00036" and o["F2"][0]["veri_gunu"] == "2026-09-30" and "F9" not in o and len(o["F2"]) == 1
    assert icerik_kapsam.TEK_KARSI_TARAF_SINIR == 20.0 and o["F1"][0]["agirlik"] > 20.0 and o["F1"][1]["agirlik"] > 20.0


def test_m66_m67_teminatli_pp_sinifi_kamu_muafiyeti_kismen_olculdu():
    S = [dict(fonKodu="K1", tur="Taahhüt Sözleşmesi Satış", isin="TRD090828T17", bistKodu="", ihracci="HAZINE", agirlik="99.36", raporTarihi="2026-08", veriGunu="2026-09-01"),
         dict(fonKodu="K1", tur="Kira Sertifikası", isin="TRDEVKSE2671", bistKodu="", ihracci="EMLAK KATILIM", agirlik="0.64", raporTarihi="2026-08", veriGunu="2026-09-01"),
         dict(fonKodu="P1", tur="MEVDUAT", isin="", bistKodu="", ihracci="T.C. ZİRAAT BANKASI A.Ş.", agirlik="30.76", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="P1", tur="TPP", isin="", bistKodu="", ihracci="", agirlik="42.61", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="P1", tur="Özel Sektör", isin="TRFA1CPK2627", bistKodu="", ihracci="", agirlik="2.59", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="P1", tur="Bono", isin="", bistKodu="", ihracci="", agirlik="5.0", raporTarihi="2026-09", veriGunu="2026-09-07"),      # adsız: kısmen ölçüldü
         dict(fonKodu="T1", tur="T.REPO", isin="TREDSTF00012", bistKodu="DSTKF", ihracci="DESTEK FAKTORIN G", agirlik="25.45", raporTarihi="2026-08", veriGunu="2026-09-01"),
         dict(fonKodu="T1", tur="T.REPO", isin="TRDTERVK2618", bistKodu="", ihracci="TERA VARLIK KİRALAMA A.Ş.", agirlik="4.02", raporTarihi="2026-08", veriGunu="2026-09-01"),
         dict(fonKodu="T1", tur="T.REPO", isin="TRT061228T16", bistKodu="", ihracci="HAZINE", agirlik="13.9", raporTarihi="2026-08", veriGunu="2026-09-01")]
    # taahhüt sözleşmesi ihraççı ölçüsünün dışında (M67); KHP benzeri fonun tek ihraççısı Hazine muaf ama yazılır
    ilk = icerik_kapsam.fon_ihracci_ilk(S, ["K1", "P1", "T1"], n=3)
    assert [x["kod"] for x in ilk["K1"]] == ["TRDEVKSE2671"] and "T1" not in ilk
    assert ilk["P1"][0]["kod"] == "T.C. ZİRAAT BANKASI A.Ş." and ilk["P1"][0]["agirlik"] == 30.76 and not ilk["P1"][0]["muaf"]   # mevduat: banka anahtar (M66)
    assert icerik_kapsam.fon_ihracci_ilk_adsiz(S, ["P1", "K1"]) == {"P1": 5.0}                                                  # TPP sayılmaz, adsız bono sayılır
    assert icerik_kapsam.kamu_mu("TRD090828T17") and icerik_kapsam.kamu_mu("TRT061228T16") and not icerik_kapsam.kamu_mu("TRDTERVK2618") and icerik_kapsam.kamu_mu("", "T.C. HAZİNE")
    ro = icerik_kapsam.repo_ozeti(S, ["K1", "P1", "T1"], grup_adlari={"TERA PORTFÖY", "TERA YATIRIM", "TERA VARLIK"})
    assert ro["K1"]["sinif"] == {"Hazine": 99.36} and ro["K1"]["tur"] == {"Taahhüt Sözleşmesi Satış": 99.36} and "ölçülemedi" in list(ro["K1"]["karsi_taraf"])[0]
    assert ro["P1"]["toplam"] == 42.61 and "Takasbank" in list(ro["P1"]["karsi_taraf"])[0]
    assert ro["T1"]["ihracci"][0] == ("DESTEK FAKTORIN G", 25.45) and ro["T1"]["grup"] == 4.02 and ro["T1"]["hazine_disi"] == 29.47


def test_m65_repo_ozeti_teminat_sinifi_ve_karsi_taraf():
    S = [dict(fonKodu="P1", tur="T.REPO", isin="TREDSTF00012", bistKodu="DSTKF", agirlik="0.05", raporTarihi="2026-08", veriGunu="2026-09-01")] * 3
    S = [dict(x) for x in S] + [dict(fonKodu="P1", tur="T.REPO", isin="TRT061228T16", bistKodu="", agirlik="4.13", raporTarihi="2026-08", veriGunu="2026-09-01"),
                                dict(fonKodu="P1", tur="T.REPO", isin="TRDTERVK2618", bistKodu="", agirlik="4.07", raporTarihi="2026-08", veriGunu="2026-09-01"),
                                dict(fonKodu="P1", tur="Hisse Türk", isin="TRAXXX", bistKodu="XXX", agirlik="10", raporTarihi="2026-08", veriGunu="2026-09-01"),
                                dict(fonKodu="P2", tur="Bono", isin="TRF1", bistKodu="", agirlik="10", raporTarihi="2026-08", veriGunu="")]
    o = icerik_kapsam.repo_ozeti(S, ["P1", "P2", "P9"])
    assert list(o) == ["P1"] and o["P1"]["satir"] == 5 and abs(o["P1"]["toplam"] - 8.35) < 1e-9
    assert o["P1"]["sinif"] == {"Hazine": 4.13, "kira sertifikası": 4.07, "hisse": 0.15} and o["P1"]["en_buyuk"] == ("TRT061228T16", 4.13)
    assert abs(o["P1"]["hazine_disi"] - 4.22) < 1e-9 and "ölçülemedi" in list(o["P1"]["karsi_taraf"])[0]
    assert icerik_kapsam.teminat_sinifi("XS3290494775") == "eurobond" and icerik_kapsam.teminat_sinifi("TRYTALP00036") == "yatırım fonu" and icerik_kapsam.teminat_sinifi("ZZ") == "diğer"


def test_m60_park_aday_kumesi_kuyruk_onceligi():
    if F is None:
        return
    kun = [dict(fonKodu="A", kategori="Para Piyasası"), dict(fonKodu="B", kategori="Para Piyasası"), dict(fonKodu="C", kategori="Hisse Senedi"), dict(fonKodu="D", kategori="Kısa Vadeli Borçlanma")]
    gun = [dict(fonKodu="A", tarih="2026-09-11", portfoyBuyukluk="6e9"), dict(fonKodu="A", tarih="2026-09-10", portfoyBuyukluk="1e9"),
           dict(fonKodu="B", tarih="2026-09-11", portfoyBuyukluk="1e9"), dict(fonKodu="C", tarih="2026-09-11", portfoyBuyukluk="9e9"), dict(fonKodu="D", tarih="2026-09-11", portfoyBuyukluk="5e9")]
    assert F.park_aday_kumesi("", kun, gun) == {"A", "D"}          # A son gün 6 mrd (önceki gün değil), B küçük, C kategori dışı, D tabanda


def test_m68_kurucu_grubu_payi_ve_banka_grubu():
    S = [dict(fonKodu="F1", tur="Hisse Türk", isin="TRETERA00013", bistKodu="TERA", ihracci="TERA YATIRIM MENKUL DEĞERLER A.Ş.", agirlik="5.29", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="Kira Sertifikası", isin="TRDTERVK2618", bistKodu="", ihracci="TERA VARLIK KİRALAMA A.Ş.", agirlik="6.26", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="T.REPO", isin="TRDTERVK2618", bistKodu="", ihracci="TERA VARLIK KİRALAMA A.Ş.", agirlik="4.02", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="Y.Fonu Türk", isin="TRYTRPY00140", bistKodu="", ihracci="TERA PORTFÖY YÖNETİMİ A.Ş.", agirlik="1.46", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="Hisse Türk", isin="TRAMEDIT0001", bistKodu="MDTRA", ihracci="MEDİTERA TIBBİ A.Ş.", agirlik="3.0", raporTarihi="2026-09", veriGunu="2026-09-07"),   # MEDİTERA: TERA değil
         dict(fonKodu="F1", tur="Hisse Türk", isin="", bistKodu="", ihracci="", kiymetAdiHam="TRHOL TERA FİNANSAL YATIRIMLA", agirlik="2.0", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="Hisse Türk", isin="TRAAKBNK91N6", bistKodu="AKBNK", ihracci="AKBANK T.A.Ş.", agirlik="10", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F2", tur="MEVDUAT", isin="", bistKodu="", ihracci="ZİRAAT BANKASI A.Ş.", agirlik="30.76", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F2", tur="KATILIM HESABI", isin="", bistKodu="", ihracci="ZİRAAT KATILIM BANKASI A.Ş.", agirlik="5", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F2", tur="MEVDUAT", isin="", bistKodu="", ihracci="TÜRKİYE VAKIFLAR BANKASI T.A.O.", agirlik="19.82", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F2", tur="U) PARA PİYASASI", isin="", bistKodu="", ihracci="Takasbank Para Piyasası- BIAS", agirlik="40", raporTarihi="2026-09", veriGunu="2026-09-07")]
    grup = {"TERA PORTFÖY": ["TERA FİNANS", "TERA FİNANSAL", "TERA GRUBU", "TERA PORTFÖY", "TERA YATIRIM"]}
    o = icerik_kapsam.kurucu_grubu_payi(S, ["F1", "F2"], {"F1": "TERA PORTFÖY", "F2": "PARDUS PORTFÖY"}, grup_tablo=grup)
    assert abs(o["F1"]["kesin"] - 17.03) < 1e-9 and abs(o["F1"]["ust_sinir"] - 19.03) < 1e-9 and o["F1"]["adsiz_satir"] == 1   # MEDİTERA ve AKBANK sayılmaz, Tera Varlık kök kelimeyle sayılır
    assert o["F1"]["olculemeyen"] == 0.0 and o["F1"]["en_kotu"] == 19.03
    assert o["F2"]["kesin"] == 0.0
    # M69: adsız satır "bilinmiyor"dur; yapısı gereği ihraççı olmayan tür (VİOP nakit teminatı) ölçülemeyenden düşülür
    S2 = S + [dict(fonKodu="F1", tur="Hisse Türk", isin="", bistKodu="", ihracci="", kiymetAdiHam="", agirlik="3.5", raporTarihi="2026-09", veriGunu="2026-09-07"),
              dict(fonKodu="F1", tur="VIOP Nakit Teminatı", isin="", bistKodu="", ihracci="", kiymetAdiHam="", agirlik="21.55", raporTarihi="2026-09", veriGunu="2026-09-07")]
    o2 = icerik_kapsam.kurucu_grubu_payi(S2, ["F1"], {"F1": "TERA PORTFÖY"}, grup_tablo=grup)["F1"]
    assert o2["olculemeyen"] == 3.5 and o2["en_kotu"] == 22.53 and o2["olculemeyen_tur"] == [("Hisse Türk", 3.5)] and o2["adsiz_satir"] == 3
    # 66 numaralı not: eşikler kategoriye göre (varsayım); fon sepeti muaf
    assert icerik_kapsam.grup_payi_durumu(30.85, "Para Piyasası") == "aykırı" and icerik_kapsam.grup_payi_durumu(20.89, "Hisse Senedi") == "aykırı"
    assert icerik_kapsam.grup_payi_durumu(30.08, "Serbest") == "uyarı" and icerik_kapsam.grup_payi_durumu(4.0, "Katılım") == "eşik içinde"
    assert icerik_kapsam.grup_payi_durumu(60.0, "Fon Sepeti") == "muaf (fon sepeti)" and icerik_kapsam.grup_payi_durumu(None, "Serbest") == "ölçülemedi"
    bg = {"ZİRAAT": ["ZİRAAT BANKASI", "ZİRAAT KATILIM"], "VAKIF": ["VAKIFLAR BANKASI", "VAKIF KATILIM"]}
    ilk = icerik_kapsam.fon_ihracci_ilk(S, ["F2"], n=3, banka_grup=bg)
    assert ilk["F2"][0]["kod"] == "ZİRAAT" and ilk["F2"][0]["agirlik"] == 30.76 and ilk["F2"][1]["kod"] == "VAKIF"     # katılım hesabı teminatlı sınıfta, mevduat banka grubuyla
    ro = icerik_kapsam.repo_ozeti(S, ["F2"])
    assert ro["F2"]["toplam"] == 45.0 and any("Takasbank" in k for k in ro["F2"]["karsi_taraf"]) and any("(banka)" in k for k in ro["F2"]["karsi_taraf"])


def test_68_yeniden_degerleme_ve_cikis_suresi():
    # rapor: FPD 10 mrd; AAA net 900.000 pay, rayiç 1,576 mrd (%15,76), rapor fiyatı 1.751; bugün 2.000 → değer 1,8 mrd
    S = [dict(fonKodu="F1", tur="Hisse Türk", bistKodu="AAA", isin="TRA", nominal="1000000", rayicDeger="1751111111", agirlik="17.51", raporTarihi="2026-09", veriGunu="2026-09-07"),
         dict(fonKodu="F1", tur="Hisse Türk", bistKodu="AAA", isin="TRA", nominal="-100000", rayicDeger="-175111111", agirlik="-1.75", raporTarihi="2026-09", veriGunu="2026-09-07"),   # net 900.000
         dict(fonKodu="F1", tur="Hisse Türk", bistKodu="BBB", isin="TRB", nominal="5000", rayicDeger="500000000", agirlik="5.0", raporTarihi="2026-09", veriGunu="2026-09-07"),         # fiyatsız
         dict(fonKodu="F1", tur="VIOP Nakit Teminatı", bistKodu="", isin="", nominal="1", rayicDeger="2000000000", agirlik="20", raporTarihi="2026-09", veriGunu="2026-09-07")]
    fiy = {"AAA": dict(tarih="2026-09-14", kapanis=2000.0, hacim_ortanca=1_000_000_000.0, seans=20)}
    o = icerik_kapsam.yeniden_degerle(S, ["F1"], fiy, buyukluk={"F1": 16_000_000_000.0})["F1"]
    a = o["satirlar"][0]
    assert a["kod"] == "AAA" and a["nominal"] == 900000 and a["deger"] == 1.8e9 and a["agirlik_rapor"] == 15.76
    assert abs(o["fpd_rapor"] - 1e10) < 2e6 and abs(o["toplam_guncel"] - (1e10 + 1.8e9 - 1.576e9)) < 2e6      # yalnızca fiyat değişimi taşınır (ağırlık iki ondalık: %0,02 pay)
    assert abs(a["agirlik_guncel"] - 1.8e9 / o["toplam_guncel"] * 100) < 0.01 and 17.5 < a["agirlik_guncel"] < 17.7
    assert abs(a["cikis_gun"] - 1.8e9 / (1e9 * icerik_kapsam.KATILIM_ORANI)) < 1e-9
    b = o["satirlar"][1]
    assert b["kod"] == "BBB" and b["fiyatsiz"] and b["cikis_gun"] is None and o["fiyatsiz_pay"] == 5.0 and o["olculen_pay_rapor"] == 15.76
    assert o["akis_uyari"] and abs(o["akis_orani"] - 0.6) < 1e-3      # TEFAS 16 mrd, rapor 10 mrd: yeni para, varsayım zayıf; payda olarak kullanılmaz
    assert icerik_kapsam.cikis_gunu(100.0, None) is None and icerik_kapsam.cikis_gunu(100.0, 0) is None
    assert not icerik_kapsam.yeniden_degerle(S, ["F1"], fiy)["F1"]["akis_uyari"]


def test_68_temel_oranlar_ve_dort_ceyrek():
    t = dict(paySayisi=100.0, ozkaynak=500.0, netKar4C=50.0, netBorc=150.0, favok4C=75.0, donenVarlik=300.0, kvYukumluluk=200.0, donem="2026-06", kaynak="x")
    o = icerik_kapsam.temel_oranlar(t, 10.0)
    assert o["piyasa_degeri"] == 1000.0 and o["pd_dd"] == 2.0 and o["fk"] == 20.0 and o["netborc_favok"] == 2.0 and o["okk"] == 0.1 and o["cari"] == 1.5
    o2 = icerik_kapsam.temel_oranlar(dict(t, ozkaynak=-5.0, netKar4C=-1.0, favok4C=0.0), 10.0)
    assert o2["pd_dd"] == "anlamsız" and o2["fk"] == "anlamsız" and o2["netborc_favok"] == "anlamsız" and o2["okk"] == "anlamsız"
    assert icerik_kapsam.temel_oranlar(None, 10.0)["pd_dd"] is None and icerik_kapsam.temel_oranlar(dict(t, paySayisi=None), 10.0)["fk"] is None
    try:
        import temel_cek as T
    except Exception:
        return
    from datetime import date
    dl = T.donemler(date(2026, 9, 15)); assert dl == [(2026, 6), (2025, 12), (2025, 6), (2025, 9)]
    assert T.dort_ceyrek([30.0, 100.0, 40.0, 70.0], dl) == 90.0 and T.dort_ceyrek([30.0, None, 40.0, 70.0], dl) is None
    assert T.dort_ceyrek([120.0, 100.0, 40.0, 70.0], T.donemler(date(2026, 3, 1))) == 120.0     # yıl sonu: doğrudan
    k = T.kayit("XXX", [dict(itemDescTr="Özkaynaklar", value1="500"), dict(itemDescTr="Ödenmiş Sermaye", value1="100"), dict(itemDescTr="Dönem Net Kar/Zararı", value1="30", value2="100", value3="40"),
                        dict(itemDescTr="Nakit ve Nakit Benzerleri", value1="20"), dict(itemDescTr="Kısa Vadeli Borçlanmalar", value1="50"), dict(itemDescTr="Uzun Vadeli Borçlanmalar", value1="120"),
                        dict(itemDescTr="Esas Faaliyet Karı", value1="45", value2="90", value3="35"), dict(itemDescTr="Amortisman Giderleri", value1="-5", value2="-12", value3="-4")], "XI_29", dl, date(2026, 9, 15))
    assert k["paySayisi"] == 100.0 and k["netKar4C"] == 90.0 and k["netBorc"] == 150.0 and k["favok4C"] == 100.0 + 13.0 and "varsayım" in k["paySayisiKaynak"]


def test_m70_portfoy_gunu_ima_edilen_fiyattan():
    """72 numaralı not: hisse satırının rayiç / nominal değeri fiyat arşivinde oy verir; en çok oy alan gün portföy günüdür (en az 3 oy ve yarıdan fazla).
    Seçim veriGunu ile (70 numaralı not); yayımcı etiketi yanıltsa da veri günü kazanır."""
    if F is None:
        return
    kap = {"AAA": {"2026-09-03": 100.0, "2026-09-04": 102.0, "2026-09-07": 105.0}, "BBB": {"2026-09-03": 50.0, "2026-09-04": 51.0, "2026-09-07": 53.0},
           "CCC": {"2026-09-04": 10.0, "2026-09-07": 10.0}, "DDD": {"2026-09-04": 7.0}}
    K = [dict(kod="AAA", tur="Hisse Türk", nominal=1000, rayic=102000.0), dict(kod="BBB", tur="Hisse Türk", nominal=10, rayic=510.0),
         dict(kod="CCC", tur="Hisse Türk", nominal=5, rayic=50.0), dict(kod="DDD", tur="Hisse Türk", nominal=1, rayic=7.0),
         dict(kod="EEE", tur="Hisse Türk", nominal=1, rayic=1.0), dict(kod="TRT1", tur="Devlet Tahvili", nominal=1, rayic=1.0)]
    g, oy, n, aday = F.portfoy_gunu_oyla(K, kap)
    assert g == "2026-09-04" and oy == 4 and n == 4                     # CCC iki güne oy verir, DDD tek; 04.09 dördü de
    assert F.portfoy_gunu_oyla(K[:2], kap)[0] is None                  # iki oy yetmez (asgari 3)
    F.ISIN_KOD["TREXAMPL0001"] = "XMPL"
    assert F.isinden_kod("TRAAKBNK91N6", {"AKBNK"}) == "AKBNK" and F.isinden_kod("TREXAMPL0001", set()) == "XMPL" and F.isinden_kod("TREZZZZZ0001", {"AKBNK"}) == ""
    assert F.HISSE_TUR.search(F.norm("A.PAY")) and F.HISSE_TUR.search("Hisse Türk") and not F.HISSE_TUR.search(F.norm("Kira Sertifikası"))
    kap2 = dict(kap, AKBNK={"2026-09-04": 60.0}); K2 = [dict(kod="TRAAKBNK91N6", isin="TRAAKBNK91N6", tur="A.PAY", nominal=10, rayic=600.0)]
    assert F.portfoy_gunu_oyla(K2 * 3, kap2, {"AKBNK"})[0] == "2026-09-04"     # Garanti: ISIN'den kod
    assert F.tefas_izleyen_gun({("2026-09-04", "F"): {"a": 1}, ("2026-09-07", "F"): {"a": 2}}, "F", "2026-09-04")[0] == "2026-09-07"
    assert F.onceki_is_gunu("2026-09-07") == "2026-09-04" and F.onceki_is_gunu("2026-09-01") == "2026-08-31"
    S = [dict(fonKodu="F1", raporTarihi="2026-09", veriGunu="2026-08-20", agirlik="1"),     # etiketi yeni, verisi eski
         dict(fonKodu="F1", raporTarihi="2026-08", veriGunu="2026-08-31", agirlik="2")]     # etiketi eski, verisi yeni: bu seçilir
    assert [r["agirlik"] for r in icerik_kapsam.son_ay_satirlari(S)] == ["2"]
    assert icerik_kapsam.akis_durumu(0.05) == "tam" and icerik_kapsam.akis_durumu(0.2) == "varsayım zayıf" and icerik_kapsam.akis_durumu(0.88).startswith("ölçülemedi") and icerik_kapsam.akis_durumu(None) == "ölçülemedi"
    tb = dict(paySayisi=100.0, ozkaynak=500.0, netKar4C=50.0, netBorc=None, favok4C=None, donenVarlik=None, kvYukumluluk=None, donem="2026-06", grup="UFRS", kaynak="x")
    o = icerik_kapsam.temel_oranlar(tb, 10.0)
    assert o["pd_dd"] == 2.0 and o["fk"] == 20.0 and o["okk"] == 0.1 and o["cari"].startswith("anlamsız") and o["netborc_favok"].startswith("anlamsız")
    import temel_cek as T
    k = T.ayikla([dict(itemDescTr="XVI. ÖZKAYNAKLAR", value1="500"), dict(itemDescTr="16.1 Ödenmiş Sermaye", value1="100"), dict(itemDescTr="XX. DÖNEM NET KAR/ZARARI", value1="30")])
    assert k["ozkaynak"][0] == 500.0 and k["odenmisSermaye"][0] == 100.0 and k["netKar"][0] == 30.0


def test_m71_m72_toplam_tablosu_agirlik_tabani_vadeli():
    S = [dict(fonKodu="F1", tur="Hisse Türk", bistKodu="AAA", isin="TRA", nominal="100", rayicDeger="1000", agirlik="10.0", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", tur="Hisse Türk", bistKodu="BBB", isin="TRB", nominal="100", rayicDeger="2000", agirlik="20.0", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", tur="VIOP Nakit Teminatı", bistKodu="", isin="", nominal="1", rayicDeger="7000", agirlik="70.0", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", tur="Uzun", bistKodu="", isin="", nominal="10", rayicDeger="1715", agirlik="0", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", tur="Kısa", bistKodu="", isin="", nominal="1", rayicDeger="300", agirlik="", raporTarihi="2026-09", veriGunu="2026-09-04")]
    taban, sapan = icerik_kapsam.agirlik_tabani(S)
    assert taban == 10000.0 and sapan == 0                                                    # vadeli satırlar (notional 2015) tabana girmez
    v = icerik_kapsam.vadeli_islem_maruziyeti(S, ["F1"])["F1"]
    assert v["uzun"] == 1715.0 and v["kisa"] == 300.0 and v["notional"] == 2015.0 and abs(v["oran"] - 0.2015) < 1e-9 and v["satir"] == 2
    assert v["brut"] == 2015.0 and v["net"] == 1415.0                                        # 78 numaralı not: yön ayrımı
    o = icerik_kapsam.yeniden_degerle(S, ["F1"], {"AAA": dict(tarih="2026-09-14", kapanis=11.0, hacim_ortanca=1e6, seans=20)}, buyukluk={"F1": 12000.0}, buyukluk_gun={"F1": 8000.0})["F1"]
    assert o["fpd_rapor"] == 10000.0 and o["hisse_sayisi"] == 2 and abs(o["artik_orani"] - 1.25) < 1e-9 and o["artik_acik"]
    if F is None:
        return
    m = """IV-FON TOPLAM DEĞERİ TABLOSU
A-)FON PORTFÖY DEĞERİ 28.280.728.111,73 126,19 %
B-)HAZIR DEĞERLER 14.728.489,91 0,07 %
C-)ALACAKLAR 1.273.546.984,79 5,68 %
D-)DİĞER VARLIKLAR 0,00 0,00 %
E-)BORÇLAR -7.157.619.913,86 -31,94 %
F-)İHTİYAT 0,00 0,00 %
FON TOPLAM DEĞERİ 22.411.383.672,57 100,00 %
D-)Toplam Değer/Net Varlık Değeri : 22.411.383.672,57
E-) Katılma Payı Sayısı : 9.205.100.303,000"""
    t = F.toplam_tablosu_metinden(m)
    assert abs(t["fpd"] - 28280728111.73) < 0.01 and abs(t["borc"] + 7157619913.86) < 0.01 and abs(t["nav"] - 22411383672.57) < 0.01
    assert abs(t["fpdYuzde"] - 126.19) < 1e-9 and abs(t["kaldirac"] - 0.3194) < 1e-4 and abs(t["fpdNav"] - 1.2619) < 1e-4 and t["paySayisi"] == 9205100303.0 and t["navSayfa1"] == t["nav"]
    assert F.toplam_tablosu_metinden("hiçbir şey") == {}


def test_m73_piyasa_gunu_ve_kaldirac_ozeti():
    assert icerik_kapsam.piyasa_gunu("2026-09-07") == "2026-09-04" and icerik_kapsam.piyasa_gunu("2026-09-01") == "2026-08-31" and icerik_kapsam.piyasa_gunu("x") is None
    ky = {"F1": dict(portfoyGunu="2026-09-04", duzen="standart", toplamTablosu=dict(fpd=28.28e9, borc=-7.16e9, nav=22.41e9)),
          "F2": dict(portfoyGunu="2026-08-31", durum="yayimlandi", surum=14, toplamTablosu={}), "F4": dict(durum="yayimlandi", surum=12)}
    v = {"F1": dict(notional=1.0e9)}
    o = icerik_kapsam.kaldirac_ozeti(ky, ["F1", "F2", "F3", "F4"], vadeli=v)
    assert abs(o["F1"]["fpd_nav"] - 1.262) < 1e-3 and abs(o["F1"]["borc_nav"] - 0.3195) < 1e-3 and abs(o["F1"]["vadeli_nav"] - 1.0 / 22.41) < 1e-4 and not o["F1"]["olculemedi"]
    assert o["F2"]["olculemedi"] and "taşımıyor" in o["F2"]["sebep"] and o["F3"]["olculemedi"] and "kuyruk kaydı yok" in o["F3"]["sebep"]
    assert o["F4"]["olculemedi"] and "sürüm 12" in o["F4"]["sebep"]
    ky["F5"] = dict(durum="yayimlandi", surum=14, duzen="garanti", toplamTablosu={"olculemez": "garanti"})
    o5 = icerik_kapsam.kaldirac_ozeti(ky, ["F5"])["F5"]
    assert o5["olculemedi"] and o5["kalici"] and o5["sebep"].startswith("KALICI ÖLÇÜLEMEZ") and "garanti" in o5["sebep"]
    ky["F6"] = dict(durum="yayimlandi", surum=14, toplamTablosu={})                      # eski kayıt işaretsiz: düzen arşiv satırından
    assert icerik_kapsam.kaldirac_ozeti(ky, ["F6"], duzen={"F6": "yapikredi"})["F6"]["kalici"]
    assert not icerik_kapsam.kaldirac_ozeti(ky, ["F6"], duzen={"F6": "standart"})["F6"]["kalici"]
    v2 = {"F1": dict(uzun=0.5e9, kisa=0.3e9, brut=0.8e9, net=0.2e9)}
    o1 = icerik_kapsam.kaldirac_ozeti(ky, ["F1"], vadeli=v2)["F1"]
    assert abs(o1["vadeli_nav"] - 0.8 / 22.41) < 1e-6 and abs(o1["vadeli_net_nav"] - 0.2 / 22.41) < 1e-6 and abs(o1["vadeli_kisa_nav"] - 0.3 / 22.41) < 1e-6


def test_m74_pay_degisimi_yon_ve_hacim_gunu():
    """78 numaralı not, bölüm 3: aynı kâğıdın raporlar arası net pay adedi, TL değeri ve günlük hacme oranı; bir günlük hacmi aşan alım kalın."""
    S = [dict(fonKodu="F1", bistKodu="AAA", nominal="500000", rayicDeger="1000000000", raporTarihi="2026-08", veriGunu=""),
         dict(fonKodu="F1", bistKodu="BBB", nominal="100", rayicDeger="1000", raporTarihi="2026-08", veriGunu=""),
         dict(fonKodu="F1", bistKodu="", isin="TRECCC00001", nominal="50", rayicDeger="500", raporTarihi="2026-08", veriGunu=""),
         dict(fonKodu="F3", bistKodu="CCC", isin="TRECCC00001", nominal="1", rayicDeger="10", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", bistKodu="AAA", nominal="1300000", rayicDeger="3000000000", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", bistKodu="AAA", nominal="740804", rayicDeger="1709547692", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F1", bistKodu="BBB", nominal="100", rayicDeger="1100", raporTarihi="2026-09", veriGunu="2026-09-04"),
         dict(fonKodu="F2", bistKodu="AAA", nominal="10", rayicDeger="100", raporTarihi="2026-09", veriGunu="2026-09-04")]
    fiyat = {"AAA": dict(hacim_ortanca=2.5e9), "BBB": dict(hacim_ortanca=1e6), "CCC": dict(hacim_ortanca=1e2)}
    o = icerik_kapsam.pay_degisimi(S, ["F1", "F2"], fiyat)
    assert o["F1"]["onceki"] == "2026-08-31" and o["F1"]["yeni"] == "2026-09-04" and not o["F1"]["olculemedi"]
    r = {e["kod"]: e for e in o["F1"]["satirlar"]}
    assert set(r) == {"AAA", "CCC"} and r["AAA"]["onceki"] == 500000 and r["AAA"]["yeni"] == 2040804 and r["AAA"]["fark"] == 1540804
    assert abs(r["AAA"]["oran"] - 3.0816) < 1e-3 and abs(r["AAA"]["deger"] - 1540804 * (4709547692 / 2040804)) < 1 and r["AAA"]["hacim_gun"] > 1 and r["AAA"]["esik_asti"]
    assert r["CCC"]["fark"] == -50 and r["CCC"]["deger"] == -500 and r["CCC"]["esik_asti"] and o["F1"]["satirlar"][0]["kod"] == "AAA"
    assert o["F2"]["olculemedi"] == "önceki rapor arşivde yok" and o["F2"]["satirlar"] == []


def test_m75_grup_pay_degisimi_ve_ters_yon():
    """80 numaralı not: kurucunun bütün fonlarında aynı kâğıdın net değişimi, borsa hacmine oranı (eşik kalın), kardeş fon ters yön ve kesişen hacim."""
    def r(f, kod, nom, ray, ay, gun):
        return dict(fonKodu=f, bistKodu=kod, nominal=str(nom), rayicDeger=str(ray), raporTarihi=ay, veriGunu=gun)
    S = [r("F1", "AAA", 100, 1000, "2026-08", ""), r("F1", "BBB", 10, 100, "2026-08", ""), r("F2", "AAA", 200, 2000, "2026-08", ""),
         r("F1", "AAA", 400, 4000, "2026-09", "2026-09-04"), r("F1", "BBB", 20, 200, "2026-09", "2026-09-04"), r("F2", "AAA", 100, 1000, "2026-09", "2026-09-04"),
         r("F3", "AAA", 5, 50, "2026-09", "2026-09-04"), r("F3", "AAA", 9, 90, "2026-09", "2026-09-07"), r("X1", "AAA", 1, 10, "2026-08", ""), r("X1", "AAA", 99, 990, "2026-09", "2026-09-04")]
    fiyat = {"AAA": dict(hacim_ortanca=1e4), "BBB": dict(hacim_ortanca=1e4)}
    kur = {"F1": "K", "F2": "K", "F3": "K", "X1": "BAŞKA"}
    hac = {("2026-08-31", "2026-09-04"): {"AAA": 10000.0, "BBB": 1e6}}
    P = icerik_kapsam.grup_pay_degisimi(S, kur, "K", fiyat, hacim_toplam=lambda b0, b1: hac.get((b0, b1), {}))
    assert [(p["onceki"], p["yeni"], p["fonlar"]) for p in P] == [("2026-08-31", "2026-09-04", ["F1", "F2"]), ("2026-09-04", "2026-09-07", ["F3"])]
    a = {g["kod"]: g for g in P[0]["kagitlar"]}["AAA"]
    assert a["net_pay"] == 200 and a["net_tl"] == 2000 and a["alan"] == {"F1": 300} and a["satan"] == {"F2": -100} and a["alim_tl"] == 3000 and a["satim_tl"] == 1000
    assert a["ters_yon"] and a["kesisen_tl"] == 1000 and a["hacim"] == 10000 and abs(a["oran"] - 0.2) < 1e-9 and a["esik_asti"]
    b = {g["kod"]: g for g in P[0]["kagitlar"]}["BBB"]
    assert not b["ters_yon"] and b["kesisen_tl"] == 0 and not b["esik_asti"] and P[0]["kagitlar"][0]["kod"] == "AAA"
    assert P[1]["kagitlar"][0]["net_pay"] == 4 and P[1]["kagitlar"][0]["oran"] is None


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


def test_kuyruk_arsiv_denetimi():
    """22 Eylül 2026 (Chat): kuyrukta yayımlandı işaretli her fon-ay çifti arşivde satır taşımalı; taşımayan kuyruk_arsiv_sapmasi ile döner."""
    if F is None:
        return
    d = tempfile.mkdtemp(); ars = os.path.join(d, "arsiv"); os.makedirs(ars)
    with gzip.open(os.path.join(ars, "fon_icerik_2026-08.csv.gz"), "wt", encoding="utf-8", newline="") as h:
        h.write("fonKodu,raporTarihi,x\nF1,2026-08,1\nF3,2026-08,1\n")
    ky = {"F1": dict(durum="yayimlandi", son="2026-08"), "F2": dict(durum="yayimlandi", son="2026-08"), "F3": dict(durum="hata", son="2026-08"),
          "F4": dict(durum="yayimlandi", son="2026-07"), "F5": dict(durum="kapsam_disi")}
    assert F.kuyruk_arsiv_denetimi(ky, ars) == [("F2", "2026-08"), ("F4", "2026-07")]      # F2 satırsız, F4'ün ay dosyası yok; F3 yayımlandı değil
    assert F.kuyruk_arsiv_denetimi({"F1": dict(durum="yayimlandi", son="2026-08")}, ars) == []


def test_kuyruk_turu_duman():
    """80 numaralı not, bölüm 1: sınanmayan yol ölçülmeyen ölçüdür. Kuyruk turu ağa çıkmadan, tek fonluk sahte raporla koşar: kuyruk kaydı
    yazılıyor mu, alanları yerinde mi (satir, surum, duzen, toplamTablosu, bildirim, portfoyGunu), arşiv dosyası ve koşu durumu üretiliyor mu.
    79 numaralı nottaki hata (kayıt sözlüğünün satır sonu yorumuyla kesilmesi, satir KeyError) bu sınamada yakalanırdı."""
    if F is None:
        return
    d = tempfile.mkdtemp(); veri = os.path.join(d, "veri"); arsiv = os.path.join(d, "arsiv"); os.makedirs(veri)
    json.dump({"K": dict(gecti=True, sinavSurumu=F.SINAV_SURUM, sonuc="gecti", duzen="standart")}, open(os.path.join(veri, "kurucu_duzen.json"), "w", encoding="utf-8"))
    kunye = {"F1": dict(fonKodu="F1", kurucu="K", fundOid="o1", fonTipi="YF", durum="faal", fonAdi="F1 FONU")}
    hedef = F.hedef_ay(date.today())
    x = dict(disclosureIndex=123, publishDate="05." + hedef[5:7] + "." + hedef[:4] + " 10:00:00", subject="Portföy Dağılım Raporu")
    # yayım günü hedef ayın içinde olursa rapor ayı bir önceki ay olur; bir sonraki ayın 5'i verilir
    yy, aa = int(hedef[:4]), int(hedef[5:7]); aa2, yy2 = (aa + 1, yy) if aa < 12 else (1, yy + 1)
    x["publishDate"] = f"05.{aa2:02d}.{yy2} 10:00:00"
    satir = [["F1", hedef, "AAA A.Ş.", "AAA A.Ş.", "AAA", "AAA A.Ş.", "TRAAAA00001", "Hisse Türk", "100", "1000", "100.0", "standart", "kap", "true", "pozisyon", hedef + "-04", hedef]]
    bilgi = dict(ray=hedef, duzen="standart", gun=hedef + "-07", gunEsleme="portföy günü oy 3/3", portfoyGunu=hedef + "-04", gunOy="3/3", raporBasligi=hedef, sapma=0.0, sapmaSebebi="",
                 toplamTablosu=dict(fpd=1000.0, borc=-10.0, nav=990.0), tefasToplam=100.0, raporIci=0.0, listeTam=True, eksikKalem="", satir=1, toplam=100.0,
                 sicSinanan=1, sicHata=0, hisse=1, yabanci=0, bistBos=0, adTemiz=1)
    eski = {k: getattr(F, k) for k in ("kurucu_sinavi", "son_raporlar", "raporlar", "rapor_isle")}
    try:
        F.kurucu_sinavi = lambda *a, **k: ([], {})
        F.son_raporlar = lambda oids, bas, bit: {"F1": x}
        F.raporlar = lambda *a, **k: [x]
        F.rapor_isle = lambda f, x_, *a, **k: ("yayimlandi", "", satir, bilgi)
        durum, ozet = F.kuyruk_turu(kunye, veri, arsiv)
    finally:
        for k, v in eski.items():
            setattr(F, k, v)
    ky = json.load(open(os.path.join(veri, "icerik_kuyruk.json"), encoding="utf-8"))["F1"]
    assert ky["durum"] == "yayimlandi" and ky["satir"] == 1 and ky["surum"] == F.AYRISTIRICI_SURUM and ky["duzen"] == "standart"
    assert ky["toplamTablosu"]["nav"] == 990.0 and ky["bildirim"] == 123 and ky["portfoyGunu"] == hedef + "-04" and ky["son"] == hedef
    assert durum["durum"] == "tamamlandi" and durum["yayimlandiBuTur"] == 1 and durum["satirBuTur"] == 1 and durum["kuyrukArsivSapmasi"] == 0
    assert os.path.exists(os.path.join(veri, "kuyruk_arsiv_sapmasi.txt"))
    assert os.path.exists(os.path.join(arsiv, f"fon_icerik_{hedef}.csv.gz")) and os.path.exists(os.path.join(veri, "fon_icerik_ozet.csv"))


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f(); print("ok", ad)
    print("bütün sınamalar geçti")
