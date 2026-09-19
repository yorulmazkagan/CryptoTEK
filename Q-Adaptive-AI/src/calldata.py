# =============================================================================
# Q-ADAPTIVE AI — Calldata Tasarrufu (src/calldata.py)
# =============================================================================
# Bu dosya, Rust tarafındaki `Q-Adaptive-ZK/src/bridge.rs` içindeki
# `CalldataRecord::compute` ile AYNI formülü uygular.
#
# Neden gerekti:
#   Aynı "%97,98" sayısı daha önce İKİ FARKLI FORMÜLLE üretiliyordu:
#
#     (a) api.py  : 1 − kanıt / (4608 + kanıt)
#                   `raw_sig_bytes = 4608.0` — hiçbir yerden gelmeyen,
#                   uydurma bir tek-imza tabanı.
#     (b) raporlar: 50 işlemlik parti (229.750 B → 4.640 B).
#
#   İkisi tesadüfen birbirine yakın sayılar veriyordu ama "hangisi doğru?"
#   sorusunun cevabı yoktu. Tutarsızlık, sayının kendisinden çok zarar
#   veriyordu.
#
# Tek tanım:
#     tasarruf% = (1 − STARK_kanıtı / (parti × ML-DSA_imza_boyutu)) × 100
#
# Formül, girdileriyle birlikte payload'a yazılır ki okuyan kişi yeniden
# hesaplayabilsin.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, asdict

#: Raporlarda kullanılan standart parti boyutu.
DEFAULT_BATCH_SIZE: int = 50

#: Tek bir ECDSA (secp256k1) imzasının calldata boyutu: r ‖ s ‖ v.
ECDSA_SIGNATURE_BYTES: int = 65


@dataclass(frozen=True)
class CalldataRecord:
    """Bir STARK kanıtının calldata tasarrufu — girdileriyle birlikte."""

    batch_size: int
    single_signature_bytes: int
    naive_batch_bytes: int
    stark_proof_bytes: int
    savings_pct: float
    ecdsa_batch_bytes: int
    beats_ecdsa: bool
    formula: str

    def to_dict(self) -> dict:
        return asdict(self)


def compute(
    batch_size: int,
    single_signature_bytes: int,
    stark_proof_bytes: int,
) -> CalldataRecord:
    """Tasarrufu tek formülden hesaplar (bridge.rs::CalldataRecord::compute).

    Args:
        batch_size:             Partideki işlem sayısı.
        single_signature_bytes: Bu zırh kademesindeki ML-DSA imza boyutu.
        stark_proof_bytes:      Partinin yerine geçen STARK kanıtının boyutu.

    Returns:
        ``CalldataRecord``

    Dürüstlük notu:
        ECDSA bu karşılaştırmada bizi yener — 50 ECDSA imzası 3.250 bayttır,
        yani tek bir STARK kanıtından küçüktür. Takas post-kuantum
        güvenliğidir, calldata değil. ``beats_ecdsa`` alanı bunu açıkça
        taşır ki "ECDSA'dan daha az calldata" iddiası sessizce kurulamasın.
    """
    naive_batch_bytes = batch_size * single_signature_bytes
    ecdsa_batch_bytes = batch_size * ECDSA_SIGNATURE_BYTES

    if naive_batch_bytes > 0:
        savings_pct = (1.0 - (stark_proof_bytes / naive_batch_bytes)) * 100.0
    else:
        savings_pct = 0.0

    return CalldataRecord(
        batch_size=batch_size,
        single_signature_bytes=single_signature_bytes,
        naive_batch_bytes=naive_batch_bytes,
        stark_proof_bytes=stark_proof_bytes,
        savings_pct=savings_pct,
        ecdsa_batch_bytes=ecdsa_batch_bytes,
        beats_ecdsa=stark_proof_bytes < ecdsa_batch_bytes,
        formula=f"(1 - {stark_proof_bytes} / ({batch_size} x {single_signature_bytes})) * 100",
    )
