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


def kopya_tazeligi(klasor, uzak="origin", dal="main", zaman_asimi=40):
    """22 Eylul 2026 (Chat): brifing deponun bayat bir kopyasindan calisip bunu bildirmedi ve kendi arizasini hattin arizasi diye raporladi.
    Klon tazelenebiliyor mu ve uzak dalin gerisinde mi olculur: git fetch, sonra ileri/geri sayimi. Donus dict(durum guncel|bayat|olculemedi,
    geri, ileri, sebep, metin). durum 'guncel' degilse brifingin en ustune 'KOPYA TAZELENEMEDI/BAYAT, asagidaki her sey bayat olabilir' yazilir;
    cagiran isterse brifingi hic uretmez. Ag yoksa 'olculemedi' doner, bu da bayat sayilir (dogrulanamayan tazelik tazelik degildir, M30)."""
    import subprocess
    if not klasor or not os.path.isdir(os.path.join(klasor, ".git")):
        return dict(durum="olculemedi", geri=None, ileri=None, sebep="git klonu degil", metin=f"Depo kopyasi: OLCULEMEDI ({klasor} git klonu degil); asagidaki her sey bayat olabilir")
    try:
        r = subprocess.run(["git", "-C", klasor, "fetch", "-q", uzak, dal], capture_output=True, text=True, timeout=zaman_asimi)
    except Exception as e:
        return dict(durum="olculemedi", geri=None, ileri=None, sebep=f"fetch: {e}", metin=f"Depo kopyasi: TAZELENEMEDI ({e}); asagidaki her sey bayat olabilir")
    if r.returncode != 0:
        return dict(durum="olculemedi", geri=None, ileri=None, sebep=(r.stderr or "").strip()[:120], metin=f"Depo kopyasi: TAZELENEMEDI ({(r.stderr or '').strip()[:80]}); asagidaki her sey bayat olabilir")
    def _say(a, b):
        q = subprocess.run(["git", "-C", klasor, "rev-list", "--count", f"{a}..{b}"], capture_output=True, text=True)
        return int(q.stdout.strip() or 0) if q.returncode == 0 else None
    geri, ileri = _say("HEAD", f"{uzak}/{dal}"), _say(f"{uzak}/{dal}", "HEAD")
    if geri is None:
        return dict(durum="olculemedi", geri=None, ileri=ileri, sebep="rev-list", metin="Depo kopyasi: OLCULEMEDI (rev-list); asagidaki her sey bayat olabilir")
    if geri > 0:
        return dict(durum="bayat", geri=geri, ileri=ileri, sebep=f"uzak dal {geri} isleme ileride", metin=f"Depo kopyasi: BAYAT, uzak dal {geri} isleme ileride; asagidaki her sey bayat olabilir, once git pull")
    return dict(durum="guncel", geri=0, ileri=ileri, sebep="", metin="Depo kopyasi: guncel (uzak dal ile esit)")
