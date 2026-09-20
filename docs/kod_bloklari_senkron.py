#!/usr/bin/env python3
"""Belgelerdeki kod bloklarını gerçek kaynak dosyalardan üretir.

Bu denetimin en büyük bulgusu şuydu: belgeler "ML-DSA kullanıyoruz" diyordu
ama kodda tek satır yoktu. `docs/` altındaki "Kod İncelemesi" bölümleri aynı
tuzağın ikinci hâliydi — kaynak dosyaların tamamını alıntılıyorlardı, ama
alıntı donmuştu. Denetim sonrası `DefaultHasher` kodda kalmadı; belgede 21
yerde duruyordu.

Elle güncellemek bu sorunu çözmez, yalnızca erteler. Bu yüzden bloklar artık
üretiliyor:

    python3 docs/kod_bloklari_senkron.py            # blokları yeniden üret
    python3 docs/kod_bloklari_senkron.py --check    # CI kapısı: kayma varsa 1

Çapalar belgeye gömülüdür ve şu biçimdedir:

    <!-- KOD-SENK kaynak=Q-Adaptive-ZK/src/trace.rs parca=1/2 ic-baslik=evet -->
    ```rust
    ...üretilen içerik...
    ```

`parca=1/2`, kaynak dosyanın ikiye bölünüp ilk yarısının basılacağı anlamına
gelir; bölme sınırı okunabilirlik için en yakın boş satıra kaydırılır.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
KOK = DOCS.parent

CAPA = re.compile(
    r"<!--\s*KOD-SENK\s+kaynak=(?P<kaynak>\S+)\s+"
    r"(?:parca=(?P<p>\d+)/(?P<t>\d+)|sembol=(?P<sembol>[\w,:]+))\s+"
    r"ic-baslik=(?P<ic>evet|hayir)\s*-->"
)

DIL = {".py": "python", ".rs": "rust", ".sol": "solidity"}
YORUM = {".py": "#", ".rs": "//", ".sol": "//"}

BELGELER = [
    "Q_ADAPTIVE_Master_Report_TR.md",
    "presentation_blueprint_guide.md",
    "integration_test_report.md",
]

# Bölme sınırının boş satır aramak için kayabileceği azami mesafe
KAYMA_PAYI = 15


def sinirlar(n: int, toplam: int, satirlar: list[str]) -> list[int]:
    """Dosyayı `toplam` parçaya bölen kesme noktalarını döndürür."""
    ham = [round(i * n / toplam) for i in range(toplam + 1)]
    kesme = [0]
    for x in ham[1:-1]:
        # en yakın boş satıra kaydır — fonksiyon ortasından bölmemek için
        en_iyi = x
        for d in range(KAYMA_PAYI + 1):
            for aday in (x + d, x - d):
                if 0 < aday < n and not satirlar[aday - 1].strip():
                    en_iyi = aday
                    break
            else:
                continue
            break
        kesme.append(en_iyi)
    kesme.append(n)
    return kesme


def sembol_cikar(satirlar: list[str], ad: str, uzanti: str) -> list[str]:
    """Bir üst düzey fonksiyonu, üstündeki doküman yorumlarıyla birlikte çıkarır."""
    # `Tip::metot` biçimi: önce ilgili impl/class bloğuna daral.
    pencere_bas, pencere_son = 0, len(satirlar)
    if "::" in ad:
        tip, ad = ad.split("::", 1)
        kap = re.compile(rf"^(?:impl|class|contract|library)\s+.*\b{re.escape(tip)}\b")
        pencere_bas = next(
            (i for i, s in enumerate(satirlar) if kap.match(s.strip())), None
        )
        if pencere_bas is None:
            raise ValueError(f"kapsayıcı bulunamadı: {tip}")
        # kapsayıcının sonunu süslü parantezle bul
        derinlik, basladi = 0, False
        for i in range(pencere_bas, len(satirlar)):
            for ch in satirlar[i]:
                if ch == "{":
                    derinlik += 1
                    basladi = True
                elif ch == "}":
                    derinlik -= 1
            if basladi and derinlik == 0:
                pencere_son = i + 1
                break

    bas_re = re.compile(
        rf"^(?:pub\s+|async\s+)*\b(?:fn|def|function|class|struct|enum)\s+"
        rf"{re.escape(ad)}\b"
    )
    bas = next(
        (
            i
            for i in range(pencere_bas, pencere_son)
            if bas_re.match(satirlar[i].strip())
        ),
        None,
    )
    if bas is None:
        raise ValueError(f"sembol bulunamadı: {ad}")

    # üstteki doküman yorumlarını ve nitelikleri de al
    on = bas
    onek = ("///", "//!", "#[", "#") if uzanti != ".py" else ("#", "@")
    while on > 0 and satirlar[on - 1].strip().startswith(onek):
        on -= 1

    if uzanti == ".py":
        girinti = len(satirlar[bas]) - len(satirlar[bas].lstrip())
        son = bas + 1
        while son < len(satirlar):
            s = satirlar[son]
            if s.strip() and (len(s) - len(s.lstrip())) <= girinti:
                break
            son += 1
        return satirlar[on:son]

    # Rust / Solidity: süslü parantez eşleme
    derinlik, basladi, son = 0, False, bas
    for i in range(bas, len(satirlar)):
        for ch in satirlar[i]:
            if ch == "{":
                derinlik += 1
                basladi = True
            elif ch == "}":
                derinlik -= 1
        son = i
        if basladi and derinlik == 0:
            break
    return satirlar[on : son + 1]


def uret(
    kaynak: str, p: int, t: int, ic_baslik: bool, sembol: str | None = None
) -> tuple[str, list[str]]:
    yol = KOK / kaynak
    if not yol.exists():
        raise FileNotFoundError(yol)
    uzanti = yol.suffix
    metin = yol.read_text(encoding="utf-8")
    satirlar = metin.split("\n")
    if satirlar and satirlar[-1] == "":
        satirlar.pop()

    gorunen = "/".join(Path(kaynak).parts[1:])

    if sembol:
        govde = []
        for ad in sembol.split(","):
            if govde:
                govde.append("")
            govde.extend(sembol_cikar(satirlar, ad, uzanti))
        etiket = ", ".join(f"{a}()" for a in sembol.split(","))
    else:
        kesme = sinirlar(len(satirlar), t, satirlar)
        bas, son = kesme[p - 1], kesme[p]
        govde = satirlar[bas:son]
        etiket = f"Satırlar {bas + 1}-{son}" if t > 1 else "Tam Dosya"

    if ic_baslik:
        govde = [f"{YORUM[uzanti]} {gorunen} ({etiket})"] + govde

    return DIL[uzanti], govde


def isle(yol: Path) -> tuple[str, int]:
    satirlar = yol.read_text(encoding="utf-8").split("\n")
    cikti: list[str] = []
    i = 0
    n = 0
    while i < len(satirlar):
        m = CAPA.search(satirlar[i])
        if not m:
            cikti.append(satirlar[i])
            i += 1
            continue

        cikti.append(satirlar[i])
        ac = i + 1
        if ac >= len(satirlar) or not satirlar[ac].startswith("```"):
            raise ValueError(f"{yol.name}:{i + 1} çapadan sonra kod bloğu yok")
        kapa = next(
            (j for j in range(ac + 1, len(satirlar)) if satirlar[j].startswith("```")),
            None,
        )
        if kapa is None:
            raise ValueError(f"{yol.name}:{ac + 1} kapanmayan kod bloğu")

        dil, govde = uret(
            m.group("kaynak"),
            int(m.group("p") or 1),
            int(m.group("t") or 1),
            m.group("ic") == "evet",
            m.group("sembol"),
        )
        cikti.append(f"```{dil}")
        cikti.extend(govde)
        cikti.append("```")
        n += 1
        i = kapa + 1

    return "\n".join(cikti), n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="yazma, yalnızca kaymayı bildir")
    a = ap.parse_args()

    kayan = []
    for ad in BELGELER:
        yol = DOCS / ad
        eski = yol.read_text(encoding="utf-8")
        yeni, n = isle(yol)
        if eski == yeni:
            print(f"  ✓ {ad} — {n} blok güncel")
            continue
        if a.check:
            kayan.append(ad)
            print(f"  ✗ {ad} — {n} bloğun en az biri kaynaktan sapmış")
        else:
            yol.write_text(yeni, encoding="utf-8")
            print(f"  ↻ {ad} — {n} blok yeniden üretildi")

    if kayan:
        print(
            "\nBelgedeki kod blokları kaynakla uyuşmuyor. Düzeltmek için:\n"
            "    python3 docs/kod_bloklari_senkron.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
