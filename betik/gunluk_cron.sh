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
# KAP fon kunyesi: haftada bir (dosya yoksa ya da 7 gunden eskiyse). Basarisizsa akis durmaz.
if [ -z "$(find veri -name fon_kunye_kap.csv -mtime -7 2>/dev/null)" ]; then
  python3 betik/kap_kunye.py || echo "uyari: KAP kunye cekimi basarisiz"
fi
# KAP portfoy icerigi: kalici kuyruk, gunluk tur; pdfplumber icin ~/fon-analiz/.venv. Basarisizsa akis durmaz.
if [ -x "$DEPO/.venv/bin/python" ]; then
  "$DEPO/.venv/bin/python" betik/fon_icerik_cek.py --asama kuyruk || echo "uyari: KAP icerik kuyrugu basarisiz"
else
  echo "uyari: .venv yok, KAP icerik kuyrugu atlandi"
fi
# Aylik arsiv: yeni gunluk dosyanin dokundugu aylar yeniden yazilir, digerleri degismez
python3 betik/arsiv_guncelle.py --arsiv arsiv "$(ls -t veri/tefas_gunluk_*.csv | head -1)"
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
  git commit -q -m "TEFAS cekimi $(date -u +%Y-%m-%d)"
  git push -q origin main
  echo "gonderildi: $(git rev-parse --short HEAD)"
fi
echo "=== bitis ==="
