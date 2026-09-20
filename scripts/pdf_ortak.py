#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q-ADAPTIVE PDF belgeleri için ortak altyapı.

Font seçimi, renk paleti, paragraf stilleri, tablo/görsel/uyarı yapı taşları
ve sayfa süslemeleri burada tek yerde durur. İki üretici betik bunu kullanır:

    generate_egitim_dokumani.py   — sıfırdan öğretici belge
    generate_juri_kitapcigi.py    — sunum taktikleri ve jüri soru-cevap

Ayrı ayrı kopyalanmış olsaydı, bir stil düzeltmesi (örneğin `borderPadding`
taşması) yalnızca bir belgede uygulanır ve diğeri sessizce bozuk kalırdı.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

KOK = Path(__file__).resolve().parent.parent
GORSEL = KOK / "images"

# ── Fontlar ──────────────────────────────────────────────────────────────────
# DejaVu seçildi çünkü Türkçe karakterlerin (ğ, ı, İ, ş, ç, ö, ü) tamamını
# ve belgede geçen matematiksel sembolleri (ρ, τ, σ, ℓ, ×, →, ≥) içeriyor.


def _font_bul(desenler: list[str], yedek: str | None = None) -> str:
    for d in desenler:
        bulunan = sorted(glob.glob(d))
        if bulunan:
            return bulunan[0]
    if yedek:
        return yedek
    raise SystemExit(f"Font bulunamadı: {desenler}")


DUZ = _font_bul([
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/**/DejaVuSans.ttf",
])
KALIN = _font_bul([
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/**/DejaVuSans-Bold.ttf",
], yedek=DUZ)
MONO = _font_bul([
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/**/DejaVuSansMono.ttf",
], yedek=DUZ)

pdfmetrics.registerFont(TTFont("DV", DUZ))
pdfmetrics.registerFont(TTFont("DV-B", KALIN))
pdfmetrics.registerFont(TTFont("DV-M", MONO))

# ── Renkler ──────────────────────────────────────────────────────────────────
LACI = colors.HexColor("#0f172a")
MAVI = colors.HexColor("#1d4ed8")
GRI = colors.HexColor("#475569")
ACIK = colors.HexColor("#f1f5f9")
CIZGI = colors.HexColor("#cbd5e1")
YESIL = colors.HexColor("#0f7a46")
KIRMIZI = colors.HexColor("#b91c1c")
AMBER = colors.HexColor("#92620e")
KREM = colors.HexColor("#fdf6e3")

# ── Stiller ──────────────────────────────────────────────────────────────────
S = {
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=19, leading=24,
                         textColor=LACI, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=14, leading=18,
                         textColor=MAVI, spaceBefore=14, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="DV-B", fontSize=11.5, leading=15,
                         textColor=LACI, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="DV", fontSize=9.6, leading=14.6,
                        textColor=LACI, alignment=TA_JUSTIFY, spaceAfter=7),
    "li": ParagraphStyle("li", fontName="DV", fontSize=9.4, leading=14,
                         textColor=LACI, leftIndent=13, bulletIndent=3,
                         spaceAfter=3.5),
    "kod": ParagraphStyle("kod", fontName="DV-M", fontSize=8.1, leading=11.6,
                          textColor=LACI, backColor=ACIK, borderPadding=7,
                          leftIndent=2, spaceBefore=3, spaceAfter=8),
    "not": ParagraphStyle("not", fontName="DV", fontSize=9.2, leading=13.6,
                          textColor=LACI, backColor=KREM, borderPadding=8,
                          borderColor=colors.HexColor("#c9a227"), borderWidth=0.8,
                          alignment=TA_JUSTIFY, spaceBefore=4, spaceAfter=9),
    "kapak_b": ParagraphStyle("kb", fontName="DV-B", fontSize=27, leading=33,
                              textColor=LACI, alignment=TA_CENTER),
    "kapak_a": ParagraphStyle("ka", fontName="DV", fontSize=12.5, leading=18,
                              textColor=GRI, alignment=TA_CENTER),
    "resim_alt": ParagraphStyle("ra", fontName="DV", fontSize=8.4, leading=12,
                                textColor=GRI, alignment=TA_JUSTIFY,
                                spaceBefore=4, spaceAfter=10),
    "tablo": ParagraphStyle("t", fontName="DV", fontSize=8.5, leading=12,
                            textColor=LACI),
    "tablo_b": ParagraphStyle("tb", fontName="DV-B", fontSize=8.5, leading=12,
                              textColor=colors.white),
}

ICERIK_GENISLIGI = A4[0] - 2 * 20 * mm


# ── Yapı taşları ─────────────────────────────────────────────────────────────
def h1(t):
    return [Paragraph(t, S["h1"]),
            Spacer(1, 2),
            Table([[""]], colWidths=[ICERIK_GENISLIGI], rowHeights=[1.6],
                  style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), MAVI)])),
            Spacer(1, 9)]


def h2(t):
    return [Paragraph(t, S["h2"])]


def h3(t):
    return [Paragraph(t, S["h3"])]


def p(t):
    return [Paragraph(t, S["p"])]


def mad(ogeler):
    return [Paragraph(o, S["li"], bulletText="•") for o in ogeler]


def kod(t):
    g = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
          .replace(" ", "&nbsp;").replace("\n", "<br/>"))
    # `notk` ile aynı sebep: borderPadding kutuyu ölçülen yüksekliğin
    # dışına taşırıyor.
    return [Spacer(1, 5), Paragraph(g, S["kod"]), Spacer(1, 2)]


def notk(t):
    # Öndeki Spacer şart: `borderPadding`, kutuyu paragrafın ÖLÇÜLEN
    # yüksekliğinin dışına taşırır ve kutu bir önceki satırın üzerine biner.
    # `spaceBefore` bu taşmayı hesaba katmaz, bu yüzden boşluk elle veriliyor.
    return [Spacer(1, 9), Paragraph(t, S["not"]), Spacer(1, 3)]


def tablo(basliklar, satirlar, genislikler=None):
    veri = [[Paragraph(b, S["tablo_b"]) for b in basliklar]]
    for s in satirlar:
        veri.append([Paragraph(str(h), S["tablo"]) for h in s])
    if genislikler is None:
        genislikler = [ICERIK_GENISLIGI / len(basliklar)] * len(basliklar)
    t = Table(veri, colWidths=genislikler, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LACI),
        ("GRID", (0, 0), (-1, -1), 0.4, CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACIK]),
    ]))
    return [t, Spacer(1, 10)]


def gorsel(ad, altyazi, genislik_orani=1.0):
    """Ekran görüntüsü + açıklama. Dosya yoksa sessizce atlanmaz, uyarılır."""
    yol = GORSEL / ad
    if not yol.exists():
        return [Paragraph(f"[görsel bulunamadı: {ad}]", S["resim_alt"])]
    from PIL import Image as PilImage
    with PilImage.open(yol) as im:
        gen, yuk = im.size
    hedef_g = ICERIK_GENISLIGI * genislik_orani
    hedef_y = hedef_g * yuk / gen
    # Tek sayfaya sığmayan görselleri küçült.
    azami_y = 205 * mm
    if hedef_y > azami_y:
        hedef_y = azami_y
        hedef_g = hedef_y * gen / yuk
    im_ogesi = Image(str(yol), width=hedef_g, height=hedef_y)
    im_ogesi.hAlign = "CENTER"
    return [im_ogesi, Paragraph(altyazi, S["resim_alt"])]


def bosluk(h=7):
    return [Spacer(1, h)]


# ── Sayfa süslemeleri ────────────────────────────────────────────────────────
class Sayfa(canvas.Canvas):
    """Üstbilgi/altbilgi çizen tuval.

    `USTBILGI`, her belge tarafından kendi başlığıyla değiştirilir. Sabit
    kodlanmış olsaydı jüri kitapçığının sayfalarında «Sıfırdan Öğretici
    Belge» yazardı — yani belge kendi adını yanlış söylerdi.
    """

    USTBILGI = "Q-ADAPTIVE (AI Guardian)"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._durumlar = []

    def showPage(self):
        self._durumlar.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._durumlar)
        for d in self._durumlar:
            self.__dict__.update(d)
            self._ciz(n)
            super().showPage()
        super().save()

    def _ciz(self, toplam):
        if self._pageNumber == 1:
            return
        self.saveState()
        self.setFont("DV", 7.6)
        self.setFillColor(GRI)
        self.drawString(20 * mm, A4[1] - 13 * mm,
                        self.USTBILGI)
        self.setStrokeColor(CIZGI)
        self.setLineWidth(0.4)
        self.line(20 * mm, A4[1] - 15 * mm, A4[0] - 20 * mm, A4[1] - 15 * mm)
        self.line(20 * mm, 13 * mm, A4[0] - 20 * mm, 13 * mm)
        self.drawString(20 * mm, 9 * mm, "CryptoTEK · TEKNOFEST 2026 Blokzincir Yarışması")
        self.drawRightString(A4[0] - 20 * mm, 9 * mm,
                             f"Sayfa {self._pageNumber} / {toplam}")
        self.restoreState()


