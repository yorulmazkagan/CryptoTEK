#!/usr/bin/env python3
# =============================================================================
# Q-ADAPTIVE — Guardian Attestation Fixture Üreticisi
# =============================================================================
# Python katmanının ürettiği GERÇEK imzayı, Solidity testinin okuyabileceği
# bir JSON dosyasına yazar.
#
# Neden böyle bir köprü gerekli:
#   İki katmanın "aynı digest'i hesapladığını" iddia etmek kolaydır. Bunu
#   KANITLAMAK için Python'un imzasının gerçek sözleşmenin `ecrecover`'ından
#   geçmesi gerekir. Bu betik o kanıtın girdisini üretir;
#   `Q-Adaptive-Contracts/test/GuardianAttestation.t.sol` de kanıtın kendisidir.
#
#   Digest hesabında tek bir bayt kayarsa (tip dizesinde bir harf, alan sırası,
#   EIP-191 ön-eki) zincir imzayı reddeder ve test kırılır. Yani bu köprü,
#   iki katmanın gerçekten hizalı olduğunu her CI koşusunda sınar.
#
# Hesap adresi neden sabit:
#   Python, imzayı atmadan önce hedef hesabın adresini bilmek zorundadır
#   (adres digest'in içinde). Bu yüzden fixture sabit bir adres belirler ve
#   Solidity testi sözleşmeyi `deployCodeTo` ile tam o adrese kurar.
#
# Kullanım:
#   python3 scripts/generate_guardian_fixture.py
#   → Q-Adaptive-Contracts/test/fixtures/guardian_attestation.json
# =============================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "Q-Adaptive-AI"))

from src.attestation import address_of, attestation_digest, create_attestation  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Sabit Parametreler
# ─────────────────────────────────────────────────────────────────────────────
#
# Hepsi sabit çünkü fixture'ın tekrarlanabilir olması gerekiyor: jüri betiği
# kendi makinesinde koşup birebir aynı imzayı elde edebilmeli.
# (İmzalama RFC 6979 ile deterministik — rastgelelik yok.)

#: Guardian gizli anahtarı. SADECE TEST İÇİN — gerçek anahtar asla depoda durmaz.
GUARDIAN_PRIVATE_KEY = 0xA11CE5EC4E7

#: Solidity testinin hesabı kuracağı sabit adres.
ACCOUNT_ADDRESS = "0x00000000000000000000000000000000000acc01"

#: Foundry'nin varsayılan zincir kimliği.
CHAIN_ID = 31337

#: Attestation'ın bağlandığı UserOperation özeti.
USER_OP_HASH = "0x" + "ab" * 32

#: Son geçerlilik. Uzak bir tarih — test `vm.warp` ile zamanı kontrol ediyor.
VALID_UNTIL = 4_102_444_800  # 2100-01-01

#: Üretilecek senaryolar: (ad, risk skoru, açıklama)
SENARYOLAR = [
    ("dusuk_risk",  1_000, "Eşiğin altında — işlem geçmeli"),
    ("esik_altinda", 7_499, "Eşiğin bir altında — geçmeli"),
    ("esik_ustunde", 7_501, "Eşiğin bir üstünde — reddedilmeli"),
    ("yuksek_risk",  9_500, "Yüksek risk — reddedilmeli"),
]


def main() -> int:
    guardian = address_of(GUARDIAN_PRIVATE_KEY)

    kayitlar = []
    for ad, skor, aciklama in SENARYOLAR:
        att = create_attestation(
            private_key  = GUARDIAN_PRIVATE_KEY,
            user_op_hash = bytes.fromhex(USER_OP_HASH.removeprefix("0x")),
            risk_score   = skor,
            valid_until  = VALID_UNTIL,
            account      = ACCOUNT_ADDRESS,
            chain_id     = CHAIN_ID,
        )
        kayitlar.append({
            "name":        ad,
            "description": aciklama,
            "riskScore":   skor,
            "validUntil":  VALID_UNTIL,
            "digest":      att.digest_hex,
            "signature":   att.signature_hex,
        })
        print(f"  {ad:14} skor={skor:5}  imza={att.signature_hex[:22]}...")

    fixture = {
        "_comment": (
            "Python (Q-Adaptive-AI/src/attestation.py) tarafindan uretildi. "
            "Yeniden uretmek icin: python3 scripts/generate_guardian_fixture.py"
        ),
        "guardianAddress": guardian,
        "accountAddress":  ACCOUNT_ADDRESS,
        "chainId":         CHAIN_ID,
        "userOpHash":      USER_OP_HASH,
        "cases":           kayitlar,
    }

    hedef = _REPO_ROOT / "Q-Adaptive-Contracts" / "test" / "fixtures"
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / "guardian_attestation.json"
    yol.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"  Guardian adresi : {guardian}")
    print(f"  Hesap adresi    : {ACCOUNT_ADDRESS}")
    print(f"  Yazıldı         : {yol.relative_to(_REPO_ROOT)}")
    print()
    print("  Doğrulama:")
    print("    cd Q-Adaptive-Contracts && forge test --match-contract GuardianAttestationTest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
