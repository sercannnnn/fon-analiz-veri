#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gunluk fon brifingini tek sayfalik, grafikli PDF olarak uretir.

Kullanim:
  python3 brifing_pdf.py --veri brifing_veri.json --cikti "Brifing.pdf"

Grafikler satir ici SVG'dir; disaridan yazi tipi ya da betik cagirmaz, boylece
wkhtmltopdf ciktisi her makinede ayni gorunur. Renkler dataviz referans
paletinden: kategorik yuva 1 mavi, ayrisan cift mavi-kirmizi, notr gri.
"""
import argparse, json, html, subprocess, os

S1, DIV_A, DIV_B, NOTR = "#2a78d6", "#2a78d6", "#d03b3b", "#e8e7e3"
INK, INK2, INK3, CIZGI = "#141413", "#52514e", "#84837c", "#e3e2de"

def tl(x, ond=0):
    if x is None: return "—"
    s = f"{x:,.{ond}f}".replace(",", " ").replace(".", ",")
    return s.replace(" ", ".")

def yz(x, ond=1):
    if x is None: return "—"
    # Turkcede eksi isareti yuzde isaretinden ONCE gelir: -%19,7
    im = "-" if x < 0 else ""
    return f"{im}%{abs(x)*100:,.{ond}f}".replace(".", ",")

def bar_yatay(satir, genislik=760, yuk_sat=26, bicim=tl, renk=S1, birim=""):
    """Buyukluk grafigi: yatay cubuk, dogrudan etiketli, tek seri."""
    if not satir: return ""
    enb = max(abs(v) for _, v in satir) or 1
    h = yuk_sat*len(satir) + 8
    p = [f'<svg viewBox="0 0 {genislik} {h}" width="{genislik}" height="{h}" role="img" style="display:block">']
    for i, (ad, v) in enumerate(satir):
        y = i*yuk_sat + 4
        w = max(2, abs(v)/enb * (genislik-330))
        p.append(f'<text x="0" y="{y+13}" font-size="10.5" fill="{INK}">{html.escape(ad)}</text>')
        p.append(f'<rect x="150" y="{y+3}" width="{w:.1f}" height="13" rx="3" fill="{renk}"/>')
        p.append(f'<text x="{150+w+7:.1f}" y="{y+14}" font-size="10" fill="{INK2}">{bicim(v)}{birim}</text>')
    p.append('</svg>')
    return "".join(p)

def bar_ayrisan(satir, genislik=760, yuk_sat=30):
    """Kutupluluk grafigi: sifir ekseninin iki yaninda, mavi artı, kirmizi eksi."""
    if not satir: return ""
    enb = max(abs(v) for _, v in satir) or 1
    orta, kol = 340, 215
    h = yuk_sat*len(satir) + 14
    p = [f'<svg viewBox="0 0 {genislik} {h}" width="{genislik}" height="{h}" role="img" style="display:block">']
    p.append(f'<line x1="{orta}" y1="0" x2="{orta}" y2="{h-14}" stroke="{CIZGI}" stroke-width="1"/>')
    for i, (ad, v) in enumerate(satir):
        y = i*yuk_sat + 4
        w = max(2, abs(v)/enb * kol)
        x = orta if v >= 0 else orta - w
        c = DIV_A if v >= 0 else DIV_B
        p.append(f'<text x="0" y="{y+14}" font-size="10.5" fill="{INK}">{html.escape(ad)}</text>')
        p.append(f'<rect x="{x:.1f}" y="{y+4}" width="{w:.1f}" height="14" rx="3" fill="{c}"/>')
        tx = orta + w + 7 if v >= 0 else orta - w - 7
        an = "start" if v >= 0 else "end"
        p.append(f'<text x="{tx:.1f}" y="{y+15}" font-size="10" fill="{INK2}" text-anchor="{an}">{yz(v)}</text>')
    p.append(f'<text x="{orta}" y="{h-2}" font-size="9" fill="{INK3}" text-anchor="middle">endeksle aynı</text>')
    p.append('</svg>')
    return "".join(p)

def mermi(deger, esik, enb, etiket, genislik=760):
    """Tetik mesafesi: olculen deger, esik cizgisi, kalan mesafe."""
    h = 56
    w = genislik - 120
    d = min(1.0, abs(deger)/enb); e = min(1.0, abs(esik)/enb)
    kritik = abs(deger) >= abs(esik)*0.9
    c = DIV_B if kritik else S1
    p = [f'<svg viewBox="0 0 {genislik} {h}" width="{genislik}" height="{h}" role="img" style="display:block">']
    p.append(f'<text x="0" y="12" font-size="10.5" fill="{INK}">{html.escape(etiket)}</text>')
    p.append(f'<rect x="0" y="20" width="{w}" height="14" rx="3" fill="{NOTR}"/>')
    p.append(f'<rect x="0" y="20" width="{w*d:.1f}" height="14" rx="3" fill="{c}"/>')
    p.append(f'<line x1="{w*e:.1f}" y1="16" x2="{w*e:.1f}" y2="38" stroke="{INK}" stroke-width="2"/>')
    p.append(f'<text x="{w*e:.1f}" y="45" font-size="9" fill="{INK2}" text-anchor="middle">eşik {yz(esik)}</text>')
    p.append(f'<text x="{w+10}" y="32" font-size="11" fill="{c}" font-weight="600">{yz(deger)}</text>')
    p.append('</svg>')
    return "".join(p)

def sayac(adaylar, genislik=760, bos_not=None):
    """Aday sureklilik sayaci: uc adimli nokta dizisi."""
    if not adaylar: return f'<p class="bos">{bos_not or "Bugün kapısı açık aday yok."}</p>'
    h = 30*len(adaylar) + 6
    p = [f'<svg viewBox="0 0 {genislik} {h}" width="{genislik}" height="{h}" role="img" style="display:block">']
    for i, a in enumerate(adaylar):
        y = i*30 + 4
        p.append(f'<text x="0" y="{y+16}" font-size="11" fill="{INK}" font-weight="600">{html.escape(a["kod"])}</text>')
        p.append(f'<text x="46" y="{y+16}" font-size="10" fill="{INK2}">{html.escape(a.get("ad","")[:52])}</text>')
        for j in range(a.get("gerekli", 3)):
            cx = 470 + j*26
            dolu = j < a.get("ardisik", 0)
            p.append(f'<circle cx="{cx}" cy="{y+11}" r="7" fill="{S1 if dolu else "#ffffff"}" stroke="{S1 if dolu else CIZGI}" stroke-width="1.5"/>')
        p.append(f'<text x="{470+a.get("gerekli",3)*26+4}" y="{y+15}" font-size="10" fill="{INK2}">{a.get("ardisik",0)}/{a.get("gerekli",3)}</text>')
    p.append('</svg>')
    return "".join(p)

# Gomulu yazi tipi (12 Eylul 2026): PDF bulutta da uretilir ve orada sistem yazi tipi yoktur; Turkce harfler (İ, ş, ğ) icin
# betik/fonts altindaki DejaVu (Bitstream Vera lisansi, dagitilabilir) @font-face ile gomulur. Yol calisma aninda mutlaktir;
# wkhtmltopdf --enable-local-file-access ile okur. Dosya yoksa CSS sistem yazi tipine duser.
FONT_KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def font_face():
    y = lambda ad: "file://" + os.path.join(FONT_KLASOR, ad).replace(" ", "%20")
    if not os.path.exists(os.path.join(FONT_KLASOR, "DejaVuSans.ttf")):
        return ""
    return (f'@font-face {{ font-family:"Gomulu"; src:url("{y("DejaVuSans.ttf")}") format("truetype"); font-weight:400; }}\n'
            f'@font-face {{ font-family:"Gomulu"; src:url("{y("DejaVuSans-Bold.ttf")}") format("truetype"); font-weight:600 700; }}\n'
            f'@font-face {{ font-family:"GomuluMono"; src:url("{y("DejaVuSansMono.ttf")}") format("truetype"); }}\n')

CSS = """
@page { size: A4; margin: 16mm 15mm 14mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Gomulu","Source Sans 3","Helvetica Neue",Arial,sans-serif; color:#141413;
       font-size: 10.5pt; line-height: 1.5; margin:0; }
h1 { font-family:"Gomulu","Montserrat",Arial,sans-serif; font-size:17pt; margin:0 0 2px; letter-spacing:-.2px; }
h2 { font-family:"Gomulu","Montserrat",Arial,sans-serif; font-size:11pt; margin:20px 0 7px;
     padding-bottom:4px; border-bottom:1px solid #e3e2de; letter-spacing:.1px; }
.ust { display:flex; justify-content:space-between; align-items:baseline;
       border-bottom:2px solid #141413; padding-bottom:7px; margin-bottom:4px; }
.tarih { font-size:9.5pt; color:#52514e; font-family:"GomuluMono","IBM Plex Mono",monospace; }
.kapsam { font-size:8.5pt; color:#84837c; font-family:"GomuluMono","IBM Plex Mono",monospace; margin:0 0 4px; }
table { width:100%; border-collapse:collapse; font-size:9.5pt; margin-top:4px; }
th { text-align:right; font-weight:600; color:#52514e; font-size:8.5pt; text-transform:uppercase;
     letter-spacing:.4px; border-bottom:1px solid #141413; padding:4px 5px; }
th:first-child, td:first-child { text-align:left; }
td { padding:4px 5px; border-bottom:1px solid #f0efec; text-align:right;
     font-variant-numeric:tabular-nums; }
td.kod { font-family:"GomuluMono","IBM Plex Mono",monospace; font-weight:600; text-align:left; }
.pos { color:#0ca30c; } .neg { color:#d03b3b; }
.talimat { border-left:3px solid #2a78d6; padding:7px 11px; margin:7px 0; background:#fafaf9; }
.talimat .bas { font-weight:600; font-size:10.5pt; }
.talimat .ger { font-size:9.5pt; color:#52514e; }
.uyari { border-left:3px solid #d03b3b; }
.bos { color:#84837c; font-size:9.5pt; font-style:italic; }
.haber { font-size:9.5pt; margin:6px 0; padding-left:11px; border-left:2px solid #e3e2de; }
.haber .kaynak { color:#84837c; font-size:8.5pt; font-family:"GomuluMono","IBM Plex Mono",monospace; }
.dip { margin-top:18px; padding-top:7px; border-top:1px solid #e3e2de;
       font-size:8pt; color:#84837c; line-height:1.45; }
.blok { page-break-inside: avoid; }
.iki { display:flex; gap:18px; } .iki > div { flex:1; }
"""


def kap_bolum(kap):
    """Gunun KAP taramasi. Kademe 1 kirmizi, kademe 2 gri."""
    if not kap: return ""
    g = [f'<p class="kapsam" style="margin:0 0 6px">{html.escape(kap.get("kapsam",""))}</p>']
    for k in kap.get("kalem", []):
        renk = DIV_B if k.get("kademe") == 1 else INK3
        etiket = "1. kademe" if k.get("kademe") == 1 else "2. kademe"
        g.append(f'<div style="margin:0 0 9px;padding-left:9px;border-left:2px solid {renk}">'
                 f'<div style="font-size:9pt"><strong>{html.escape(k.get("sirket",""))}</strong>'
                 f' <span style="color:{INK3}">· {html.escape(k.get("konu",""))}</span>'
                 f' <span style="color:{renk};font-size:7.5pt;letter-spacing:.3px">{etiket}</span></div>'
                 f'<div style="font-size:8.5pt;color:{INK2};margin-top:1px">{html.escape(k.get("ozet",""))}</div>'
                 f'<div style="font-size:8pt;color:{INK3};margin-top:1px">İzleme listesine giriş sebebi: '
                 f'{html.escape(k.get("gerekce",""))}</div></div>')
    return "".join(g)
# KAP_BOLUM

def yaz(v, cikti):
    p = v.get("pozisyon", []); tp = sum(x["deger"] for x in p) or 1
    # Ayni fon birden cok kurumda durabilir; agirlik grafigi kod bazinda toplanir.
    top = {}
    for x in p: top[x["kod"]] = top.get(x["kod"], 0) + x["deger"]
    agirlik = sorted(top.items(), key=lambda t:-t[1])[:12]
    hisse = [(a, d) for a, d in v.get("hisse_grafik", [])] or \
            [(x["kod"], x["fark"]) for x in p if x.get("fark") is not None]
    g = ['<!doctype html><html lang="tr"><head><meta charset="utf-8">',
         f'<style>{font_face()}{CSS}</style></head><body>']
    g.append(f'<div class="ust"><h1>Fon brifingi</h1><span class="tarih">{v["tarih"]}</span></div>')
    g.append(f'<p class="kapsam">{html.escape(v["kapsam"])}</p>')

    if v.get("dun"):
        g.append('<h2>Dün yapılmayanlar</h2>')
        for x in v["dun"]:
            g.append(f'<div class="talimat uyari"><div class="bas">{html.escape(x["bas"])}</div>'
                     f'<div class="ger">{html.escape(x["ger"])}</div></div>')

    g.append('<h2>Portföy</h2>')
    g.append(f'<p style="margin:0 0 6px;font-size:10pt">Toplam <strong>{tl(tp)} TL</strong></p>')
    g.append(bar_yatay(agirlik, bicim=lambda x: tl(x), birim=" TL"))
    g.append('<table><thead><tr><th>Fon</th><th>Kurum</th><th>Adet</th><th>Değer TL</th>'
             '<th>Ağırlık</th><th>K/Z TL</th><th>Girişten</th></tr></thead><tbody>')
    for x in sorted(p, key=lambda t:-t["deger"]):
        kz = x.get("kz"); gt = x.get("getiri")
        g.append(f'<tr><td class="kod">{x["kod"]}</td><td style="text-align:left">{html.escape(x.get("kurum",""))}</td>'
                 f'<td>{tl(x.get("adet"))}</td><td>{tl(x["deger"])}</td>'
                 f'<td>{yz(x["deger"]/tp)}</td>'
                 f'<td class="{"pos" if (kz or 0)>=0 else "neg"}">{tl(kz)}</td>'
                 f'<td class="{"pos" if (gt or 0)>=0 else "neg"}">{yz(gt)}</td></tr>')
    g.append('</tbody></table>')

    if v.get("talimat"):
        g.append('<h2>Fon talimatları</h2>')
        for x in v["talimat"]:
            g.append(f'<div class="talimat"><div class="bas">{html.escape(x["bas"])}</div>'
                     f'<div class="ger">{html.escape(x["ger"])}</div></div>')
    else:
        g.append('<h2>Fon talimatları</h2><p class="bos">Bugün fon talimatı yok.</p>')

    if hisse:
        g.append('<div class="blok"><h2>Hisse dilimi, endekse göre 12 aylık fark</h2>')
        g.append(bar_ayrisan(hisse))
        g.append(f'<p style="font-size:9pt;color:#52514e;margin:2px 0 0">{html.escape(v.get("hisse_not",""))}</p></div>')

    if v.get("tetik"):
        g.append('<div class="blok"><h2>Tetikler</h2>')
        for t in v["tetik"]:
            g.append(mermi(t["deger"], t["esik"], t["enb"], t["etiket"]))
        g.append('</div>')

    g.append('<div class="blok"><h2>Parlayan fonlar</h2>')
    g.append(sayac(v.get("adaylar", []), bos_not=v.get("adaylar_bos")))
    g.append('</div>')

    if v.get("kap"):
        g.append('<div class="blok"><h2>KAP taraması</h2>')
        g.append(kap_bolum(v["kap"]))
        g.append('</div>')

    if v.get("haber"):
        g.append('<div class="blok"><h2>Haber</h2>')
        for h_ in v["haber"]:
            g.append(f'<div class="haber">{html.escape(h_["metin"])}<br>'
                     f'<span class="kaynak">{html.escape(h_["kaynak"])}</span></div>')
        g.append('</div>')

    g.append(f'<div class="dip">{html.escape(v.get("dip",""))}</div>')
    g.append('</body></html>')
    ara = os.path.splitext(cikti)[0] + ".html"
    open(ara, "w", encoding="utf-8").write("".join(g))
    subprocess.run(["wkhtmltopdf", "--quiet", "--enable-local-file-access",
                    "--encoding", "utf-8", ara, cikti], check=True)
    return cikti

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--veri", required=True); a.add_argument("--cikti", required=True)
    n = a.parse_args()
    print(yaz(json.load(open(n.veri, encoding="utf-8")), n.cikti))
