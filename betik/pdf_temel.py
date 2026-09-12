#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ortak PDF katmanı (12 Eylül 2026): brifing_pdf.py ve defter_pdf.py bu sınıfla çizer.

Yalnızca fpdf2 (pip ile kurulur, saf Python); wkhtmltopdf ya da başka bir dış araç yoktur. Yazı tipi betik/fonts altındaki
DejaVu (Bitstream Vera lisansı) dosyalarından gömülür; sistem yazı tipi aranmaz, Türkçe harfler (ş, ğ, ü, ö, ç, ı, İ) her
ortamda basılır. Renkler dataviz referans paletinden: kategorik mavi, ayrışan mavi-kırmızı, nötr gri.
"""
import os
from fpdf import FPDF, XPos, YPos

FONT_KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
S1, KIRMIZI, YESIL, NOTR = "#2a78d6", "#d03b3b", "#0ca30c", "#e8e7e3"
INK, INK2, INK3, CIZGI, ZEMIN = "#141413", "#52514e", "#84837c", "#e3e2de", "#fafaf9"


def buyuk(s):
    """Türkçe büyük harf: i -> İ, ı -> I (Python'un upper'ı i'yi I yapar)."""
    return str(s).replace("i", "İ").replace("ı", "I").upper()


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def tl(x, ond=0):
    if x is None: return "—"
    return f"{x:,.{ond}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def yz(x, ond=1):
    if x is None: return "—"
    im = "-" if x < 0 else ""          # Türkçede eksi işareti yüzde işaretinden önce gelir: -%19,7
    return f"{im}%{abs(x) * 100:,.{ond}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


class Belge(FPDF):
    """A4, gömülü DejaVu; başlık, alt başlık, paragraf, tablo, kutu ve basit grafikler."""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(15, 16, 15); self.set_auto_page_break(auto=True, margin=14)
        eksik = [a for a in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf") if not os.path.exists(os.path.join(FONT_KLASOR, a))]
        if eksik:
            raise FileNotFoundError(f"gömülü yazı tipi yok: {', '.join(eksik)} ({FONT_KLASOR})")
        self.add_font("G", "", os.path.join(FONT_KLASOR, "DejaVuSans.ttf"))
        self.add_font("G", "B", os.path.join(FONT_KLASOR, "DejaVuSans-Bold.ttf"))
        self.add_font("GM", "", os.path.join(FONT_KLASOR, "DejaVuSansMono.ttf"))
        self.add_page()
        self.G = self.w - self.l_margin - self.r_margin      # yazılabilir genişlik, mm

    # ---- yazı
    def yazi(self, boy=9.5, kalin=False, renk=INK, mono=False):
        self.set_font("GM" if mono else "G", "B" if kalin and not mono else "", boy); self.set_text_color(*rgb(renk))

    def ust(self, baslik, tarih):
        self.yazi(15, True); self.cell(self.G * 0.7, 9, baslik, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.yazi(9, mono=True, renk=INK2); self.cell(self.G * 0.3, 9, tarih, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*rgb(INK)); self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1); self.ln(3)

    def h2(self, metin):
        if self.get_y() > self.h - 40: self.add_page()
        self.ln(3); self.yazi(10.5, True); self.cell(0, 6, metin, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*rgb(CIZGI)); self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y()); self.ln(2)

    def h3(self, metin):
        self.ln(1.5); self.yazi(9, True, INK2); self.cell(0, 5, metin, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def p(self, metin, boy=9.5, renk=INK, mono=False, kalin=False, bosluk=1.5):
        self.yazi(boy, kalin, renk, mono); self.multi_cell(0, boy * 0.5 + 0.8, metin, new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(bosluk)

    def kapsam(self, metin):
        self.p(metin, 8, INK3, mono=True)

    def bos(self, metin):
        self.p(metin, 9, INK3)

    def kutu(self, bas, ger, renk=S1):
        """Talimat kutusu: sol şerit, kalın başlık, gri gerekçe."""
        if self.get_y() > self.h - 35: self.add_page()
        y0 = self.get_y(); x0 = self.l_margin
        self.set_x(x0 + 4); self.yazi(9.5, True); self.multi_cell(self.G - 6, 5, bas, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(x0 + 4); self.yazi(8.5, renk=INK2); self.multi_cell(self.G - 6, 4.3, ger, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y1 = self.get_y() + 1
        self.set_fill_color(*rgb(renk)); self.rect(x0, y0, 1.0, y1 - y0, style="F"); self.ln(3)

    def dip(self, metin):
        self.ln(4); self.set_draw_color(*rgb(CIZGI)); self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y()); self.ln(2); self.p(metin, 7.5, INK3)

    # ---- tablo
    def tablo(self, basliklar, satirlar, genislik, hiza=None, renkler=None, boy=8.5, satir_yuk=5.2, gerekceler=None):
        """basliklar: liste; satirlar: metin listeleri; genislik: mm listesi; hiza: 'L'/'R' listesi; renkler: satır başına
        {sütun: renk}; gerekceler: satır altına yazılan gri metin (None ya da liste)."""
        n = len(basliklar); hiza = hiza or (["L"] + ["R"] * (n - 1))
        self.yazi(7.5, True, INK2)
        for i, b in enumerate(basliklar):
            self.cell(genislik[i], 5, buyuk(b), align=hiza[i], new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(5); self.set_draw_color(*rgb(INK)); self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.l_margin + sum(genislik), self.get_y()); self.ln(0.5)
        for r_i, s in enumerate(satirlar):
            if self.get_y() > self.h - 22:
                self.add_page()
            for i, h in enumerate(s):
                renk = (renkler[r_i] or {}).get(i, INK) if renkler else INK
                self.yazi(boy, False, renk, mono=(i == 0))
                b = boy
                while self.get_string_width(str(h)) > genislik[i] - 1.5 and b > 5.5:   # taşan hücre küçültülür, üst üste basılmaz
                    b -= 0.5; self.set_font_size(b)
                self.cell(genislik[i], satir_yuk, str(h), align=hiza[i], new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.ln(satir_yuk)
            if gerekceler and gerekceler[r_i]:
                self.yazi(7.8, renk=INK2); self.multi_cell(sum(genislik), 4, gerekceler[r_i], new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(0.8)
            self.set_draw_color(*rgb("#f0efec")); self.set_line_width(0.15)
            self.line(self.l_margin, self.get_y(), self.l_margin + sum(genislik), self.get_y())
        self.ln(2)

    # ---- grafikler
    def bar_yatay(self, satir, bicim=tl, birim="", renk=S1, etiket_g=40):
        """Yatay çubuk, doğrudan etiketli, tek seri."""
        if not satir: return
        enb = max(abs(v) for _, v in satir) or 1; kol = self.G - etiket_g - 45
        for ad, v in satir:
            if self.get_y() > self.h - 20: self.add_page()
            y = self.get_y(); w = max(0.6, abs(v) / enb * kol)
            self.yazi(8.5); self.cell(etiket_g, 5.5, str(ad), new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_fill_color(*rgb(renk)); self.rect(self.l_margin + etiket_g, y + 1.2, w, 3.4, style="F")
            self.yazi(8, renk=INK2); self.set_x(self.l_margin + etiket_g + w + 2); self.cell(40, 5.5, f"{bicim(v)}{birim}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def bar_ayrisan(self, satir, etiket_g=30):
        """Sıfır ekseninin iki yanında: mavi artı, kırmızı eksi."""
        if not satir: return
        enb = max(abs(v) for _, v in satir) or 1; orta = self.l_margin + etiket_g + (self.G - etiket_g) / 2; kol = (self.G - etiket_g) / 2 - 22
        y_bas = self.get_y()
        for ad, v in satir:
            if self.get_y() > self.h - 20: self.add_page(); y_bas = self.get_y()
            y = self.get_y(); w = max(0.6, abs(v) / enb * kol); x = orta if v >= 0 else orta - w
            self.yazi(8.5); self.cell(etiket_g, 6, str(ad), new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_fill_color(*rgb(S1 if v >= 0 else KIRMIZI)); self.rect(x, y + 1.3, w, 3.6, style="F")
            self.yazi(8, renk=INK2)
            if v >= 0: self.set_x(orta + w + 1.5); self.cell(20, 6, yz(v), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else: self.set_x(orta - w - 21.5); self.cell(20, 6, yz(v), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*rgb(CIZGI)); self.set_line_width(0.25); self.line(orta, y_bas, orta, self.get_y())
        self.yazi(7.5, renk=INK3); self.set_x(orta - 15); self.cell(30, 4, "endeksle aynı", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(1)

    def mermi(self, deger, esik, enb, etiket):
        """Tetik mesafesi: ölçülen değer, eşik çizgisi."""
        if self.get_y() > self.h - 25: self.add_page()
        self.yazi(8.5); self.cell(0, 5, etiket, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y(); w = self.G - 30; d = min(1.0, abs(deger) / enb); e = min(1.0, abs(esik) / enb)
        kritik = abs(deger) >= abs(esik) * 0.9; c = KIRMIZI if kritik else S1
        self.set_fill_color(*rgb(NOTR)); self.rect(self.l_margin, y + 0.5, w, 3.6, style="F")
        self.set_fill_color(*rgb(c)); self.rect(self.l_margin, y + 0.5, w * d, 3.6, style="F")
        self.set_draw_color(*rgb(INK)); self.set_line_width(0.5); self.line(self.l_margin + w * e, y - 0.5, self.l_margin + w * e, y + 5.2)
        self.yazi(8.5, True, c); self.set_xy(self.l_margin + w + 2, y - 0.5); self.cell(26, 5.5, yz(deger), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.yazi(7.5, renk=INK2); self.set_xy(self.l_margin + max(0, w * e - 12), y + 5.5); self.cell(24, 4, f"eşik {yz(esik)}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(2)

    def sayac(self, adaylar):
        """Aday süreklilik sayacı: gerekli gün kadar daire, dolu olanlar ardışık gün."""
        for a in adaylar:
            if self.get_y() > self.h - 20: self.add_page()
            y = self.get_y()
            self.yazi(9, True); self.cell(14, 6, a.get("kod", ""), new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.yazi(8.5, renk=INK2); self.cell(self.G - 14 - 40, 6, str(a.get("ad", ""))[:60], new_x=XPos.RIGHT, new_y=YPos.TOP)
            g, n = int(a.get("gerekli", 3)), int(a.get("ardisik", 0)); x = self.get_x()
            for j in range(g):
                dolu = j < n; self.set_fill_color(*rgb(S1 if dolu else "#ffffff")); self.set_draw_color(*rgb(S1 if dolu else CIZGI)); self.set_line_width(0.3)
                self.ellipse(x + j * 6, y + 1.2, 3.6, 3.6, style="FD")
            self.yazi(8, renk=INK2); self.set_x(x + g * 6 + 2); self.cell(12, 6, f"{n}/{g}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
