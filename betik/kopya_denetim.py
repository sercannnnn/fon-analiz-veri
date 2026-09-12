#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ikinci kopya denetimi (Gorev 1.6). Sanal makine, GitHub deposunun (fon-analiz-veri) klonudur; makinedeki
betikler depodaki betik/ klasorunden gelir. Bu betik yerel 02 Betik altindaki kopyalari deponun ham
adreslerinden okuyup karsilastirir. Fark varsa kirmizi doner. Yalnizca standart kutuphane ve requests."""
import hashlib, os, sys
import requests

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HAM = "https://raw.githubusercontent.com/sercannnnn/fon-analiz-veri/main/betik/"
# 12 Eylul 2026: bulut gorevinin betikleri de depoda; liste betik_esitle.sh ile aynidir. Depodaki SAGLAMA.sha256 ayrica okunur
# ve depodaki dosya kendi saglamasiyla da karsilastirilir (bozuk ya da eksik gonderim gorunur olsun).
BETIKLER = ["tefas_cek.py", "gunluk_cron.sh", "arsiv_guncelle.py", "hisse_cek.py", "kap_kunye.py", "kategori.py", "fon_icerik_cek.py",
            "kap_ucret.py", "tefas_yas.py", "kap_gunluk.py", "kapilar.py", "parlayan_fon.py", "oneri.py", "kap_izleme.py", "takvim.py",
            "kapsam.py", "denetim.py", "brifing_pdf.py", "defter_pdf.py", "sayfa_html.py", "requirements.txt", "kopya_denetim.py",
            "fonts/DejaVuSans.ttf", "fonts/DejaVuSans-Bold.ttf", "fonts/DejaVuSansMono.ttf"]


def ozet(b):
    return hashlib.sha256(b).hexdigest()[:12]


def saglama_oku():
    try:
        r = requests.get(HAM + "SAGLAMA.sha256", timeout=60)
        if r.status_code != 200:
            return {}
        return {l.split()[1].lstrip("*"): l.split()[0] for l in r.text.splitlines() if len(l.split()) == 2}
    except Exception:
        return {}


def main():
    fark = 0
    sag = saglama_oku()
    if not sag:
        print("  ?  SAGLAMA.sha256 depodan okunamadı; sağlama karşılaştırması yapılmadı")
    for ad in BETIKLER:
        yerel = os.path.join(KOK, "02 Betik", ad)
        try:
            uzak = requests.get(HAM + ad, timeout=60)
        except Exception as e:
            print(f"  ?  {ad}: depo okunamadı ({e})"); fark += 1; continue
        if uzak.status_code != 200:
            print(f"  ?  {ad}: depoda yok (HTTP {uzak.status_code})"); fark += 1; continue
        y = open(yerel, "rb").read() if os.path.exists(yerel) else b""
        tam = hashlib.sha256(uzak.content).hexdigest()
        if sag.get(ad) and sag[ad] != tam:
            print(f"  SAGLAMA {ad}: depodaki dosya SAGLAMA.sha256 ile uyuşmuyor ({tam[:12]} / {sag[ad][:12]})"); fark += 1
        if y == uzak.content:
            print(f"  ok {ad} {tam[:12]}")
        else:
            print(f"  FARKLI {ad}: yerel {ozet(y)} depo {ozet(uzak.content)}"); fark += 1
    print("sonuç:", "iki kopya aynı" if not fark else f"{fark} betikte fark var; tek kaynak depodur, yerel kopya güncellenmeli ya da depoya gönderilmeli")
    sys.exit(1 if fark else 0)


if __name__ == "__main__":
    main()
