#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Depoda duran, kendi kendine yeten sınama (kural 20: her kuralın bir çağıranı ve çağıranı gösteren bir sınaması olur).
Çalıştırma: python3 betik/sinama_kap_izleme.py  (pytest de toplar). Yalnızca standart kütüphane ve kap_izleme.

Kanıtlar: rutin süzgeç tür adıyla (M24, M25), ağır konu kökü (M24), eksik gövde triyajı (madde 3), haber kapısının TEK giriş
noktası `haber_kapisi` ve komut satırının bu noktayı çağırdığı (M26), kapanmış pozisyonun sermayeye katılmadığı (M27)."""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kap_izleme as K
import oneri

GRUP = {"ÖRNEK PORTFÖY": ["ORNEK PORTFOY", "ORNEK GRUBU"]}


def _liste():
    return K.izleme_listesi([{"kod": "AAA", "tip": "Fon"}], "", "", ek_kurucular=["ÖRNEK PORTFÖY"], kurucu_grup=GRUP)


def test_rutin_ve_agir_konu():
    assert K.rutin_mu("01285 - Borsa Dışı Repo - Ters Repo Sözleşmesi") and not K.rutin_mu("Repo Karşı Tarafı Temerrüdü")
    assert not K.rutin_mu("İzahname") and not K.rutin_mu("Finansal Tablo Bildirimi") and len(K.RUTIN_TURLER) == 12
    assert K.agir_konu_mu("Repo Karşı Tarafı Temerrüdü") and K.agir_konu_mu("Şirketin iflası") and not K.agir_konu_mu("Fiyat Raporu")


def test_haber_kapisi_tek_giris():
    b = [dict(id=1, sirket="ÖRNEK PORTFÖY YÖNETİMİ A.Ş.", konu="Yatırımcı Bilgi Formu", ozet="", metin="", metinDurumu="tam", fon="X"),
         dict(id=2, sirket="ÖRNEK PORTFÖY YÖNETİMİ A.Ş.", konu="Fon Sürekli Bilgilendirme Formu", ozet="Ortak temerrüdü", metin="", metinDurumu="tam", fon="X"),
         dict(id=3, sirket="BAŞKA A.Ş.", konu="Özel Durum Açıklaması (Genel)", ozet="Ornek Grubu ile birleşme görüşmeleri", metin="", metinDurumu="tam", fon="")]
    r = K.haber_kapisi(b, _liste(), ["ÖRNEK PORTFÖY"], kurucu_grup=GRUP)
    assert r["elenen"] == 2 and r["haber"]["ÖRNEK PORTFÖY"] is False and {v["id"] for v in r["k1"]} == {2, 3}
    b3 = [dict(id=5, sirket="ÖRNEK FİNANS A.Ş.", konu="Özel Durum Açıklaması (Genel)", ozet="konkordato", metin="", metinDurumu="eksik", fon="")]
    r3 = K.haber_kapisi(b3, _liste(), ["ÖRNEK PORTFÖY"], kurucu_grup={"ÖRNEK PORTFÖY": ["ORNEK PORTFOY", "ORNEK FINANS"]})
    assert r3["haber"]["ÖRNEK PORTFÖY"] is None and len(r3["engelleyici"]) == 1


def test_komut_satiri_haber_kapisini_cagirir():
    """Depodaki çağıran: kap_izleme.py komut satırı. Çıktıda haber_kapisi ve engelleyici alanları yalnızca o yoldan gelir."""
    d = tempfile.mkdtemp()
    poz = os.path.join(d, "poz.json"); bil = os.path.join(d, "bil.json"); grp = os.path.join(d, "grup.json"); cik = os.path.join(d, "cikti.json")
    json.dump([{"kod": "AAA", "tip": "Fon"}], open(poz, "w"))
    json.dump(dict(govdeTam=1, bildirimler=[dict(id=3, sirket="BAŞKA A.Ş.", konu="Özel Durum Açıklaması (Genel)", ozet="Ornek Grubu ile birleşme", metin="", metinDurumu="tam", fon="")]), open(bil, "w"))
    json.dump(GRUP, open(grp, "w"), ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kap_izleme.py"), "--poz", poz, "--icerik", "", "--kunye", "",
                        "--bildirim", bil, "--kurucu-grup", grp, "--kurucular", "ÖRNEK PORTFÖY", "--cikti", cik], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    j = json.load(open(cik, encoding="utf-8"))
    assert j["haber_kapisi"] == {"ÖRNEK PORTFÖY": False} and "birinci kademe" in j["kapsam"]


def test_kapanmis_pozisyon_sermayeye_katilmaz():
    """M27: kapanmış pozisyon içeren defterle hesaplanan sermaye, o pozisyon çıkarılmış defterle hesaplanana eşittir."""
    defter = {"k1": dict(kod="AAA", adet=100, deger=1000.0), "k2": dict(kod="BBB", adet=0, deger=0.0, durum="KAPANDI", kapanis_deger=500.0),
              "k3": dict(kod="CCC", adet=5, deger=300.0, durum="KAPANDI"), "k4": dict(kod="DDD", adet=0, deger=200.0)}
    tam = oneri.sermaye_hesapla(defter, 700.0); azaltilmis = oneri.sermaye_hesapla({"k1": defter["k1"]}, 700.0)
    assert tam["sermaye"] == azaltilmis["sermaye"] == 1700.0 and tam["kapanan"] == 3 and tam["kodlar"] == {"AAA": 1000.0}




def test_m28_bellek_deposu_defter_uzerinden_sureklilik():
    """M28: bulutta durum dosyada değil defterde; gün 1 belgeleri deftere, gün 2 defterden kurulur ve sayaç 2 döner."""
    b1 = oneri.BellekDeposu(); assert oneri.ardisik_guncelle("2026-09-14", ["AAA"], depo=b1)["AAA"] == 1
    a, s = b1.belgeler()
    b2 = oneri.BellekDeposu.defterden(a, s); assert oneri.ardisik_guncelle("2026-09-15", ["AAA"], depo=b2)["AAA"] == 2
    d = tempfile.mkdtemp(); d2 = tempfile.mkdtemp()      # dosya deposu her gün temiz dizinde: 1 döner (bulut kesintisi)
    assert oneri.ardisik_guncelle("2026-09-15", ["AAA"], depo=oneri.DosyaDeposu(os.path.join(d2, "a.json"), os.path.join(d2, "s.json")))["AAA"] == 1


if __name__ == "__main__":
    for ad, f in list(globals().items()):
        if ad.startswith("test_") and callable(f):
            f(); print("ok", ad)
    print("bütün sınamalar geçti")
