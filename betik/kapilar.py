#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kapı motoru (Görev 2). Kural kaynağı: fon-analizi becerisi, bölüm 3, 3c, 3d ve 4.

Dört kapı ailesi: çıkış (altı), giriş (beş, ayrıca altı çıkış kapısının hiçbirinin tetiklenmemesi),
park, hisse (dört). Her kapı tek bir sözlük döndürür:

    ad, aile, sonuc, tetiklendi, deger, esik, kunye, zorunlu

`sonuc` üç durumludur: "acik", "kapali", "olculemedi". Anlamı aileye göre okunur:
  çıkış ve hisse kapısı "acik" = tetiklendi, fon ya da hisse gündeme alınır;
  giriş ve park kapısı "acik" = şart sağlandı, geçiş serbest.
`tetiklendi` bu ayrımdan bağımsızdır: True kapının şartı sağlandı, False sağlanmadı, None ölçülemedi.
Ölçülemeyen kapı sessizce geçilmiş sayılmaz (kural 14): `gecilebilir()` yalnızca bütün zorunlu kapılar
ölçülmüş ve lehte ise doğru döner. Bileşik puan üretilmez (bölüm 3).

Girdi bir ölçüm sözlüğüdür (pandas Series de olur); anahtarlar aşağıda her kapıda yazılıdır.
Eşikler ve künyeler burada tek yerde durur; başka betikte kapı mantığı yazılmaz (M10).
"""
import math

# ---- eşikler (bölüm 3 ve 4) ----
C1_MADDI = -0.05        # çıkış 1: alt çeyrekten küçük VE eksi yüzde beşten kötü (M6)
C2_PENCERE = 20         # çıkış 2: son 20 işlem günü
C2_ASGARI_GUN = 15      # çıkış 2: pencerenin en az 15'inde alt çeyrek ("dört hafta sürmüş"; CLAUDE.md kapı tablosu)
C3_ESIK = -0.05         # çıkış 3: dört hafta üst üste çıkış, toplam büyüklüğün yüzde beşi
C4_KAYMA = 10.0         # çıkış 4: aile ağırlığında on puan
C5_KAT = 2.0            # çıkış 5: 60 günlük oynaklık, tarihsel ortancanın iki katı
C6_ITFA = -0.15         # çıkış 6: 20 seansta pay adedi yüzde on beş
G1_DILIM = 0.75         # giriş 1: emsalde üst çeyrek, 3 ve 6 ay
G2_AY = 24              # giriş 2: en az 24 ay ölçülebilir fiyat geçmişi (12 Eylül 2026 değerlendirmesi: kapı gözlem yeterliliğini ölçer, kurumsal geçmişi değil)
G2_AD = f"G2 en az {G2_AY} ay ölçülebilir fiyat geçmişi"
G5B_AD = "G5b haber kapısı: kurucu ya da grup şirketi birinci kademe bildirimde geçmiyor"
AGRESIF_ASKIDA = ("C1", "C5")   # agresif dilim: yirmi seanslık fonda ölçülemeyen bu iki kapı, iki zorunlu gerekçe karşılığında askıya alınır
AGRESIF_GEREKCE = ("net_giris20", "kurucu_gecmis")   # askıya almanın şartı: yirmi seanslık net giriş oranı ve kurucunun diğer fonlarının geçmişi
AGRESIF_ASGARI_SEANS = 20
AGRESIF_DILIM = 0.10    # sermayenin yüzde onu (kullanıcı kararı, 12 Eylül 2026: kademesiz)
AGRESIF_TEK_FON = 0.05  # tek fonda yüzde beş
AGRESIF_PAY_ARTIS = 10.0   # büyüme kaynağı: 20 seansta pay adedi yüzde 1.000'in üzerinde artan fon boyutlandırılır
ASGARI_BUY = 250e6      # giriş 3: büyüklük
ASGARI_KISI = 1000      # giriş 3: yatırımcı sayısı
G4_UCRET_DILIM = 0.75   # giriş 4: yönetim ücreti kategorinin üst çeyreğinde değil
G5A_KURUCU = -0.10      # giriş 5: kurucunun bütün fonlarında 20 seanslık net akış, 21 seans önceki büyüklüğe oranı
H2_ENDEKS_PUAN = 30.0   # hisse 2: 12 ayda ana endeksin 30 puandan fazla altında

KUNYE_OLCUM, KUNYE_KAYIT, KUNYE_HESAP, KUNYE_VARSAYIM, KUNYE_PROJEKSIYON = "ölçüm", "kayıt", "hesaplama", "varsayım", "projeksiyon"
HIZ_KUNYE = "kısa dönem hızı; mevcut durumu gösterir, projeksiyon değildir (M2)"


def _al(o, ad):
    """Ölçüm sözlüğünden değer; yok, None ya da NaN ise None."""
    try:
        v = o.get(ad) if hasattr(o, "get") else o[ad]
    except (KeyError, IndexError, TypeError):
        return None
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
        if hasattr(v, "__float__") and not isinstance(v, (bool, str)) and math.isnan(float(v)):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _kapi(ad, aile, tetik, deger, esik, kunye, zorunlu=True, acik_ne="tetik", birim="oran"):
    """Tek kapı sözlüğü. acik_ne: 'tetik' (çıkış, hisse: tetiklenince açık) ya da 'sart' (giriş, park: şart sağlanınca açık).
    birim: değerin ve eşiğin biçimi: oran (yüzde olarak yazılır), puan, dilim (0-1), sayi, tl, ay, gun, metin."""
    sonuc = "olculemedi" if tetik is None else ("acik" if tetik else "kapali")
    return dict(ad=ad, aile=aile, sonuc=sonuc, tetiklendi=tetik, deger=deger, esik=esik, kunye=kunye, zorunlu=zorunlu, birim=birim)


# ================================================================ çıkış kapıları (bölüm 3)

def cikis_kapilari(o):
    """Altı çıkış kapısı. Anahtarlar: ddsimdi, ddceyrek (zirveden düşüş, alt çeyrek); altceyrek_gun, olculen_gun;
    neg4hafta, akis4hafta_o; kayma (puan); vol60, volort; dpay20."""
    k = []
    dd, ddc = _al(o, "ddsimdi"), _al(o, "ddceyrek")
    t = None if dd is None or ddc is None else bool(dd < ddc and dd <= C1_MADDI)
    k.append(_kapi("C1 zirveden düşüş, alt çeyrekten küçük ve -%5'ten kötü", "cikis", t, dd,
                   {"altCeyrek": ddc, "maddi": C1_MADDI}, KUNYE_HESAP, birim="oran"))
    ag, og = _al(o, "altceyrek_gun"), _al(o, "olculen_gun")
    if ag is None or (og is not None and og < C2_ASGARI_GUN):
        t = None
    else:
        t = bool(ag >= C2_ASGARI_GUN)
    k.append(_kapi(f"C2 emsal alt çeyrek, {C2_PENCERE} günün en az {C2_ASGARI_GUN}'inde", "cikis", t, ag,
                   {"asgariGun": C2_ASGARI_GUN, "pencere": C2_PENCERE}, KUNYE_HESAP, birim="gun"))
    n4, a4 = _al(o, "neg4hafta"), _al(o, "akis4hafta_o")
    t = None if n4 is None or a4 is None else bool(n4 and a4 < C3_ESIK)
    k.append(_kapi("C3 dört hafta üst üste net çıkış, toplam >%5", "cikis", t, a4, {"oran": C3_ESIK, "hafta": 4}, KUNYE_HESAP))
    ky = _al(o, "kayma")
    t = None if ky is None else bool(abs(ky) > C4_KAYMA)
    k.append(_kapi("C4 dağılımda yapısal kayma, >10 puan", "cikis", t, ky, {"puan": C4_KAYMA}, KUNYE_OLCUM, birim="puan"))
    v60, vort = _al(o, "vol60"), _al(o, "volort")
    t = None if v60 is None or vort is None or vort == 0 else bool(v60 > C5_KAT * vort)
    k.append(_kapi("C5 60 günlük oynaklık, ortancanın 2 katı", "cikis", t, v60, {"ortanca": vort, "kat": C5_KAT}, KUNYE_HESAP, birim="oran"))
    dp = _al(o, "dpay20")
    t = None if dp is None else bool(dp < C6_ITFA)
    k.append(_kapi("C6 pay adedi 20 seansta -%15", "cikis", t, dp, {"oran": C6_ITFA}, KUNYE_OLCUM))
    return k


# ================================================================ giriş kapıları (bölüm 3)

def giris_kapilari(o):
    """Beş giriş kapısı; çıkış kapılarının hiçbirinin tetiklenmemesi şartı ayrıca `giris_sonucu` içinde sınanır.
    Anahtarlar: r63_d, r126_d (emsal dilimi); gecmis_ay (TEFAS'ta ilk fiyat ayından ölçülen yaş, fon_yas.csv);
    buyukluk, kisi; ucret_dilim (kategori içinde yönetim ücreti dilimi; yoksa ölçülemedi);
    kurucu_akis20 (ölçülebilen bileşen); kurucu_haber (haber bileşeni: True temiz, False sorunlu, yok ise ölçülemedi)."""
    k = []
    r63, r126 = _al(o, "r63_d"), _al(o, "r126_d")
    t = None if r63 is None or r126 is None else bool(r63 >= G1_DILIM and r126 >= G1_DILIM)
    k.append(_kapi("G1 emsalde 3 ve 6 ayda üst çeyrek", "giris", t, {"r63_d": r63, "r126_d": r126}, G1_DILIM, KUNYE_HESAP, acik_ne="sart", birim="dilim"))
    # 12 Eylül 2026 kural metni: yaş yalnızca TEFAS'ta ilk fiyat ayından ölçülür (veri/fon_yas.csv); arşivdeki seans sayısı
    # ve künyedeki üç yıllık getiri alanı yaş delili değildir (M17). Yaş dosyasında karşılığı olmayan fon ölçülemedi döner.
    ay = _al(o, "gecmis_ay")
    t = None if ay is None else bool(ay >= G2_AY)
    k.append(_kapi(G2_AD, "giris", t, ay, G2_AY, KUNYE_OLCUM, acik_ne="sart", birim="ay"))
    b, ks = _al(o, "buyukluk"), _al(o, "kisi")
    t = None if b is None or ks is None else bool(b >= ASGARI_BUY and ks >= ASGARI_KISI)
    k.append(_kapi("G3 büyüklük ve yatırımcı eşiği", "giris", t, {"buyukluk": b, "kisi": ks},
                   {"buyukluk": ASGARI_BUY, "kisi": ASGARI_KISI}, KUNYE_OLCUM, acik_ne="sart", birim="sayi"))
    u = _al(o, "ucret_dilim")
    t = None if u is None else bool(u < G4_UCRET_DILIM)
    k.append(_kapi("G4 yönetim ücreti üst çeyrekte değil", "giris", t, u, G4_UCRET_DILIM, KUNYE_KAYIT, acik_ne="sart", birim="dilim"))
    ka = _al(o, "kurucu_akis20")
    t = None if ka is None else bool(ka > G5A_KURUCU)
    k.append(_kapi("G5a kurucuda kitlesel çıkış yok (20 seans net akış)", "giris", t, ka, G5A_KURUCU, KUNYE_HESAP, acik_ne="sart"))
    # Haber kapısı (12 Eylül 2026 kural metni, bölüm 5): günün bütün KAP bildirimleri tam metin taranır; fonun kurucusu ya da
    # grup şirketi birinci kademe bir eşleşmede geçiyorsa giriş kapısı kapanır. kurucu_haber: True temiz, False birinci kademe
    # eşleşme var, yok ise tarama yapılmamıştır ve kapı ölçülemedi döner (kural 14: geçilmemiş sayılır).
    h = _al(o, "kurucu_haber")
    t = None if h is None else bool(h)
    k.append(_kapi(G5B_AD, "giris", t, h, None, KUNYE_KAYIT, acik_ne="sart", birim="metin"))
    return k


# ================================================================ park kapıları (bölüm 3d)

def park_kapilari(o, park_asgari_buy=None, park_asgari_kisi=None):
    """Park kapıları: altı çıkış kapısının hiçbiri tetiklenmemiş, G5a açık, en az 24 ay ölçülebilir fiyat geçmişi, park için ayrı
    büyüklük ve yatırımcı eşiği, 30 seans getirisi emsal ortancasının altında değil (r30_d >= 0,5), valörler mümkünse sıfır.
    Park eşikleri kullanıcıyla belirlenir; verilmemişse o kapı ölçülemedi döner. Anahtarlar: cikis_kapilari'nınkiler,
    kurucu_akis20, gecmis_ay/g3y, buyukluk, kisi, r30_d, valor_alis, valor_satis."""
    k = []
    c = cikis_kapilari(o)
    tetik = [x for x in c if x["tetiklendi"]]
    olcm = [x for x in c if x["tetiklendi"] is None]
    t = False if tetik else (None if olcm else True)
    k.append(_kapi("P0 çıkış kapılarının hiçbiri tetiklenmemiş", "park", t,
                   {"tetiklenen": [x["ad"] for x in tetik], "olculemeyen": [x["ad"] for x in olcm]}, None, KUNYE_HESAP, acik_ne="sart", birim="metin"))
    g = {x["ad"]: x for x in giris_kapilari(o)}
    for ad in (G2_AD, "G5a kurucuda kitlesel çıkış yok (20 seans net akış)"):
        x = dict(g[ad]); x["aile"] = "park"; k.append(x)
    b, ks = _al(o, "buyukluk"), _al(o, "kisi")
    if park_asgari_buy is None or park_asgari_kisi is None or b is None or ks is None:
        t = None
    else:
        t = bool(b >= park_asgari_buy and ks >= park_asgari_kisi)
    k.append(_kapi("P3 park büyüklük ve yatırımcı eşiği", "park", t, {"buyukluk": b, "kisi": ks},
                   {"buyukluk": park_asgari_buy, "kisi": park_asgari_kisi}, KUNYE_OLCUM, acik_ne="sart", birim="sayi"))
    r30 = _al(o, "r30_d")
    t = None if r30 is None else bool(r30 >= 0.5)
    k.append(_kapi("P4 30 seans getirisi emsal ortancasının altında değil", "park", t, r30, 0.5, KUNYE_HESAP, acik_ne="sart", birim="dilim"))
    va, vs = _al(o, "valor_alis"), _al(o, "valor_satis")
    t = None if va is None or vs is None else bool(va == 0 and vs == 0)
    k.append(_kapi("P5 alış ve satış valörü sıfır (mümkünse)", "park", t, {"alis": va, "satis": vs}, 0, KUNYE_KAYIT,
                   zorunlu=False, acik_ne="sart", birim="gun"))
    return k


# ================================================================ hisse kapıları (bölüm 3c)

def hisse_kapilari(o):
    """Dört hisse çıkış kapısı. Anahtarlar: finansal_bozulma_ceyrek (üst üste bozulan çeyrek sayısı);
    endeks_fark12ay (puan, hissenin ana endekse göre 12 aylık farkı), sektor_fark12ay (sektörün aynı farkı);
    sirkete_ozgu_islem (True/False); agirlik, ust_sinir (hisse diliminin portföy ağırlığı ve üst sınırı).
    Talimat olmasa da bölüm üretilir (M7): girdi boşsa dört kapı da ölçülemedi döner, sessiz kalmaz."""
    k = []
    fb = _al(o, "finansal_bozulma_ceyrek")
    t = None if fb is None else bool(fb >= 2)
    k.append(_kapi("H1 tezin dayandığı finansal büyüklük iki çeyrek üst üste bozuldu", "hisse", t, fb, 2, KUNYE_KAYIT, birim="sayi"))
    ef, sf = _al(o, "endeks_fark12ay"), _al(o, "sektor_fark12ay")
    if ef is None:
        t = None
    elif ef >= -H2_ENDEKS_PUAN:
        t = False
    else:
        t = None if sf is None else bool(ef - sf < -H2_ENDEKS_PUAN)   # sektör karşılaştırması yapılmadan kapı açılmaz
    k.append(_kapi("H2 12 ayda endeksin 30 puandan fazla altında ve sektörle açıklanamıyor", "hisse", t,
                   {"endeksFark": ef, "sektorFark": sf}, -H2_ENDEKS_PUAN, KUNYE_HESAP, birim="puan"))
    so = _al(o, "sirkete_ozgu_islem")
    t = None if so is None else bool(so)
    k.append(_kapi("H3 şirkete özgü düzenleyici işlem, olumsuz görüş ya da ortaklık değişimi", "hisse", t, so, None, KUNYE_KAYIT, birim="metin"))
    ag, us = _al(o, "agirlik"), _al(o, "ust_sinir")
    t = None if ag is None or us is None else bool(ag > us)
    k.append(_kapi("H4 pozisyon hisse diliminin üst sınırını aştı", "hisse", t, ag, us, KUNYE_OLCUM, birim="oran"))
    return k


# ================================================================ özetler ve rapor

def gecilebilir(kapilar):
    """Giriş ve park aileleri için: bütün zorunlu kapılar ölçülmüş ve şartı sağlanmış mı. Bilinemeyen geçilmemiş sayılır."""
    return all(k["tetiklendi"] is True for k in kapilar if k["zorunlu"])


def tetiklenenler(kapilar):
    return [k for k in kapilar if k["tetiklendi"] is True]


def olculemeyenler(kapilar):
    return [k for k in kapilar if k["tetiklendi"] is None]


def giris_sonucu(o, dilim="ana"):
    """Aday fon: altı çıkış kapısının hiçbiri tetiklenmemiş VE giriş kapıları geçilmiş. Dönüş: sözlük
    (durum: acik/kapali, kapali: engelleyen kapılar, bilinmez: ölçülemeyenler, askida, cikis, giris).

    dilim="agresif" (12 Eylül 2026 kural metni, bölüm 6): giriş kapısı 2 uygulanmaz; C1 ve C5 ölçülemiyorsa
    kural 14'ün adı konmuş istisnasıyla askıya alınır, şartı ölçüm sözlüğünde `net_giris20` ve `kurucu_gecmis`
    gerekçelerinin bulunmasıdır; gerekçe yoksa kapı bilinmez kalır ve fon önerilmez. Askıya alma `askida`
    listesinde döner ve her öneride açıkça yazılır. Diğer bütün çıkış kapıları ve haber kapısı aynen uygulanır."""
    c = cikis_kapilari(o); g = giris_kapilari(o)
    askida = []
    if dilim == "agresif":
        g = [k for k in g if k["ad"] != G2_AD]
        gerekce_var = all(_al(o, a) is not None for a in AGRESIF_GEREKCE)
        for k in c:
            if k["ad"].split()[0] in AGRESIF_ASKIDA and k["tetiklendi"] is None and gerekce_var:
                k = dict(k); k["zorunlu"] = False; k["sonuc"] = "askida"; askida.append(k["ad"])
                c[c.index(next(x for x in c if x["ad"] == k["ad"]))] = k
    kapali = [k["ad"] for k in c if k["tetiklendi"] is True] + [k["ad"] for k in g if k["zorunlu"] and k["tetiklendi"] is False]
    bilinmez = [k["ad"] for k in c + g if k["zorunlu"] and k["tetiklendi"] is None]
    return dict(durum="acik" if not kapali and not bilinmez else "kapali", kapali=kapali, bilinmez=bilinmez, askida=askida,
                dilim=dilim, cikis=c, giris=g)


DUZ_ANAHTAR = {"kat", "hafta", "pencere", "asgariGun", "kisi", "maddiGun"}   # sözlük eşiklerinde birimden bağımsız düz sayılar


def _sayi_tr(x, hane):
    return f"{x:,.{hane}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _bicim(v, birim="oran", anahtar=None):
    """Türkçe biçim: ondalık virgül, binlik nokta, eksi işareti yüzde işaretinden önce (-%19,7)."""
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "evet" if v else "hayır"
    if isinstance(v, dict):
        return ", ".join(f"{a} {_bicim(b, birim, a)}" for a, b in v.items())
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v) or "-"
    if isinstance(v, str):
        return v
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if anahtar in DUZ_ANAHTAR or birim in ("sayi", "gun", "ay"):
        return _sayi_tr(x, 0) if float(x).is_integer() else _sayi_tr(x, 1)
    if birim == "oran":
        return ("-" if x < 0 else "") + "%" + _sayi_tr(abs(x) * 100, 1)
    if birim == "puan":
        return _sayi_tr(x, 1) + " puan"
    if birim == "dilim":
        return _sayi_tr(x, 2)
    if birim == "tl":
        return _sayi_tr(x, 0) + " TL"
    return _sayi_tr(x, 2)


def kapi_raporu(kapilar):
    """İnsan okunabilir kapı raporu; brifing bu satırları olduğu gibi kullanır, elle kapı listesi yazmaz (M10).
    Her satır: ad, sonuç, ölçülen değer, eşik, künye."""
    durum = {"acik": "açık", "kapali": "kapalı", "olculemedi": "ölçülemedi", "askida": "askıda (agresif dilim, kural 14 istisnası)"}
    L = []
    for k in kapilar:
        b = k.get("birim", "oran")
        esik = _bicim(k["esik"], b) if k["esik"] is not None else "-"
        L.append(f"{k['ad']}: {durum[k['sonuc']]}; değer {_bicim(k['deger'], b)}, eşik {esik} [{k['kunye']}]"
                 + ("" if k["zorunlu"] else " (bilgi)"))
    return L


def kapi_ozeti(kapilar):
    """Tek satır: tetiklenen, ölçülemeyen. Çıkış ailesinde 'tetiklenen' satış gündemidir."""
    t = [k["ad"].split(" ")[0] for k in tetiklenenler(kapilar)]
    b = [k["ad"].split(" ")[0] for k in olculemeyenler(kapilar) if k["zorunlu"]]
    return ("tetiklenen: " + (", ".join(t) or "yok")) + ("; ölçülemeyen: " + ", ".join(b) if b else "")
