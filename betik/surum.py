#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Betik sürüm denetimi (12 Eylül 2026): bulut görevi Mac'ten eşitlenen betiklerle koşar; eşitleme Mac cron'una bağlıdır ve
Mac kapalıysa depo eskir. Sessiz eskime kabul edilmez: `betik_esitle.sh` her koşuda betik/SURUM.json (eşitleme zamanı, Mac'teki
git işleme kimliği, dosya sayısı) ve betik/SAGLAMA.sha256 yazar; brifing bu ikisini okur ve eşitleme üç iş gününden eskiyse ya da
sağlama tutmuyorsa kapsam satırına yazar.

Kullanım: surum_kontrol(klasor) -> {"durum": guncel|eski|bozuk|eksik|yok, "metin": ..., "esitleme": ..., "isleme": ...}
"eksik": SAGLAMA listesindeki bir dosya klasörde yok (M23, 12 Eylül 2026: dört yazı tipi eksikken denetim "güncel" demişti).
klasor verilmezse bu dosyanın kendi klasörü (bulutta betik/) alınır."""
import hashlib, json, os
from datetime import date, datetime, timezone

ESIK_IS_GUNU = 3


def is_gunu_farki(bas, bit):
    """bas ve bit arasındaki hafta içi gün sayısı (bas hariç, bit dahil)."""
    n, g = 0, bas
    while g < bit:
        g = date.fromordinal(g.toordinal() + 1)
        if g.weekday() < 5:
            n += 1
    return n


def surum_kontrol(klasor=None, bugun=None, esik=ESIK_IS_GUNU):
    klasor = klasor or os.path.dirname(os.path.abspath(__file__))
    bugun = bugun or date.today()
    sy = os.path.join(klasor, "SURUM.json"); sg = os.path.join(klasor, "SAGLAMA.sha256")
    if not os.path.exists(sy):
        return dict(durum="yok", metin="betik sürüm kaydı (SURUM.json) yok; eşitleme hiç çalışmamış ya da betikler eşitleme dışı bir yoldan gelmiş", esitleme=None, isleme=None)
    try:
        j = json.load(open(sy, encoding="utf-8"))
        t = datetime.strptime(j["esitlemeZamaniUtc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception as e:
        return dict(durum="bozuk", metin=f"SURUM.json okunamadı ({e})", esitleme=None, isleme=None)
    isleme = str(j.get("macIsleme", ""))[:7]; gun = is_gunu_farki(t.date(), bugun)
    bozuk, eksik = [], []
    if os.path.exists(sg):
        for satir in open(sg, encoding="utf-8"):
            parca = satir.split()
            if len(parca) != 2:
                continue
            ad = parca[1].lstrip("*"); yol = os.path.join(klasor, ad)
            if not os.path.exists(yol):
                eksik.append(ad)          # M23: listede olup klasörde olmayan dosya "güncel" saydırmaz; yazı tipi yoksa PDF üretilemez
            elif hashlib.sha256(open(yol, "rb").read()).hexdigest() != parca[0]:
                bozuk.append(ad)
    else:
        bozuk.append("SAGLAMA.sha256 yok")
    tarih = t.strftime("%d.%m.%Y %H:%M")
    if bozuk:
        return dict(durum="bozuk", metin=f"betik sağlaması tutmuyor ({', '.join(bozuk[:5])}); eşitleme {tarih} UTC, Mac işleme {isleme}", esitleme=tarih, isleme=isleme)
    if eksik:
        return dict(durum="eksik", metin=f"betik klasöründe {len(eksik)} dosya eksik ({', '.join(eksik[:5])}); eşitleme {tarih} UTC, Mac işleme {isleme}", esitleme=tarih, isleme=isleme)
    if gun > esik:
        return dict(durum="eski", metin=f"betik sürümü eski, eşitleme {tarih} UTC ({gun} iş günü önce), Mac işleme {isleme}", esitleme=tarih, isleme=isleme)
    return dict(durum="guncel", metin=f"betik sürümü güncel, eşitleme {tarih} UTC, Mac işleme {isleme}", esitleme=tarih, isleme=isleme)


if __name__ == "__main__":
    import sys
    print(json.dumps(surum_kontrol(sys.argv[1] if len(sys.argv) > 1 else None), ensure_ascii=False))
