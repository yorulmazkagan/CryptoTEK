#!/usr/bin/env python3
# =============================================================================
# Q-ADAPTIVE — Katmanlar Arası Eşitlik Testi (test_layer_parity.py)
# =============================================================================
# Bu test, Rust ve Python katmanlarının AYNI kuralı uyguladığını iddia etmez —
# GERÇEK Rust ikilisini çalıştırıp çıktısını Python'unkiyle karşılaştırır.
#
# Neden gerekli:
#   Denetimin yakaladığı en sinsi hata, aynı kuralın iki yerde farklı
#   yazılmasıydı (Rust sabit 90.0, Python τ(t)). İki uygulama sessizce
#   ayrıştığında hiçbir test kırılmıyordu, çünkü ikisini karşılaştıran bir
#   test yoktu. Bu dosya o boşluğu kapatır.
#
# Çalıştırma:
#   cd Q-Adaptive-ZK && cargo build && cd ..
#   python3 Q-Adaptive-AI/test_layer_parity.py
# =============================================================================

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_AI_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _AI_ROOT.parent
_ZK_ROOT = _REPO_ROOT / "Q-Adaptive-ZK"

sys.path.insert(0, str(_AI_ROOT))

from src import armor, calldata  # noqa: E402
from src.armor import ArmorTier  # noqa: E402


def _zk_binary() -> Path:
    """Derlenmiş prover ikilisini bulur (önce release, sonra debug)."""
    for profil in ("release", "debug"):
        yol = _ZK_ROOT / "target" / profil / "q-adaptive-zk"
        if yol.exists():
            return yol
    raise unittest.SkipTest(
        f"ZK prover ikilisi bulunamadı. Derleyin: cd {_ZK_ROOT} && cargo build"
    )


def _kosu(risk: float, tau: float, baseline: ArmorTier) -> tuple[int, str]:
    """Prover'ı verilen parametrelerle çalıştırır, (çıkış kodu, stdout) döner."""
    sonuc = subprocess.run(
        [
            str(_zk_binary()),
            "--risk-score", f"{risk:.6f}",
            "--tau", f"{tau:.6f}",
            "--baseline", baseline.cli_value,
            "--user-op-hash", "0xparite",
            "--epoch-ns", "1700000000000000000",
            "--run-id", "parity",
        ],
        cwd=str(_ZK_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return sonuc.returncode, sonuc.stdout


class ArmorPolicyParityTest(unittest.TestCase):
    """Rust `armor::decide` ile Python `armor.decide` aynı kararı vermeli."""

    #: Sınır vektörleri — kademe eşiklerinin tam üstü ve altı dahil.
    VEKTORLER = [
        (10.0, 75.0),   # çok altında
        (74.99, 75.0),  # hemen altında
        (75.0, 75.0),   # tam eşikte (>= dahil)
        (76.0, 75.0),   # aşım 1  → 44
        (79.99, 75.0),  # aşım ~5 altı → 44
        (80.0, 75.0),   # aşım 5  → 65
        (82.0, 75.0),   # DENETİM SENARYOSU: eski Rust 90.0 bunu kaçırıyordu
        (89.99, 75.0),  # aşım ~15 altı → 65
        (90.0, 75.0),   # aşım 15 → 87
        (95.0, 75.0),   # aşım 20 → 87
        (82.0, 90.0),   # τ yükseldi → normal
        (99.0, 99.0),   # yüksek τ, tam eşik
        (50.0, 40.0),   # düşük risk ama τ daha düşük → panik
    ]

    def test_kanit_karari_iki_katmanda_ayni(self):
        for risk, tau in self.VEKTORLER:
            with self.subTest(risk=risk, tau=tau):
                py = armor.decide(risk, tau, ArmorTier.L44)
                kod, cikti = _kosu(risk, tau, ArmorTier.L44)

                self.assertEqual(kod, 0, f"prover çıkış kodu {kod}:\n{cikti}")

                rust_panik = "PANIC_MODE_ACTIVATED" in cikti
                self.assertEqual(
                    rust_panik,
                    py.proof_required,
                    f"risk={risk} τ={tau}: Rust panik={rust_panik}, "
                    f"Python panik={py.proof_required} — kural ayrışmış",
                )

    def test_secilen_kademe_iki_katmanda_ayni(self):
        for risk, tau in self.VEKTORLER:
            py = armor.decide(risk, tau, ArmorTier.L44)
            if not py.proof_required:
                continue  # kanıt yoksa kademe payload'a yazılmıyor

            with self.subTest(risk=risk, tau=tau):
                _, cikti = _kosu(risk, tau, ArmorTier.L44)
                payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())

                self.assertEqual(
                    payload["pqc_armor_tier"],
                    py.level.display,
                    f"risk={risk} τ={tau}: kademe ayrıştı",
                )

    def test_varsayilan_tau_eski_sabit_degil(self):
        """90.0 sabitinin geri gelmediğini sabitler."""
        self.assertNotEqual(armor.VARSAYILAN_TAU, 90.0)


class PqcSizeParityTest(unittest.TestCase):
    """Python'un beklediği imza boyutları, Rust'ın ÖLÇTÜKLERİYLE uyuşmalı."""

    def test_imza_boyutlari_olculenle_uyusuyor(self):
        # Python tarafı bu sayıları sabit tutuyor; Rust tarafı fips204'ten
        # ölçüyor. Ayrışırlarsa calldata hesabı da yanlış olur.
        beklenen = {
            ArmorTier.L44: 2_420,
            ArmorTier.L65: 3_309,
            ArmorTier.L87: 4_627,
        }

        # Her kademeyi tetikleyecek risk/τ çiftleri.
        tetikleyici = {
            ArmorTier.L44: (76.0, 75.0),
            ArmorTier.L65: (82.0, 75.0),
            ArmorTier.L87: (95.0, 75.0),
        }

        for tier, (risk, tau) in tetikleyici.items():
            with self.subTest(tier=tier.display):
                kod, cikti = _kosu(risk, tau, ArmorTier.L44)
                self.assertEqual(kod, 0, cikti)

                payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())
                olculen = payload["pqc"]["signature_bytes"]

                self.assertEqual(
                    olculen,
                    beklenen[tier],
                    f"{tier.display}: Rust {olculen} B ölçtü, Python {beklenen[tier]} B bekliyor",
                )
                self.assertEqual(olculen, tier.signature_bytes)
                self.assertTrue(
                    payload["pqc"]["signature_verified"],
                    "İmza doğrulanmamış olarak işaretlenmiş",
                )


class CalldataParityTest(unittest.TestCase):
    """Rust `CalldataRecord::compute` ile Python `calldata.compute` aynı olmalı."""

    def test_formul_ve_yuzde_ayni(self):
        kod, cikti = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod, 0, cikti)

        payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())
        rust = payload["calldata"]

        py = calldata.compute(
            batch_size=rust["batch_size"],
            single_signature_bytes=rust["single_signature_bytes"],
            stark_proof_bytes=rust["stark_proof_bytes"],
        )

        self.assertEqual(py.formula, rust["formula"], "Formül metni ayrıştı")
        self.assertAlmostEqual(py.savings_pct, rust["savings_pct"], places=9)
        self.assertEqual(py.naive_batch_bytes, rust["naive_batch_bytes"])
        self.assertEqual(py.ecdsa_batch_bytes, rust["ecdsa_batch_bytes"])
        self.assertEqual(py.beats_ecdsa, rust["beats_ecdsa"])

    def test_uydurma_4608_tabani_geri_gelmemis(self):
        kod, _ = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod, 0)

        payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())
        self.assertNotEqual(
            payload["calldata"]["naive_batch_bytes"],
            4_608,
            "raw_sig_bytes = 4608 tabanı geri gelmiş olabilir",
        )


class DeterminismParityTest(unittest.TestCase):
    """Aynı girdi iki koşuda birebir aynı ρ' ve imzayı vermeli."""

    def test_ayni_girdi_ayni_cikti(self):
        kod1, _ = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod1, 0)
        ilk = json.loads((_ZK_ROOT / "proof_payload.json").read_text())

        kod2, _ = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod2, 0)
        ikinci = json.loads((_ZK_ROOT / "proof_payload.json").read_text())

        self.assertEqual(
            ilk["rho_prime_hex"], ikinci["rho_prime_hex"],
            "ρ' iki koşuda farklı — process::id() benzeri bir kaynak karışmış olabilir",
        )
        self.assertEqual(
            ilk["pqc"]["public_key_commitment_hex"],
            ikinci["pqc"]["public_key_commitment_hex"],
        )
        self.assertTrue(ilk["deterministic_run"])


class SecurityBitsConsistencyTest(unittest.TestCase):
    """README'deki güvenlik seviyesi, kodun ürettiğiyle uyuşmalı."""

    def test_readme_kodla_ayni_biti_soyluyor(self):
        kod, _ = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod, 0)

        payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())
        kod_biti = payload["stark"]["conjectured_security_bits"]

        readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")

        # README'de "STARK security bits" satırını bul.
        satir = next(
            (s for s in readme.splitlines() if "STARK security bits" in s), None
        )
        self.assertIsNotNone(satir, "README'de 'STARK security bits' satırı yok")
        self.assertIn(
            str(kod_biti), satir,
            f"README satırı kodun ürettiği {kod_biti} bit ile uyuşmuyor: {satir!r}",
        )

    def test_alan_adi_kodla_ayni(self):
        kod, _ = _kosu(95.0, 75.0, ArmorTier.L44)
        self.assertEqual(kod, 0)

        payload = json.loads((_ZK_ROOT / "proof_payload.json").read_text())
        self.assertEqual(payload["stark"]["field"], "f128")

        readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "Goldilocks", readme,
            "README hâlâ Goldilocks diyor; kod f128 kullanıyor",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
