#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ikinci kopya denetimi (Gorev 1.6). Sanal makine, GitHub deposunun (fon-analiz-veri) klonudur; makinedeki
betikler depodaki betik/ klasorunden gelir. Bu betik yerel 02 Betik altindaki kopyalari deponun ham
adreslerinden okuyup karsilastirir. Fark varsa kirmizi doner. Yalnizca standart kutuphane ve requests."""
import hashlib, os, sys, time
import requests

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HAM = "https://raw.githubusercontent.com/sercannnnn/fon-analiz-veri/main/betik/"
# 12 Eylul 2026: bulut gorevinin betikleri de depoda; liste betik_esitle.sh ile aynidir. Depodaki SAGLAMA.sha256 ayrica okunur
# ve depodaki dosya kendi saglamasiyla da karsilastirilir (bozuk ya da eksik gonderim gorunur olsun).
BETIKLER = ["tefas_cek.py", "gunluk_cron.sh", "arsiv_guncelle.py", "hisse_cek.py", "kap_kunye.py", "kategori.py", "fon_icerik_cek.py",
            "kap_ucret.py", "tefas_yas.py", "kap_gunluk.py", "kapilar.py", "parlayan_fon.py", "oneri.py", "kap_izleme.py", "takvim.py",
            "kapsam.py", "denetim.py", "brifing_pdf.py", "defter_pdf.py", "sayfa_html.py", "requirements.txt", "kopya_denetim.py",
            "fonts/DejaVuSans.ttf", "fonts/DejaVuSans-Bold.ttf", "fonts/DejaVuSansMono.ttf"]


API = "https://api.github.com/repos/sercannnnn/fon-analiz-veri/contents/betik/"


def _baslik():
    """Kimliksiz API saatte 60 istek verir; GITHUB_TOKEN ya da Mac'teki gh oturumu varsa onunla (5.000 istek) sorulur."""
    b = {"Accept": "application/vnd.github+json"}
    t = os.environ.get("GITHUB_TOKEN")
    if not t:
        try:
            import subprocess
            t = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            t = ""
    if t:
        b["Authorization"] = "Bearer " + t
    return b


YEDEK_KULLANILDI = []


def blob_sha(b):
    """git'in nesne kimliği: sha1('blob <uzunluk>\\0' + içerik). GitHub içerik API'sindeki sha ile birebir karşılaştırılır."""
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def api_oku(ad):
    """GitHub içerik API'si (kimliksiz, saatte 60 istek): (blob sha, içerik ya da None). raw.githubusercontent birkaç dakika
    önbellekler ve gönderimden hemen sonra sahte fark verir; API deponun o anki hâlini verir. Erişilemezse ham adrese düşülür."""
    import base64
    try:
        r = requests.get(API + ad, timeout=60, headers=_baslik())
        if r.status_code == 200:
            j = r.json()
            icerik = base64.b64decode(j["content"]) if j.get("encoding") == "base64" and j.get("content") else None
            return j["sha"], icerik
        if r.status_code == 404:
            return None, None
    except Exception:
        pass
    YEDEK_KULLANILDI.append(ad)
    r = requests.get(HAM + ad, timeout=60)
    if r.status_code != 200:
        return None, None
    return blob_sha(r.content), r.content


def saglama_oku():
    _, b = api_oku("SAGLAMA.sha256")
    if not b:
        return {}
    return {l.split()[1].lstrip("*"): l.split()[0] for l in b.decode("utf-8").splitlines() if len(l.split()) == 2}


def main():
    fark = 0
    sag = saglama_oku()
    if not sag:
        print("  ?  SAGLAMA.sha256 depodan okunamadı; sağlama karşılaştırması yapılmadı")
    for ad in BETIKLER:
        yerel = os.path.join(KOK, "02 Betik", ad)
        y = open(yerel, "rb").read() if os.path.exists(yerel) else b""
        try:
            sha, uzak = api_oku(ad)
        except Exception as e:
            print(f"  ?  {ad}: depo okunamadı ({e})"); fark += 1; continue
        if sha is None:
            print(f"  ?  {ad}: depoda yok"); fark += 1; continue
        if uzak is not None and sag.get(ad) and sag[ad] != hashlib.sha256(uzak).hexdigest():
            print(f"  SAGLAMA {ad}: depodaki dosya SAGLAMA.sha256 ile uyuşmuyor"); fark += 1
        if blob_sha(y) == sha:
            print(f"  ok {ad} {sha[:12]}")
        else:
            print(f"  FARKLI {ad}: yerel {blob_sha(y)[:12]} depo {sha[:12]}"); fark += 1
    if YEDEK_KULLANILDI:
        print(f"  not: {len(YEDEK_KULLANILDI)} dosya API yerine ham adresten okundu (API sınırı ya da erişim); ham adres birkaç dakika önbellekler, gönderimden hemen sonra sahte fark verebilir")
    print("sonuç:", "iki kopya aynı" if not fark else f"{fark} betikte fark var; tek kaynak depodur, yerel kopya güncellenmeli ya da depoya gönderilmeli")
    sys.exit(1 if fark else 0)


if __name__ == "__main__":
    main()
