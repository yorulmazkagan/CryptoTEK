#!/usr/bin/env python3
"""Arayüzün bölüm bölüm ekran görüntüsünü alır (README görselleri).

Bu betiğin eski hâli şu adresleri çekiyordu:

    http://127.0.0.1:8000/?tab=telemetri&mock=drainer

İki ayrı sorun vardı. Birincisi, o dört sekmeli arayüz **artık yok** — tek
ekranlı nedensellik konsolu ile değiştirildi; yani betik var olmayan
sayfaların görüntüsünü almaya çalışıyordu. İkincisi ve daha önemlisi:
`mock=` parametresi. README'deki görseller ölçülmüş bir koşudan değil,
**sahte veriden** üretilmişti.

Yeni sürüm Chrome'u CDP üzerinden sürer ve **gerçek bir koşu tetikler**:
Drainer senaryosunu seçer, "Koştur"a basar, Rust prover'ın gerçekten kanıt
üretmesini bekler. Görüntülerdeki her sayı canlı API'den gelir.

Kullanım:
    # Sunucu ayrı bir terminalde çalışıyor olmalı:
    cd Q-Adaptive-AI && python3 run_server.py

    python3 scripts/capture_screenshots.py                 # varsayılan :8000
    python3 scripts/capture_screenshots.py --port 8788
    python3 scripts/capture_screenshots.py --tema light    # yalnızca açık tema
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:  # pragma: no cover
    sys.exit("websockets gerekli:  pip install websockets")

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "images"

# Playwright / Puppeteer önbelleğindeki Chrome da kabul edilir; sistemde
# ayrı bir Chrome kurulu olmayabilir.
CHROME_ADAYLARI = [
    shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
    *[str(p) for p in Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome")],
    *[str(p) for p in Path.home().glob(".cache/puppeteer/chrome/*/chrome-linux64/chrome")],
]

GENISLIK = 1440
OLCEK = 2  # deviceScaleFactor — README'de net görünmesi için 2x

# (element seçici, dosya adı, açıklama, görüntü öncesi çalıştırılacak JS)
#
# Sınırlar paneli varsayılan ekranda gizli; yalnızca Sunum Modu'nda açılıyor.
# Görüntüsünü alabilmek için önce o modu açmak gerekiyor.
BOLUMLER = [
    ("#top",         "01_ust_serit",      "Bağlantı, koşu kimliği, τ(t), zırh, determinizm", None),
    ("#nedensellik", "02_nedensellik",    "İşlem → Sezgi → Zırh → Kanıt akışı", None),
    ("#pipe",        "03_yurutme_izi",    "11 aşamalı boru hattı, her süre ölçülmüş", None),
    ("#kafes",       "04_kafes_ve_karar", "Kafes matrisi, imza uzunlukları, karar gerekçesi", None),
    ("#limits",      "05_iddia_etmedik",  "İddia Etmediklerimiz (Sunum Modu)",
     "document.querySelector('#presBtn').click()"),
]


def chrome_bul() -> str:
    for c in CHROME_ADAYLARI:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium bulunamadı. CHROME_ADAYLARI listesine yol ekleyin.")


def bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sunucu_ayakta(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


class Cdp:
    """Chrome DevTools Protocol için minimal istemci."""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def cagir(self, yontem: str, **params):
        self._id += 1
        istek = self._id
        await self.ws.send(json.dumps({"id": istek, "method": yontem, "params": params}))
        while True:
            yanit = json.loads(await self.ws.recv())
            if yanit.get("id") == istek:
                if "error" in yanit:
                    raise RuntimeError(f"{yontem}: {yanit['error']}")
                return yanit.get("result", {})

    async def js(self, ifade: str):
        r = await self.cagir(
            "Runtime.evaluate",
            expression=ifade,
            awaitPromise=True,
            returnByValue=True,
        )
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS hatası: {r['exceptionDetails']}")
        return r["result"].get("value")

    async def bekle(self, kosul_js: str, saniye: float = 60, aralik: float = 0.5) -> bool:
        son = time.time() + saniye
        while time.time() < son:
            if await self.js(f"!!({kosul_js})"):
                return True
            await asyncio.sleep(aralik)
        return False


async def gorus_alani(cdp: Cdp, genislik: int, yukseklik: int = 1000):
    await cdp.cagir(
        "Emulation.setDeviceMetricsOverride",
        width=genislik,
        height=yukseklik,
        deviceScaleFactor=OLCEK,
        mobile=False,
    )


async def tasma_genisligi(cdp: Cdp, secici: str) -> int:
    """Bölüm içinde yatay kayan bir şerit varsa gereken toplam genişlik.

    Yürütme izi aşamaları yatay kaydırılabilir bir şeritte gösteriyor;
    1440 px'de son birkaç aşama kırpılıyordu. Görüntüde hepsinin
    görünmesi gerek — aksi halde "her süre ölçülüyor" iddiası ekran
    görüntüsüyle DOĞRULANAMAZ, ki bu belgenin amacı tam olarak bu.
    """
    return await cdp.js(f"""
        (() => {{
          const k = document.querySelector({secici!r});
          if (!k) return 0;
          let fazla = 0;
          for (const e of [k, ...k.querySelectorAll('*')])
            fazla = Math.max(fazla, e.scrollWidth - e.clientWidth);
          return Math.ceil(fazla);
        }})()
    """) or 0


async def yakala(cdp: Cdp, secici: str, dosya: Path):
    """Tek bir elementi kırparak PNG kaydeder."""
    kutu = await cdp.js(f"""
        (() => {{
          const e = document.querySelector({secici!r});
          if (!e) return null;
          const r = e.getBoundingClientRect();
          if (r.height < 5) return null;
          return {{x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}};
        }})()
    """)
    if not kutu:
        print(f"    ! bulunamadı veya görünmez: {secici}")
        return None

    pay = 6  # kenarlık ve gölge kırpılmasın
    r = await cdp.cagir(
        "Page.captureScreenshot",
        format="png",
        captureBeyondViewport=True,
        clip={
            "x": max(0, kutu["x"] - pay),
            "y": max(0, kutu["y"] - pay),
            "width": kutu["w"] + pay * 2,
            "height": kutu["h"] + pay * 2,
            "scale": OLCEK,
        },
    )
    dosya.write_bytes(base64.b64decode(r["data"]))
    return int(kutu["w"]), int(kutu["h"])


async def tam_sayfa(cdp: Cdp, dosya: Path):
    h = await cdp.js("document.documentElement.scrollHeight")
    r = await cdp.cagir(
        "Page.captureScreenshot",
        format="png",
        captureBeyondViewport=True,
        clip={"x": 0, "y": 0, "width": GENISLIK, "height": h, "scale": OLCEK},
    )
    dosya.write_bytes(base64.b64decode(r["data"]))
    return GENISLIK, h


async def tema_cek(cdp: Cdp, port: int, tema: str):
    """Bir temayı uygular, gerçek koşu tetikler ve tüm bölümleri kaydeder."""
    print(f"\n  ── {tema} tema ──")

    # `localStorage` yalnızca sayfanın kendi kaynağında yazılabilir; henüz
    # about:blank'teyken denemek SecurityError verir. Bu yüzden sıra: önce
    # git, sonra tercihi yaz, sonra YENİLE — tema <head> içindeki erken
    # betik tarafından ilk boyamadan önce uygulansın.
    await cdp.cagir("Page.navigate", url=f"http://127.0.0.1:{port}/ui/")
    await cdp.bekle("document.readyState === 'complete'", 30)
    await cdp.js(f"localStorage.setItem('qadaptive-tema', {tema!r})")
    await cdp.cagir("Page.reload", ignoreCache=False)
    await asyncio.sleep(2.5)

    if not await cdp.bekle("document.querySelector('#conn')?.textContent.includes('canlı')", 60):
        sys.exit("    Arayüz sunucuya bağlanamadı — sunucu ayakta mı?")
    print("    bağlantı canlı")

    uygulanan = await cdp.js("document.documentElement.getAttribute('data-theme')")
    if tema == "light" and uygulanan != "light":
        sys.exit(f"    Tema uygulanmadı (beklenen light, gelen {uygulanan})")

    # GERÇEK koşu: panellerde uydurma değil ölçülmüş veri olsun.
    # Drainer en yüksek riski üretir → ML-DSA-87 + STARK kanıtı.
    await cdp.js("""
        [...document.querySelectorAll('button')]
          .find(b => b.textContent.trim() === 'Drainer')?.click()
    """)
    await asyncio.sleep(0.4)
    await cdp.js("document.querySelector('#run')?.click()")

    print("    koşu tetiklendi, kanıt bekleniyor…")
    if not await cdp.bekle("document.querySelectorAll('#track .stage').length > 0", 240):
        sys.exit("    Koşu tamamlanmadı — prover ikilisi derli mi? (cargo build --release)")

    asama = await cdp.js("document.querySelectorAll('#track .stage').length")
    zirh = await cdp.js("document.querySelector('[data-bind=\"pqc_metrics.armor_tier\"]')?.textContent")
    print(f"    {asama} aşama · zırh {zirh}")

    # Katlanır bölümleri aç ki içerikleri görüntüde görünsün.
    await cdp.js("document.querySelectorAll('details').forEach(d => d.open = true)")
    await asyncio.sleep(1.2)

    ek = "" if tema == "dark" else "_acik"
    for secici, ad, _aciklama, hazirla in BOLUMLER:
        yol = CIKTI / f"{ad}{ek}.png"

        if hazirla:
            await cdp.js(hazirla)
            await asyncio.sleep(0.5)

        # Yatay taşma varsa görüntü alanını geçici olarak genişlet.
        fazla = await tasma_genisligi(cdp, secici)
        if fazla > 0:
            await gorus_alani(cdp, GENISLIK + fazla + 40)
            await asyncio.sleep(0.6)

        boyut = await yakala(cdp, secici, yol)

        if fazla > 0:
            await gorus_alani(cdp, GENISLIK)
            await asyncio.sleep(0.6)

        if boyut:
            not_ = f"  (+{fazla}px taşma)" if fazla else ""
            print(f"    ✓ {yol.name:28} {boyut[0]}×{boyut[1]}"
                  f"  {yol.stat().st_size // 1024} KB{not_}")

    yol = CIKTI / f"00_tam_ekran{ek}.png"
    w, h = await tam_sayfa(cdp, yol)
    print(f"    ✓ {yol.name:28} {w}×{h}  {yol.stat().st_size // 1024} KB")


async def ana(port: int, temalar: list[str]):
    if not sunucu_ayakta(port):
        sys.exit(
            f"127.0.0.1:{port} yanıt vermiyor.\n"
            "Önce sunucuyu başlatın:  cd Q-Adaptive-AI && python3 run_server.py"
        )

    CIKTI.mkdir(exist_ok=True)
    chrome = chrome_bul()
    hata_ayikla = bos_port()
    profil = tempfile.mkdtemp(prefix="qadaptive-shot-")

    print(f"  Chrome : {chrome}")
    print(f"  Sunucu : http://127.0.0.1:{port}/ui/")
    print(f"  Çıktı  : {CIKTI}")

    proc = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            f"--remote-debugging-port={hata_ayikla}",
            f"--user-data-dir={profil}",
            f"--window-size={GENISLIK},1000",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-sandbox",
            "--disable-gpu",
            f"http://127.0.0.1:{port}/ui/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{hata_ayikla}/json/list", timeout=2
                ) as r:
                    sekmeler = json.load(r)
                sayfa = next((t for t in sekmeler if t.get("type") == "page"), None)
                if sayfa:
                    ws_url = sayfa["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws_url:
            sys.exit("Chrome hata ayıklama portu açılmadı.")

        async with websockets.connect(ws_url, max_size=80 * 1024 * 1024) as ws:
            cdp = Cdp(ws)
            await cdp.cagir("Page.enable")
            await cdp.cagir("Runtime.enable")
            await gorus_alani(cdp, GENISLIK)
            for tema in temalar:
                await tema_cek(cdp, port, tema)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profil, ignore_errors=True)

    print(f"\n  Bitti. {len(list(CIKTI.glob('*.png')))} PNG → {CIKTI}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--tema", choices=["dark", "light", "ikisi"], default="ikisi")
    a = ap.parse_args()

    secim = ["dark", "light"] if a.tema == "ikisi" else [a.tema]
    asyncio.run(ana(a.port, secim))
