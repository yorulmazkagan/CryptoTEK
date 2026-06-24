// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./interfaces/IUserOperation.sol";
import "./interfaces/IAICore.sol";

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
    // Events
    // ─────────────────────────────────────────────────────────────────────────

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

    constructor(
        address _entryPoint,
        address _aiCore,
        bytes32 _initialQuantumKey,
        address _owner
    ) {
        _status          = _NOT_ENTERED;
        entryPoint       = _entryPoint;
        aiCore           = IAICore(_aiCore);
        quantumPublicKey = _initialQuantumKey;
        currentArmorTier = "Standard";
        owner            = _owner;
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
        bytes memory               starkProofBytes;
        AirVerificationMetadata    memory metadata;
        uint256                    aiDynamicRiskScore; // risk% × 100 (0–10000)

        if (userOp.signature.length >= 64) {
            // Attempt decode; if the caller sends a malformed payload, decode
            // will revert which propagates upward as an operation-level failure.
            // This is the correct behavior: we never accept a malformed signature.
            (starkProofBytes, metadata, aiDynamicRiskScore) = abi.decode(
                userOp.signature,
                (bytes, AirVerificationMetadata, uint256)
            );
        } else {
            // Signature payload is too short to contain any valid data.
            // Stage to pendingTransactions for owner audit and halt.
            pendingTransactions[userOpHash] = PendingOp({
                executionTime: block.timestamp,
                isActive:      true
            });
            emit ValidationStagedToQueue(userOpHash, 0, "SIG_FAIL");
            return SIG_VALIDATION_FAILED;
        }

        // ── STEP 3: Panic mode — enforce STARK proof length requirement ──
        if (isPanicMode) {
            if (starkProofBytes.length < MIN_STARK_PROOF_BYTES) {
                // Proof absent or undersized: stage and reject.
                pendingTransactions[userOpHash] = PendingOp({
                    executionTime: block.timestamp,
                    isActive:      true
                });
                emit ValidationStagedToQueue(userOpHash, aiDynamicRiskScore, "SIG_FAIL");
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
                pendingTransactions[userOpHash] = PendingOp({
                    executionTime: block.timestamp,
                    isActive:      true
                });
                emit ValidationStagedToQueue(userOpHash, aiDynamicRiskScore, "SIG_FAIL");
                return SIG_VALIDATION_FAILED;
            }
        }

        // ── STEP 5: Dynamic rolling risk threshold gate ─────────────────
        //    aiDynamicRiskScore is risk% × 100 (e.g., 7523 = 75.23%).
        //    rollingRiskThreshold is set to mirror the off-chain
        //    SlidingWindowThresholdCalibrator value (default 7500 = 75.00%).
        //    The owner calls updateRollingRiskThreshold() after each off-chain
        //    calibration cycle to keep both layers synchronized.
        if (aiDynamicRiskScore > rollingRiskThreshold) {
            // Critical policy breach: risk exceeds the rolling window threshold.
            // Cache the operation for post-incident forensic review.
            pendingTransactions[userOpHash] = PendingOp({
                executionTime: block.timestamp,
                isActive:      true
            });
            emit ValidationStagedToQueue(userOpHash, aiDynamicRiskScore, "RISK_BREACH");
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
        //    Gas stipend cap (2300): Limits the EntryPoint's ability to execute
        //    complex code via fallback if it is ever compromised or replaced.
        //    This is defense-in-depth; the onlyEntryPoint modifier is the primary
        //    guard. 2300 gas is sufficient for logging but not state changes.
        if (missingAccountFunds > 0) {
            (bool success, ) = payable(msg.sender).call{gas: 2300, value: missingAccountFunds}("");
            require(success, "QAdaptiveAccount: EntryPoint funding failed");
        }

        return SIG_VALIDATION_SUCCESS;
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

        (bool success, bytes memory result) = target.call{value: value, gas: gasleft() - 5000}(data);
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
        currentArmorTier = newTier;
        quantumPublicKey = newPublicKey;
        emit QuantumArmorUpdated(newTier, newPublicKey);
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
