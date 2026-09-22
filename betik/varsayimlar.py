#!/usr/bin/env python3
"""Varsayım sabitlerinin tek listesi (82 numaralı not, 15 Eylül 2026).

Kural: her eşik adlı bir sabittir (kural 23) ve ya kullanıcı onayı almıştır ya da varsayımdır. Bu dosya sabitleri tek yerde listeler; DEĞERİ
buradan değil, sabitin yaşadığı modülden okur (liste ile kod ayrışamaz). Her kayıt: kimlik (Chat'in karar listesindeki harf), modül, sabit adı,
önerildiği not, onay durumu (onaylı / bekliyor / kodda yok), ne yaptığı, onay tarihi. Portföy bilgisi taşımaz (açık depo); fon kodu, banka adı yok.

Kullanım: python3 varsayimlar.py            -> markdown tablo
          python3 varsayimlar.py --json     -> kayıtlar
"""
import importlib, json, sys

KAYITLAR = [
    # kimlik, modül, sabit, not, durum, açıklama, onay
    ("B1", "icerik_kapsam", "GRUP_PAYI_ESIK", 67, "bekliyor", "kurucu grubu payı: kategoriye göre uyarı ve aykırılık eşiği (puan); fon sepeti muaf", ""),
    ("B2", "icerik_kapsam", "KATILIM_ORANI", 69, "bekliyor", "çıkış süresi tabanı: günlük hacmin fiyatı bozmadan alınabilir payı", ""),
    ("B3", "icerik_kapsam", "CIKIS_UYARI_GUN", 69, "bekliyor", "çıkış süresi uyarı eşiği (gün)", ""),
    ("B3", "icerik_kapsam", "CIKIS_AYKIRI_GUN", 69, "bekliyor", "çıkış süresi aykırılık eşiği (gün)", ""),
    ("B4", "icerik_kapsam", "AKIS_UYARI_ORAN", 69, "bekliyor", "portföy gününden bu yana akış bu oranı aşarsa 'alım satım yok varsayımı zayıf'", ""),
    ("B4", "icerik_kapsam", "AKIS_OLCULEMEDI_ORAN", 73, "bekliyor", "akış bu oranı aşarsa yoğunlaşma ve grup payı kapı için ölçülemedi", ""),
    ("B5", None, "TOPLU_YATIRIM_ARACI_SINIRI", 65, "kodda yok", "fon sepetinde tek BYF ağırlığı; %35 uyarı, %50 sert önerildi, onaysız kodlanmadı", ""),
    ("B6", "icerik_kapsam", "GRUP_HACIM_PAYI_ESIK", 81, "bekliyor", "kurucu grubunun bir kâğıttaki net alım ya da satımının pencerede borsa hacmine oranı; aşan kalın", ""),
    ("B7", "icerik_kapsam", "PAY_DEGISIM_HACIM_ESIK_GUN", 79, "bekliyor", "tek raporda bu kadar günlük ortanca hacmi aşan alım ya da satım kalın", ""),
    ("B8", "icerik_kapsam", "ICERIK_YAS_ESIK_GUN", 59, "onaylı", "içerik tazeliği: rapor bu kadar günden eskiyse bakış geçirgen ve yoğunlaşma ölçülemedi", "15 Eylül 2026"),
    ("B9", "icerik_kapsam", "TEK_KARSI_TARAF_SINIR", 59, "bekliyor", "tek ihraççı sınırı (puan); Hazine muaf", ""),
    ("B10", "icerik_kapsam", "ARTIK_ORAN", 75, "bekliyor", "portföy değeri / NAV bu oranın üstünde kaldıraç satırı kalın", ""),
    ("B11", "oneri", "OLAY_PENCERE_GUN", 79, "bekliyor", "olay etki ölçüsü penceresi (olaydan sonraki TEFAS günü sayısı)", ""),
    ("B12", "oneri", "PARK_RISK_ARALIGI", 39, "bekliyor", "park fonu risk değeri aralığı; boş ve sıfır hane elenir", ""),
    ("B13", "denetim", "COKUS_ORAN", 35, "bekliyor", "büyüklük tek seansta bu oranın üstünde düşerse çöküş", ""),
    ("B13", "denetim", "COKUS_KALICI_ORAN", 35, "bekliyor", "düşüşten sonra büyüklük önceki seviyenin bu oranına dönmüyorsa kalıcı", ""),
    ("B14", "denetim", "ANI_DUSUS_ORAN", 39, "bekliyor", "büyüklük ya da fiyat tek seansta bu orandan fazla düşerse ani düşüş (park dışlamasına girmez, kullanıcı kararı)", ""),
    ("B14", "denetim", "DEGER_KAYBI_PUAN", 39, "bekliyor", "20 seans getirisi kategori ortancasından bu kadar puan gerideyse değer kaybı (park dışlamasına girer)", ""),
    ("B15", "denetim", "BUYUME_KAT", 46, "bekliyor", "20 seansta pay adedi ya da büyüklük bu katı aşarsa büyüme kaydı", ""),
    ("B16", "kap_izleme", "TASFIYE_KURUCU_ESIK", 52, "bekliyor", "aynı kurucuda pencere içinde bu kadar kamuya açık fon tasfiyesi kurucuyu kapatır", ""),
    ("B16", "kap_izleme", "TASFIYE_PENCERE_GUN", 52, "bekliyor", "tasfiye sayım penceresi (takvim günü)", ""),
    ("B18", "fon_icerik_cek", "YENIDEN_CEKIM_TAVAN", 99, "onaylı", "kuyruk-arşiv sapmasında tur başına kurtarma kuyruğuna alınan en çok fon; kurtarma normal turdan AYRI bütçeyle koşar (Chat şartı)", "22 Eylül 2026"),
    ("B19", "fon_icerik_cek", "KURTARMA_BUTCE", 101, "onaylı", "kurtarma aşamasının kendi istek bütçesi; normal turun 400'ünden almaz, ona vermez", "22 Eylül 2026"),
    ("B20", "kapilar", "FIYAT_YASI_ESIK_IS_GUNU", 107, "bekliyor", "kural C: fonun son sıfır dışı fiyatı ölçüm gününden bu kadar iş günü eskiyse çıkış kapıları ölçülemedi (iki tarafta 3)", ""),
    ("B17", "takvim", "VERI_YASI_UYARI_IS_GUNU", 91, "bekliyor", "ölçü 13: son veri günü ile bugün arasındaki iş günü bunu aşarsa brifing 'veri eski' uyarısı", ""),
    ("O1", "oneri", "PARK_ASGARI_BUYUKLUK", 42, "onaylı", "park fonu asgari büyüklük (TL)", "13 Eylül 2026"),
    ("O2", "oneri", "PARK_MEVCUT_RISK_ESIT_KABUL", 59, "onaylı", "mevcut park fonu ancak en az onun kadar kazandıran ve daha az riskli adayla değişir (eşit risk kabul edilmez)", "15 Eylül 2026"),
    ("O3", "kapilar", "G2_AY", 10, "onaylı", "giriş kapısı 2: en az bu kadar ay ölçülebilir fiyat geçmişi", "12 Eylül 2026"),
    ("O4", "kapilar", "AGRESIF_DILIM", 8, "onaylı", "agresif dilim: sermayenin payı", "12 Eylül 2026"),
    ("O4", "kapilar", "AGRESIF_TEK_FON", 8, "onaylı", "agresif dilimde tek fon payı", "12 Eylül 2026"),
    ("O5", "denetim", "SAPMA_YAS_ESIK_IS_GUNU", 28, "onaylı", "açık sapma bu kadar iş gününü aşınca ayrı satırda", "13 Eylül 2026"),
    ("O6", "denetim", "COKUS_KESIN_SEANS", 36, "onaylı", "çöküşten sonra bu kadar seans yoksa kayıt kesinleşmemiş", "13 Eylül 2026"),
    ("O7", "kapsam", "TAM_ORAN", 40, "onaylı", "tam kapsamlı gün: fiyatlı fon sayısı pencere azamisinin bu katı", "13 Eylül 2026"),
]


def deger(modul, ad):
    """Sabitin bugünkü değeri modülünden okunur; modül yoksa (kodda yok) None."""
    if not modul:
        return None
    return getattr(importlib.import_module(modul), ad)


def kayitlar():
    out = []
    for kimlik, modul, ad, not_, durum, aciklama, onay in KAYITLAR:
        out.append(dict(kimlik=kimlik, modul=modul, sabit=ad, deger=deger(modul, ad), not_=not_, durum=durum, aciklama=aciklama, onay=onay))
    return out


def bekleyenler():
    return [k for k in kayitlar() if k["durum"] != "onaylı"]


def _d(v):
    if v is None:
        return "kodda yok"
    if isinstance(v, bool):
        return "evet" if v else "hayır"
    if isinstance(v, float):
        return (f"{v:.4f}".rstrip("0").rstrip(".") if v < 1000 else f"{v:,.0f}".replace(",", ".")).replace(".", ",") if v < 1000 else f"{v:,.0f}".replace(",", ".")
    if isinstance(v, dict):
        return "; ".join(f"{k}: {'/'.join(_d(x) for x in (val if isinstance(val, (list, tuple)) else [val]))}" for k, val in v.items())
    if isinstance(v, (list, tuple)):
        return "-".join(_d(x) for x in v)
    return str(v)


def metin(baslik="## Varsayımlar ve onay durumu"):
    """Brifingin sonuna giden blok: değerler koddan okunur, tablo elle yazılmaz."""
    K = kayitlar(); bek = [k for k in K if k["durum"] != "onaylı"]
    L = [baslik, "",
         f"Adlı eşikler tek listede (82 numaralı not; değerler sabitin yaşadığı modülden okunur, `varsayimlar.py`). {len(K)} sabit: onaylı {len(K) - len(bek)}, "
         f"karar bekleyen {len(bek)}. Kimlik Chat'in karar listesindeki harftir; aynı kimlikte birden çok sabit tek karardır.", "",
         "| Kimlik | Sabit | Bugünkü değer | Not | Durum | Ne yapar |", "|---|---|---|---|---|---|"]
    for k in K:
        L.append(f"| {k['kimlik']} | `{k['modul'] + '.' if k['modul'] else ''}{k['sabit']}` | {_d(k['deger'])} | {k['not_']} | {k['durum']}{' (' + k['onay'] + ')' if k['onay'] else ''} | {k['aciklama']} |")
    L.append("")
    return L


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(kayitlar(), ensure_ascii=False, indent=1))
    else:
        print("\n".join(metin()))
