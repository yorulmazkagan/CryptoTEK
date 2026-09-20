#!/usr/bin/env python3
# =============================================================================
# Q-ADAPTIVE — API ↔ Arayüz Sözleşme Testi (test_api_contract.py)
# =============================================================================
# Bu denetimin asıl dersinin otomatikleştirilmiş hâli.
#
# Denetimde çıkan en büyük sorun şuydu: belgeler "ML-DSA kullanıyoruz" diyordu
# ama kodda tek satır yoktu. Aynı hatanın arayüz tarafındaki karşılığı,
# arayüzün API'de OLMAYAN bir alanı gösteriyormuş gibi yapmasıdır.
#
# Arayüzdeki her bağlı alan `data-bind="pqc_detail.signature_bytes"` biçiminde
# işaretli. Bu test o nitelikleri HTML'den okur ve her yolun Pydantic yanıt
# modelinde GERÇEKTEN var olduğunu doğrular. Arayüz var olmayan bir alana
# bağlanırsa CI kırılır.
#
# Ayrıca uydurma verinin geri gelmediğini sınar:
#   • Eski arayüz API'ye ulaşamazsa `proof_size_kb: 3.85` gibi örnek değerlere
#     düşüyordu. Yeni arayüzde böyle bir geri dönüş olmamalı.
#   • Normal modda ayrıntı alanları None dönmeli, örnek değerle dolmamalı.
#
# Çalıştırma:
#   cd Q-Adaptive-AI && python3 test_api_contract.py
# =============================================================================

from __future__ import annotations

import re
import sys
import typing
import unittest
from pathlib import Path

_AI_ROOT = Path(__file__).resolve().parent
_UI_PATH = (
    _AI_ROOT.parent / "stitch_q_adaptive_ai_guardian_dashboards" / "index.html"
)

sys.path.insert(0, str(_AI_ROOT))


def _yanit_modeli():
    """`ExtendedPredictResponse`'u içe aktarır.

    `src.api` ağır bağımlılıklar (onnxruntime, fastapi) çekiyor; bunlar yoksa
    test çalıştırılamaz ve sessizce geçmek yerine atlanır.
    """
    try:
        from src.api import ExtendedPredictResponse  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover
        raise unittest.SkipTest(f"src.api içe aktarılamadı: {exc}") from exc
    return ExtendedPredictResponse


def _alan_var_mi(model, yol: str) -> tuple[bool, str]:
    """Noktalı bir yolun Pydantic modelinde var olup olmadığını izler.

    `Optional[X]`, `list[X]` gibi sarmalayıcıları açarak iner.

    Returns:
        ``(bulundu, aciklama)``
    """
    geçerli = model

    for i, parca in enumerate(yol.split(".")):
        alanlar = getattr(geçerli, "model_fields", None)
        if alanlar is None:
            return False, f"'{parca}' öncesinde yaprak tipe ulaşıldı ({geçerli})"

        if parca not in alanlar:
            mevcut = ", ".join(sorted(alanlar)) or "(yok)"
            nerede = ".".join(yol.split(".")[:i]) or "<kök>"
            return False, f"'{parca}' alanı {nerede} içinde yok. Mevcut: {mevcut}"

        tip = alanlar[parca].annotation

        # Optional[X] / X | None ve list[X] sarmalayıcılarını aç.
        for _ in range(4):
            kok = typing.get_origin(tip)
            if kok is None:
                break
            argümanlar = [a for a in typing.get_args(tip) if a is not type(None)]
            if not argümanlar:
                break
            tip = argümanlar[0]

        geçerli = tip

    return True, "ok"


class ArayuzSozlesmesiTest(unittest.TestCase):
    """Arayüzün bağlandığı her alan API şemasında var mı?"""

    @classmethod
    def setUpClass(cls):
        if not _UI_PATH.exists():
            raise unittest.SkipTest(f"Arayüz bulunamadı: {_UI_PATH}")
        cls.html = _UI_PATH.read_text(encoding="utf-8")

        # Yorumlar çıkarılır: dosyanın başındaki açıklama bloğu örnek olarak
        # `data-bind="yol.alan"` yazıyor ve bu gerçek bir bağ değil. Yorumları
        # taramak testi yanlış pozitife düşürürdü.
        yorumsuz = re.sub(r"<!--.*?-->", "", cls.html, flags=re.S)

        cls.yollar = sorted(set(re.findall(r'data-bind="([^"]+)"', yorumsuz)))
        cls.model = _yanit_modeli()

    def test_arayuz_gercekten_alan_bagliyor(self):
        """En az birkaç bağ olmalı — regex bozulursa test anlamsızlaşır."""
        self.assertGreaterEqual(
            len(self.yollar), 20,
            f"Yalnızca {len(self.yollar)} bağ bulundu; data-bind düzeni bozulmuş olabilir",
        )

    def test_her_bagli_alan_semada_var(self):
        """Arayüz var olmayan bir alana bağlanamaz.

        Bu testin kırılması şu anlama gelir: arayüz, API'nin döndürmediği bir
        şeyi gösteriyormuş gibi yapıyor. Düzeltme yolu alanı API'ye eklemek
        ya da arayüzden çıkarmaktır — testi gevşetmek değil.
        """
        eksik = []
        for yol in self.yollar:
            tamam, aciklama = _alan_var_mi(self.model, yol)
            if not tamam:
                eksik.append(f"  data-bind=\"{yol}\" → {aciklama}")

        self.assertEqual(
            eksik, [],
            "Arayüz API'de OLMAYAN alanlara bağlanıyor:\n" + "\n".join(eksik),
        )


class UydurmaVeriTest(unittest.TestCase):
    """Arayüz örnek veriye düşmemeli — bulgu 3b'nin arayüz karşılığı."""

    @classmethod
    def setUpClass(cls):
        if not _UI_PATH.exists():
            raise unittest.SkipTest(f"Arayüz bulunamadı: {_UI_PATH}")
        cls.html = _UI_PATH.read_text(encoding="utf-8")

    def test_eski_sahte_degerler_geri_gelmemis(self):
        """Eski arayüzdeki uydurma sayılar HTML'de yer almamalı.

        Eski `index.html` API'ye ulaşamayınca şu değerlere düşüyordu:
            proof_size_kb: 3.85 · risk_score: 98.52 · prover_time_ms: 56.4
        Bunlar kodda ölçülen değil, elle yazılmış sayılardı.
        """
        yasakli = ["3.85", "98.52", "56.4", "94.2", "97.98", "18.52"]

        # Yorum satırları hariç tutulur: eski değerlere AÇIKLAMA amacıyla
        # atıfta bulunmak serbest, veri olarak kullanmak yasak.
        yorumsuz = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        yorumsuz = re.sub(r"/\*.*?\*/", "", yorumsuz, flags=re.S)

        bulunan = [d for d in yasakli if d in yorumsuz]
        self.assertEqual(
            bulunan, [],
            f"Arayüzde uydurma sayı bulundu: {bulunan}. "
            "Bu değerler ölçülmüş değil, elle yazılmıştı.",
        )

    def test_sinirlar_paneli_eksiksiz(self):
        """«İddia Etmediklerimiz» paneli, bilinen her sınırı saymalı.

        Bu panel, denetimin asıl dersinin sahnedeki karşılığı: jüri bir sınırı
        bizden ÖNCE bulmasın. Bir madde sessizce silinirse — ya da yeni bir
        sınır ortaya çıkıp panele eklenmezse — bu test kırılır.

        Özellikle «sıfır bilgi» maddesi: ρ' arayüzde yayınlandığı için s1, s2
        ve A matrisi herkesçe yeniden hesaplanabilir. Yani kanıt özlüdür ama
        bir sır gizlemez. Bunu söylemezsek, soran ilk jüri üyesinde yakalanırız.
        """
        panel = self.html.split('id="limits"', 1)
        self.assertEqual(len(panel), 2, "«İddia Etmediklerimiz» paneli kayıp")
        panel = panel[1].split("</div>", 1)[0]

        zorunlu = {
            "STARK ML-DSA doğrulamıyor": "devre içinde ispatlamıyor",
            "ZK nominal — sır gizlenmiyor": "gizlediği bir sır yok",
            "rotasyon zorluk artırmıyor": "artırmıyor",
            "AI kuantum tespit etmiyor": "kuantum saldırısı tespit etmiyor",
            "eğitim verisi sentetik": "kontrollü sentetik",
            "zincirde doğrulanmıyor": "zincirde doğrulanmıyor",
            "denetim/konuşlandırma yok": "yapılmadı",
            "ECDSA calldata'da kazanıyor": "bir STARK kanıtından küçük",
        }

        eksik = [ad for ad, iz in zorunlu.items() if iz not in panel]
        self.assertEqual(
            eksik, [],
            f"Sınırlar panelinden şu madde(ler) düşmüş: {eksik}. "
            "Bir sınırı panelden çıkarmak, onu ortadan kaldırmaz — "
            "yalnızca jürinin bulmasını bekler.",
        )

    def test_olculmeyen_asama_python_tarafindan_eklenmiyor(self):
        """`payload_yazma` aşaması API tarafından geri eklenmemeli.

        Rust bu aşamayı bilinçli olarak listelemez — prover kendi dosya
        yazımını ölçemez, süre her zaman 0.000 ms çıkar. `pipeline.rs`
        içindeki `olculmeyen_asama_listeye_girmiyor` testi Rust tarafını
        koruyordu, ama Python katmanı aynı aşamayı "tamamlanma işareti"
        olarak GERİ EKLİYORDU.

        Sonuç ekranda şöyle görünüyordu: başlığı
        "YÜRÜTME İZİ · HER SÜRE ÖLÇÜLDÜ" olan şeritte iri puntoyla
        `0.00 ms`. Açıklama satırında "süre ölçülmedi" yazması yetmez.

        Bir katmanda kapatılan bir bulgu, diğer katmanda geri açılabiliyorsa
        kapatılmamıştır.
        """
        kaynak = (
            Path(__file__).resolve().parent / "src" / "api.py"
        ).read_text(encoding="utf-8")

        # Yorumlar serbest: kararın gerekçesi kodda yazılı kalmalı.
        kod = "\n".join(
            s for s in kaynak.split("\n") if not s.lstrip().startswith("#")
        )

        self.assertNotIn(
            '"name"  : "payload_yazma"', kod,
            "api.py ölçülemeyen `payload_yazma` aşamasını listeye geri ekliyor. "
            "Rust bu aşamayı kasıtlı olarak dışarıda bırakıyor.",
        )
        self.assertNotIn(
            '"payload_yazma"', kod,
            "api.py `payload_yazma` aşamasını bir biçimde listeye ekliyor.",
        )

    def test_baglanti_yoksa_temizleniyor(self):
        """Bağlantı koptuğunda arayüz her şeyi temizlemeli."""
        self.assertIn(
            "boya(null)", self.html,
            "Bağlantı koptuğunda alanları temizleyen çağrı yok",
        )
        self.assertIn(
            "SUNUCUYA BAĞLANILAMADI", self.html,
            "Bağlantı yok bandı yok — kullanıcı canlı veri sandığını düşünebilir",
        )

    def test_cdn_bagimliligi_yok(self):
        """Projeksiyon güvenliği: dış kaynak çekilmemeli.

        Eski arayüz Tailwind, Chart.js ve Google Fonts'u CDN'den çekiyordu;
        sahnede internet yoksa arayüz çıplak kalırdı.
        """
        yorumsuz = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        dis_kaynak = re.findall(
            r'(?:src|href)="(https?://[^"]+)"', yorumsuz, flags=re.I
        )
        self.assertEqual(
            dis_kaynak, [],
            f"Arayüz dış kaynak çekiyor: {dis_kaynak}. "
            "Sahnede internet olmayabilir.",
        )


class AyrintiAlanlariTest(unittest.TestCase):
    """Yeni ayrıntı alanları şemada ve Optional mı?"""

    def setUp(self):
        self.model = _yanit_modeli()

    def test_ayrinti_alanlari_opsiyonel(self):
        """Normal modda None dönebilmeliler — zorunlu olsalar sahte değer gerekirdi."""
        for ad in ("pipeline", "pqc_detail", "stark_detail",
                   "calldata_detail", "lattice", "deterministic_run"):
            with self.subTest(alan=ad):
                self.assertIn(ad, self.model.model_fields, f"{ad} şemada yok")
                self.assertFalse(
                    self.model.model_fields[ad].is_required(),
                    f"{ad} zorunlu — normal modda örnek değerle doldurulması gerekirdi",
                )

    def test_geriye_uyumluluk_korunuyor(self):
        """Eski arayüz ve test_layer_parity.py bu alanlara bağlı."""
        for ad in ("status", "action", "ai_metrics", "pqc_metrics", "evm_metrics"):
            with self.subTest(alan=ad):
                self.assertIn(ad, self.model.model_fields, f"{ad} kaldırılmış")


if __name__ == "__main__":
    unittest.main(verbosity=2)
