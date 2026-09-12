#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kapsam (Görev 3.3): kısmi kapsamlı gün kodda engellenir.

Sabah çekimi, TEFAS'ın o günün fiyatlarını yayımlaması bitmeden yapılabilir; o gün fiyatı sıfır gelen
fon sayısı yüzlerce olur ve dağılım satırı eksik kalır (9 Eylül 2026: 2.044 kayıtta 384 sıfır fiyat,
dağılımda 1.083 satır; son tam gün 8 Eylül, 2.035 satır). Kural iki parçadır: fon bazındaki ölçüm fonun
kendi son geçerli satırından alınabilir; kurucu büyüklüğü, evren geneli, emsal dilimi gibi toplam alan ölçümler
kısmi kapsamlı günde yapılmaz, tam kapsamlı son güne çekilir. Aksi hâlde yayımlanmamış fonlar sıfır sayılır.

Tam gün tanımı: o gün geçerli fiyatı olan fon sayısı, penceredeki en yüksek günün en az TAM_ORAN katı.
Yalnızca numpy ve pandas.
"""
import numpy as np
import pandas as pd

TAM_ORAN = 0.98      # geçerli fiyatlı fon sayısı, penceredeki en yüksek günün en az bu katı ise gün tam kapsamlıdır


class KapsamHatasi(RuntimeError):
    """Toplam alan bir ölçüm kısmi kapsamlı günde çağrıldı."""


def gun_kapsami(d, dagilim=None, beklenen=None):
    """Gün başına: kayıt, geçerli fiyatlı fon, (varsa) dağılım satırı, tam bayrağı. d: tarih, fonKodu, fiyat sütunlu çerçeve
    (fiyat 0 ya da boş olabilir; geçerli = fiyat > 0). beklenen: evrendeki fon sayısı (kapsam_son.json'daki tam günün
    geçerli sayısı gibi); verilirse tam günün ölçütü pencere içi en yüksek gün değil bu sayıdır, böylece penceredeki
    bütün günler kısmi olsa da gün yanlışlıkla tam sayılmaz."""
    g = d.assign(gecerli=(d["fiyat"] > 0)).groupby("tarih").agg(kayit=("fonKodu", "size"), gecerli=("gecerli", "sum"))
    g["gecerli"] = g["gecerli"].astype(int)
    if dagilim is not None and len(dagilim):
        g["dagilim"] = dagilim.groupby("tarih").size().reindex(g.index).fillna(0).astype(int)
    enb = beklenen if beklenen else g["gecerli"].max()
    g["tam"] = g["gecerli"] >= TAM_ORAN * enb
    if "dagilim" in g:
        g["tam"] &= g["dagilim"] >= TAM_ORAN * g["dagilim"].max()
    return g


def son_tam_gun(d, dagilim=None, beklenen=None):
    """Kapsamı tam olan en son gün; hiç yoksa None."""
    g = gun_kapsami(d, dagilim, beklenen)
    tam = g.index[g["tam"]]
    return tam.max() if len(tam) else None


def toplam_alan(d, dagilim=None, izin_kismi=False, beklenen=None):
    """Toplam alan ölçümler için çerçeve: kısmi kapsamlı son günler atılır, tam kapsamlı son güne kadar olan veri döner.
    Dönüş: (çerçeve, son tam gün, atılan gün listesi). izin_kismi=False iken tam gün yoksa KapsamHatasi."""
    g = gun_kapsami(d, dagilim, beklenen)
    tam = g.index[g["tam"]]
    if not len(tam):
        if izin_kismi:
            return d, None, list(g.index)
        raise KapsamHatasi("hiçbir günün kapsamı tam değil; toplam alan ölçüm yapılamaz")
    son = tam.max()
    atilan = [t for t in g.index if t > son]
    return d[d["tarih"] <= son], son, atilan
