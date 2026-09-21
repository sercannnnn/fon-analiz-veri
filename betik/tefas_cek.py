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
import argparse, csv, gzip, json, os, re, sys, time
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

# 21 EYLUL 2026 SERTLESTIRMESI (M86, gorev dosyasi bolum 2). HTTP 200 basari DEGILDIR: TEFAS hatali govdede de 200 doner ve
# resultList bos gelir; eski hat bunu "sifir satir" diye yazip gunu sahte sifirla dolduruyordu (15 Eylul). Arizalar ayri sinif ve
# ayri cikis koduyla: uc yok (404, yeniden denenmez), bicim (yanit beklenen alanlari tasimiyor, yeniden denenmez), bos yanit,
# cekim (ag). Eksik alana sifir ya da bos yazilmaz: alan yoksa dosya uretilmez.
CIKIS = dict(uc_yok=2, bicim=3, cekim=4, bos=6, saglik=7)
TARIH_DESENI = re.compile(r"^\d{4}-\d{2}-\d{2}")   # yanitin tarih alani; biçim degisirse (GG.AA.YYYY gibi) bicim hatasidir


class UcYok(Exception):
    """HTTP 404: uc adi degismis ya da kaldirilmis; yeniden denemek anlamsizdir."""


class BicimHatasi(Exception):
    """Yanit beklenen bicimde degil: JSON degil, resultList yok, zorunlu alan yok, tarih deseni tutmuyor."""


class BosYanit(Exception):
    """HTTP 200 ama resultList bos: govde ya da uc degismis olabilir; basari sayilmaz."""


def yanit_coz(r, uc, alanlar):
    """Yanitin sozlesmesini sinar ve satir listesini dondurur. Basari olcutu HTTP kodu degil, icerigin bicimidir."""
    try:
        j = r.json()
    except ValueError:
        raise BicimHatasi(f"{uc}: yanit JSON degil (ilk 80 karakter: {r.text[:80]!r})")
    if not isinstance(j, dict) or "resultList" not in j:
        raise BicimHatasi(f"{uc}: yanitta resultList yok; gelen: {sorted(j)[:8] if isinstance(j, dict) else type(j).__name__}")
    if j.get("errorMessage"):
        raise RuntimeError(j["errorMessage"])
    L = j["resultList"]
    if not isinstance(L, list):
        raise BicimHatasi(f"{uc}: resultList liste degil ({type(L).__name__})")
    if not L:
        raise BosYanit(f"{uc}: HTTP 200 ama resultList bos; basari sayilmaz")
    ilk = L[0]
    eksik = [k for k in alanlar if not isinstance(ilk, dict) or k not in ilk]
    if eksik:
        raise BicimHatasi(f"{uc}: zorunlu alan yok {eksik}; gelen alanlar {sorted(ilk)[:14] if isinstance(ilk, dict) else '?'}")
    if not TARIH_DESENI.match(str(ilk.get("tarih") or "")):
        raise BicimHatasi(f"{uc}: tarih deseni tutmuyor ({ilk.get('tarih')!r}); beklenen YYYY-AA-GG")
    return L


def cek(uc, bas, bit, alanlar, deneme=5):
    """Tek aralik icin satirlari dondurur. Ag hatasi ve bos yanitta artan araliklarla bes kez dener (toplam bekleme yaklasik
    8 dakika); 404 ve bicim hatasi yeniden denenmez, aninda yukari firlatilir."""
    son = None
    for i in range(deneme):
        try:
            r = requests.post(KOK_UC + uc, json=govde(bas, bit), headers=BASLIK, timeout=180)
            if r.status_code == 404:
                raise UcYok(f"{uc}: HTTP 404, uc yok (adi degismis ya da kaldirilmis olabilir)")
            r.raise_for_status()
            return yanit_coz(r, uc, alanlar)
        except (UcYok, BicimHatasi):
            raise
        except Exception as e:
            son = e
            print(f"  deneme {i+1}/{deneme} basarisiz ({uc} {bas}-{bit}): {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(BEKLEME[min(i, len(BEKLEME) - 1)])
    if isinstance(son, BosYanit):
        raise son
    raise RuntimeError(f"cekim basarisiz: {uc} {bas}-{bit}: {son}")


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
        parca = cek(uc, pb, pe, alanlar)
        for x in parca:
            anahtar = (x["tarih"], x["fonKodu"])
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            eksik = [k for k in alanlar if k not in x]
            if eksik:      # alan yoksa sifir ya da bos yazilmaz; dosya uretilmez (M86)
                raise BicimHatasi(f"{ad}: satirda zorunlu alan yok {eksik} ({x.get('tarih')} {x.get('fonKodu')})")
            satirlar.append([x[k] if x[k] is not None else "" for k in alanlar])
        print(f"  {ad} {pb}-{pe}: {len(parca):,} satir, {time.time()-t0:.1f} s", file=sys.stderr)

    if not satirlar:
        raise BosYanit(f"{ad}: hic satir gelmedi; dosya uretilmedi")

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


SAGLIK_EN_AZ_GUN = 5     # saglik sinamasi: yeni cekimin son gununden en az bu kadar takvim gunu onceki, arsivde de bulunan en yeni gun


def arsiv_gunu_oku(arsiv, gun):
    """arsiv/tefas_YYYY-MM.csv.gz icinden tek gunun satirlari: fonKodu -> (fiyat, tedPaySayisi, portfoyBuyukluk). Dosya yoksa {}."""
    yol = os.path.join(arsiv or "", f"tefas_{gun[:7]}.csv.gz")
    out = {}
    if not os.path.exists(yol):
        return out
    with gzip.open(yol, "rt", encoding="utf-8", newline="") as h:
        for r in csv.DictReader(h):
            if r.get("tarih", "")[:10] == gun:
                out[r["fonKodu"]] = (_f(r.get("fiyat")), _f(r.get("tedPaySayisi")), _f(r.get("portfoyBuyukluk")))
    return out


def saglik_sinamasi(satirlar, arsiv, en_az_gun=SAGLIK_EN_AZ_GUN):
    """Gorev dosyasi bolum 3 (21 Eylul 2026): bilinen bir fonun bilinen bir gunune ait fiyat yeniden uretilebilmeli. Gun: yeni cekimin
    son gununden en az en_az_gun takvim gunu onceki ve arsivde bulunan en yeni gun; fon: o gun arsivde buyuklugu en yuksek, fiyati pozitif
    fon (belirlenimci, secim bilgisi tasimaz). Fiyat ve pay adedi arsivdekiyle birebir olmali. Donus dict(durum ok|farkli|olculemedi, ...);
    'ok' olmadan son_cekim damgasi tazelenmez (gunluk_cron.sh)."""
    i_t, i_k, i_f, i_p = FIYAT_ALAN.index("tarih"), FIYAT_ALAN.index("fonKodu"), FIYAT_ALAN.index("fiyat"), FIYAT_ALAN.index("tedPaySayisi")
    gunler = sorted({s_[i_t][:10] for s_ in satirlar})
    if not gunler:
        return dict(durum="olculemedi", sebep="yeni cekimde gun yok")
    son = datetime.strptime(gunler[-1], "%Y-%m-%d").date()
    adaylar = [g for g in gunler if (son - datetime.strptime(g, "%Y-%m-%d").date()).days >= en_az_gun]
    for g in reversed(adaylar):
        ars = arsiv_gunu_oku(arsiv, g)
        if not ars:
            continue
        secim = max(((k, v) for k, v in ars.items() if v[0] and v[0] > 0 and v[2]), key=lambda kv: kv[1][2], default=None)
        if not secim:
            continue
        kod, (a_f, a_p, _) = secim
        yeni = next((s_ for s_ in satirlar if s_[i_t][:10] == g and s_[i_k] == kod), None)
        if yeni is None:
            return dict(durum="farkli", gun=g, fonKodu=kod, sebep="fon yeni cekimde yok", arsivFiyat=a_f)
        y_f, y_p = _f(yeni[i_f]), _f(yeni[i_p])
        ayni = (y_f is not None and abs(y_f - a_f) < 1e-9) and (a_p is None or (y_p is not None and abs(y_p - a_p) < 0.5))
        return dict(durum="ok" if ayni else "farkli", gun=g, fonKodu=kod, arsivFiyat=a_f, yeniFiyat=y_f, arsivPay=a_p, yeniPay=y_p)
    return dict(durum="olculemedi", sebep=f"arsivde {en_az_gun} gunden eski ortak gun yok ({arsiv})")


def sabit_referans_sinamasi(referans_yolu, cek_fn=None):
    """Kendine referans sorunu (21 Eylul 2026, Chat): arsivden secilen hareketli gun surukleyi yakalar ama sistematik bozulmayi yakalamaz;
    arsiv de ayni hatli kosuyla yazildiysa hatali veri hatali veriyle eslesir. Bu yuzden depoda SABIT, elle dogrulanmis referans kayitlari
    durur (veri/saglik_referans.csv: fonKodu, tarih, fiyat, tedPaySayisi, kaynak, dogrulama). Her referans gunu TEFAS'tan tek gunluk
    istekle yeniden cekilir ve kayitla birebir karsilastirilir. Donus dict(durum ok|farkli|olculemedi, kayitlar=[...])."""
    if not referans_yolu or not os.path.exists(referans_yolu):
        return dict(durum="olculemedi", sebep=f"referans dosyasi yok ({referans_yolu})", kayitlar=[])
    refler = [r for r in csv.DictReader(open(referans_yolu, encoding="utf-8")) if r.get("fonKodu") and r.get("tarih")]
    if not refler:
        return dict(durum="olculemedi", sebep="referans dosyasi bos", kayitlar=[])
    cek_fn = cek_fn or (lambda g: cek("fonGnlBlgSiraliGetir", g, g, FIYAT_ALAN))
    out, durum = [], "ok"
    for gun in sorted({r["tarih"][:10] for r in refler}):
        g = gun.replace("-", "")
        try:
            satirlar = cek_fn(g)
        except Exception as e:
            for r in refler:
                if r["tarih"][:10] == gun:
                    out.append(dict(fonKodu=r["fonKodu"], gun=gun, durum="olculemedi", sebep=str(e)[:120]))
            durum = "farkli" if durum == "farkli" else "olculemedi"
            continue
        for r in refler:
            if r["tarih"][:10] != gun:
                continue
            x = next((s_ for s_ in satirlar if s_.get("fonKodu") == r["fonKodu"] and str(s_.get("tarih", ""))[:10] == gun), None)
            y_f, y_p = (_f(x.get("fiyat")), _f(x.get("tedPaySayisi"))) if x else (None, None)
            r_f, r_p = _f(r.get("fiyat")), _f(r.get("tedPaySayisi"))
            ayni = x is not None and y_f is not None and abs(y_f - r_f) < 1e-9 and (r_p is None or (y_p is not None and abs(y_p - r_p) < 0.5))
            out.append(dict(fonKodu=r["fonKodu"], gun=gun, durum="ok" if ayni else "farkli", referansFiyat=r_f, gelenFiyat=y_f, referansPay=r_p, gelenPay=y_p))
            if not ayni:
                durum = "farkli"
    return dict(durum=durum, kayitlar=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", help="yyyyMMdd, varsayilan: bugun - 10 gun")
    ap.add_argument("--bit", help="yyyyMMdd, varsayilan: bugun")
    ap.add_argument("--uc", default="hepsi", choices=["fiyat", "dagilim", "hepsi"])
    ap.add_argument("--cikti", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "veri"))
    ap.add_argument("--arsiv", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "arsiv"), help="saglik sinamasi icin aylik arsiv")
    ap.add_argument("--saglik", action="store_true", help="hareketli gun (arsiv) ve sabit referans (saglik_referans.csv) sinamasi; farkli ise cikis 7")
    ap.add_argument("--referans", default=None, help="sabit referans dosyasi; varsayilan <cikti>/saglik_referans.csv")
    a = ap.parse_args()

    bugun = date.today()
    bit = a.bit or bugun.strftime("%Y%m%d")
    bas = a.bas or (bugun - timedelta(days=10)).strftime("%Y%m%d")
    os.makedirs(a.cikti, exist_ok=True)

    sonuc = {}
    try:
        for ad in (["fiyat", "dagilim"] if a.uc == "hepsi" else [a.uc]):
            sonuc[ad] = uc_calistir(ad, bas, bit, a.cikti)
    except UcYok as e:
        print(f"HATA uc_yok: {e}", file=sys.stderr); sys.exit(CIKIS["uc_yok"])
    except BicimHatasi as e:
        print(f"HATA bicim: {e}", file=sys.stderr); sys.exit(CIKIS["bicim"])
    except BosYanit as e:
        print(f"HATA bos_yanit: {e}", file=sys.stderr); sys.exit(CIKIS["bos"])
    except Exception as e:
        print(f"HATA cekim: {e}", file=sys.stderr); sys.exit(CIKIS["cekim"])
    if "fiyat" in sonuc:
        k = kapsam_hesapla(sonuc["fiyat"], sonuc.get("dagilim"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        yol = kapsam_yaz(a.cikti, k)
        print(f"{yol}: son gun {k['sonGun']}, kayit {k['sonGunKayit']:,}, fiyatsiz {k['sonGunFiyatsiz']:,}, "
              f"dagilim {k['sonGunDagilimSatir']:,}, tam kapsamli son gun {k['tamKapsamliSonGun']}, kimlik sapan {k['kimlikSapmaSayisi']}")
        if a.saglik:
            s = saglik_sinamasi(sonuc["fiyat"], a.arsiv)
            print(f"saglik hareketli gun: {s}")
            r = sabit_referans_sinamasi(a.referans or os.path.join(a.cikti, "saglik_referans.csv"))
            print(f"saglik sabit referans: {r}")
            if s["durum"] == "farkli" or r["durum"] == "farkli":
                sys.exit(CIKIS["saglik"])


if __name__ == "__main__":
    main()
