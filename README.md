# fon-analiz-veri

TEFAS günlük fon verisi. GCP sanal makinesi her hafta içi günü 05.15 UTC (08.15 İstanbul) son 10 günü çeker ve buraya gönderir. Cowork görevi 09.00'da depoyu çekip brifingi üretir.

| Yol | İçerik |
|---|---|
| `veri/tefas_gunluk_<yyyymmdd>.csv` | tarih, fon kodu, pay fiyatı, kişi sayısı, portföy büyüklüğü, tedavüldeki pay |
| `veri/tefas_dagilim_<yyyymmdd>.csv` | tarih, fon kodu ve 56 varlık sınıfı ağırlığı, yüzde puanı |
| `arsiv/tefas_YYYY-MM.csv.gz` | Fiyat serisinin tam geçmişi, aylık gzip; 3 Şubat 2025'ten bugüne. Yalnızca içinde bulunulan ay her gün yeniden yazılır |
| `veri/son_gunluk.csv`, `veri/son_dagilim.csv` | En son çekimin sabit adlı kopyaları; günlük okuma bu ikisinden yapılır |
| `son_cekim.txt` | Son çekimin zamanı, satır sayısı ve son veri tarihi |
| `betik/tefas_cek.py` | Çekici; yalnızca `requests` ister |
| `betik/gunluk_cron.sh` | Makinedeki cron sarmalayıcısı |
| `betik/arsiv_guncelle.py` | Günlük dosyaları aylık arşive işler; standart kütüphane |

Her dosya 10 günlük pencere taşır; aynı tarih-fon çifti birden çok dosyada bulunabilir, analiz betiği ayıklar. 45 günden eski günlük dosyalar makine tarafından silinir; tam geçmiş `arsiv/` altındadır. Bilinen boşluklar: 27 Şubat 2025 ile 1 Eylül 2025 arası, 27 ile 29 Mayıs 2026 arası.

Kaynak ve yöntem: `Fon Analiz/CLAUDE.md` ve `00_Yontem.md`.
