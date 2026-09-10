#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEFAS gunluk cekici. Tarayici gerektirmez; yalnizca 'requests' kullanir.
Sistem python3 ile calisir, sanal ortam gerekmez.

Kullanim:
  tefas_cek.py                                 son 10 gunu ceker, iki ucu da
  tefas_cek.py --bas 20250227 --bit 20250901   verilen araligi aylik parcalarla ceker
  tefas_cek.py --uc fiyat                      yalnizca fiyat ucu (fiyat | dagilim | hepsi)
  tefas_cek.py --cikti /yol/veri               CSV'lerin yazilacagi klasor

Ciktilar:
  <cikti>/tefas_gunluk_<bit>.csv    tarih,fonKodu,fiyat,kisiSayisi,portfoyBuyukluk,tedPaySayisi
  <cikti>/tefas_dagilim_<bit>.csv   tarih,fonKodu + 56 varlik sinifi agirligi (yuzde)
"""
import argparse, csv, json, os, sys, time
from datetime import date, datetime, timedelta, timezone
import requests

KOK_UC = "https://www.tefas.gov.tr/api/funds/"
BASLIK = {
    "Content-Type": "application/json",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
    "User-Agent": "Mozilla/5.0 (fon-analiz cekici)",
}

# Fiyat ucu
# fonUnvan eklendi 07.09.2026 (M9): ayni yanit zaten unvani donuyordu, kaydedilmiyordu.
# Unvani olmayan fon emsal grubuna atanamiyor ve taramaya hic girmiyordu.
FIYAT_ALAN = ["tarih", "fonKodu", "fonUnvan", "fiyat", "kisiSayisi", "portfoyBuyukluk", "tedPaySayisi"]

# Dagilim ucu: TEFAS'in 56 varlik sinifi kodu. Sira sabittir, CSV basligi budur.
# Onemli olanlar: hs hisse senedi, tr ters repo, r repo (eksi = borclanma),
# vmtl vadeli mevduat TL, vmd vadeli mevduat doviz, dt devlet tahvili,
# ost ozel sektor tahvili, kh kiymetli maden, yyf yabanci yatirim fonu, yhs yabanci hisse.
DAGILIM_ALAN = ["tarih", "fonKodu",
    "bb", "byf", "d", "db", "bpp", "btaa", "btas", "dt", "dot", "eut", "fb", "fkb",
    "gas", "gsykb", "gsyy", "gykb", "gyy", "hb", "hs", "kba", "kh", "khau", "khd",
    "khtl", "kks", "kksd", "kkstl", "kksyd", "km", "kmbyf", "kmkba", "kmkks", "kibd",
    "osks", "ost", "r", "t", "tpp", "tr", "vdm", "vm", "vmau", "vmd", "vmtl", "vint",
    "yba", "ybkb", "ybosb", "ybyf", "yhs", "ymk", "yyf", "oksyd", "osdb"]

UCLAR = {
    "fiyat":   ("fonGnlBlgSiraliGetir", FIYAT_ALAN,   "tefas_gunluk_{}.csv"),
    "dagilim": ("dagilimSiraliGetirT",  DAGILIM_ALAN, "tefas_dagilim_{}.csv"),
}


def govde(bas, bit):
    return {
        "dil": "TR", "fonTipi": "YAT", "fonKod": None, "fonGrup": None,
        "basTarih": bas, "bitTarih": bit, "fonTurKod": None, "fonUnvanTip": None,
        "kurucuKod": None, "fonTurAciklama": None, "sfonTurKod": None,
        "basSira": 1, "bitSira": 200000, "sira": "tarih", "yon": "ASC",
    }


BEKLEME = (30, 60, 120, 240)    # denemeler arasi saniye; en kotu durumda uc basina ~8 dk


def cek(uc, bas, bit, deneme=5):
    """Tek aralik icin satirlari dondurur. Hata olursa artan araliklarla bes kez dener
    (toplam bekleme yaklasik 8 dakika)."""
    for i in range(deneme):
        try:
            r = requests.post(KOK_UC + uc, json=govde(bas, bit), headers=BASLIK, timeout=180)
            r.raise_for_status()
            j = r.json()
            if j.get("errorMessage"):
                raise RuntimeError(j["errorMessage"])
            return j.get("resultList") or []
        except Exception as e:
            print(f"  deneme {i+1}/{deneme} basarisiz ({uc} {bas}-{bit}): {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(BEKLEME[min(i, len(BEKLEME) - 1)])
    raise SystemExit(f"cekim basarisiz: {uc} {bas}-{bit}")


def aylik_parcalar(bas, bit):
    """TEFAS tek istekte azami bir ay verir ("Tarih araligi 1 ayi asamaz"); ay sonundan
    baslayan 30 gunluk parca bu siniri asiyordu. Parcalar 27 gun tutulur."""
    b = datetime.strptime(bas, "%Y%m%d").date()
    s = datetime.strptime(bit, "%Y%m%d").date()
    while b <= s:
        e = min(b + timedelta(days=27), s)
        yield b.strftime("%Y%m%d"), e.strftime("%Y%m%d")
        b = e + timedelta(days=1)


TAM_ORAN = 0.98      # kapsam: gecerli fiyatli fon sayisi penceredeki en yuksek gunun en az bu kati ise gun tam kapsamlidir
FIYAT_ONDALIK = 6        # TEFAS pay fiyatini alti ondalikla yayimlar; kimlik sinamasinin toleransi bu basim hassasiyetinden turer
KIMLIK_KURUS = 0.01      # ek mutlak tolerans, TL


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kapsam_hesapla(fiyat, dagilim, cekim_zamani):
    """Gorev 3.1 ve 3.4: kapsam cekim aninda olculur. fiyat ve dagilim, uc_calistir'in dondurdugu satir listeleridir
    (fiyat: FIYAT_ALAN sirasinda). Donus: kapsam_son.json'a yazilacak sozluk. Gun tam: gecerli fiyatli fon sayisi
    penceredeki en yuksek gunun TAM_ORAN kati ve dagilim satiri da oyle. Kimlik: her fonda pay adedi x fiyat = buyukluk;
    sapan fonlarin kodu yazilir; sapma sifir cikmadan akis hesabi kullanilmaz."""
    gun = {}
    kimlik_sapan = []
    i_t, i_k, i_f = FIYAT_ALAN.index("tarih"), FIYAT_ALAN.index("fonKodu"), FIYAT_ALAN.index("fiyat")
    i_b, i_p = FIYAT_ALAN.index("portfoyBuyukluk"), FIYAT_ALAN.index("tedPaySayisi")
    for s_ in fiyat:
        g = gun.setdefault(s_[i_t], dict(kayit=0, gecerli=0, dagilim=0))
        g["kayit"] += 1
        f, b, pay = _f(s_[i_f]), _f(s_[i_b]), _f(s_[i_p])
        if f and f > 0:
            g["gecerli"] += 1
            if b is not None and pay is not None and b > 0:
                # tolerans: pay adedi x fiyatin son basamaginin yarisi + bir kurus (olculen basim hassasiyeti, uydurma degil)
                tol = pay * (10 ** -FIYAT_ONDALIK) / 2.0 + KIMLIK_KURUS
                if abs(pay * f - b) > tol:
                    kimlik_sapan.append(dict(tarih=s_[i_t], fonKodu=s_[i_k], payXfiyat=round(pay * f, 2), buyukluk=b, tolerans=round(tol, 2)))
    for s_ in dagilim or []:
        if s_[0] in gun:
            gun[s_[0]]["dagilim"] += 1
    enb_g = max((g["gecerli"] for g in gun.values()), default=0)
    enb_d = max((g["dagilim"] for g in gun.values()), default=0)
    for t, g in gun.items():
        g["fiyatsiz"] = g["kayit"] - g["gecerli"]
        g["tam"] = bool(g["gecerli"] >= TAM_ORAN * enb_g and (not enb_d or g["dagilim"] >= TAM_ORAN * enb_d))
    tam_gunler = sorted(t for t, g in gun.items() if g["tam"])
    son = max(gun) if gun else None
    return dict(
        cekimZamaniUtc=cekim_zamani,
        sonGun=son,
        toplamKayit=len(fiyat),
        sonGunKayit=gun[son]["kayit"] if son else 0,
        sonGunFiyatsiz=gun[son]["fiyatsiz"] if son else 0,
        sonGunDagilimSatir=gun[son]["dagilim"] if son else 0,
        tamKapsamliSonGun=tam_gunler[-1] if tam_gunler else None,
        kimlikSapmaSayisi=len(kimlik_sapan),
        kimlikSapanlar=kimlik_sapan[:200],
        gunler={t: gun[t] for t in sorted(gun)},
        tanim=f"tam gun: gecerli fiyatli fon sayisi penceredeki en yuksek gunun en az {TAM_ORAN} kati ve dagilim satiri da oyle; "
              "kimlik: tedPaySayisi x fiyat = portfoyBuyukluk, tolerans pay x 0,5e-6 + 0,01 TL (fiyat alti ondalikla basilir); brifing kapsam satiri yalnizca bu dosyadan beslenir",
    )


def kapsam_yaz(cikti, kapsam):
    """veri/kapsam_son.json: mevcut anahtarlar (dagilimGecikmeGun vb.) korunur, kapsam alanlari uzerine yazilir."""
    yol = os.path.join(cikti, "kapsam_son.json")
    try:
        d = json.load(open(yol, encoding="utf-8"))
    except Exception:
        d = {}
    d.update(kapsam)
    json.dump(d, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return yol


def uc_calistir(ad, bas, bit, cikti):
    uc, alanlar, dosya = UCLAR[ad]
    satirlar, gorulen = [], set()
    for pb, pe in aylik_parcalar(bas, bit):
        t0 = time.time()
        parca = cek(uc, pb, pe)
        for x in parca:
            anahtar = (x["tarih"], x["fonKodu"])
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            satirlar.append([x.get(k) if x.get(k) is not None else "" for k in alanlar])
        print(f"  {ad} {pb}-{pe}: {len(parca):,} satir, {time.time()-t0:.1f} s", file=sys.stderr)

    if not satirlar:
        raise SystemExit(f"{ad}: hic satir gelmedi; rapor uretilmemeli")

    yol = os.path.join(cikti, dosya.format(bit))
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(alanlar)
        w.writerows(satirlar)

    tarihler = sorted({s[0] for s in satirlar})
    fonlar = {s[1] for s in satirlar}
    print(f"{yol}: {len(satirlar):,} satir, {len(fonlar):,} fon, "
          f"{len(tarihler)} gun ({tarihler[0]} .. {tarihler[-1]})")
    return satirlar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", help="yyyyMMdd, varsayilan: bugun - 10 gun")
    ap.add_argument("--bit", help="yyyyMMdd, varsayilan: bugun")
    ap.add_argument("--uc", default="hepsi", choices=["fiyat", "dagilim", "hepsi"])
    ap.add_argument("--cikti", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "veri"))
    a = ap.parse_args()

    bugun = date.today()
    bit = a.bit or bugun.strftime("%Y%m%d")
    bas = a.bas or (bugun - timedelta(days=10)).strftime("%Y%m%d")
    os.makedirs(a.cikti, exist_ok=True)

    sonuc = {}
    for ad in (["fiyat", "dagilim"] if a.uc == "hepsi" else [a.uc]):
        sonuc[ad] = uc_calistir(ad, bas, bit, a.cikti)
    if "fiyat" in sonuc:
        k = kapsam_hesapla(sonuc["fiyat"], sonuc.get("dagilim"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        yol = kapsam_yaz(a.cikti, k)
        print(f"{yol}: son gun {k['sonGun']}, kayit {k['sonGunKayit']:,}, fiyatsiz {k['sonGunFiyatsiz']:,}, "
              f"dagilim {k['sonGunDagilimSatir']:,}, tam kapsamli son gun {k['tamKapsamliSonGun']}, kimlik sapan {k['kimlikSapmaSayisi']}")


if __name__ == "__main__":
    main()
