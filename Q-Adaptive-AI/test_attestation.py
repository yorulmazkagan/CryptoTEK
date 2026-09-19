#!/usr/bin/env python3
# =============================================================================
# Q-ADAPTIVE AI — Attestation Kripto Birim Testleri (test_attestation.py)
# =============================================================================
# `src/attestation.py` saf Python ile Keccak-256 ve secp256k1 uygular.
# Elle yazılmış kriptoya körlemesine güvenilmez; bu dosya onu bilinen
# vektörlerle sınar.
#
# İkinci ve asıl doğrulama zincirde yapılır:
#   Q-Adaptive-Contracts/test/GuardianAttestation.t.sol
# Orada Python'un ürettiği imza gerçek sözleşmenin `ecrecover`'ına verilir.
#
# Çalıştırma:
#   python3 Q-Adaptive-AI/test_attestation.py
# =============================================================================

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.attestation import (  # noqa: E402
    _N,
    address_of,
    attestation_digest,
    create_attestation,
    keccak256,
    public_key,
    sign,
    signature_bytes,
)


class Keccak256Test(unittest.TestCase):
    """Keccak-256, bilinen vektörlerle."""

    #: (girdi, beklenen hex özet) — yaygın olarak yayımlanmış vektörler.
    VEKTORLER = [
        (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
        (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
        (
            b"The quick brown fox jumps over the lazy dog",
            "4d741b6f1eb29cb2a9b9911c82f56fa8d73b04959d3d9d222895df6c0b28aa15",
        ),
    ]

    def test_bilinen_vektorler(self):
        for girdi, beklenen in self.VEKTORLER:
            with self.subTest(girdi=girdi[:20]):
                self.assertEqual(keccak256(girdi).hex(), beklenen)

    def test_sha3_ile_karistirilmamis(self):
        """Keccak-256 ≠ SHA3-256.

        İkisi farklı dolgu kullanır (Keccak 0x01, SHA3 0x06). `hashlib.sha3_256`
        kullanmak sessizce yanlış imza üretmeye yol açan klasik bir tuzaktır;
        bu test o hatayı yakalar.
        """
        for girdi, _ in self.VEKTORLER:
            self.assertNotEqual(
                keccak256(girdi),
                hashlib.sha3_256(girdi).digest(),
                "Keccak-256 SHA3-256 ile aynı çıktı verdi — dolgu yanlış",
            )

    def test_blok_sinirlarinda_dogru(self):
        """Rate (136 bayt) sınırı çevresinde dolgu doğru çalışmalı."""
        # Farklı uzunluklar farklı özet vermeli ve hepsi 32 bayt olmalı.
        ozetler = set()
        for uzunluk in (135, 136, 137, 271, 272, 273):
            ozet = keccak256(b"A" * uzunluk)
            self.assertEqual(len(ozet), 32)
            ozetler.add(ozet)
        self.assertEqual(len(ozetler), 6, "Farklı uzunluklar aynı özeti verdi")


class Secp256k1Test(unittest.TestCase):
    """secp256k1 anahtar türetimi ve imzalama."""

    #: Ethereum belgelerinde yaygın olarak geçen test anahtarı.
    TEST_KEY = 0x4C0883A69102937D6231471B5DBB6204FE5129617082792AE468D01A3F362318
    TEST_ADDRESS = "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23"

    def test_bilinen_anahtar_bilinen_adres(self):
        self.assertEqual(address_of(self.TEST_KEY), self.TEST_ADDRESS)

    def test_acik_anahtar_egri_uzerinde(self):
        x, y = public_key(self.TEST_KEY)
        p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        self.assertEqual((y * y) % p, (x * x * x + 7) % p, "Nokta eğri üzerinde değil")

    def test_gecersiz_anahtar_reddediliyor(self):
        for gecersiz in (0, _N, _N + 1):
            with self.subTest(anahtar=gecersiz):
                with self.assertRaises(ValueError):
                    public_key(gecersiz)

    def test_imza_deterministik(self):
        """RFC 6979 — aynı girdi her zaman aynı imza."""
        ozet = keccak256(b"deterministik mi")
        self.assertEqual(sign(self.TEST_KEY, ozet), sign(self.TEST_KEY, ozet))

    def test_s_dusuk_yarida(self):
        """EIP-2: s değeri eğrinin yarısını aşamaz.

        Sözleşme tarafı yüksek-s imzaları reddediyor; üretici taraf da
        üretmemeli.
        """
        for i in range(25):
            _, _, s = sign(self.TEST_KEY, keccak256(f"mesaj-{i}".encode()))
            self.assertLessEqual(s, _N // 2, f"{i}. imzada s yüksek yarıda")

    def test_v_gecerli_aralikta(self):
        for i in range(25):
            v, _, _ = sign(self.TEST_KEY, keccak256(f"mesaj-{i}".encode()))
            self.assertIn(v, (27, 28))

    def test_farkli_mesaj_farkli_imza(self):
        a = sign(self.TEST_KEY, keccak256(b"A"))
        b = sign(self.TEST_KEY, keccak256(b"B"))
        self.assertNotEqual(a, b)

    def test_imza_baytlari_65(self):
        v, r, s = sign(self.TEST_KEY, keccak256(b"uzunluk"))
        ham = signature_bytes(v, r, s)
        self.assertEqual(len(ham), 65)
        self.assertEqual(ham[64], v)

    def test_gecersiz_ozet_uzunlugu_reddediliyor(self):
        with self.assertRaises(ValueError):
            sign(self.TEST_KEY, b"kisa")


class AttestationDigestTest(unittest.TestCase):
    """Digest'in girdilerine gerçekten bağlı olduğunu sınar.

    Digest'in sözleşmeyle AYNI olduğu burada değil, zincirde kanıtlanır:
    `GuardianAttestation.t.sol::test_python_digesti_sozlesme_digestiyle_ayni`.
    Buradaki testler digest'in hiçbir alanı sessizce yok saymadığını sınar.
    """

    OP_HASH = bytes.fromhex("ab" * 32)
    ACCOUNT = "0x00000000000000000000000000000000000acc01"
    CHAIN   = 31337

    def _digest(self, **degisiklik):
        parametreler = dict(
            user_op_hash=self.OP_HASH,
            risk_score=1000,
            valid_until=4_102_444_800,
            account=self.ACCOUNT,
            chain_id=self.CHAIN,
        )
        parametreler.update(degisiklik)
        return attestation_digest(**parametreler)

    def test_her_alan_digesti_etkiliyor(self):
        temel = self._digest()

        self.assertNotEqual(temel, self._digest(risk_score=1001), "riskScore")
        self.assertNotEqual(temel, self._digest(valid_until=4_102_444_801), "validUntil")
        self.assertNotEqual(temel, self._digest(chain_id=1), "chainId")
        self.assertNotEqual(
            temel, self._digest(account="0x00000000000000000000000000000000000acc02"), "account"
        )
        self.assertNotEqual(
            temel, self._digest(user_op_hash=bytes.fromhex("cd" * 32)), "userOpHash"
        )

    def test_digest_deterministik(self):
        self.assertEqual(self._digest(), self._digest())

    def test_gecersiz_girdiler_reddediliyor(self):
        with self.assertRaises(ValueError):
            self._digest(user_op_hash=b"kisa")
        with self.assertRaises(ValueError):
            self._digest(account="0x1234")


class CreateAttestationTest(unittest.TestCase):
    """Uçtan uca attestation üretimi."""

    GUARDIAN_KEY = 0xA11CE5EC4E7

    def test_attestation_alanlari_tutarli(self):
        att = create_attestation(
            private_key=self.GUARDIAN_KEY,
            user_op_hash=bytes.fromhex("ab" * 32),
            risk_score=7499,
            valid_until=4_102_444_800,
            account="0x00000000000000000000000000000000000acc01",
            chain_id=31337,
        )

        self.assertEqual(att.risk_score, 7499)
        self.assertEqual(att.signer_address, address_of(self.GUARDIAN_KEY))
        # 0x + 130 hex karakter = 65 bayt
        self.assertEqual(len(att.signature_hex), 132)
        self.assertEqual(len(att.digest_hex), 66)

    def test_uretim_tekrarlanabilir(self):
        """Jüri betiği kendi makinesinde koşup aynı imzayı elde edebilmeli."""
        argumanlar = dict(
            private_key=self.GUARDIAN_KEY,
            user_op_hash=bytes.fromhex("ab" * 32),
            risk_score=1000,
            valid_until=4_102_444_800,
            account="0x00000000000000000000000000000000000acc01",
            chain_id=31337,
        )
        self.assertEqual(
            create_attestation(**argumanlar).signature_hex,
            create_attestation(**argumanlar).signature_hex,
        )


class FixtureGuncelTest(unittest.TestCase):
    """Depodaki fixture'ın güncel kodla üretilmiş olduğunu sınar.

    `attestation.py` değişir ama fixture yeniden üretilmezse Solidity testleri
    eski imzalarla koşar ve ayrışmayı fark etmeyiz. Bu test o durumu yakalar.
    """

    FIXTURE = (
        Path(__file__).resolve().parent.parent
        / "Q-Adaptive-Contracts" / "test" / "fixtures" / "guardian_attestation.json"
    )

    def test_fixture_yeniden_uretilebiliyor(self):
        import json

        if not self.FIXTURE.exists():
            self.skipTest("Fixture yok; üretin: python3 scripts/generate_guardian_fixture.py")

        veri = json.loads(self.FIXTURE.read_text(encoding="utf-8"))
        op_hash = bytes.fromhex(veri["userOpHash"].removeprefix("0x"))

        for durum in veri["cases"]:
            with self.subTest(durum=durum["name"]):
                yeniden = create_attestation(
                    private_key=CreateAttestationTest.GUARDIAN_KEY,
                    user_op_hash=op_hash,
                    risk_score=durum["riskScore"],
                    valid_until=durum["validUntil"],
                    account=veri["accountAddress"],
                    chain_id=veri["chainId"],
                )
                self.assertEqual(
                    yeniden.signature_hex, durum["signature"],
                    "Fixture bayat — yeniden üretin: "
                    "python3 scripts/generate_guardian_fixture.py",
                )
                self.assertEqual(yeniden.digest_hex, durum["digest"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
