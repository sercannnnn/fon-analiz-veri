# -*- coding: utf-8 -*-
"""Fon unvanindan kategori turetir.

M9'un ikinci yarisi. Gunluk cekim artik fonUnvan donuyor; kategoriyi
statik kunye dosyasindan degil unvandan turetmek, kunyede olmayan yeni
fonun taramaya girmesini saglar. Sira onemlidir: ilk eslesme kazanir.
"""
import re, unicodedata

def _norm(s):
    s = str(s).upper()
    s = s.replace("İ", "I").replace("I", "I").replace("Ş", "S").replace("Ğ", "G")
    s = s.replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")
    return unicodedata.normalize("NFKD", s)

KURAL = [
    ("Para Piyasası",         [r"PARA PIYASASI"]),
    ("Kısa Vadeli Borçlanma", [r"KISA VADELI"]),
    ("Fon Sepeti",            [r"FON SEPETI"]),
    ("Kıymetli Madenler",     [r"KIYMETLI MADEN", r"\bALTIN\b", r"\bGUMUS\b"]),
    ("Hisse Senedi",          [r"HISSE SENEDI"]),
    ("Katılım",               [r"KATILIM"]),
    ("Değişken",              [r"DEGISKEN"]),
    ("Karma",                 [r"\bKARMA\b"]),
    ("Borçlanma Araçları",    [r"BORCLANMA ARAC", r"\bTAHVIL\b", r"\bBONO\b", r"EUROBOND"]),
    ("Serbest",               [r"\bSERBEST\b"]),
]

def kategori_turet(unvan):
    if not unvan or str(unvan).strip() == "":
        return None
    u = _norm(unvan)
    for ad, kaliplar in KURAL:
        for k in kaliplar:
            if re.search(k, u):
                return ad
    return "Diğer"
