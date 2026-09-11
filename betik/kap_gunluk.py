#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KAP günlük bildirim dizini. Yalnızca 'requests'; sistem python3 ile çalışır.

Günün bütün KAP bildirimlerini (şirketler ve fonlar) çeker, kap_izleme.py'nin beklediği biçimde yazar:
  veri/kap_gunluk.json           [{id, tarih, sirket, konu, ozet, metin, url, hisse, sinif, ekSayisi}]
  arsiv/kap_YYYY-MM.json.gz      aylık birikimli, id'ye göre tekil
Bu dizin KAP'ın kendi kamuya açık kaydıdır; izleme listesi ve eşleştirme özel tarafta yapılır (gizlilik notu kap_izleme.py).

Gövde metni (11 Eylül 2026 değerlendirmesi, madde 3.1): kural tam metin taraması ister; 9 Eylül'de Tera-Pusula haberi yalnızca
Katılımevim'in bildirim gövdesinde geçiyordu. Her bildirimin sayfası (/tr/Bildirim/<id>, sunucuda üretilir) çekilir, 'Özet Bilgi'
bölümünden alt bilgiye kadar düz metin alınır ve `metin` alanına yazılır. Fonların dönemsel raporları (portföy dağılımı, gider,
performans) gövde taşımaz, atlanır (metinDurumu "gerekmez"). Çekilemeyen bildirim "eksik" işaretlenir; sayılar dosyanın başında
(govdeTam, govdeEksik, govdeGerekmez) durur ve brifingin kapsam satırına girer. Gövde bütçesi aşılırsa kalanlar "eksik" kalır.

Kullanım: kap_gunluk.py [--gun 2] [--cikti veri] [--arsiv arsiv] [--govde-butce 700]
"""
import argparse, gzip, html as html_mod, json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone
import requests

KAP = "https://www.kap.org.tr/tr/api/"
BASLIK = {"Content-Type": "application/json", "Origin": "https://www.kap.org.tr",
          "Referer": "https://www.kap.org.tr/tr/bildirim-sorgu", "User-Agent": "Mozilla/5.0 (fon-analiz kap dizini)"}
ARA = 2.5


def _post(yol, govde, deneme=3):
    for i in range(deneme):
        try:
            r = requests.post(KAP + yol, json=govde, headers=BASLIK, timeout=120)
            if r.status_code == 429:
                raise RuntimeError("HTTP 429")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  {yol}: deneme {i+1} {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(10 * (i + 1))
    raise SystemExit(f"KAP dizini alinamadi: {yol}")


def cek(bas, bit):
    """Şirket bildirimleri (bütün üye türleri) + fon bildirimleri (YF). Dönüş: KAP ham kayıtları."""
    ortak = {"fromDate": bas, "toDate": bit, "mkkMemberOidList": [], "disclosureClass": "", "isLate": "",
             "subjectList": [], "discIndex": [], "fromSrc": False, "srcCategory": ""}
    sirket = _post("disclosure/members/byCriteria", dict(ortak, memberTypeList=[]))
    time.sleep(ARA)
    fon = _post("disclosure/funds/byCriteria", dict(ortak, fundTypeList=["YF"], fundOidList=[], passiveFundOidList=[]))
    L = (sirket if isinstance(sirket, list) else sirket.get("resultList") or []) + (fon if isinstance(fon, list) else fon.get("resultList") or [])
    return L


GEREKMEZ = re.compile(r"Portföy Dağılım|Toplam Gider|Gider Bilgileri|Aracı Kuruma Ödenen|Performans Sunum|Fiyat Raporu|Katılma Payı Fiyat", re.I)
GOVDE_ARA = 2.5
GOVDE_AZAMI = 20000


def govde_cek(idx, deneme=2):
    """Bildirim sayfasının düz metni: 'Özet Bilgi'den sayfa sonuna kadar, etiketler atılmış. Dönüş: metin ya da None."""
    for i in range(deneme):
        try:
            r = requests.get(f"https://www.kap.org.tr/tr/Bildirim/{idx}", headers={"User-Agent": BASLIK["User-Agent"]}, timeout=90)
            if r.status_code == 429:
                raise RuntimeError("HTTP 429")
            r.raise_for_status()
            t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
            t = html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
            j = t.find("Özet Bilgi")
            if j < 0:
                return None
            t = t[j:]
            k = t.find("Copyright ©")
            if k > 0:
                t = t[:k]
            return t[:GOVDE_AZAMI]
        except Exception as e:
            print(f"  govde {idx}: deneme {i+1} {e}", file=sys.stderr)
            if i < deneme - 1:
                time.sleep(10)
    return None


def donustur(x):
    """KAP kaydını kap_izleme.py biçimine çevirir."""
    idx = x.get("disclosureIndex")
    t = x.get("publishDate") or ""
    try:
        tarih = datetime.strptime(t[:19], "%d.%m.%Y %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        tarih = t
    return dict(id=idx, tarih=tarih, sirket=x.get("kapTitle") or "", konu=x.get("subject") or "", ozet=x.get("summary") or "",
                metin="", url=f"https://www.kap.org.tr/tr/Bildirim/{idx}", hisse=x.get("stockCodes") or "",
                fon=x.get("fundCode") or "", sinif=x.get("disclosureClass") or "", ekSayisi=x.get("attachmentCount") or 0)


def arsiv_isle(arsiv, kayitlar):
    os.makedirs(arsiv, exist_ok=True)
    aylar = {}
    for k in kayitlar:
        aylar.setdefault(k["tarih"][:7], {})[k["id"]] = k
    for ay, yeni in aylar.items():
        yol = os.path.join(arsiv, f"kap_{ay}.json.gz")
        eski = {}
        if os.path.exists(yol):
            with gzip.open(yol, "rt", encoding="utf-8") as f:
                eski = {k["id"]: k for k in json.load(f)}
        eski.update(yeni)
        veri = json.dumps(sorted(eski.values(), key=lambda k: (k["tarih"], k["id"])), ensure_ascii=False).encode("utf-8")
        with open(yol, "wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
                g.write(veri)
        print(f"{yol}: {len(eski):,} bildirim", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=2, help="bugün dahil geriye kaç gün (hafta sonu ve tatil için 2 yeterli)")
    ap.add_argument("--cikti", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "veri"))
    ap.add_argument("--arsiv", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "arsiv"))
    ap.add_argument("--govde-butce", type=int, default=900, help="bugün çekilecek en fazla bildirim gövdesi (2,5 s aralıkla; 700 sayfa yaklaşık 30 dakika)")
    a = ap.parse_args()
    bugun = date.today()
    ham = cek((bugun - timedelta(days=a.gun - 1)).isoformat(), bugun.isoformat())
    tekil = {}
    for x in ham:
        k = donustur(x)
        if k["id"]:
            tekil[k["id"]] = k
    kayitlar = sorted(tekil.values(), key=lambda k: (k["tarih"], k["id"]))
    # gövde: önce arşivde zaten gövdesi olan kayıtlar tekrar çekilmez
    eski = {}
    ay_yol = os.path.join(a.arsiv, f"kap_{bugun.isoformat()[:7]}.json.gz")
    if os.path.exists(ay_yol):
        with gzip.open(ay_yol, "rt", encoding="utf-8") as f:
            eski = {k["id"]: k for k in json.load(f) if k.get("metinDurumu") == "tam"}
    sayac = dict(tam=0, eksik=0, gerekmez=0); butce = a.govde_butce
    for k in sorted(kayitlar, key=lambda k: (bool(k["fon"]), k["tarih"])):   # sirket bildirimleri once: butce biterse fon formlari eksik kalir
        if k["id"] in eski:
            k["metin"] = eski[k["id"]]["metin"]; k["metinDurumu"] = "tam"; sayac["tam"] += 1; continue
        if k["fon"] and GEREKMEZ.search(k["konu"]):
            k["metinDurumu"] = "gerekmez"; sayac["gerekmez"] += 1; continue
        if butce <= 0:
            k["metinDurumu"] = "eksik"; sayac["eksik"] += 1; continue
        butce -= 1
        m = govde_cek(k["id"]); time.sleep(GOVDE_ARA)
        if m:
            k["metin"] = m; k["metinDurumu"] = "tam"; sayac["tam"] += 1
        else:
            k["metinDurumu"] = "eksik"; sayac["eksik"] += 1
    os.makedirs(a.cikti, exist_ok=True)
    yol = os.path.join(a.cikti, "kap_gunluk.json")
    json.dump(dict(cekimZamaniUtc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), bas=(bugun - timedelta(days=a.gun - 1)).isoformat(),
                   bit=bugun.isoformat(), adet=len(kayitlar), govdeTam=sayac["tam"], govdeEksik=sayac["eksik"], govdeGerekmez=sayac["gerekmez"],
                   metinNotu="govde /tr/Bildirim/<id> sayfasindan; 'eksik' olan bildirimde tarama yalnizca ozet ve konu uzerindendir",
                   bildirimler=kayitlar), open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{yol}: {len(kayitlar):,} bildirim ({(bugun - timedelta(days=a.gun - 1)).isoformat()} .. {bugun.isoformat()}); "
          f"gövde tam {sayac['tam']}, eksik {sayac['eksik']}, gerekmez {sayac['gerekmez']}")
    arsiv_isle(a.arsiv, kayitlar)


if __name__ == "__main__":
    main()
