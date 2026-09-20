// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {UserOperation} from "./interfaces/IUserOperation.sol";
import {IAICore} from "./interfaces/IAICore.sol";

/**
 * @title  QAdaptiveAccount
 * @author Q-ADAPTIVE Team
 * @notice ERC-4337 Programmable Smart Account for the Q-Adaptive AI Guardian system.
 *
 * @dev    ════════════════════════════════════════════════════════════════════
 *         SECURITY ARCHITECTURE — READ BEFORE MODIFYING validateUserOp()
 *         ════════════════════════════════════════════════════════════════════
 *
 *         1. REENTRANCY PROTECTION
 *            ─────────────────────
 *            Two independent, complementary reentrancy guards are active:
 *
 *            a) `nonReentrant` modifier: sets a storage mutex (_status) to
 *               _ENTERED at function entry and back to _NOT_ENTERED at exit.
 *               Any reentrant call reverts before touching state.
 *
 *            b) Checks-Effects-Interactions (CEI) pattern: all state mutations
 *               (EFFECTS) are completed before any external call (INTERACTION).
 *               Even if a future modifier is accidentally removed, the CEI order
 *               alone prevents classic reentrancy fund-drain attacks.
 *
 *            Both guards are applied together. The `nonReentrant` modifier handles
 *            cross-function reentrancy (e.g., fallback → validateUserOp). The CEI
 *            pattern handles same-function interaction ordering. Neither replaces
 *            the other.
 *
 *         2. TIME-LOCK INDEPENDENCE
 *            ──────────────────────
 *            The Time-Lock (SECURITY_DELAY = 2 hours) in `transferHighValue()` is
 *            a separate, independently triggered security layer. It does NOT gate
 *            `validateUserOp`. Its purpose is to delay execution of high-value
 *            transfers so the owner has a 2-hour cancellation window. This is
 *            completely decoupled from the signature validation pipeline.
 *
 *         3. HYBRID SIGNATURE PAYLOAD FORMAT (ERC-4337 userOp.signature)
 *            ─────────────────────────────────────────────────────────────
 *            ABI-encoded as:
 *              abi.encode(
 *                bytes    starkProofBytes,          // Winterfell ZK-STARK proof
 *                AirVerificationMetadata metadata,  // Boundary conditions from ZK trace
 *                uint256  aiDynamicRiskScore        // AI rolling window risk %×100 (0–10000)
 *              )
 *
 *         4. CEI ORDER IN validateUserOp — CRITICAL INVARIANT
 *            ─────────────────────────────────────────────────
 *            CHECKS:      Decode hybrid payload → verify proof length →
 *                         verify AIR boundary conditions → check AI risk score →
 *                         if breach: write pendingTransactions, return SIG_VALIDATION_FAILED
 *            EFFECTS:     Update lastValidatedOpHash (only if all checks pass)
 *            INTERACTION: payable(msg.sender).call{value: missingAccountFunds}
 *                         ← This is the ONLY external call; it runs LAST.
 *
 *            The fund-transfer call to msg.sender (EntryPoint) must be the
 *            absolute last operation. Moving it before any CHECKS or EFFECTS
 *            creates a fund-draining vulnerability.
 *         ════════════════════════════════════════════════════════════════════
 */
contract QAdaptiveAccount {

    // ─────────────────────────────────────────────────────────────────────────
    // Constants
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev ERC-4337 standard validation bitmap for a failed signature check.
    ///      Returning this value tells the EntryPoint to abort the UserOperation.
    uint256 public constant SIG_VALIDATION_FAILED = 1;

    /// @dev ERC-4337 standard validation bitmap for a successful validation.
    uint256 public constant SIG_VALIDATION_SUCCESS = 0;

    /// @notice Time-lock delay for high-value transfers. Independent of signature validation.
    uint256 public constant SECURITY_DELAY = 2 hours;

    /// @notice Threshold above which a transfer enters the time-lock queue.
    uint256 public constant HIGH_VALUE_THRESHOLD = 5000 ether;

    /// @notice Minimum STARK proof byte length accepted in panic mode.
    ///         Derived from Winterfell proof size at 80-bit conjectured security.
    uint256 public constant MIN_STARK_PROOF_BYTES = 3000;

    /// @notice AI risk score above which a UserOperation is staged to pendingTransactions.
    ///         Encoded as risk% × 100 (e.g., 7500 = 75.00% risk).
    ///         This mirrors the dynamic rolling-window threshold from the off-chain
    ///         SlidingWindowThresholdCalibrator in model.py — updated via updateRiskThreshold().
    uint256 public rollingRiskThreshold = 7500; // 75.00% default; adjustable by owner

    // ─────────────────────────────────────────────────────────────────────────
    // Structures
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Staged (time-locked) operation record.
    struct PendingOp {
        uint256 executionTime;
        bool    isActive;
    }

    /**
     * @notice AIR (Algebraic Intermediate Representation) boundary condition
     *         metadata from the ZK-STARK Winterfell proof.
     *
     * @dev    These values correspond to the public inputs of the STARK proof:
     *           - start_* : Initial state of the ML-DSA lattice trace (row 0)
     *           - final_* : Final state of the ML-DSA lattice trace (last row)
     *
     *         On-chain verification checks that start_a corresponds to the
     *         commitment derived from the current quantumPublicKey (keccak256
     *         of the expanded A-matrix root). A mismatch means the proof was
     *         generated for a different key rotation epoch.
     */
    struct AirVerificationMetadata {
        uint256 start_a;
        uint256 start_s1;
        uint256 start_s2;
        uint256 start_t;
        uint256 final_a;
        uint256 final_s1;
        uint256 final_s2;
        uint256 final_t;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // ReentrancyGuard Storage
    // ─────────────────────────────────────────────────────────────────────────

    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED     = 2;
    uint256 private _status;

    // ─────────────────────────────────────────────────────────────────────────
    // State Variables
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice The contract owner / authorized guardian.
    address public owner;

    /// @notice ERC-4337 EntryPoint contract address (immutable post-deployment).
    address public immutable entryPoint;

    /// @notice AI Core contract for on-chain risk status queries.
    IAICore public aiCore;

    /**
     * @notice Current post-quantum public key matrix commitment.
     * @dev    This is the keccak256 root of the ML-DSA A-matrix expanded from
     *         the rho-prime seed. When the AI triggers a key rotation, this is
     *         updated via updateQuantumArmor(). The STARK proof's start_a
     *         boundary condition must match the commitment derived from this value.
     */
    bytes32 public quantumPublicKey;

    /// @notice Active security armor tier string (e.g., "ML-DSA-87 (Dilithium-5)").
    string public currentArmorTier;

    /**
     * @notice Hash of the last successfully validated UserOperation.
     * @dev    EFFECT written in validateUserOp AFTER all CHECKS pass
     *         and BEFORE the fund-transfer INTERACTION. Provides an
     *         additional replay guard at the application layer.
     */
    bytes32 public lastValidatedOpHash;

    /// @notice Whitelist of addresses safe to interact with during high-risk mode.
    mapping(address => bool) public safeDestinationWhitelist;

    /**
     * @notice High-value transfers staged by the time-lock mechanism.
     * @dev    Key: keccak256(abi.encode(target, amount))
     *         This mapping is also used by validateUserOp to stage failed
     *         validations for owner review.
     */
    mapping(bytes32 => PendingOp) public lockedOperations;

    /**
     * @notice UserOperations that failed validation and were staged for review.
     * @dev    Key: userOpHash (from the EntryPoint). Value: PendingOp with the
     *         block.timestamp at the time of rejection and isActive = true.
     *         The owner can inspect and cancel these via cancelTransaction().
     */
    mapping(bytes32 => PendingOp) public pendingTransactions;

    // ─────────────────────────────────────────────────────────────────────────
    // BULGU 6 — Risk Skoru Kaynağı
    // ─────────────────────────────────────────────────────────────────────────
    //
    // Eski kod `aiDynamicRiskScore`'u UserOperation'ın İMZA ALANINDAN çözüyordu:
    //
    //     (starkProofBytes, metadata, aiDynamicRiskScore) =
    //         abi.decode(userOp.signature, (bytes, AirVerificationMetadata, uint256));
    //     ...
    //     if (aiDynamicRiskScore > rollingRiskThreshold) { reddet }
    //
    // Yani skoru yazan taraf ile işlemi gönderen taraf aynıydı. Anahtarı çalan
    // biri skoru 0 yazıp AI kapısından doğrudan geçebilirdi. Kapı, kendisini
    // açması gereken kişinin elindeydi.
    //
    // Artık skor üç kaynaktan gelir ve hiçbiri gönderenin yazdığı alan değildir.

    /// @notice Risk skorunun hangi kaynaktan alınacağı.
    enum RiskSource {
        /// Zincir üstü AI Core oracle'ı (varsayılan).
        AI_CORE_ORACLE,
        /// Guardian'ın (Python katmanı) imzaladığı attestation.
        GUARDIAN_SIGNATURE,
        /// İkisinin BÜYÜĞÜ — hiçbir kaynak riski tek başına düşüremez.
        HIGHEST_OF_BOTH
    }

    /**
     * @notice Guardian'ın imzaladığı risk attestation'ı.
     * @dev    `signature`, `_attestationDigest()` çıktısı üzerine atılmış
     *         65 baytlık ECDSA imzasıdır. Digest userOpHash'i, skoru ve
     *         son geçerlilik zamanını birlikte bağlar; böylece bir
     *         attestation başka bir işleme taşınamaz (replay).
     */
    struct GuardianAttestation {
        uint256 riskScore;
        uint256 validUntil;
        bytes   signature;
    }

    /// @notice Aktif risk kaynağı politikası.
    RiskSource public riskSource;

    /// @notice Guardian attestation'larını imzalamaya yetkili adres.
    address public guardianSigner;

    // ─────────────────────────────────────────────────────────────────────────
    // HATA E4 — Zırh Kademesi (tek yönlü tırmanma)
    // ─────────────────────────────────────────────────────────────────────────
    //
    // Kural zincir DIŞI katmanda vardı ama `updateQuantumArmor` hiçbir kontrol
    // yapmadan kademeyi yazıyordu. EntryPoint yoluyla gelen bir çağrı zırhı
    // ML-DSA-87'den ML-DSA-44'e DÜŞÜREBİLİYORDU.

    /// @notice Aktif zırhın sırası (0=Standard, 1=44, 2=65, 3=87).
    uint8 public currentArmorRank;

    /// @notice Zırhın asla altına inemeyeceği taban sıra.
    uint8 public armorBaselineRank;

    // ─────────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Gönderenin iddia ettiği skor ile gerçek skor ayrıştığında.
    /// @dev Bu olay, skoru düşürme girişimini zincire kalıcı olarak yazar.
    event RiskScoreClaimMismatch(
        bytes32 indexed opHash,
        uint256 claimedScore,
        uint256 resolvedScore
    );

    /// @notice Doğrulama sonucu — reddedişler artık YALNIZCA olay olarak kaydedilir.
    event ValidationResult(bytes32 indexed opHash, bool accepted, bytes32 reason);

    /// @notice Risk kaynağı politikası değiştiğinde.
    event RiskSourceUpdated(RiskSource previous, RiskSource current);

    /// @notice Guardian imzalayıcısı değiştiğinde.
    /// @dev Adresler `indexed`: guardian rotasyonu denetim açısından kritik
    ///      bir olay ve belirli bir adrese göre filtrelenebilmeli.
    event GuardianSignerUpdated(address indexed previous, address indexed current);

    /// @notice Sahiplik devredildiğinde.
    event OwnershipTransferred(address indexed previous, address indexed current);

    /// @notice AI Core oracle adresi değiştiğinde.
    event AICoreUpdated(address indexed previous, address indexed current);

    /// @notice Zırh düşürüldüğünde (yalnızca sahip yapabilir).
    event QuantumArmorDowngraded(string newTier, uint8 newRank);

    /// @notice Zırh taban sırası değiştiğinde.
    event ArmorBaselineUpdated(uint8 previous, uint8 current);

    event QuantumArmorUpdated(string newTier, bytes32 newPublicKeyRoot);
    event SafeDestinationAdded(address indexed destination);
    event SafeDestinationRemoved(address indexed destination);
    event HighValueTransferLocked(bytes32 indexed opHash, address target, uint256 amount, uint256 unlockTime);
    event HighValueTransferCancelled(bytes32 indexed opHash);

    /**
     * @notice Emitted when a failed-validation record is removed from pendingTransactions
     *         via cancelTransaction(). Distinct from HighValueTransferCancelled which
     *         covers lockedOperations (time-lock queue entries).
     */
    event ValidationStageCancelled(bytes32 indexed opHash);

    /**
     * @notice Emitted when validateUserOp rejects an operation due to risk breach
     *         or signature failure and writes it to pendingTransactions.
     * @param  opHash    The UserOperation hash provided by the EntryPoint.
     * @param  riskScore The AI-reported risk score that triggered the rejection (×100).
     * @param  reason    Short ASCII reason code: "SIG_FAIL" or "RISK_BREACH".
     */
    event ValidationStagedToQueue(bytes32 indexed opHash, uint256 riskScore, bytes32 reason);

    /// @notice Emitted when the rolling risk threshold is updated by the owner.
    event RollingRiskThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);

    // ─────────────────────────────────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @dev Reentrancy guard. Sets storage mutex before function body and
     *      clears it after. Any re-entrant call (e.g., via a malicious
     *      fallback on msg.sender) will hit the require and revert before
     *      touching any state.
     *
     *      Note: This modifier is applied to validateUserOp in addition to
     *      execute() and transferHighValue() because the fund-transfer
     *      INTERACTION at the end of validateUserOp is an external call.
     *      Even though msg.sender is the EntryPoint (trusted), defense-in-depth
     *      requires the guard to be present wherever external calls occur.
     */
    modifier nonReentrant() {
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    modifier onlyEntryPoint() {
        require(msg.sender == entryPoint, "QAdaptiveAccount: caller must be EntryPoint");
        _;
    }

    modifier onlyOwnerOrSelf() {
        require(
            msg.sender == owner || msg.sender == address(this),
            "QAdaptiveAccount: not owner or self"
        );
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev `slither-disable-next-line missing-zero-check`: `_guardianSigner`
    ///      için sıfır kontrolü KASITLI olarak yok — sıfır adres "guardian yok"
    ///      demektir. Gerekçe aşağıdaki kurucu yorumunda ve
    ///      `SLITHER_TRIYAJI.md`'de. Dedektörün tamamı kapatılmadı: aynı
    ///      dedektör `_entryPoint` ve `_owner` için GERÇEK bir eksik yakalamıştı.
    // slither-disable-next-line missing-zero-check
    constructor(
        address _entryPoint,
        address _aiCore,
        bytes32 _initialQuantumKey,
        address _owner,
        address _guardianSigner
    ) {
        // Slither `missing-zero-check`: Paymaster bu kontrolleri yapiyordu,
        // Account yapmiyordu — tutarsizlik. Sifir EntryPoint hesabi tamamen
        // kullanilamaz kilar, sifir sahip ise geri alinamaz sekilde sahipsiz
        // birakir; ikisi de deploy aninda yakalanmali.
        require(_entryPoint != address(0), "QAdaptiveAccount: entryPoint is zero");
        require(_owner != address(0), "QAdaptiveAccount: owner is zero");
        // NOT: `_guardianSigner` icin sifir kontrolu KASITLI olarak yok.
        // Sifir adres "guardian yok" anlamina gelir ve `_verifyAttestation`
        // bunu acikca ele alir (`if (guardianSigner == address(0)) return
        // (0, false)`), yani guardian imzasi kaynagi devre disi kalir.

        _status          = _NOT_ENTERED;
        entryPoint       = _entryPoint;
        aiCore           = IAICore(_aiCore);
        quantumPublicKey = _initialQuantumKey;
        currentArmorTier = "Standard";
        owner            = _owner;

        // Varsayılan politika: skoru oracle'dan al. Gönderenin imza alanındaki
        // iddiası hiçbir koşulda karara girmez.
        riskSource       = RiskSource.AI_CORE_ORACLE;
        guardianSigner   = _guardianSigner;

        // Zırh "Standard" (sıra 0) ile başlar ve buradan yalnızca yükselebilir.
        currentArmorRank  = 0;
        armorBaselineRank = 0;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Core ERC-4337: validateUserOp (CEI-Hardened)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Validates a UserOperation's hybrid ZK-STARK + AI risk signature.
     *
     * @dev    ════════════ STRICT CEI EXECUTION ORDER ════════════
     *
     *         ── CHECKS (all state reads, all require() calls) ─────────────
     *
     *         STEP 1 — Decode hybrid signature payload:
     *           userOp.signature must be ABI-encoded as:
     *             abi.encode(bytes starkProofBytes,
     *                        AirVerificationMetadata metadata,
     *                        uint256 aiDynamicRiskScore)
     *
     *         STEP 2 — Panic mode signature integrity check:
     *           If the AI reports panic mode (isPanicMode = true), the STARK
     *           proof is mandatory and must meet minimum byte length.
     *           Failure → stage to pendingTransactions → return SIG_VALIDATION_FAILED.
     *
     *         STEP 3 — AIR boundary condition check:
     *           Verify that metadata.start_a matches the expected commitment
     *           derived from the current quantumPublicKey. A mismatch indicates
     *           the proof was generated for a stale or forged key epoch.
     *           Failure → stage to pendingTransactions → return SIG_VALIDATION_FAILED.
     *
     *         STEP 4 — Dynamic rolling risk threshold check:
     *           If aiDynamicRiskScore (scaled ×100) exceeds the current
     *           rollingRiskThreshold, the operation is considered a critical
     *           policy breach regardless of signature validity.
     *           Breach → stage to pendingTransactions → return SIG_VALIDATION_FAILED.
     *
     *         ── EFFECTS (all state mutations) ────────────────────────────
     *
     *         STEP 5 — Record the validated operation hash:
     *           lastValidatedOpHash = userOpHash
     *           This runs ONLY when all four checks above pass.
     *
     *         ── INTERACTIONS (external calls) ─────────────────────────────
     *
     *         STEP 6 — Fund the EntryPoint (missingAccountFunds):
     *           payable(msg.sender).call{value: missingAccountFunds}("")
     *           This is the ONLY external call in this function and it runs
     *           ABSOLUTELY LAST after all state changes are committed.
     *           Moving this call above any EFFECT or CHECK is a fund-drain
     *           vulnerability and must never be done.
     *         ══════════════════════════════════════════════════════════════
     *
     * @param  userOp              The UserOperation to validate.
     * @param  userOpHash          Hash of the UserOperation (provided by EntryPoint).
     * @param  missingAccountFunds ETH this account must send to the EntryPoint.
     * @return validationData      SIG_VALIDATION_SUCCESS (0) or SIG_VALIDATION_FAILED (1).
     */
    function validateUserOp(
        UserOperation calldata userOp,
        bytes32                userOpHash,
        uint256                missingAccountFunds
    ) external onlyEntryPoint nonReentrant returns (uint256 validationData) {

        // ════════════════════════════════════════════════════════════════
        // PHASE A: CHECKS
        // ════════════════════════════════════════════════════════════════

        // ── STEP 1: Query global risk status from AI Core ─────────────
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();

        // ── STEP 2: Decode hybrid signature payload ───────────────────
        //    Decode into local memory variables before any state write.
        //
        //    HATA E3 NOTU: Aşağıdaki reddediş yollarının hiçbiri artık
        //    DEPOLAMAYA YAZMIYOR. Eskiden her reddediş `pendingTransactions`'a
        //    yazıyordu; bu iki ayrı sorun üretiyordu:
        //      • ERC-7562 (bundler simülasyon kuralları) ihlali — birçok
        //        bundler böyle bir işlemi mempool'a hiç almaz,
        //      • saldırgana ucuz depolama şişirme (storage-bloat DoS) vektörü:
        //        geçersiz imzalarla sınırsız SSTORE tetiklenebiliyordu.
        //    Reddedişler artık yalnızca `ValidationResult` olayıdır. Sahip
        //    incelemek istediğini `stageForReview()` ile açıkça sıraya alır.
        bytes memory               starkProofBytes;
        AirVerificationMetadata    memory metadata;
        uint256                    claimedRiskScore;   // GÖNDERENİN İDDİASI — güvenilmez
        GuardianAttestation memory attestation;

        if (userOp.signature.length >= 64) {
            // Attempt decode; if the caller sends a malformed payload, decode
            // will revert which propagates upward as an operation-level failure.
            // This is the correct behavior: we never accept a malformed signature.
            (starkProofBytes, metadata, claimedRiskScore, attestation) = abi.decode(
                userOp.signature,
                (bytes, AirVerificationMetadata, uint256, GuardianAttestation)
            );
        } else {
            // Signature payload is too short to contain any valid data.
            emit ValidationResult(userOpHash, false, "SIG_TOO_SHORT");
            return SIG_VALIDATION_FAILED;
        }

        // ── STEP 2b: Gerçek risk skorunu ÇÖZ (gönderenden DEĞİL) ────────
        //    `claimedRiskScore` yalnızca sapma olayını yayınlamak için
        //    tutulur; karara asla girmez.
        (uint256 resolvedRiskScore, bool riskResolved) =
            _resolveRiskScore(userOpHash, attestation);

        if (!riskResolved) {
            emit ValidationResult(userOpHash, false, "RISK_UNRESOLVED");
            return SIG_VALIDATION_FAILED;
        }

        if (claimedRiskScore != resolvedRiskScore) {
            // Gönderen gerçek skordan farklı bir şey iddia etti. İşlem bu
            // yüzden reddedilmez (iddia zaten yok sayılıyor) ama girişim
            // zincire kalıcı olarak yazılır.
            emit RiskScoreClaimMismatch(userOpHash, claimedRiskScore, resolvedRiskScore);
        }

        // ── STEP 3: Panic mode — enforce STARK proof length requirement ──
        if (isPanicMode) {
            if (starkProofBytes.length < MIN_STARK_PROOF_BYTES) {
                // Proof absent or undersized: reject (no storage write).
                emit ValidationResult(userOpHash, false, "PROOF_TOO_SHORT");
                return SIG_VALIDATION_FAILED;
            }

            // ── STEP 4: AIR boundary condition verification ─────────────
            //    The expected start_a commitment is derived as:
            //      keccak256(abi.encode(quantumPublicKey, "start_a")) truncated to uint256.
            //    This ties the proof epoch to the current on-chain key rotation.
            //
            //    NOTE: A full on-chain STARK verifier would call a dedicated
            //    StarkVerifier contract here. This boundary check is the
            //    lightweight on-chain anchor that ensures the proof was generated
            //    against the same key epoch stored in quantumPublicKey.
            uint256 expectedStartA = uint256(
                keccak256(abi.encode(quantumPublicKey, bytes32("start_a")))
            ) % (2 ** 128); // Truncate to field element range (f128 BaseElement max)

            if (metadata.start_a != expectedStartA) {
                // Proof epoch mismatch — stale or forged public matrix.
                emit ValidationResult(userOpHash, false, "PROOF_EPOCH_MISMATCH");
                return SIG_VALIDATION_FAILED;
            }
        }

        // ── STEP 5: Dynamic rolling risk threshold gate ─────────────────
        //    aiDynamicRiskScore is risk% × 100 (e.g., 7523 = 75.23%).
        //    rollingRiskThreshold is set to mirror the off-chain
        //    SlidingWindowThresholdCalibrator value (default 7500 = 75.00%).
        //    The owner calls updateRollingRiskThreshold() after each off-chain
        //    calibration cycle to keep both layers synchronized.
        //    DİKKAT: burada kullanılan değer `resolvedRiskScore`'dur —
        //    gönderenin imza alanına yazdığı `claimedRiskScore` DEĞİL.
        if (resolvedRiskScore > rollingRiskThreshold) {
            // Critical policy breach: risk exceeds the rolling window threshold.
            emit ValidationResult(userOpHash, false, "RISK_BREACH");
            return SIG_VALIDATION_FAILED;
        }

        // ════════════════════════════════════════════════════════════════
        // PHASE B: EFFECTS
        // All CHECKS have passed. Mutate state before any external call.
        // ════════════════════════════════════════════════════════════════

        // ── STEP 6: Record validated operation hash ─────────────────────
        //    Written BEFORE the external call below. If the external call
        //    somehow re-enters, lastValidatedOpHash is already set, and the
        //    nonReentrant mutex will also block re-entry.
        lastValidatedOpHash = userOpHash;

        // ════════════════════════════════════════════════════════════════
        // PHASE C: INTERACTIONS
        // The ONLY external call. Runs LAST, after all state is committed.
        // ════════════════════════════════════════════════════════════════

        // ── STEP 7: Fund the EntryPoint (ERC-4337 prefund) ──────────────
        //    This call is to msg.sender which is enforced to be the EntryPoint
        //    by the onlyEntryPoint modifier. However, we still place it last
        //    as defense-in-depth per the CEI pattern.
        //
        //    ── HATA E1: 2300 GAZ STIPEND'İ KALDIRILDI ──────────────────────
        //
        //    Eski satır şuydu:
        //        payable(msg.sender).call{gas: 2300, value: missingAccountFunds}("")
        //    ve gerekçesi "defense-in-depth" diye yazılmıştı.
        //
        //    Ancak gerçek ERC-4337 EntryPoint'in `receive()` fonksiyonu mevduat
        //    muhasebesi için DEPOLAMAYA YAZAR (~20.000+ gaz) ve 2300 gaz bir
        //    SSTORE'a yetmez. Yani bu çağrı gerçek bir EntryPoint'te HER ZAMAN
        //    başarısız olurdu ve alttaki `require(success)` yüzünden HER İŞLEM
        //    REVERT EDERDİ. Hesap canlı ağda hiçbir işlemi tamamlayamazdı.
        //
        //    Stipend'i kaldırmak yeniden giriş riski yaratmıyor:
        //      • hedef `onlyEntryPoint` ile zorlanmış (msg.sender = EntryPoint),
        //      • `nonReentrant` mutex'i açık,
        //      • CEI sırası gereği tüm durum bu çağrıdan ÖNCE yazıldı.
        if (missingAccountFunds > 0) {
            (bool success, ) = payable(msg.sender).call{value: missingAccountFunds}("");
            require(success, "QAdaptiveAccount: EntryPoint funding failed");
        }

        emit ValidationResult(userOpHash, true, "OK");
        return SIG_VALIDATION_SUCCESS;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Risk Skoru Çözümlemesi (BULGU 6)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Gerçek risk skorunu politikaya göre çözer.
     *
     * @dev Üç kaynağın HİÇBİRİ gönderenin yazdığı alan değildir:
     *        • AI_CORE_ORACLE     — zincir üstü oracle.
     *        • GUARDIAN_SIGNATURE — guardian'ın imzaladığı attestation;
     *                               `ecrecover` ile doğrulanır.
     *        • HIGHEST_OF_BOTH    — ikisinin büyüğü, yani hiçbir kaynak
     *                               riski tek başına DÜŞÜREMEZ.
     *
     * @return score    Çözülen risk skoru (risk% × 100).
     * @return resolved Çözümleme başarılı mı (guardian imzası geçersizse false).
     */
    function _resolveRiskScore(
        bytes32 userOpHash,
        GuardianAttestation memory attestation
    ) internal view returns (uint256 score, bool resolved) {
        (uint256 oracleScore, ) = aiCore.getGlobalRiskStatus();

        if (riskSource == RiskSource.AI_CORE_ORACLE) {
            return (oracleScore, true);
        }

        // Guardian imzası gerekiyor — doğrula.
        (uint256 guardianScore, bool ok) = _verifyAttestation(userOpHash, attestation);

        if (riskSource == RiskSource.GUARDIAN_SIGNATURE) {
            return (guardianScore, ok);
        }

        // HIGHEST_OF_BOTH: guardian imzası geçersizse oracle'a düşülür —
        // ama bu güvenli yön, çünkü skor asla düşürülmez.
        if (!ok) {
            return (oracleScore, true);
        }
        return (guardianScore > oracleScore ? guardianScore : oracleScore, true);
    }

    /**
     * @notice Guardian attestation'ının imzasını doğrular.
     * @dev Digest userOpHash + skor + geçerlilik + bu sözleşme + zincir
     *      kimliğini birlikte bağlar; attestation başka bir işleme veya
     *      başka bir zincire taşınamaz.
     */
    function _verifyAttestation(
        bytes32 userOpHash,
        GuardianAttestation memory attestation
    ) internal view returns (uint256 score, bool ok) {
        if (guardianSigner == address(0)) return (0, false);
        if (attestation.signature.length != 65) return (0, false);
        if (attestation.validUntil < block.timestamp) return (0, false);

        bytes32 digest = attestationDigest(
            userOpHash, attestation.riskScore, attestation.validUntil
        );

        bytes32 r;
        bytes32 s;
        uint8   v;
        bytes memory sig = attestation.signature;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }

        // EIP-2 gereği yüksek-s imzalar reddedilir (imza esnekliği savunması).
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return (0, false);
        }
        if (v != 27 && v != 28) return (0, false);

        address recovered = ecrecover(digest, v, r, s);
        if (recovered == address(0) || recovered != guardianSigner) {
            return (0, false);
        }

        return (attestation.riskScore, true);
    }

    /**
     * @notice Guardian'ın imzalaması gereken digest'i üretir.
     * @dev Zincir dışı Python katmanı aynı digest'i hesaplayıp imzalar.
     *      Dışarı açık çünkü test ve istemci tarafı buna ihtiyaç duyar.
     */
    function attestationDigest(
        bytes32 userOpHash,
        uint256 riskScore,
        uint256 validUntil
    ) public view returns (bytes32) {
        // DIKKAT: Asagidaki tip dizesi Python tarafindaki
        // `attestation.py::_ATTESTATION_TYPEHASH_SOURCE` ile BIREBIR ayni
        // olmak zorunda. Tek bir karakter degisirse digest degisir ve
        // guardian imzalari zincirde reddedilir.
        //
        // Satir 120 karakteri astigi icin bolundu. Solidity'de yan yana
        // yazilan dize sabitleri derleme aninda BIRLESTIRILIR ("ab" "cd"
        // == "abcd"), yani dizenin icerigi degismedi.
        // GuardianAttestation.t.sol::test_python_digesti_sozlesme_digestiyle_ayni
        // bu esitligi her kosuda dogruluyor.
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256(
                    "QAdaptiveRiskAttestation(bytes32 userOpHash,uint256 riskScore,"
                    "uint256 validUntil,address account,uint256 chainId)"
                ),
                userOpHash,
                riskScore,
                validUntil,
                address(this),
                block.chainid
            )
        );
        // EIP-191 kişisel imza ön-eki — Python tarafı `eth_account.sign_message`
        // ile aynı biçimi üretir.
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", structHash));
    }

    /**
     * @notice Sahip, reddedilmiş bir işlemi incelemek üzere açıkça sıraya alır.
     *
     * @dev HATA E3: Bu iş eskiden `validateUserOp` içinde OTOMATİK yapılıyordu
     *      ve her reddediş bir SSTORE demekti. Artık sıraya alma, sahibin
     *      bilinçli bir kararı — doğrulama yolu depolamaya dokunmuyor.
     */
    function stageForReview(bytes32 opHash) external onlyOwnerOrSelf {
        pendingTransactions[opHash] = PendingOp({
            executionTime: block.timestamp,
            isActive:      true
        });
        emit ValidationStagedToQueue(opHash, 0, "MANUAL_STAGE");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Execution Functions & Time-Lock Security
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Executes an arbitrary call on behalf of the account.
     * @dev    CEI: checks isPanicMode → no effects → external call (target).
     *         nonReentrant guards against malicious target callbacks.
     */
    function execute(
        address target,
        uint256 value,
        bytes calldata data
    ) external onlyEntryPoint nonReentrant {
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();
        if (isPanicMode) {
            require(
                safeDestinationWhitelist[target],
                "QAdaptiveAccount: Target not whitelisted for Panic Mode"
            );
        }

        // ── HATA E7: elle gaz ayırma KALDIRILDI ─────────────────────────────
        //
        // Eski satır `gas: gasleft() - 5000` kullanıyordu. `gasleft() < 5000`
        // olduğunda Solidity 0.8'de çıkarma taşması olur ve işlem, asıl
        // sebebi gizleyen anlamsız bir panic(0x11) ile revert eder.
        //
        // Ayrıca ayırmanın kendisi gereksizdi: EIP-150'nin 63/64 kuralı
        // gereği çağrılana gazın tamamı zaten geçmez, çağırana her hâlükârda
        // 1/64'ü kalır. Elle yapılan ayırma bunu tekrarlıyordu.
        require(gasleft() > 10_000, "QAdaptiveAccount: insufficient gas for execution");

        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
    }

    /**
     * @notice Dedicated function for high-value transfers, protected by the Time-Lock.
     *
     * @dev    Time-Lock flow (independent of validateUserOp):
     *           First call  → stages to lockedOperations, emits event, returns early.
     *           Retry call  → checks 2-hour delay, deactivates lock, executes transfer.
     *
     *         The Time-Lock and validateUserOp are completely decoupled:
     *         a successfully validated UserOperation can still be time-locked at
     *         execution time if it meets the HIGH_VALUE_THRESHOLD condition.
     *
     *         CEI here: CHECK (amount threshold) → EFFECT (lockedOperations write) →
     *         INTERACTION (target.call). nonReentrant guards the interaction.
     */
    function transferHighValue(
        address target,
        uint256 amount
    ) external onlyEntryPoint nonReentrant {
        // CHECKS — AI panic mode
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();
        if (isPanicMode) {
            require(
                safeDestinationWhitelist[target],
                "QAdaptiveAccount: Target not whitelisted for Panic Mode"
            );
        }

        // CHECKS & EFFECTS — Time-Lock interception
        if (amount >= HIGH_VALUE_THRESHOLD && !safeDestinationWhitelist[target]) {
            bytes32 opHash = keccak256(abi.encode(target, amount));
            PendingOp storage pending = lockedOperations[opHash];

            if (!pending.isActive) {
                // EFFECT: Stage the transfer, stop execution.
                pending.executionTime = block.timestamp + SECURITY_DELAY;
                pending.isActive      = true;
                emit HighValueTransferLocked(opHash, target, amount, pending.executionTime);
                return;
            } else {
                // CHECKS: Enforce the 2-hour delay on retry.
                require(
                    block.timestamp >= pending.executionTime,
                    "Q-ADAPTIVE: GUVENLIK RISKI! ISLEM 2 SAAT KILITLENDI."
                );
                // EFFECT: Deactivate lock before the external call.
                pending.isActive = false;
            }
        }

        // INTERACTION — Execute transfer only after all state mutations above.
        (bool success, ) = target.call{value: amount}("");
        require(success, "QAdaptiveAccount: transfer failed");
    }

    /**
     * @notice Emergency cancel mechanism for the owner to wipe a malicious or
     *         erroneously staged operation from either lockedOperations or
     *         pendingTransactions.
     *
     * @dev    CEI: CHECKS (isActive) → EFFECTS (deactivate) → no INTERACTION.
     *         This function intentionally has no external call; nonReentrant
     *         is still applied as a policy invariant for all state-mutating functions.
     *
     * @param  opHash  keccak256 of the operation to cancel. Covers both
     *                 lockedOperations keys and pendingTransactions keys
     *                 (userOpHash from the EntryPoint).
     */
    function cancelTransaction(bytes32 opHash) external onlyOwnerOrSelf nonReentrant {
        bool foundInLocked  = lockedOperations[opHash].isActive;
        bool foundInPending = pendingTransactions[opHash].isActive;

        require(
            foundInLocked || foundInPending,
            "QAdaptiveAccount: operation not active or already processed"
        );

        // EFFECTS only — no external call follows.
        if (foundInLocked) {
            lockedOperations[opHash].isActive      = false;
            lockedOperations[opHash].executionTime = 0;
            emit HighValueTransferCancelled(opHash);
        }
        if (foundInPending) {
            pendingTransactions[opHash].isActive      = false;
            pendingTransactions[opHash].executionTime = 0;
            emit ValidationStageCancelled(opHash);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Defensive State Management
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Updates the post-quantum armor tier and public key commitment.
     * @dev    Called by the EntryPoint when the AI triggers a key rotation.
     *         The new quantumPublicKey is the keccak256 root of the new
     *         ML-DSA A-matrix expanded from the new rho-prime seed.
     *         After this call, all future STARK proofs must target the new epoch.
     */
    function updateQuantumArmor(
        string calldata newTier,
        bytes32         newPublicKey
    ) external onlyEntryPoint {
        _applyArmorUpdate(newTier, newPublicKey);
    }

    /**
     * @notice Zırh güncellemesini TEK YÖNLÜ TIRMANMA kuralıyla uygular.
     *
     * @dev HATA E4: Eski `updateQuantumArmor` hiçbir kontrol yapmadan kademeyi
     *      yazıyordu. EntryPoint yoluyla gelen bir çağrı zırhı ML-DSA-87'den
     *      ML-DSA-44'e DÜŞÜREBİLİYORDU — yani saldırgan, savunmayı güçlendirmek
     *      için tasarlanmış fonksiyonu savunmayı zayıflatmak için kullanabilirdi.
     *
     *      Kural artık zincirde de zorlanıyor (zincir dışı `armor::decide` ile
     *      aynı kural):
     *        • kademe yalnızca YÜKSELEBİLİR,
     *        • taban sıranın altına ASLA inilmez,
     *        • düşürmenin tek yolu sahibin `downgradeArmor()` çağrısıdır.
     */
    function _applyArmorUpdate(string memory newTier, bytes32 newPublicKey) internal {
        uint8 newRank = _tierRank(newTier);

        require(
            newRank >= armorBaselineRank,
            "QAdaptiveAccount: tier below armor baseline"
        );
        require(
            newRank >= currentArmorRank,
            "QAdaptiveAccount: armor escalation is one-way"
        );

        currentArmorRank = newRank;
        currentArmorTier = newTier;
        quantumPublicKey = newPublicKey;

        emit QuantumArmorUpdated(newTier, newPublicKey);
    }

    /**
     * @notice Sahip, zırhı bilinçli olarak düşürür.
     * @dev Düşürmenin TEK yolu budur ve taban sıranın altına inemez.
     *      `onlyEntryPoint` değil `onlyOwnerOrSelf` olması kasıtlı: bu bir
     *      yönetim kararıdır, bir UserOperation yan etkisi değil.
     */
    function downgradeArmor(string calldata newTier, bytes32 newPublicKey)
        external
        onlyOwnerOrSelf
    {
        uint8 newRank = _tierRank(newTier);
        require(
            newRank >= armorBaselineRank,
            "QAdaptiveAccount: tier below armor baseline"
        );

        currentArmorRank = newRank;
        currentArmorTier = newTier;
        quantumPublicKey = newPublicKey;

        emit QuantumArmorDowngraded(newTier, newRank);
    }

    /**
     * @notice Zırh taban sırasını yükseltir.
     * @dev Taban yalnızca yükselebilir — aksi hâlde tek yönlü tırmanma
     *      kuralı tabanı düşürerek dolanılabilirdi.
     */
    function raiseArmorBaseline(uint8 newBaseline) external onlyOwnerOrSelf {
        require(newBaseline > armorBaselineRank, "QAdaptiveAccount: baseline is one-way");
        require(newBaseline <= 3, "QAdaptiveAccount: unknown baseline rank");

        uint8 previous    = armorBaselineRank;
        armorBaselineRank = newBaseline;

        // Mevcut zırh yeni tabanın altındaysa tabana çekilir.
        if (currentArmorRank < newBaseline) {
            currentArmorRank = newBaseline;
        }

        emit ArmorBaselineUpdated(previous, newBaseline);
    }

    /**
     * @notice Zırh kademesi adını sıra numarasına çevirir.
     *
     * @dev Adlar, zincir dışı prover'ın ürettikleriyle BİREBİR aynıdır
     *      (`MlDsaSecurityLevel::name()` — bkz. Q-Adaptive-ZK/src/trace.rs).
     *      Bilinmeyen bir ad revert eder; sessizce 0 kabul edilseydi
     *      yazım hatası olan bir kademe zırhı düşürürdü.
     *
     *      Fonksiyon seçicisi kasıtlı olarak değiştirilmedi
     *      (`updateQuantumArmor(string,bytes32)`), çünkü Paymaster tam olarak
     *      bu seçiciyi sponsorluyor.
     */
    function _tierRank(string memory tier) internal pure returns (uint8) {
        bytes32 h = keccak256(bytes(tier));

        if (h == keccak256(bytes("Standard")))                return 0;
        if (h == keccak256(bytes("ML-DSA-44")))               return 1;
        if (h == keccak256(bytes("ML-DSA-65")))               return 2;
        if (h == keccak256(bytes("ML-DSA-87 (Dilithium-5)"))) return 3;

        revert("QAdaptiveAccount: unknown armor tier");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Risk Kaynağı Yönetimi
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Risk skorunun hangi kaynaktan alınacağını belirler.
    function setRiskSource(RiskSource newSource) external onlyOwnerOrSelf {
        RiskSource previous = riskSource;
        riskSource = newSource;
        emit RiskSourceUpdated(previous, newSource);
    }

    /// @notice Guardian attestation'larını imzalamaya yetkili adresi ayarlar.
    ///
    /// @dev SIFIR ADRES KASITLI OLARAK GEÇERLİ: "guardian yok" anlamına gelir
    ///      ve `_verifyAttestation` bunu açıkça ele alır
    ///      (`if (guardianSigner == address(0)) return (0, false)`).
    ///      Guardian imzası kaynağını devre dışı bırakmanın tek yolu budur;
    ///      sıfır kontrolü eklemek o yeteneği ortadan kaldırırdı.
    // slither-disable-next-line missing-zero-check
    function setGuardianSigner(address newSigner) external onlyOwnerOrSelf {
        address previous = guardianSigner;
        guardianSigner = newSigner;
        emit GuardianSignerUpdated(previous, newSigner);
    }

    /**
     * @notice Sahipliği yeni bir adrese devreder.
     *
     * @dev Bu fonksiyon Slither'ın `immutable-states` bulgusu üzerine eklendi.
     *      Slither `owner`'ın hiç yeniden atanmadığını, dolayısıyla
     *      `immutable` yapılabileceğini söylüyordu — teknik olarak doğruydu.
     *
     *      Ama `immutable` yapmak yanlış çözümdü: `owner` bu sözleşmede 11
     *      fonksiyonu kapılıyor ve bir AKILLI HESAP'ta sahip anahtarının
     *      ele geçirilmesi gerçek bir senaryodur. Sahipliği kalıcı olarak
     *      dondurmak, ele geçirilmiş bir anahtardan kurtulma yolunu da
     *      kapatırdı.
     *
     *      Doğru çözüm alanı gerçekten değiştirilebilir kılmaktı. Eksik olan
     *      şey gaz optimizasyonu değil, devir yeteneğiydi.
     */
    function transferOwnership(address newOwner) external onlyOwnerOrSelf {
        require(newOwner != address(0), "QAdaptiveAccount: new owner is zero");
        address previous = owner;
        owner = newOwner;
        emit OwnershipTransferred(previous, newOwner);
    }

    /**
     * @notice AI Core oracle adresini günceller.
     *
     * @dev Aynı gerekçe: oracle sabitlenirse, oracle sözleşmesi
     *      kullanımdan kalktığında ya da ele geçirildiğinde hesap kurtarılamaz
     *      hâle gelirdi. Risk skorunun kaynağı değiştirilebilir olmalı.
     */
    function setAICore(address newAICore) external onlyOwnerOrSelf {
        require(newAICore != address(0), "QAdaptiveAccount: aiCore is zero");
        address previous = address(aiCore);
        aiCore = IAICore(newAICore);
        emit AICoreUpdated(previous, newAICore);
    }

    /**
     * @notice Updates the on-chain rolling risk threshold to mirror the off-chain
     *         SlidingWindowThresholdCalibrator's current τ(t) value.
     *
     * @dev    The AI API layer encodes τ(t) as uint256 = round(τ × 100).
     *         Example: τ = 72.34% → rollingRiskThreshold = 7234.
     *         Valid range enforced: [5500, 9000] matching [TAU_MIN, TAU_MAX].
     *
     * @param  newThreshold  New risk threshold (risk% × 100). Range: [5500, 9000].
     */
    function updateRollingRiskThreshold(uint256 newThreshold) external onlyOwnerOrSelf {
        require(
            newThreshold >= 5500 && newThreshold <= 9000,
            "QAdaptiveAccount: threshold out of valid range [5500, 9000]"
        );
        uint256 old = rollingRiskThreshold;
        rollingRiskThreshold = newThreshold;
        emit RollingRiskThresholdUpdated(old, newThreshold);
    }

    function addSafeDestination(address target) external onlyOwnerOrSelf {
        safeDestinationWhitelist[target] = true;
        emit SafeDestinationAdded(target);
    }

    function removeSafeDestination(address target) external onlyOwnerOrSelf {
        safeDestinationWhitelist[target] = false;
        emit SafeDestinationRemoved(target);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Receive
    // ─────────────────────────────────────────────────────────────────────────

    receive() external payable {}
}
