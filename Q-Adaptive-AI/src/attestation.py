# =============================================================================
# Q-ADAPTIVE AI — Guardian Risk Attestation (src/attestation.py)
# =============================================================================
# Zincir tarafı hazırdı ama Python tarafı attestation ÜRETMİYORDU.
#
# `QAdaptiveAccount._resolveRiskScore` üç kaynak tanır ve bunlardan biri
# `GUARDIAN_SIGNATURE`'dır: guardian'ın imzaladığı bir risk skoru, zincirde
# `ecrecover` ile doğrulanır. Sözleşme bunu bekliyordu, ama imzayı üretecek
# kod yoktu — yani o kaynak pratikte kullanılamıyordu.
#
# Bu modül o boşluğu kapatır: `QAdaptiveAccount.attestationDigest()` ile
# BİREBİR aynı digest'i hesaplar ve imzalar.
#
# ─────────────────────────────────────────────────────────────────────────────
# Neden sıfır bağımlılık
# ─────────────────────────────────────────────────────────────────────────────
# Keccak-256 ve secp256k1 burada saf Python ile uygulanmıştır. Sebepleri:
#
#   • `hashlib.sha3_256` KULLANILAMAZ. O, FIPS 202 SHA3-256'dır ve Ethereum'un
#     kullandığı Keccak-256'dan FARKLI dolgu (padding) kullanır: SHA3 0x06,
#     Keccak 0x01. Aynı girdi için farklı çıktı verirler. Bu, sessizce yanlış
#     imza üretmeye yol açan klasik bir tuzaktır.
#   • Projenin kripto tarafı zaten bilinçli olarak C bağımlılığı almıyor
#     (Rust'ta `fips204` saf Rust seçildi). Aynı çizgi burada da korundu.
#
# ─────────────────────────────────────────────────────────────────────────────
# DOĞRULAMA — bu dosyaya körlemesine güvenmeyin
# ─────────────────────────────────────────────────────────────────────────────
# Buradaki uygulamanın doğruluğu iki bağımsız yerde sınanır:
#
#   1. `test_attestation.py` — bilinen Keccak-256 ve ECDSA test vektörleri.
#   2. `Q-Adaptive-Contracts/test/GuardianAttestation.t.sol` — Python'un
#      ÜRETTİĞİ gerçek imza, GERÇEK sözleşmenin `ecrecover`'ına verilir.
#      Bu ikincisi asıl kanıttır: zincir kabul etmiyorsa imza yanlıştır.
#
# Üretim kullanımı için not: burada gizli anahtar bellekte tutulur ve
# sabit-zamanlı değildir. Gerçek konuşlandırmada bir HSM/KMS kullanılmalıdır.
# Bu sınır README'de ve raporlarda açıkça belirtilmelidir.
# =============================================================================

from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass, asdict
from typing import Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Keccak-256 (Ethereum varyantı — SHA3 DEĞİL)
# ─────────────────────────────────────────────────────────────────────────────

_KECCAK_ROUND_CONSTANTS = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]

# ρ adımının kaydırma miktarları (lane indeksine göre).
_KECCAK_ROTATION_OFFSETS = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]

_MASK64 = (1 << 64) - 1


def _rotl64(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(state: list[list[int]]) -> None:
    """Keccak-f[1600] permütasyonu — durumu yerinde değiştirir."""
    for rnd in range(24):
        # θ (theta)
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]

        # ρ (rho) ve π (pi)
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rotl64(
                    state[x][y], _KECCAK_ROTATION_OFFSETS[x][y]
                )

        # χ (chi): a[x] ^= (NOT a[x+1]) AND a[x+2]
        for x in range(5):
            for y in range(5):
                degil = ~b[(x + 1) % 5][y] & _MASK64
                state[x][y] = b[x][y] ^ (degil & b[(x + 2) % 5][y])

        # ι (iota)
        state[0][0] ^= _KECCAK_ROUND_CONSTANTS[rnd]


def keccak256(data: bytes) -> bytes:
    """Ethereum'un kullandığı Keccak-256 özetini hesaplar.

    **`hashlib.sha3_256` ile aynı DEĞİLDİR.** Fark dolgu baytındadır:
    Keccak 0x01, SHA3-256 0x06 kullanır.

    Args:
        data: Özetlenecek baytlar.

    Returns:
        32 baytlık özet.
    """
    rate = 136  # (1600 - 2*256) / 8
    state = [[0] * 5 for _ in range(5)]

    # Dolgu: 0x01 ... 0x80 (Keccak orijinal dolgusu)
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] |= 0x80

    # Emme (absorb)
    for offset in range(0, len(padded), rate):
        blok = padded[offset:offset + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(blok[i * 8:(i + 1) * 8], "little")
            state[i % 5][i // 5] ^= lane
        _keccak_f1600(state)

    # Sıkma (squeeze) — 32 bayt yeterli, tek tur.
    cikti = bytearray()
    for i in range(rate // 8):
        cikti += state[i % 5][i // 5].to_bytes(8, "little")
        if len(cikti) >= 32:
            break

    return bytes(cikti[:32])


# ─────────────────────────────────────────────────────────────────────────────
# secp256k1
# ─────────────────────────────────────────────────────────────────────────────

_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_A = 0
_B = 7
_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

#: EIP-2: s değeri eğrinin yarısını aşamaz (imza esnekliği savunması).
#: Sözleşme tarafı da bunu zorluyor (`_verifyAttestation`).
_HALF_N = _N // 2

Point = Tuple[int, int] | None


def _inv_mod(a: int, m: int) -> int:
    return pow(a, m - 2, m)


def _point_add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2 and (y1 + y2) % _P == 0:
        return None

    if p1 == p2:
        lam = (3 * x1 * x1 + _A) * _inv_mod(2 * y1, _P) % _P
    else:
        lam = (y2 - y1) * _inv_mod(x2 - x1, _P) % _P

    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _point_mul(k: int, point: Point) -> Point:
    """Çift-ve-topla skalar çarpım.

    Sabit-zamanlı DEĞİLDİR. Bu modül fixture ve demo üretimi içindir;
    üretimde HSM/KMS kullanılmalıdır (bkz. dosya başlığı).
    """
    sonuc: Point = None
    eklenen = point
    while k:
        if k & 1:
            sonuc = _point_add(sonuc, eklenen)
        eklenen = _point_add(eklenen, eklenen)
        k >>= 1
    return sonuc


def _rfc6979_k(private_key: int, message_hash: bytes) -> int:
    """RFC 6979 deterministik nonce üretimi (HMAC-SHA256).

    Deterministik nonce şart: rastgele k tekrar kullanılırsa gizli anahtar
    iki imzadan geri hesaplanabilir. Aynı zamanda fixture'ların
    tekrarlanabilir olmasını sağlar — jüri aynı imzayı elde eder.
    """
    v = b"\x01" * 32
    k = b"\x00" * 32
    priv_bytes = private_key.to_bytes(32, "big")

    k = hmac.new(k, v + b"\x00" + priv_bytes + message_hash, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + priv_bytes + message_hash, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()

    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        aday = int.from_bytes(v, "big")
        if 1 <= aday < _N:
            return aday
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def public_key(private_key: int) -> Tuple[int, int]:
    """Gizli anahtardan açık anahtar noktasını türetir."""
    if not 1 <= private_key < _N:
        raise ValueError("Gizli anahtar [1, n) aralığında olmalı")
    nokta = _point_mul(private_key, (_GX, _GY))
    assert nokta is not None
    return nokta


def address_of(private_key: int) -> str:
    """Gizli anahtara karşılık gelen Ethereum adresini döndürür."""
    x, y = public_key(private_key)
    ham = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return "0x" + keccak256(ham)[12:].hex()


def sign(private_key: int, message_hash: bytes) -> Tuple[int, int, int]:
    """32 baytlık bir özeti imzalar.

    Returns:
        ``(v, r, s)`` — `v` 27 veya 28 (Ethereum kurtarma kimliği).
        `s` daima düşük yarıdadır (EIP-2).
    """
    if len(message_hash) != 32:
        raise ValueError("message_hash 32 bayt olmalı")

    z = int.from_bytes(message_hash, "big")
    k = _rfc6979_k(private_key, message_hash)

    nokta = _point_mul(k, (_GX, _GY))
    assert nokta is not None
    x1, y1 = nokta

    r = x1 % _N
    if r == 0:
        raise ValueError("r sıfır çıktı — farklı bir nonce gerekli")

    s = (_inv_mod(k, _N) * (z + r * private_key)) % _N
    if s == 0:
        raise ValueError("s sıfır çıktı — farklı bir nonce gerekli")

    # Kurtarma kimliği: k*G noktasının y paritesi ve x'in n'i aşıp aşmadığı.
    recid = (y1 & 1) | (2 if x1 >= _N else 0)

    # EIP-2 düşük-s normalizasyonu. s çevrilirse parite de çevrilir.
    if s > _HALF_N:
        s = _N - s
        recid ^= 1

    return (27 + recid, r, s)


def signature_bytes(v: int, r: int, s: int) -> bytes:
    """(v, r, s) üçlüsünü sözleşmenin beklediği 65 baytlık düzene çevirir."""
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])


# ─────────────────────────────────────────────────────────────────────────────
# Attestation Digest — QAdaptiveAccount.attestationDigest() ile birebir
# ─────────────────────────────────────────────────────────────────────────────

#: Sözleşmedeki tip dizesinin birebir aynısı. Tek bir karakter farkı
#: digest'i değiştirir ve imza zincirde reddedilir.
_ATTESTATION_TYPEHASH_SOURCE = (
    "QAdaptiveRiskAttestation(bytes32 userOpHash,uint256 riskScore,"
    "uint256 validUntil,address account,uint256 chainId)"
)

#: EIP-191 kişisel imza ön-eki.
_EIP191_PREFIX = b"\x19Ethereum Signed Message:\n32"


def _abi_encode_uint(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _abi_encode_address(addr: str) -> bytes:
    temiz = addr.lower().removeprefix("0x")
    if len(temiz) != 40:
        raise ValueError(f"Geçersiz adres: {addr}")
    return bytes(12) + bytes.fromhex(temiz)


def attestation_digest(
    user_op_hash : bytes,
    risk_score   : int,
    valid_until  : int,
    account      : str,
    chain_id     : int,
) -> bytes:
    """`QAdaptiveAccount.attestationDigest()` ile BİREBİR aynı digest'i üretir.

    Sözleşme tarafı::

        structHash = keccak256(abi.encode(
            keccak256(TYPE_STRING), userOpHash, riskScore, validUntil,
            address(this), block.chainid
        ));
        return keccak256(abi.encodePacked(
            "\\x19Ethereum Signed Message:\\n32", structHash
        ));

    Digest userOpHash'i, skoru, son geçerliliği, hesabı ve zincir kimliğini
    birlikte bağlar. Böylece bir attestation başka bir işleme, başka bir
    hesaba veya başka bir zincire TAŞINAMAZ.
    """
    if len(user_op_hash) != 32:
        raise ValueError("user_op_hash 32 bayt olmalı")

    type_hash = keccak256(_ATTESTATION_TYPEHASH_SOURCE.encode("ascii"))

    struct_hash = keccak256(
        type_hash
        + user_op_hash
        + _abi_encode_uint(risk_score)
        + _abi_encode_uint(valid_until)
        + _abi_encode_address(account)
        + _abi_encode_uint(chain_id)
    )

    return keccak256(_EIP191_PREFIX + struct_hash)


@dataclass(frozen=True)
class Attestation:
    """İmzalanmış bir risk attestation'ı — zincire verilmeye hazır."""

    risk_score     : int
    valid_until    : int
    signature_hex  : str
    digest_hex     : str
    signer_address : str

    def to_dict(self) -> dict:
        return asdict(self)


def create_attestation(
    private_key  : int,
    user_op_hash : bytes,
    risk_score   : int,
    valid_until  : int,
    account      : str,
    chain_id     : int,
) -> Attestation:
    """Guardian attestation'ı üretir ve imzalar.

    Args:
        private_key:  Guardian gizli anahtarı (tamsayı).
        user_op_hash: Attestation'ın bağlanacağı UserOperation özeti.
        risk_score:   Risk yüzdesi × 100 (ör. 7523 = %75,23).
        valid_until:  Son geçerlilik zaman damgası (unix saniye).
        account:      Hedef `QAdaptiveAccount` adresi.
        chain_id:     Zincir kimliği.

    Returns:
        `Attestation` — `signature_hex` doğrudan sözleşmeye verilebilir.
    """
    digest = attestation_digest(user_op_hash, risk_score, valid_until, account, chain_id)
    v, r, s = sign(private_key, digest)

    return Attestation(
        risk_score     = risk_score,
        valid_until    = valid_until,
        signature_hex  = "0x" + signature_bytes(v, r, s).hex(),
        digest_hex     = "0x" + digest.hex(),
        signer_address = address_of(private_key),
    )
