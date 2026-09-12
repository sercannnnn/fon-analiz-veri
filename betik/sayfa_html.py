#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gunluk brifing ve emir defterini tek sayfalik Artifact icerigine cevirir.

  python3 sayfa_html.py --brifing brifing_veri.json --defter defter_veri.json --cikti sayfa.html

Cikti doctype/html/head/body TASIMAZ: Artifact araci sayfayi kendi iskeletine
sarar. Bu yuzden dosya <title> ve <style> ile baslar.
"""
import argparse, json, html

def tl(x, ond=0):
    if x is None: return "—"
    return f"{x:,.{ond}f}".replace(",", " ").replace(".", ",").replace(" ", ".")

def yz(x, ond=1):
    if x is None: return "—"
    # Turkcede eksi isareti yuzde isaretinden ONCE gelir: -%19,7
    im = "-" if x < 0 else ""
    return f"{im}%{abs(x)*100:,.{ond}f}".replace(".", ",")

def e(s): return html.escape(str(s or ""))

CSS = """
:root{
  --zemin:#fbfaf8; --yuzey:#ffffff; --yuzey2:#f4f2ed;
  --murekkep:#141413; --murekkep2:#55534e; --murekkep3:#8a8780;
  --cizgi:#e4e2dc; --cizgi2:#d3d0c8;
  --vurgu:#2a6fb8; --vurgu-zayif:#dce8f5;
  --eksi:#b93a2c; --arti:#1a7f37; --uyari:#a56a12; --uyari-zemin:#faf1df;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --zemin:#141519; --yuzey:#1b1c21; --yuzey2:#212329;
    --murekkep:#e9e7e2; --murekkep2:#a9a69f; --murekkep3:#78756e;
    --cizgi:#2c2e35; --cizgi2:#3a3d45;
    --vurgu:#74acdf; --vurgu-zayif:#1e2c3c;
    --eksi:#e88073; --arti:#5cbd77; --uyari:#d3a24a; --uyari-zemin:#2a2416;
  }
}
:root[data-theme="dark"]{
  --zemin:#141519; --yuzey:#1b1c21; --yuzey2:#212329;
  --murekkep:#e9e7e2; --murekkep2:#a9a69f; --murekkep3:#78756e;
  --cizgi:#2c2e35; --cizgi2:#3a3d45;
  --vurgu:#74acdf; --vurgu-zayif:#1e2c3c;
  --eksi:#e88073; --arti:#5cbd77; --uyari:#d3a24a; --uyari-zemin:#2a2416;
}
*{box-sizing:border-box;}
body{
  background:var(--zemin); color:var(--murekkep);
  font-family:"Source Sans 3","Segoe UI",Helvetica,Arial,sans-serif;
  font-size:16px; line-height:1.55; margin:0;
  -webkit-text-size-adjust:100%;
}
.sarmal{max-width:880px; margin:0 auto; padding:0 20px 72px;}

/* ust serit */
.serit{
  position:sticky; top:0; z-index:20; background:var(--zemin);
  border-bottom:1px solid var(--cizgi); margin-bottom:26px;
}
.serit-ic{
  max-width:880px; margin:0 auto; padding:10px 20px;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 18px;
}
.serit .ad{
  font-family:Montserrat,"Segoe UI",Arial,sans-serif; font-weight:700;
  font-size:15px; letter-spacing:-.1px; margin-right:auto;
}
.serit a{
  color:var(--murekkep2); text-decoration:none; font-size:13.5px;
  border-bottom:1px solid transparent; padding-bottom:1px;
}
.serit a:hover,.serit a:focus-visible{color:var(--vurgu); border-bottom-color:var(--vurgu);}

h1{
  font-family:Montserrat,"Segoe UI",Arial,sans-serif; font-weight:700;
  font-size:30px; line-height:1.15; letter-spacing:-.5px; margin:22px 0 4px;
  text-wrap:balance;
}
h2{
  font-family:Montserrat,"Segoe UI",Arial,sans-serif; font-weight:600;
  font-size:15px; letter-spacing:.3px; text-transform:uppercase;
  margin:40px 0 12px; padding-bottom:7px; border-bottom:2px solid var(--murekkep);
}
h3{font-family:Montserrat,"Segoe UI",Arial,sans-serif; font-size:14px; font-weight:600;
   margin:22px 0 6px; color:var(--murekkep2);}
p{margin:0 0 12px;}
.tarih{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:13.5px;
  color:var(--murekkep2); margin:0 0 14px;
}
.kapsam{font-size:14px; color:var(--murekkep2); margin:0 0 6px; max-width:66ch;}
.dip{
  margin-top:44px; padding-top:12px; border-top:1px solid var(--cizgi);
  font-size:12.5px; line-height:1.5; color:var(--murekkep3);
}

/* bugun yapilacaklar */
.sayi-serit{
  display:flex; flex-wrap:wrap; gap:10px 28px; align-items:baseline;
  padding:14px 0 2px; margin-bottom:4px;
}
.sayi{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:26px; font-weight:600;
      font-variant-numeric:tabular-nums; line-height:1;}
.sayi-et{font-size:13px; color:var(--murekkep2); display:block; margin-top:4px;
         letter-spacing:.2px;}
.is{display:flex; flex-direction:column; gap:12px; list-style:none; padding:0; margin:14px 0 0;}
.is li{
  background:var(--yuzey); border:1px solid var(--cizgi); border-left:3px solid var(--vurgu);
  border-radius:3px; padding:13px 15px;
}
.is li.satir-sat{border-left-color:var(--eksi);}
.is li.satir-karar{border-left-color:var(--uyari);}
.is .bas{
  display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; margin-bottom:5px;
}
.is .yon{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600; font-size:12px;
  letter-spacing:.6px; padding:1px 6px; border-radius:2px;
  background:var(--vurgu-zayif); color:var(--vurgu);
}
.is .yon.sat{background:transparent; color:var(--eksi); border:1px solid var(--eksi);}
.is .yon.karar{background:transparent; color:var(--uyari); border:1px solid var(--uyari);}
.is .kod{font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600; font-size:16px;}
.is .kurum{color:var(--murekkep2); font-size:14px;}
.is .tutar{
  margin-left:auto; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-variant-numeric:tabular-nums; font-weight:600; font-size:15px;
}
.is .saat{
  font-size:12.5px; color:var(--murekkep2); font-family:"IBM Plex Mono",ui-monospace,monospace;
  display:block; margin-bottom:6px;
}
.is .ger{font-size:14px; color:var(--murekkep2); margin:0;}

/* bulgular */
.bulgu{display:flex; flex-direction:column; gap:16px; margin-top:6px;}
.bulgu article{border-left:2px solid var(--cizgi2); padding-left:14px;}
.bulgu h3{margin:0 0 4px; color:var(--murekkep); font-size:15px;}
.bulgu p{font-size:14.5px; color:var(--murekkep2); margin:0; max-width:68ch;}

/* tablolar */
.kaydir{overflow-x:auto; margin:6px 0 0; -webkit-overflow-scrolling:touch;}
table{border-collapse:collapse; width:100%; font-size:14px; min-width:520px;}
th{
  text-align:right; font-weight:600; font-size:11.5px; letter-spacing:.5px;
  text-transform:uppercase; color:var(--murekkep2);
  border-bottom:1px solid var(--murekkep); padding:6px 8px; white-space:nowrap;
}
th.sol,td.sol{text-align:left;}
td{
  padding:6px 8px; border-bottom:1px solid var(--cizgi); text-align:right;
  font-variant-numeric:tabular-nums; vertical-align:top;
}
td.kod{font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600; text-align:left;}
td.gerekce{
  text-align:left; font-size:13px; color:var(--murekkep2); padding:0 8px 10px;
  border-bottom:1px solid var(--cizgi);
}
.arti{color:var(--arti);} .eksi{color:var(--eksi);}
.sat{color:var(--eksi); font-weight:600;} .al{color:var(--arti); font-weight:600;}
.bos{color:var(--murekkep3); font-style:italic; font-size:14px;}
.ozet{font-size:14.5px; color:var(--murekkep2); margin:0 0 4px;}
caption{caption-side:top; text-align:left; font-size:13px; color:var(--murekkep3); padding:0 0 4px;}

/* grafikler */
.grafik{margin:10px 0 0;}
.grafik svg{display:block; width:100%; height:auto;}
.gaciklama{font-size:12.5px; color:var(--murekkep3); margin:6px 0 0;}

/* haber ve acik sorular */
.haber{display:flex; flex-direction:column; gap:14px;}
.haber article{font-size:14.5px; color:var(--murekkep2); max-width:68ch;}
.haber .kaynak{
  display:block; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11.5px; color:var(--murekkep3); margin-top:3px; letter-spacing:.2px;
}
ol.acik{margin:6px 0 0; padding-left:22px; display:flex; flex-direction:column; gap:8px;}
ol.acik li{font-size:14.5px; color:var(--murekkep2); max-width:68ch; padding-left:4px;}

@media (max-width:560px){
  h1{font-size:25px;}
  .sarmal{padding:0 14px 56px;}
  .serit-ic{padding:9px 14px;}
  .is .tutar{margin-left:0; width:100%;}
}
@media print{ .serit{position:static;} }
"""

def bar_agirlik(kalemler, toplam):
    """Yatay agirlik cubuklari. Tek olcek: en buyuk kalem tam genislik."""
    if not kalemler: return ""
    g, sat, bosluk = 760, 20, 8
    enb = max(v for _, v in kalemler)
    etiket, sayi = 54, 175
    kol = g - etiket - sayi - 12
    h = len(kalemler) * (sat + bosluk)
    p = [f'<svg viewBox="0 0 {g} {h}" role="img" aria-label="Portföy ağırlıkları">']
    for i, (ad, v) in enumerate(kalemler):
        y = i * (sat + bosluk)
        w = max(2, kol * v / enb)
        p.append(f'<text x="0" y="{y+14}" font-size="12.5" font-family="IBM Plex Mono,monospace" '
                 f'font-weight="600" fill="var(--murekkep)">{e(ad)}</text>')
        p.append(f'<rect x="{etiket}" y="{y+2}" width="{w:.1f}" height="{sat-6}" rx="2" fill="var(--vurgu)"/>')
        p.append(f'<text x="{etiket+w+8:.1f}" y="{y+14}" font-size="12" '
                 f'font-family="IBM Plex Mono,monospace" fill="var(--murekkep2)">'
                 f'{tl(v)} TL · {yz(v/toplam)}</text>')
    p.append('</svg>')
    return f'<div class="grafik">{"".join(p)}</div>'

def bar_tetik(tetikler):
    """Kapi mesafesi. Sifirdan sola dogru buyuyen cubuk, esik dikey cizgi."""
    if not tetikler: return ""
    g, sat, bosluk = 760, 34, 14
    h = len(tetikler) * (sat + bosluk)
    kol = g - 132
    p = [f'<svg viewBox="0 0 {g} {h}" role="img" aria-label="Kapı mesafeleri">']
    for i, t in enumerate(tetikler):
        y = i * (sat + bosluk)
        enb = t.get("enb", 0.3)
        d, es = abs(t["deger"]), abs(t["esik"])
        w = min(kol, kol * d / enb)
        wx = min(kol, kol * es / enb)
        acik = d >= es
        renk = "var(--eksi)" if acik else "var(--vurgu)"
        p.append(f'<text x="0" y="{y+11}" font-size="12.5" fill="var(--murekkep2)">{e(t["etiket"])}</text>')
        p.append(f'<rect x="0" y="{y+16}" width="{kol}" height="10" rx="2" fill="var(--yuzey2)"/>')
        p.append(f'<rect x="0" y="{y+16}" width="{w:.1f}" height="10" rx="2" fill="{renk}"/>')
        p.append(f'<line x1="{wx:.1f}" y1="{y+12}" x2="{wx:.1f}" y2="{y+30}" '
                 f'stroke="var(--murekkep)" stroke-width="1.5"/>')
        p.append(f'<text x="{wx:.1f}" y="{y+41}" font-size="10.5" text-anchor="middle" '
                 f'fill="var(--murekkep3)">eşik {yz(t["esik"])}</text>')
        p.append(f'<text x="{kol+10}" y="{y+26}" font-size="13" font-weight="600" '
                 f'font-family="IBM Plex Mono,monospace" fill="{renk}">{yz(t["deger"])}</text>')
    p.append('</svg>')
    return (f'<div class="grafik">{"".join(p)}</div>'
            '<p class="gaciklama">Kırmızı çubuk eşiği aşmış, yani çıkış kapısı açık demektir. '
            'Dikey çizgi eşiğin kendisidir.</p>')

def emir_tablosu(emirler, sutun, gerekce=True):
    if not emirler:
        return '<p class="bos">Bu listede emir bulunmamaktadır.</p>'
    g = ['<div class="kaydir"><table><thead><tr>'
         '<th class="sol">Kod</th><th class="sol">Kurum</th><th class="sol">Portföy</th>'
         f'<th class="sol">Yön</th><th>Adet</th><th>Tutar TL</th><th class="sol">{sutun}</th>'
         '</tr></thead><tbody>']
    for x in emirler:
        yon = x.get("yon", "")
        sinif = "sat" if yon == "SAT" else "al"
        son = x.get("saat") if sutun == "Son saat" else x.get("valor")
        g.append(f'<tr><td class="kod">{e(x["kod"])}</td><td class="sol">{e(x.get("kurum"))}</td>'
                 f'<td class="sol">{e(x.get("portfoy"))}</td>'
                 f'<td class="sol {sinif}">{e(yon)}</td><td>{tl(x.get("adet"))}</td>'
                 f'<td>{tl(x.get("tutar"))}</td><td class="sol">{e(son or "—")}</td></tr>')
        if gerekce and x.get("gerekce"):
            g.append(f'<tr><td class="gerekce" colspan="7">{e(x["gerekce"])}</td></tr>')
    g.append('</tbody></table></div>')
    return "".join(g)

def yaz(b, d, cikti):
    poz = d.get("pozisyon", [])
    top = sum(x["deger"] for x in poz) or 1
    ver = d.get("verilecek", [])
    nak = d.get("nakit", [])
    hazir = sum(n.get("tutar") or 0 for n in nak if n.get("yon") == "MEVCUT")

    # agirlik cubuklari kod bazinda toplanir: ayni fon iki kurumda olabilir
    birlesik = {}
    for x in poz:
        birlesik[x["kod"]] = birlesik.get(x["kod"], 0) + x["deger"]
    kalemler = sorted(birlesik.items(), key=lambda t: -t[1])

    g = [f"<title>Fon Günlüğü</title>", f"<style>{CSS}</style>",
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Montserrat:wght@600;700&family=Source+Sans+3:wght@400;600&'
         'family=IBM+Plex+Mono:wght@400;600&display=swap">']

    g.append('<header class="serit"><div class="serit-ic">'
             '<span class="ad">Fon günlüğü</span>'
             '<a href="#bugun">Bugün</a><a href="#portfoy">Portföy</a>'
             '<a href="#tetik">Tetikler</a><a href="#kap">KAP</a><a href="#defter">Defter</a>'
             '<a href="#nakit">Nakit</a><a href="#acik">Açık</a>'
             '</div></header>')

    g.append('<div class="sarmal">')
    g.append(f'<h1>{e(b.get("tarih",""))}</h1>')
    g.append(f'<p class="kapsam">{e(b.get("kapsam",""))}</p>')

    # --- bugun
    g.append('<h2 id="bugun">Bugün ne yapılacak</h2>')
    g.append('<div class="sayi-serit">')
    g.append(f'<div><span class="sayi">{len(ver)}</span>'
             f'<span class="sayi-et">bankaya girilecek emir</span></div>')
    g.append(f'<div><span class="sayi">{tl(sum(x.get("tutar") or 0 for x in ver))}</span>'
             f'<span class="sayi-et">toplam tutar, TL</span></div>')
    g.append(f'<div><span class="sayi">{tl(hazir)}</span>'
             f'<span class="sayi-et">hazır nakit, TL</span></div>')
    g.append('</div>')

    talimat = b.get("talimat", [])
    if talimat:
        g.append('<ul class="is">')
        for t in talimat:
            bas = t.get("bas", "")
            parca = [p.strip() for p in bas.split("·")]
            yon = parca[0] if parca else ""
            sinif = "satir-sat" if yon == "SAT" else ("satir-karar" if yon == "KARAR" else "")
            ysinif = "sat" if yon == "SAT" else ("karar" if yon == "KARAR" else "")
            kod = parca[1] if len(parca) > 1 else ""
            kalan = parca[2:]
            # Son parca bir tutarsa saga yaslanan hucreye alinir, kurum adina degil.
            tutar = kalan.pop() if kalan and ("TL" in kalan[-1] or "pay" in kalan[-1]) else ""
            if kalan and tutar and ("TL" in kalan[-1] or "pay" in kalan[-1]):
                tutar = kalan.pop() + " · " + tutar
            kurum = " · ".join(kalan)
            g.append(f'<li class="{sinif}"><div class="bas">'
                     f'<span class="yon {ysinif}">{e(yon)}</span>'
                     f'<span class="kod">{e(kod)}</span>'
                     f'<span class="kurum">{e(kurum)}</span>'
                     f'<span class="tutar">{e(tutar)}</span></div>')
            eslesen = next((v for v in ver if v["kod"] == kod), None)
            if eslesen and eslesen.get("saat"):
                g.append(f'<span class="saat">Son işlem saati {e(eslesen["saat"])}</span>')
            g.append(f'<p class="ger">{e(t.get("ger",""))}</p></li>')
        g.append('</ul>')
    else:
        g.append('<p class="bos">Bugün bankaya girilmesi gereken emir bulunmamaktadır.</p>')

    # --- bulgular
    if b.get("dun"):
        g.append('<h2>Dün yapılmayanlar ve bugün çıkanlar</h2><div class="bulgu">')
        for x in b["dun"]:
            g.append(f'<article><h3>{e(x.get("bas"))}</h3><p>{e(x.get("ger"))}</p></article>')
        g.append('</div>')

    # --- portfoy
    g.append(f'<h2 id="portfoy">Portföy · {tl(top)} TL</h2>')
    g.append(bar_agirlik(kalemler, top))
    g.append('<div class="kaydir"><table><thead><tr>'
             '<th class="sol">Kod</th><th class="sol">Kurum</th><th class="sol">Tür</th>'
             '<th>Adet</th><th>Değer TL</th><th>Ağırlık</th><th>K/Z TL</th><th>Girişten</th>'
             '</tr></thead><tbody>')
    for x in sorted(poz, key=lambda t: -t["deger"]):
        kz, gt = x.get("kz"), x.get("getiri")
        g.append(f'<tr><td class="kod">{e(x["kod"])}</td><td class="sol">{e(x.get("kurum"))}</td>'
                 f'<td class="sol">{e(x.get("tip"))}</td><td>{tl(x.get("adet"))}</td>'
                 f'<td>{tl(x["deger"])}</td><td>{yz(x["deger"]/top)}</td>'
                 f'<td class="{"arti" if (kz or 0)>=0 else "eksi"}">{tl(kz)}</td>'
                 f'<td class="{"arti" if (gt or 0)>=0 else "eksi"}">{yz(gt)}</td></tr>')
    g.append('</tbody></table></div>')

    # --- tetikler
    if b.get("tetik"):
        g.append('<h2 id="tetik">Çıkış kapıları</h2>')
        g.append(bar_tetik(b["tetik"]))

    # --- defter
    g.append('<h2 id="defter">Emir defteri</h2>')
    g.append('<h3>İleri tarihe planlanmış</h3>')
    g.append(emir_tablosu(d.get("planli", []), "Son saat"))
    g.append('<h3>Verilmiş, gerçekleşmeyi bekleyen</h3>')
    g.append(emir_tablosu(d.get("verilmis", []), "Gerçekleşme"))
    if d.get("kapanan"):
        g.append('<h3>Son kapanan emirler</h3>')
        g.append(emir_tablosu(d["kapanan"], "Gerçekleşme", gerekce=False))

    # --- nakit
    g.append('<h2 id="nakit">Nakit ve ödeme takvimi</h2>')
    if nak:
        g.append('<div class="kaydir"><table><thead><tr>'
                 '<th class="sol">Valör</th><th class="sol">Kurum</th><th class="sol">Yön</th>'
                 '<th>Tutar TL</th><th class="sol">Açıklama</th></tr></thead><tbody>')
        for n in nak:
            g.append(f'<tr><td class="sol">{e(n.get("valor"))}</td>'
                     f'<td class="sol">{e(n.get("kurum"))}</td>'
                     f'<td class="sol">{e(n.get("yon"))}</td><td>{tl(n.get("tutar"))}</td>'
                     f'<td class="sol">{e(n.get("aciklama"))}</td></tr>')
        g.append('</tbody></table></div>')
    else:
        g.append('<p class="bos">Beklenen nakit hareketi bulunmamaktadır.</p>')

    # --- kap taramasi
    kap = b.get("kap")
    if kap:
        g.append('<h2 id="kap">KAP taraması</h2>')
        g.append(f'<p class="kapsam">{e(kap.get("kapsam"))}</p><div class="bulgu">')
        for k in kap.get("kalem", []):
            k1 = k.get("kademe") == 1
            renk = "var(--eksi)" if k1 else "var(--cizgi2)"
            g.append(f'<article style="border-left-color:{renk}">'
                     f'<h3>{e(k.get("sirket"))} <span style="color:var(--murekkep3);font-weight:400">· '
                     f'{e(k.get("konu"))}</span></h3>'
                     f'<p>{e(k.get("ozet"))}</p>'
                     f'<p style="font-size:12.5px;color:var(--murekkep3);margin-top:3px">'
                     f'{"Birinci" if k1 else "İkinci"} kademe · izleme listesine giriş sebebi: '
                     f'{e(k.get("gerekce"))}</p></article>')
        g.append('</div>')

    # --- haber
    if b.get("haber"):
        g.append('<h2>Ölçüm ve haber</h2><div class="haber">')
        for h_ in b["haber"]:
            g.append(f'<article>{e(h_.get("metin"))}'
                     f'<span class="kaynak">{e(h_.get("kaynak"))}</span></article>')
        g.append('</div>')

    # --- acik sorular
    if b.get("acik"):
        g.append('<h2 id="acik">Açık kalan sorular</h2><ol class="acik">')
        for s in b["acik"]:
            g.append(f'<li>{e(s)}</li>')
        g.append('</ol>')

    g.append(f'<p class="dip">{e(d.get("dip",""))}</p>')
    g.append('</div>')

    open(cikti, "w", encoding="utf-8").write("".join(g))
    return cikti

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--brifing", required=True); a.add_argument("--defter", required=True)
    a.add_argument("--cikti", required=True)
    n = a.parse_args()
    print(yaz(json.load(open(n.brifing, encoding="utf-8")),
              json.load(open(n.defter, encoding="utf-8")), n.cikti))
