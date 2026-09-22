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
# Kilit once denenir; alinamazsa ve dosya uc saatten eskiyse asili kosu sayilir, kirilir ve bir kez daha denenir (M84a).
# 22 Eylul 2026: eski sira dosya yasina flock'tan ONCE bakiyordu; bitmis kosunun dosyasi da yaslaniyor, her sabah "kiriliyor" yaziyordu.
exec 9>"$KILIT"
if ! flock -n 9; then
  yas=$(( $(date +%s) - $(stat -c %Y "$KILIT" 2>/dev/null || echo 0) ))
  if [ "$yas" -gt 10800 ]; then
    echo "uyari: kilit $yas saniyedir tutuluyor, asili kosu sayildi, kiriliyor"; exec 9>&-; rm -f "$KILIT"; exec 9>"$KILIT"
    flock -n 9 || { echo "kilit yine alinamadi, atlandi"; exit 0; }
  else
    echo "onceki calisma suruyor, atlandi"; exit 0
  fi
fi
touch "$KILIT"

DEPO="$HOME/fon-analiz"
cd "$DEPO"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) baslangic ==="
# 21 EYLUL 2026 (gorev dosyasi, madde 2): yarim kalmis git islemi varsa kosu HEMEN durur. 15 Eylul 06.52 UTC'de gonderim yedegi
# olan 'git pull --rebase' yarim kaldi, .git/rebase-merge acik kaldi; alti gun boyunca pull ve push sessizce basarisiz oldu,
# cekimler makinede birikti (M91: sistemin kostugu makinede olcum yapilmadan teshis kesinlestirilmez).
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  echo "HATA git_yarim_islem: .git/rebase-merge ya da .git/rebase-apply var; elle onarim gerekir (git rebase --abort ya da yedek dal), kosu durdu"
  echo "=== bitis (git_yarim_islem) ==="; exit 5
fi
git pull -q --ff-only origin main || echo "uyari: pull basarisiz, yerel kopya ile devam"
# Yedek calisma: bugunku cekim zaten yapildiysa (son_cekim.txt bugunun tarihini tasiyorsa) atla.
# --zorla ile bu kontrol devre disi kalir (elle calistirma icin).
# 22 Eylul 2026: gunun fiyatlari 05.15 UTC'de kismi (TEFAS 09.00 UTC'de tamamlar, sonda olcumu); yedek kosular (05.50, 09.15 UTC) gun
# "tam" olana kadar atlamaz, kural 15 ile uzerine yazar. Yalnizca bugunku cekim TAM ise atlanir.
bugun_bitti=$(grep -o "son_cekim_utc=$(date -u +%Y-%m-%d)" son_cekim.txt 2>/dev/null || true)
bugun_tam=$(grep -o "son_gun_durumu=tam" son_cekim.txt 2>/dev/null || true)
if [ -n "$bugun_bitti" ] && [ -n "$bugun_tam" ] && [ "${1:-}" != "--zorla" ]; then echo "bugunku cekim tam, atlandi"; exit 0; fi

# TEFAS cekimi. Kritik istir, ama korumasiz DEGILDIR: hata verirse betik olmez, sonuc kaydedilir ve
# elde olan neyse gonderilir. Korumasiz birakmak, hatayi depoda gorunmez kilan seydi.
# Cikis kodlari (M86): 0 temiz, 2 uc yok (404), 3 bicim, 4 ag, 6 bos yanit, 7 saglik sinamasi farkli, 8 fiyatsiz oran sicramasi (supheli).
# Saglik: bilinen fonun bilinen gunu arsivdekiyle birebir yeniden uretilmeli; bu olmadan damga tazelenmez. Supheli gunde de tazelenmez.
tefas_kod=0
python3 betik/tefas_cek.py --cikti veri --arsiv arsiv --saglik || tefas_kod=$?
[ "$tefas_kod" -ne 0 ] && echo "uyari: TEFAS cekimi basarisiz ya da saglik sinamasi gecmedi, cikis kodu $tefas_kod"
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
  # TAZELIK YANILTILAMAZ (M85). son_cekim_utc YALNIZCA cekim ve saglik sinamasi basariliysa bugune gecer. Cekim basarisizken de
  # bu damgayi tazelemek, eski veriyi taze gostermek olurdu; kapsam satiri ve tazelik alarmi buna bakiyor.
  # Her kosu ayrica son_deneme_utc birakir: "makine kostu ama TEFAS vermedi" ile "makine hic kosmadi" ayrilir.
  # Gonderim basarisiz olursa damga geri alinir (asagida): damga yalnizca depoya ulasan kosunun damgasidir.
  # Damga CEKIM anidir (kapsam_son.json cekimZamaniUtc), gonderim ani degil (22 Eylul 2026: gonder() her cagrida saatini yaziyordu; KAP
  # turundan sonraki gonderim damgayi 10.14'e tasiyip 09.15 cekimini saklamisti). Okuyanlar "son cekim" derken cekimi kastediyor.
  eski_damga=$(grep -m1 '^son_cekim_utc=' son_cekim.txt 2>/dev/null || echo "son_cekim_utc=bilinmiyor")
  if [ "$tefas_kod" -eq 0 ]; then
    cz=$(python3 -c "import json; print(json.load(open('veri/kapsam_son.json')).get('cekimZamaniUtc') or '')" 2>/dev/null)
    damga="son_cekim_utc=${cz:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  else
    damga="$eski_damga"
  fi
  {
    echo "$damga"
    echo "son_deneme_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "tefas_cekim_cikis=$tefas_kod"
    # son gunun sifir fiyat orani ve durumu (tam | kismi | supheli): kapsam_son.json'dan; okuyanlar bunu kural 15 ile birlikte okur
    python3 -c "
import json
try:
    k = json.load(open('veri/kapsam_son.json')).get('fiyatsiz') or {}
    print('son_gun_fiyatsiz_oran=' + str(k.get('sonGunFiyatsizOran'))); print('son_gun_durumu=' + str(k.get('sonGunDurumu'))); print('onceki_gun_durumu=' + str(k.get('oncekiGunDurumu')))
    print('fiyat_tam_son_gun=' + str(k.get('fiyatTamSonGun')))
    print('tam_kapsamli_son_gun=' + str(json.load(open('veri/kapsam_son.json')).get('tamKapsamliSonGun')))
except Exception as e:
    print('son_gun_durumu=olculemedi')
" 2>/dev/null
    for f in $(ls -t veri/tefas_gunluk_*.csv | head -1) $(ls -t veri/tefas_dagilim_*.csv | head -1) veri/hisse_son_gunluk.csv; do
      [ -f "$f" ] && echo "$(basename "$f")=$(($(wc -l < "$f") - 1)) satir, son tarih $(tail -n +2 "$f" | cut -d, -f1 | sort | tail -1)"
    done
    [ -s veri/hisse_hata.txt ] && echo "hisse_hata=$(tr '\n' ' ' < veri/hisse_hata.txt)"
  } > son_cekim.txt
  # M92 (Chat, 21 Eylul 2026): isleme adimi, uretilen dosyalar bicim denetiminden gecmeden calismaz. JSON ayristirilabilmeli, metin
  # dosyasinda cakisma imi olmamali, gzip arsivler acilabilmeli. Gecmezse isleme YAPILMAZ ve kosu cikis 3 ile biter; zincir && ile degil
  # acik kosulla kurulur (birlestirme betiginin dusup ardindaki islemenin yine de yapildigi 21 Eylul vakasi).
  if ! python3 - <<'PY'
import json, glob, gzip, sys
hata = []
for p in glob.glob("veri/*.json"):
    try: json.load(open(p, encoding="utf-8"))
    except Exception as e: hata.append(f"{p}: JSON degil ({e})")
for p in glob.glob("veri/*.csv") + glob.glob("veri/*.txt") + ["son_cekim.txt"]:
    try:
        if b"<<<<<<<" in open(p, "rb").read(): hata.append(f"{p}: cakisma imi")
    except FileNotFoundError: pass
for p in glob.glob("arsiv/*.gz"):
    try:
        with gzip.open(p, "rb") as g: g.read(64)
    except Exception as e: hata.append(f"{p}: gzip acilamadi ({e})")
# SATIR GERILEMESI (22 Eylul 2026, Chat): kumulatif arsiv (arsiv/*.gz) bir onceki islemeye gore satir kaybettiyse GONDERILMEZ (hata);
# anlik pencere dosyalari (veri/*.csv) kuculdugunde uyari yazilir ve son_cekim.txt 'gerileme=' satiri tasir, gonderim surer.
import subprocess
def satir(b):
    if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
    return b.count(b"\n")
uyari = []
for p in glob.glob("arsiv/*.gz") + glob.glob("veri/*.csv"):
    r = subprocess.run(["git", "show", "HEAD:" + p], capture_output=True)
    if r.returncode != 0: continue
    try: eski, yeni = satir(r.stdout), satir(open(p, "rb").read())
    except Exception: continue
    if yeni < eski:
        (hata if p.startswith("arsiv/") else uyari).append(f"{p}: satir {eski} -> {yeni}")
if uyari:
    print("uyari gerileme (anlik dosya, pencere daralmasi olabilir): " + "; ".join(uyari), file=sys.stderr)
    open("son_cekim.txt", "a", encoding="utf-8").write("gerileme=" + "; ".join(uyari) + "\n")
if hata:
    print("BICIM DENETIMI GECMEDI: " + "; ".join(hata[:8]), file=sys.stderr); sys.exit(1)
print("bicim denetimi gecti" + (f" ({len(uyari)} anlik dosyada gerileme uyarisi)" if uyari else ""))
PY
  then
    gonderim_kod=3; echo "HATA: bicim denetimi gecmedi, isleme yapilmadi (M92)"; return 0
  fi
  git add -A veri arsiv son_cekim.txt   # veri/hisse_son_gunluk.csv, veri/hisse_hata.txt, arsiv/hisse_*.csv.gz dahil
  if git diff --cached --quiet; then
    echo "degisiklik yok"
  else
    git commit -q -m "$1 $(date -u +%Y-%m-%d)"
    # Gonderim iki kez denenir. Yine olmazsa betik OLMEZ: durum kaydedilir, kosu devam eder ve
    # cikis kodu 3 ile biter. Eskiden burada 'set -e' betigi oldururdu ve geriye yalnizca sessizlik kalirdi.
    # Yedek yol 'git pull --rebase' yarim kalirsa hemen geri alinir (--abort); acik rebase klasoru sonraki her kosuyu oldururdu (15 Eylul).
    gonderildi=0
    if git push -q origin main; then
      gonderildi=1; echo "gonderildi: $(git rev-parse --short HEAD)"
    elif git pull -q --rebase origin main && git push -q origin main; then
      gonderildi=1; echo "gonderildi (rebase sonrasi): $(git rev-parse --short HEAD)"
    else
      [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] && { git rebase --abort 2>/dev/null; echo "uyari: yarim rebase geri alindi"; }
    fi
    if [ "$gonderildi" -eq 1 ]; then
      # Gonderim basarili sayilmaz, olculur: depo ile yerel ileri geri sifir olmali (gorev dosyasi, madde 3).
      git fetch -q origin main 2>/dev/null
      ileri=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?"); geri=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
      if [ "$ileri" != "0" ] || [ "$geri" != "0" ]; then
        gonderildi=0; echo "HATA: gonderimden sonra depo ile yerel esit degil (yerel ileri $ileri, uzak ileri $geri)"
      fi
    fi
    if [ "$gonderildi" -ne 1 ]; then
      gonderim_kod=3
      # Damga geri alinir: depoya ulasmayan kosu taze sayilmaz; boylece 08.50 yedek kosusu atlanmaz ve alarm susmaz.
      if [ "$damga" != "$eski_damga" ]; then
        sed -i "1s|^son_cekim_utc=.*|$eski_damga|" son_cekim.txt
        echo "gonderim=basarisiz $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> son_cekim.txt
        git add son_cekim.txt; git commit -q --amend --no-edit
        echo "uyari: son_cekim_utc damgasi geri alindi ($eski_damga)"
      fi
      echo "HATA: depoya gonderim basarisiz. Olasi sebepler: GitHub kimlik belgesi, uzak dalin ilerlemesi, yarim git islemi."
      echo "      Kontrol: git -C $DEPO status -sb ; git -C $DEPO push origin main"
      echo "      Gonderilemeyen yerel isleme: $(git rev-parse --short HEAD)"
      return 0
    fi
  fi
}
# 22 Eylul 2026: TEFAS ve hisse verisi KAP taramasindan ONCE gonderilir. KAP govde cekimi (900 sayfa, 2,5 sn) 40 dakikayi bulur ve
# gonderimi 06.30 UTC'ye itiyordu; bulut brifingi (06.05 UTC) hep bir onceki gunu okuyordu. KAP ciktilari ikinci gonderimle gider.
gonder "TEFAS cekimi"
# KAP gunluk bildirim dizini (sirketler + fonlar, iki istek): veri/kap_gunluk.json ve arsiv/kap_YYYY-MM.json.gz.
# Kamuya acik kayittir; izleme listesiyle eslestirme ozel tarafta yapilir. Basarisizsa akis durmaz.
python3 betik/kap_gunluk.py --cikti veri --arsiv arsiv || echo "uyari: KAP gunluk dizini alinamadi"
# Kamuya acik fon kunyesi (M47, 13 Eylul 2026): bulut parlayan fon ekrani veri/kunye_tam.csv okur; unvan ve kurucu her gun tazelenir,
# risk degeri ve kunye getirileri onceki dosyadan tasinir. Basarisizsa akis durmaz.
python3 betik/kunye_tam_uret.py --veri veri || echo "uyari: kunye_tam uretilemedi"
# Kurucu grup tablosu, butun kurucular icin (M54): KAP dizinindeki sirket adlarindan kok kelimeyle ve kamuya acik ek dosyayla; veri/kurucu_grup.json
python3 betik/kurucu_grup_uret.py --veri veri --arsiv arsiv || echo "uyari: kurucu_grup uretilemedi"   # ek dosya veri/kurucu_grup_ek.json (veri olarak depoda)
gonder "KAP dizini ve kunye"
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
# Cikis kodu cron gunlugunde gorunur: 0 temiz, 3 gonderim basarisiz, 4 TEFAS cekimi, saglik sinamasi ya da supheli gun (damga tazelenmedi), 5 yarim git islemi.
# Kosu ancak uc kosul birden saglaninca temizdir: saglik sinamasi gecti (tefas_kod 0), gonderim basarili, depo ile yerel esit.
if [ "$gonderim_kod" -ne 0 ]; then exit 3; fi
if [ "$tefas_kod" -ne 0 ]; then exit 4; fi
exit 0
