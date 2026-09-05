#!/usr/bin/env bash
# Tek seferlik: 27.02.2025 - 01.09.2025 fiyat boslugunu TEFAS'tan ceker, arsive isler, depoya gonderir.
# Basarinca kendi cron satirini siler. TEFAS 500 verirse bir sonraki saatte yeniden dener.
# Kurulum: (crontab -l; echo "0 * * * * ~/fon-analiz/betik/bosluk_doldur.sh >> ~/fon-analiz-bosluk.log 2>&1") | crontab -
set -euo pipefail
exec 9>"$HOME/.bosluk_doldur.lock"; flock -n 9 || { echo "zaten calisiyor"; exit 0; }
DEPO="$HOME/fon-analiz"; GECICI="$HOME/bosluk_tmp"
cd "$DEPO"; mkdir -p "$GECICI"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) bosluk denemesi ==="
if ! python3 betik/tefas_cek.py --uc fiyat --bas 20250227 --bit 20250901 --cikti "$GECICI"; then
  echo "TEFAS'tan alinamadi, sonraki saatte yeniden"; exit 1
fi
git pull -q --ff-only origin main || true
python3 betik/arsiv_guncelle.py --arsiv arsiv "$GECICI"/tefas_gunluk_20250901.csv
git add -A arsiv
git commit -q -m "Arşiv: 27.02.2025 - 01.09.2025 boşluğu dolduruldu" && git push -q origin main
echo "gonderildi: $(git rev-parse --short HEAD)"
crontab -l | grep -v bosluk_doldur.sh | crontab -
echo "cron satiri kaldirildi; bitti"
