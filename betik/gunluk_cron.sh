#!/usr/bin/env bash
# Sanal makinede cron ile calisir: TEFAS'tan son 10 gunu ceker, GitHub deposuna gonderir.
# Depo klonu ~/fon-analiz altindadir. Cron satiri (05.15 UTC = 08.15 Istanbul, hafta ici):
#   15 5 * * 1-5 ~/fon-analiz/betik/gunluk_cron.sh >> ~/fon-analiz-cron.log 2>&1
#   50 5 * * 1-5 ~/fon-analiz/betik/gunluk_cron.sh >> ~/fon-analiz-cron.log 2>&1   (yedek, 08.50 Istanbul; Cowork 09.05'ten once)
set -euo pipefail
exec 9>"$HOME/.gunluk_cron.lock"; flock -n 9 || { echo "onceki calisma suruyor, atlandi"; exit 0; }
DEPO="$HOME/fon-analiz"
cd "$DEPO"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) baslangic ==="
git pull -q --ff-only origin main || echo "uyari: pull basarisiz, yerel kopya ile devam"
# Yedek calisma: bugunku cekim zaten yapildiysa (son_cekim.txt bugunun tarihini tasiyorsa) atla.
# --zorla ile bu kontrol devre disi kalir (elle calistirma icin).
bugun_bitti=$(grep -o "son_cekim_utc=$(date -u +%Y-%m-%d)" son_cekim.txt 2>/dev/null || true)
if [ -n "$bugun_bitti" ] && [ "${1:-}" != "--zorla" ]; then echo "bugunku cekim zaten var, atlandi"; exit 0; fi
python3 betik/tefas_cek.py --cikti veri
# Eski gunluk dosyalari temizle: 45 gunden eski tefas_gunluk_/tefas_dagilim_ dosyalari
# (her dosya 10 gunluk pencere tasir; 45 gun yeterli ortusme birakir)
find veri -name 'tefas_gunluk_*.csv' -mtime +45 -delete
find veri -name 'tefas_dagilim_*.csv' -mtime +45 -delete
# BIST hisse hatti (Is Yatirim). Basarisizsa TEFAS akisini durdurmaz; hata veri/hisse_hata.txt'de.
python3 betik/hisse_cek.py || echo "uyari: hisse cekimi basarisiz"

# ---- Kritik yol once tamamlanir ve depoya gonderilir (11 Eylul 2026): 8 ve 10 Eylul'de KAP kuyrugu bellek sinirinda
# oldurulunce (cikis 137) 'set -e' betigi o satirda kesti ve TEFAS verisi hic gonderilmedi. Kuyruk artik gondermeden sonra
# calisir ve basarisizligi akisi durdurmaz.
gonder() {
  # Aylik arsiv: yeni gunluk dosyanin dokundugu aylar yeniden yazilir, digerleri degismez
  python3 betik/arsiv_guncelle.py --arsiv arsiv "$(ls -t veri/tefas_gunluk_*.csv | head -1)"
  # Dagilim arsivi (Talimat 8): kapinin 3. sarti eski raporlar icin de dogrulanabilsin
  python3 betik/arsiv_guncelle.py --arsiv arsiv --tur dagilim "$(ls -t veri/tefas_dagilim_*.csv | head -1)"
  # Sabit adli kopyalar: Cowork tarih hesaplamadan hep ayni URL'den okur
  cp "$(ls -t veri/tefas_gunluk_*.csv | head -1)" veri/son_gunluk.csv
  cp "$(ls -t veri/tefas_dagilim_*.csv | head -1)" veri/son_dagilim.csv
  {
    echo "son_cekim_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for f in $(ls -t veri/tefas_gunluk_*.csv | head -1) $(ls -t veri/tefas_dagilim_*.csv | head -1) veri/hisse_son_gunluk.csv; do
      [ -f "$f" ] && echo "$(basename "$f")=$(($(wc -l < "$f") - 1)) satir, son tarih $(tail -n +2 "$f" | cut -d, -f1 | sort | tail -1)"
    done
    [ -s veri/hisse_hata.txt ] && echo "hisse_hata=$(tr '\n' ' ' < veri/hisse_hata.txt)"
  } > son_cekim.txt
  git add -A veri arsiv son_cekim.txt   # veri/hisse_son_gunluk.csv, veri/hisse_hata.txt, arsiv/hisse_*.csv.gz dahil
  if git diff --cached --quiet; then
    echo "degisiklik yok"
  else
    git commit -q -m "$1 $(date -u +%Y-%m-%d)"
    git push -q origin main || { git pull -q --rebase origin main && git push -q origin main; }
    echo "gonderildi: $(git rev-parse --short HEAD)"
  fi
}
gonder "TEFAS cekimi"

# KAP fon kunyesi: haftada bir (dosya yoksa ya da 7 gunden eskiyse). Basarisizsa akis durmaz.
if [ -z "$(find veri -name fon_kunye_kap.csv -mtime -7 2>/dev/null)" ]; then
  python3 betik/kap_kunye.py || echo "uyari: KAP kunye cekimi basarisiz"
fi
# KAP portfoy icerigi: kalici kuyruk, gunluk tur; pdfplumber icin ~/fon-analiz/.venv.
# SART: bu is makineyi donduramaz. Bellek siniri 700 MB (e2-small 2 GB, 1 GB takas; 400 MB buyuk PDF'lerde yetmedi,
# 8 ve 10 Eylul 2026), dusuk oncelik (nice 15, ionice bosta). Sinir asilirsa yalnizca bu surec olur (cikis 137) ve
# kosu_durumu.json'a basarisiz yazilir; akis durmaz ('set -e' icin komut if icinde calistirilir).
ic_kod=0
if [ -x "$DEPO/.venv/bin/python" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
  if systemd-run --user --scope -q -p MemoryMax=700M -p MemorySwapMax=0 true 2>/dev/null; then
    if ! systemd-run --user --scope -q -p MemoryMax=700M -p MemorySwapMax=0 \
      nice -n 15 ionice -c 3 "$DEPO/.venv/bin/python" betik/fon_icerik_cek.py --asama kuyruk; then ic_kod=$?; fi
  else
    echo "uyari: systemd-run kullanilamadi, ulimit ile sinirlaniyor"
    if ! ( ulimit -v 1400000; nice -n 15 ionice -c 3 "$DEPO/.venv/bin/python" betik/fon_icerik_cek.py --asama kuyruk ); then ic_kod=$?; fi
  fi
  if [ "$ic_kod" -ne 0 ]; then
    echo "uyari: KAP icerik kuyrugu basarisiz, cikis kodu $ic_kod"
    python3 - "$ic_kod" <<'PY'
import json, sys, os, datetime
yol = "veri/kosu_durumu.json"
try: d = json.load(open(yol, encoding="utf-8"))
except Exception: d = {}
kod = int(sys.argv[1]); d.setdefault("icerik", {})
d["icerik"].update(durum="basarisiz", cikisKodu=kod, sebep="bellek siniri (400 MB) asildi, surec olduruldu" if kod == 137 else "betik hatayla bitti",
                   tarih=datetime.date.today().isoformat())
json.dump(d, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
PY
  fi
else
  echo "uyari: .venv yok, KAP icerik kuyrugu atlandi"
fi
# KAP kuyrugunun ciktilari ikinci gonderimle gider; basarisiz olsa bile TEFAS verisi coktan depodadir
gonder "KAP icerik turu"
echo "=== bitis ==="
