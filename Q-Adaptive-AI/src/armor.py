# =============================================================================
# Q-ADAPTIVE AI — Zırh Kararı (src/armor.py)
# =============================================================================
# Bu dosya, Rust tarafındaki `Q-Adaptive-ZK/src/armor.rs` ile AYNI politikayı
# uygular. İkisi tek bir kuralın iki dildeki karşılığıdır.
#
# Neden iki dilde aynı kural yazıldı:
#   Karar iki katmanda da gerekiyor — Python API yanıtı üretirken, Rust prover
#   da kanıt üretip üretmeyeceğine karar verirken. Önceden bu iki karar FARKLI
#   kurallarla veriliyordu:
#
#     • Rust  : `if ai_risk_score > 90.0`  — sabit eşik, AI'dan habersiz.
#     • Python: `risk_pct >= dynamic_threshold` — τ(t), kayan pencereden.
#
#   risk = 82 / τ = 75 durumunda Python "panik" diyor, Rust ise 90'ı aşmadığı
#   için kanıt üretmeden çıkıyordu. API bunu hata saymayıp diskteki ESKİ
#   proof_payload.json'ı okuyordu — sahnede "kanıt üretildi" denen şey bayat
#   bir dosya olabiliyordu.
#
# Çözüm: kural tek, τ argümanla geçiyor, sabit yok. `test_layer_parity.py`
# gerçek Rust ikilisini çalıştırıp bu iki uygulamayı sınır vektörlerinde
# karşılaştırır — ayrışırlarsa CI kırılır.
#
# DİKKAT: Bu dosyadaki sabitleri değiştirirsen armor.rs'teki karşılıklarını da
# değiştirmelisin. Eşitlik testi seni zaten durduracaktır.
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# Politika Sabitleri — armor.rs ile birebir aynı
# ─────────────────────────────────────────────────────────────────────────────

#: τ'nun bu kadar üstüne çıkan risk ML-DSA-87'yi tetikler.
ESIK_ASIMI_L87: float = 15.0

#: τ'nun bu kadar üstüne çıkan risk ML-DSA-65'i tetikler.
ESIK_ASIMI_L65: float = 5.0

#: τ verilmediğinde kullanılan varsayılan eşik.
#
#  **90.0 DEĞİLDİR** ve bilinçli olarak öyle seçilmiştir: eski sabit eşiğin
#  sessizce geri gelmesi hâlinde eşitlik testi kırılsın diye.
VARSAYILAN_TAU: float = 75.0

#: Panik durumunun metinsel karşılığı — Rust, JSON ve zincir tarafıyla ortak.
STATUS_PANIC: str = "PANIC_MODE_ACTIVATED"

#: Normal durumun metinsel karşılığı.
STATUS_NORMAL: str = "NORMAL"


class ArmorTier(Enum):
    """ML-DSA güvenlik kademesi.

    ``rank`` değeri tek yönlü tırmanma kuralını uygular: zırh yalnızca
    rank'i artacak şekilde değişebilir.
    """

    L44 = ("44", "ML-DSA-44", 0, 2_420)
    L65 = ("65", "ML-DSA-65", 1, 3_309)
    L87 = ("87", "ML-DSA-87 (Dilithium-5)", 2, 4_627)

    def __init__(self, cli_value: str, display: str, rank: int, signature_bytes: int):
        self.cli_value = cli_value
        self.display = display
        self.rank = rank
        #: NIST FIPS 204 Tablo 2'deki imza boyutu (bayt).
        #: Rust tarafı bu sayıyı fips204'ten ÖLÇER; buradaki değer yalnızca
        #: calldata hesabının girdisidir ve eşitlik testiyle doğrulanır.
        self.signature_bytes = signature_bytes

    @classmethod
    def parse(cls, value: str) -> "ArmorTier":
        """CLI değerinden kademeyi ayrıştırır.

        Geçersiz girdide ``ValueError`` fırlatır. Rust tarafındaki eski
        ``"87" | _ => Level87`` deseni geçersiz girdiyi sessizce en yüksek
        kademeye düşürüyordu; burada da sessiz düşüş yok.
        """
        for tier in cls:
            if tier.cli_value == value.strip():
                return tier
        raise ValueError(
            f"Geçersiz zırh kademesi: {value!r}. Beklenen: 44, 65 veya 87."
        )


@dataclass(frozen=True)
class ArmorDecision:
    """Bir risk/τ çiftinin ürettiği zırh kararı."""

    #: Uygulanacak ML-DSA kademesi.
    level: ArmorTier
    #: STARK kanıtı üretilmeli mi?
    proof_required: bool
    #: Zincire ve JSON'a yazılan durum metni.
    status: str
    #: Riskin τ'yu aşma miktarı (aşmıyorsa 0.0).
    asim: float


def _yuksegi_al(a: ArmorTier, b: ArmorTier) -> ArmorTier:
    """İki kademeden yüksek olanı döndürür — tek yönlü tırmanmanın uygulayıcısı."""
    return a if a.rank >= b.rank else b


def decide(
    risk: float,
    tau: float,
    taban: ArmorTier = ArmorTier.L44,
) -> ArmorDecision:
    """Risk skoru, dinamik eşik ve taban kademeden zırh kararını üretir.

    Kural (armor.rs::decide ile birebir aynı)::

        risk <  τ   → taban kademe, kanıt üretilmez
        risk >= τ   → panik; aşım miktarına göre kademe seçilir:
                        aşım >= 15 → ML-DSA-87
                        aşım >=  5 → ML-DSA-65
                        aksi halde → ML-DSA-44
        her durumda → kademe taban kademenin altına DÜŞEMEZ

    Args:
        risk:  AI'ın ürettiği risk yüzdesi (0.0 – 100.0).
        tau:   Dinamik eşik τ(t).
        taban: Hesabın mevcut taban zırhı.

    Returns:
        ``ArmorDecision``
    """
    # NaN savunması: NaN ile yapılan her karşılaştırma False döner, bu da
    # sessizce "normal" kararına düşmek demektir. Açıkça panik tarafına al.
    if math.isnan(risk) or math.isnan(tau):
        return ArmorDecision(
            level=_yuksegi_al(ArmorTier.L87, taban),
            proof_required=True,
            status=STATUS_PANIC,
            asim=0.0,
        )

    if risk < tau:
        return ArmorDecision(
            level=taban,
            proof_required=False,
            status=STATUS_NORMAL,
            asim=0.0,
        )

    asim = risk - tau

    if asim >= ESIK_ASIMI_L87:
        onerilen = ArmorTier.L87
    elif asim >= ESIK_ASIMI_L65:
        onerilen = ArmorTier.L65
    else:
        onerilen = ArmorTier.L44

    return ArmorDecision(
        level=_yuksegi_al(onerilen, taban),
        proof_required=True,
        status=STATUS_PANIC,
        asim=asim,
    )
