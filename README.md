# fon-analiz-veri

TEFAS günlük fon verisi. GCP sanal makinesi her hafta içi günü 05.15 UTC (08.15 İstanbul) son 10 günü çeker ve buraya gönderir. Cowork görevi 09.00'da depoyu çekip brifingi üretir.

| Yol | İçerik |
|---|---|
| `veri/tefas_gunluk_<yyyymmdd>.csv` | tarih, fon kodu, pay fiyatı, kişi sayısı, portföy büyüklüğü, tedavüldeki pay |
| `veri/tefas_dagilim_<yyyymmdd>.csv` | tarih, fon kodu ve 56 varlık sınıfı ağırlığı, yüzde puanı |
| `son_cekim.txt` | Son çekimin zamanı, satır sayısı ve son veri tarihi |
| `betik/tefas_cek.py` | Çekici; yalnızca `requests` ister |
| `betik/gunluk_cron.sh` | Makinedeki cron sarmalayıcısı |

Her dosya 10 günlük pencere taşır; aynı tarih-fon çifti birden çok dosyada bulunabilir, analiz betiği ayıklar. 45 günden eski dosyalar makine tarafından silinir; tam geçmiş Mac'teki `Fon Analiz/veri` klasöründedir.

Kaynak ve yöntem: `Fon Analiz/CLAUDE.md` ve `00_Yontem.md`.
