#!/usr/bin/env bash
# Sanal makinede cron ile calisir: TEFAS'tan son 10 gunu ceker, GitHub deposuna gonderir.
# Depo klonu ~/fon-analiz altindadir. Cron satiri (05.15 UTC = 08.15 Istanbul, hafta ici):
#   15 5 * * 1-5 ~/fon-analiz/betik/gunluk_cron.sh >> ~/fon-analiz-cron.log 2>&1
#   50 5 * * 1-5 ~/fon-analiz/betik/gunluk_cron.sh >> ~/fon-analiz-cron.log 2>&1   (yedek, 08.50 Istanbul; Cowork 09.05'ten once)
#
# 17 EYLUL 2026 SAGLAMLASTIRMASI (M84). 15 Eylul 05.53 UTC'den sonra uc gun boyunca depoya hicbir sey gelmedi
# ve bunu kimse fark etmedi. Uc ayri sessiz olum yolu vardi; ucu de kapatildi:
#   1. Kilit dosyasi: asili kalan bir kosu kilidi birakmazsa sonraki her kosu "atlandi" deyip sifirla cikiyordu.
#      Kilit artik yaslanir; uc saatten eski kilit kirilir.
#   2. tefas_cek.py korumasizdi: hata verince 'set -e' betigi oracikta kesiyor, depoya hicbir iz dusmuyordu.
#      Artik korumali calisir, sonucu kaydedilir ve kosu yine gonderime kadar gider.
#   3. Gonderim hatasi sessizdi: push basarisiz olunca betik oluyordu. Artik gonderim durumu ayrica raporlanir
#      ve kosu sonunda cikis kodu 3 ile biter; cron gunlugunde gorunur.
# Bu betik kendi basina alarm veremez, cunku alarmin gitmesi icin de gonderimin calismasi gerekir.
# Tazelik alarmi bu yuzden disaridadir: bulut gorevi her sabah son_cekim.txt tarihini okur.
set -uo pipefail

KILIT="$HOME/.gunluk_cron.lock"
# Yaslanan kilit kirilir: uc saatten eski kilit dosyasi asili kosu demektir, sonsuza kadar atlamak yerine devam edilir.
if [ -f "$KILIT" ]; then
  yas=$(( $(date +%s) - $(stat -c %Y "$KILIT" 2>/dev/null || echo 0) ))
  if [ "$yas" -gt 10800 ]; then echo "uyari: kilit $yas saniyedir duruyor, kiriliyor"; rm -f "$KILIT"; fi
fi
exec 9>"$KILIT"; flock -n 9 || { echo "onceki calisma suruyor, atlandi"; exit 0; }

DEPO="$HOME/fon-analiz"
cd "$DEPO"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) baslangic ==="
git pull -q --ff-only origin main || echo "uyari: pull basarisiz, yerel kopya ile devam"
# Yedek calisma: bugunku cekim zaten yapildiysa (son_cekim.txt bugunun tarihini tasiyorsa) atla.
# --zorla ile bu kontrol devre disi kalir (elle calistirma icin).
bugun_bitti=$(grep -o "son_cekim_utc=$(date -u +%Y-%m-%d)" son_cekim.txt 2>/dev/null || true)
if [ -n "$bugun_bitti" ] && [ "${1:-}" != "--zorla" ]; then echo "bugunku cekim zaten var, atlandi"; exit 0; fi

# TEFAS cekimi. Kritik istir, ama korumasiz DEGILDIR: hata verirse betik olmez, sonuc kaydedilir ve
# elde olan neyse gonderilir. Korumasiz birakmak, hatayi depoda gorunmez kilan seydi.
tefas_kod=0
python3 betik/tefas_cek.py --cikti veri || tefas_kod=$?
[ "$tefas_kod" -ne 0 ] && echo "uyari: TEFAS cekimi basarisiz, cikis kodu $tefas_kod"
# Eski gunluk dosyalari temizle: 45 gunden eski tefas_gunluk_/tefas_dagilim_ dosyalari
# (her dosya 10 gunluk pencere tasir; 45 gun yeterli ortusme birakir)
find veri -name 'tefas_gunluk_*.csv' -mtime +45 -delete
find veri -name 'tefas_dagilim_*.csv' -mtime +45 -delete
# BIST hisse hatti (Is Yatirim). Basarisizsa TEFAS akisini durdurmaz; hata veri/hisse_hata.txt'de.
python3 betik/hisse_cek.py --ek veri/hisse_evren_icerik.txt || echo "uyari: hisse cekimi basarisiz"   # 68 numarali not: fiyat arsivi fon icerik evrenine genisler

# ---- Kritik yol once tamamlanir ve depoya gonderilir (11 Eylul 2026): 8 ve 10 Eylul'de KAP kuyrugu bellek sinirinda
# oldurulunce (cikis 137) 'set -e' betigi o satirda kesti ve TEFAS verisi hic gonderilmedi. Kuyruk artik gondermeden sonra
# calisir ve basarisizligi akisi durdurmaz.
gonderim_kod=0
gonder() {
  # Aylik arsiv: yeni gunluk dosyanin dokundugu aylar yeniden yazilir, digerleri degismez
  python3 betik/arsiv_guncelle.py --arsiv arsiv "$(ls -t veri/tefas_gunluk_*.csv | head -1)" || echo "uyari: arsiv guncellenemedi"
  # Dagilim arsivi (Talimat 8): kapinin 3. sarti eski raporlar icin de dogrulanabilsin
  python3 betik/arsiv_guncelle.py --arsiv arsiv --tur dagilim "$(ls -t veri/tefas_dagilim_*.csv | head -1)" || echo "uyari: dagilim arsivi guncellenemedi"
  # Sabit adli kopyalar: Cowork tarih hesaplamadan hep ayni URL'den okur
  cp "$(ls -t veri/tefas_gunluk_*.csv | head -1)" veri/son_gunluk.csv
  cp "$(ls -t veri/tefas_dagilim_*.csv | head -1)" veri/son_dagilim.csv
  # TAZELIK YANILTILAMAZ (M85). son_cekim_utc YALNIZCA cekim basariliysa bugune gecer. Cekim basarisizken de
  # bu damgayi tazelemek, eski veriyi taze gostermek olurdu; kapsam satiri ve tazelik alarmi buna bakiyor.
  # Her kosu ayrica son_deneme_utc birakir: "makine kostu ama TEFAS vermedi" ile "makine hic kosmadi" ayrilir.
  if [ "$tefas_kod" -eq 0 ]; then
    damga="son_cekim_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  else
    damga=$(grep -m1 '^son_cekim_utc=' son_cekim.txt 2>/dev/null || echo "son_cekim_utc=bilinmiyor")
  fi
  {
    echo "$damga"
    echo "son_deneme_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "tefas_cekim_cikis=$tefas_kod"
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
    # Gonderim iki kez denenir. Yine olmazsa betik OLMEZ: durum kaydedilir, kosu devam eder ve
    # cikis kodu 3 ile biter. Eskiden burada 'set -e' betigi oldururdu ve geriye yalnizca sessizlik kalirdi.
    if ! git push -q origin main; then
      if git pull -q --rebase origin main && git push -q origin main; then
        echo "gonderildi (rebase sonrasi): $(git rev-parse --short HEAD)"
      else
        gonderim_kod=3
        echo "HATA: depoya gonderim basarisiz. En olasi sebep GitHub kimlik belgesinin suresinin dolmasidir."
        echo "      Kontrol: git -C $DEPO remote -v ; git -C $DEPO push origin main"
        echo "      Gonderilemeyen yerel isleme: $(git rev-parse --short HEAD)"
        return 0
      fi
    else
      echo "gonderildi: $(git rev-parse --short HEAD)"
    fi
  fi
}
# KAP gunluk bildirim dizini (sirketler + fonlar, iki istek): veri/kap_gunluk.json ve arsiv/kap_YYYY-MM.json.gz.
# Kamuya acik kayittir; izleme listesiyle eslestirme ozel tarafta yapilir. Basarisizsa akis durmaz.
python3 betik/kap_gunluk.py --cikti veri --arsiv arsiv || echo "uyari: KAP gunluk dizini alinamadi"
# Kamuya acik fon kunyesi (M47, 13 Eylul 2026): bulut parlayan fon ekrani veri/kunye_tam.csv okur; unvan ve kurucu her gun tazelenir,
# risk degeri ve kunye getirileri onceki dosyadan tasinir. Basarisizsa akis durmaz.
python3 betik/kunye_tam_uret.py --veri veri || echo "uyari: kunye_tam uretilemedi"
# Kurucu grup tablosu, butun kurucular icin (M54): KAP dizinindeki sirket adlarindan kok kelimeyle ve kamuya acik ek dosyayla; veri/kurucu_grup.json
python3 betik/kurucu_grup_uret.py --veri veri --arsiv arsiv || echo "uyari: kurucu_grup uretilemedi"   # ek dosya veri/kurucu_grup_ek.json (veri olarak depoda)
gonder "TEFAS cekimi"
# Fon yonetim ucreti (giris kapisi 4): KAP genel bilgiler sayfasindan gunde 150 fon, 30 gunde bir yenilenir; veri/fon_ucret.csv
python3 betik/kap_ucret.py --butce 150 || echo "uyari: ucret cekimi basarisiz"
# fon yasi, artimli (pazartesi): taramadan sonra acilan fonlar veri/fon_yas.csv'ye girer; kural G2 yalnizca bu dosyayla olculur
if [ "$(date +%u)" = "1" ]; then python3 betik/tefas_yas.py || echo "uyari: yas taramasi basarisiz"; fi

# KAP fon kunyesi: haftada bir (dosya yoksa ya da 7 gunden eskiyse). Basarisizsa akis durmaz.
if [ -z "$(find veri -name fon_kunye_kap.csv -mtime -7 2>/dev/null)" ]; then
  python3 betik/kap_kunye.py || echo "uyari: KAP kunye cekimi basarisiz"
fi
# KAP portfoy icerigi: kalici kuyruk, gunluk tur; pdfplumber icin ~/fon-analiz/.venv.
# SART: bu is makineyi donduramaz. Bellek siniri 700 MB (e2-small 2 GB, 1 GB takas; 400 MB buyuk PDF'lerde yetmedi,
# 8 ve 10 Eylul 2026), dusuk oncelik (nice 15, ionice bosta). Sinir asilirsa yalnizca bu surec olur (cikis 137) ve
# kosu_durumu.json'a basarisiz yazilir; akis durmaz.
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
echo "=== bitis (tefas=$tefas_kod icerik=$ic_kod gonderim=$gonderim_kod) ==="
# Cikis kodu cron gunlugunde gorunur: 0 temiz, 3 gonderim basarisiz, 4 TEFAS cekimi basarisiz.
if [ "$gonderim_kod" -ne 0 ]; then exit 3; fi
if [ "$tefas_kod" -ne 0 ]; then exit 4; fi
exit 0
