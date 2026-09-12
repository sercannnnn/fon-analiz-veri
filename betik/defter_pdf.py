#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emir defterini tek sayfalik PDF olarak uretir.

Kullanim:
  python3 defter_pdf.py --veri defter_veri.json --cikti "Emir Defteri.pdf"

Brifing gunun kararini anlatir; bu belge defterin kendisidir. Bekleyen
emirler, pozisyonlar, nakit takvimi ve son kapanan emirler. Grafik yoktur,
tablo vardir: kullanici bu belgeyi banka ekraniyla karsilastirarak okuyor.
"""
import argparse, json, html, subprocess, os

INK, INK2, INK3, CIZGI = "#141413", "#52514e", "#84837c", "#e3e2de"
S1, KIRMIZI, YESIL = "#2a78d6", "#d03b3b", "#0ca30c"

def tl(x, ond=0):
    if x is None: return "—"
    return f"{x:,.{ond}f}".replace(",", " ").replace(".", ",").replace(" ", ".")

def yz(x, ond=1):
    if x is None: return "—"
    # Turkcede eksi isareti yuzde isaretinden ONCE gelir: -%19,7
    im = "-" if x < 0 else ""
    return f"{im}%{abs(x)*100:,.{ond}f}".replace(".", ",")

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
@page { size: A4; margin: 15mm 14mm 13mm 14mm; }
* { box-sizing: border-box; }
body { font-family:"Gomulu","Source Sans 3","Helvetica Neue",Arial,sans-serif; color:#141413;
       font-size:10pt; line-height:1.45; margin:0; }
h1 { font-family:"Gomulu","Montserrat",Arial,sans-serif; font-size:17pt; margin:0; letter-spacing:-.2px; }
h2 { font-family:"Gomulu","Montserrat",Arial,sans-serif; font-size:10.5pt; margin:18px 0 6px;
     padding-bottom:4px; border-bottom:1px solid #e3e2de; letter-spacing:.1px; }
h3 { font-size:9.5pt; margin:11px 0 3px; color:#52514e; font-weight:600; }
.ust { display:flex; justify-content:space-between; align-items:baseline;
       border-bottom:2px solid #141413; padding-bottom:6px; margin-bottom:4px; }
.tarih { font-size:9.5pt; color:#52514e; font-family:"GomuluMono","IBM Plex Mono",monospace; }
.kapsam { font-size:8.5pt; color:#84837c; margin:0 0 2px; }
table { width:100%; border-collapse:collapse; font-size:9pt; margin-top:3px; }
th { text-align:right; font-weight:600; color:#52514e; font-size:8pt; text-transform:uppercase;
     letter-spacing:.4px; border-bottom:1px solid #141413; padding:4px 4px; }
th.sol, td.sol { text-align:left; }
td { padding:4px 4px; border-bottom:1px solid #f0efec; text-align:right;
     font-variant-numeric:tabular-nums; vertical-align:top; }
td.kod { font-family:"GomuluMono","IBM Plex Mono",monospace; font-weight:600; text-align:left; }
.ger { font-size:8.5pt; color:#52514e; padding:0 4px 7px; border-bottom:1px solid #f0efec;
       text-align:left; }
.sat { color:#d03b3b; font-weight:600; } .al { color:#0ca30c; font-weight:600; }
.pos { color:#0ca30c; } .neg { color:#d03b3b; }
.bos { color:#84837c; font-size:9pt; font-style:italic; }
.blok { page-break-inside:avoid; }
.dip { margin-top:16px; padding-top:6px; border-top:1px solid #e3e2de;
       font-size:8pt; color:#84837c; line-height:1.45; }
.ozet { font-size:9.5pt; margin:0 0 2px; }
"""

def emir_tablosu(emirler, gerekce=True, saat=False):
    son = '<th class="sol">Son saat</th>' if saat else '<th class="sol">Gerçekleşme</th>'
    g = ['<table><thead><tr><th class="sol">Kod</th><th class="sol">Kurum</th>'
         '<th class="sol">Portföy</th><th class="sol">Yön</th><th>Adet</th><th>Tutar TL</th>'
         + son + '</tr></thead><tbody>']
    for e in emirler:
        sinif = "sat" if e["yon"] == "SAT" else "al"
        g.append(f'<tr><td class="kod">{html.escape(e["kod"])}</td>'
                 f'<td class="sol">{html.escape(e.get("kurum",""))}</td>'
                 f'<td class="sol">{html.escape(e.get("portfoy",""))}</td>'
                 f'<td class="sol {sinif}">{e["yon"]}</td>'
                 f'<td>{tl(e.get("adet"))}</td><td>{tl(e.get("tutar"))}</td>'
                 f'<td class="sol">{html.escape(e.get("saat","—") if saat else e.get("valor","—"))}</td></tr>')
        if gerekce and e.get("gerekce"):
            g.append(f'<tr><td colspan="7" class="ger">{html.escape(e["gerekce"])}</td></tr>')
    g.append('</tbody></table>')
    return "".join(g)

def yaz(v, cikti):
    g = ['<!doctype html><html lang="tr"><head><meta charset="utf-8">',
         f'<style>{font_face()}{CSS}</style></head><body>']
    g.append(f'<div class="ust"><h1>Emir defteri</h1>'
             f'<span class="tarih">{v["tarih"]}</span></div>')
    g.append(f'<p class="kapsam">{html.escape(v.get("kapsam",""))}</p>')

    # Iki liste ayri tutulur: birincisi kullanicidan islem bekler, ikincisi beklemez.
    # Tek listede gosterildiginde "bugun yapmam gereken bir sey var mi" sorusu
    # okunamiyordu; kullanici 08.09'da bunu bildirdi.
    ver = v.get("verilecek", [])
    g.append('<div class="blok"><h2>Bugün verilecek emirler</h2>')
    if ver:
        t = sum(x.get("tutar") or 0 for x in ver)
        g.append(f'<p class="ozet">Bankaya girilmesi gereken <strong>{len(ver)} emir</strong> '
                 f'bulunmaktadır, toplam {tl(t)} TL. Son işlem saatleri aşağıdadır.</p>')
        g.append(emir_tablosu(ver, saat=True))
    else:
        g.append('<p class="bos">Bugün bankaya girilmesi gereken emir bulunmamaktadır.</p>')
    g.append('</div>')

    pln = v.get("planli", [])
    if pln:
        g.append('<div class="blok"><h2>İleri tarihe planlanmış emirler</h2>')
        t = sum(x.get("tutar") or 0 for x in pln)
        bilinmez = sum(1 for x in pln if x.get("tutar") is None)
        if bilinmez == len(pln):
            ozet = (f'{len(pln)} emir ileri bir tarihe planlanmıştır; tutarları koşula bağlı olduğu için '
                    f'henüz yazılmamıştır. Bugün yapılacak bir işlem yoktur.')
        elif bilinmez:
            ozet = (f'{len(pln)} emir ileri bir tarihe planlanmıştır; tutarı belli olanların toplamı {tl(t)} TL, '
                    f'{bilinmez} emrin tutarı koşula bağlıdır. Bugün yapılacak bir işlem yoktur.')
        else:
            ozet = (f'{len(pln)} emir ileri bir tarihe planlanmıştır, toplam {tl(t)} TL. '
                    f'Bugün yapılacak bir işlem yoktur.')
        g.append(f'<p class="ozet">{ozet}</p>')
        g.append(emir_tablosu(pln, saat=True))
        g.append('</div>')

    vms = v.get("verilmis", [])
    g.append('<div class="blok"><h2>Verilmiş, gerçekleşmeyi bekleyen emirler</h2>')
    if vms:
        t = sum(x.get("tutar") or 0 for x in vms)
        g.append(f'<p class="ozet">{len(vms)} emir bankada iletilmiş durumdadır, toplam {tl(t)} TL. '
                 f'Bu emirler için yapılacak bir işlem yoktur; gerçekleşme tarihleri aşağıdadır.</p>')
        g.append(emir_tablosu(vms))
    else:
        g.append('<p class="bos">Bankada bekleyen emir bulunmamaktadır.</p>')
    g.append('</div>')

    poz = v.get("pozisyon", [])
    tp = sum(x["deger"] for x in poz) or 1
    g.append('<div class="blok"><h2>Pozisyonlar</h2>')
    g.append(f'<p class="ozet">{len(poz)} pozisyon, toplam <strong>{tl(tp)} TL</strong>.</p></div>')
    kurumlar = {}
    for x in poz: kurumlar.setdefault((x.get("kurum",""), x.get("portfoy","")), []).append(x)
    for (kur, prt), lst in sorted(kurumlar.items(), key=lambda t: -sum(y["deger"] for y in t[1])):
        alt = sum(y["deger"] for y in lst)
        g.append(f'<div class="blok"><h3>{html.escape(kur)}, {html.escape(prt.lower())} · {tl(alt)} TL</h3>')
        g.append('<table><thead><tr><th class="sol">Kod</th><th class="sol">Tür</th><th>Adet</th>'
                 '<th>Değer TL</th><th>Ağırlık</th><th>K/Z TL</th><th>Girişten</th></tr></thead><tbody>')
        for x in sorted(lst, key=lambda t:-t["deger"]):
            kz, gt = x.get("kz"), x.get("getiri")
            g.append(f'<tr><td class="kod">{x["kod"]}</td><td class="sol">{html.escape(x.get("tip",""))}</td>'
                     f'<td>{tl(x.get("adet"))}</td><td>{tl(x["deger"])}</td>'
                     f'<td>{yz(x["deger"]/tp)}</td>'
                     f'<td class="{"pos" if (kz or 0)>=0 else "neg"}">{tl(kz)}</td>'
                     f'<td class="{"pos" if (gt or 0)>=0 else "neg"}">{yz(gt)}</td></tr>')
        g.append('</tbody></table></div>')

    nak = v.get("nakit", [])
    g.append('<div class="blok"><h2>Nakit ve ödeme takvimi</h2>')
    if nak:
        g.append('<table><thead><tr><th class="sol">Valör</th><th class="sol">Kurum</th>'
                 '<th class="sol">Portföy</th><th class="sol">Yön</th><th>Tutar TL</th>'
                 '<th class="sol">Açıklama</th></tr></thead><tbody>')
        for n in sorted(nak, key=lambda t: t.get("valor","")):
            g.append(f'<tr><td class="sol">{html.escape(n.get("valor","—"))}</td>'
                     f'<td class="sol">{html.escape(n.get("kurum",""))}</td>'
                     f'<td class="sol">{html.escape(n.get("portfoy",""))}</td>'
                     f'<td class="sol">{html.escape(n.get("yon",""))}</td>'
                     f'<td>{tl(n.get("tutar"))}</td>'
                     f'<td class="sol" style="font-size:8.5pt">{html.escape(n.get("aciklama","")[:120])}</td></tr>')
        g.append('</tbody></table>')
    else:
        g.append('<p class="bos">Beklenen nakit hareketi bulunmamaktadır.</p>')
    g.append('</div>')

    kap = v.get("kapanan", [])
    if kap:
        g.append('<div class="blok"><h2>Son kapanan emirler</h2>')
        g.append(emir_tablosu(kap, gerekce=False))
        g.append('</div>')

    g.append(f'<div class="dip">{html.escape(v.get("dip",""))}</div></body></html>')
    ara = os.path.splitext(cikti)[0] + ".html"
    open(ara, "w", encoding="utf-8").write("".join(g))
    subprocess.run(["wkhtmltopdf", "--quiet", "--enable-local-file-access",
                    "--encoding", "utf-8", ara, cikti], check=True)
    return cikti

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--veri", required=True); a.add_argument("--cikti", required=True)
    n = a.parse_args()
    print(yaz(json.load(open(n.veri, encoding="utf-8")), n.cikti))
