#!/usr/bin/env bash
# Sanal makinede cron ile calisir: TEFAS'tan son 10 gunu ceker, GitHub deposuna gonderir.
# Depo klonu ~/fon-analiz altindadir. Cron satiri (05.15 UTC = 08.15 Istanbul, hafta ici):
#   15 5 * * 1-5 ~/fon-analiz/betik/gunluk_cron.sh >> ~/fon-analiz-cron.log 2>&1
set -euo pipefail
DEPO="$HOME/fon-analiz"
cd "$DEPO"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) baslangic ==="
git pull -q --ff-only origin main || echo "uyari: pull basarisiz, yerel kopya ile devam"
python3 betik/tefas_cek.py --cikti veri
# Eski gunluk dosyalari temizle: 45 gunden eski tefas_gunluk_/tefas_dagilim_ dosyalari
# (her dosya 10 gunluk pencere tasir; 45 gun yeterli ortusme birakir)
find veri -name 'tefas_gunluk_*.csv' -mtime +45 -delete
find veri -name 'tefas_dagilim_*.csv' -mtime +45 -delete
{
  echo "son_cekim_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  for f in $(ls -t veri/tefas_gunluk_*.csv | head -1) $(ls -t veri/tefas_dagilim_*.csv | head -1); do
    echo "$(basename "$f")=$(($(wc -l < "$f") - 1)) satir, son tarih $(tail -n +2 "$f" | cut -d, -f1 | sort | tail -1)"
  done
} > son_cekim.txt
git add -A veri son_cekim.txt
if git diff --cached --quiet; then
  echo "degisiklik yok"
else
  git commit -q -m "TEFAS cekimi $(date -u +%Y-%m-%d)"
  git push -q origin main
  echo "gonderildi: $(git rev-parse --short HEAD)"
fi
echo "=== bitis ==="
