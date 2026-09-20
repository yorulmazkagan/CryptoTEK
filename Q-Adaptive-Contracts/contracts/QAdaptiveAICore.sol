// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./interfaces/IAICore.sol";

/**
 * @title  QAdaptiveAICore
 * @notice On-chain risk oracle. The off-chain AI Guardian pushes a risk score
 *         and a panic flag here; `QAdaptiveAccount` reads them during
 *         `validateUserOp`.
 *
 * @dev    Why this contract exists
 *         ────────────────────────
 *         Until now the only `IAICore` implementation in this repository was
 *         `test/mocks/Mocks.sol::MockAICore`, which has **no access control**:
 *         any address can call `setStatus` and flip the whole wallet into
 *         panic mode. That is acceptable inside a test harness and completely
 *         unacceptable on a live network. Deploying the mock to a testnet
 *         would have shipped that hole.
 *
 *         Staleness — the decision that actually matters
 *         ──────────────────────────────────────────────
 *         An oracle that stops updating is more dangerous than one that was
 *         never deployed, because the wallet keeps trusting its last value.
 *         Two failure directions:
 *
 *           • fail-open  (report risk = 0 when stale) → an attacker who can
 *             silence the updater downgrades the armor to its weakest tier.
 *             Unacceptable: it rewards the attack.
 *
 *           • fail-closed (report panic = true when stale) → every operation
 *             then requires a >= 3000-byte STARK proof. If the whole off-chain
 *             stack is down — which is exactly why the oracle went stale —
 *             nobody can produce that proof and the wallet is bricked.
 *
 *         So this contract does neither. When the data is older than
 *         `maxAge`, it reports **maximum risk with panic OFF**:
 *
 *             (MAX_RISK_SCORE, false)
 *
 *         Maximum risk drives the armor to its strongest tier (ML-DSA-87),
 *         which is the defensive choice and costs the user nothing on-chain.
 *         Leaving panic off keeps the wallet usable. Defensive without
 *         locking the owner out.
 *
 *         `isStale()` is public so the dashboard can show the degraded state
 *         instead of silently presenting a stale number as live — the same
 *         rule the rest of this project follows.
 */
contract QAdaptiveAICore is IAICore {
    // ─────────────────────────────────────────────────────────────────────
    // Constants
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Risk scores are fixed-point ×100, so 100.00% is 10_000.
    uint256 public constant MAX_RISK_SCORE = 10_000;

    /// @notice Lower bound for `maxAge`. Prevents an owner from setting a
    ///         window so short that the oracle is permanently "stale".
    uint256 public constant MIN_MAX_AGE = 1 minutes;

    /// @notice Upper bound for `maxAge`. Prevents disabling staleness
    ///         protection by setting an effectively infinite window.
    uint256 public constant MAX_MAX_AGE = 7 days;

    // ─────────────────────────────────────────────────────────────────────
    // State
    // ─────────────────────────────────────────────────────────────────────

    address public owner;

    /// @notice The only address allowed to push risk updates. This is the
    ///         off-chain guardian's hot key; it is deliberately separate from
    ///         `owner` so a compromised updater cannot change ownership.
    address public updater;

    uint256 public riskScore;
    bool    public panicMode;

    /// @notice Timestamp of the last successful `updateRiskStatus` call.
    uint256 public lastUpdate;

    /// @notice Data older than this is treated as stale.
    uint256 public maxAge;

    // ─────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────

    event RiskStatusUpdated(
        uint256 indexed riskScore,
        bool    indexed panicMode,
        uint256         timestamp
    );
    event UpdaterChanged(address indexed previousUpdater, address indexed newUpdater);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event MaxAgeChanged(uint256 previousMaxAge, uint256 newMaxAge);

    // ─────────────────────────────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "QAdaptiveAICore: caller is not owner");
        _;
    }

    modifier onlyUpdater() {
        require(msg.sender == updater, "QAdaptiveAICore: caller is not updater");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @param _owner   Address that can rotate the updater and tune `maxAge`.
     * @param _updater Address the off-chain guardian signs with.
     * @param _maxAge  Staleness window in seconds.
     */
    constructor(address _owner, address _updater, uint256 _maxAge) {
        require(_owner != address(0), "QAdaptiveAICore: owner is zero");
        require(_updater != address(0), "QAdaptiveAICore: updater is zero");
        require(
            _maxAge >= MIN_MAX_AGE && _maxAge <= MAX_MAX_AGE,
            "QAdaptiveAICore: maxAge out of range"
        );

        owner   = _owner;
        updater = _updater;
        maxAge  = _maxAge;

        // `lastUpdate` is deliberately left at 0, which makes the oracle stale
        // from block one. A freshly deployed oracle has not measured anything
        // yet; reporting risk = 0 until the first push would be a lie in the
        // most dangerous direction.

        emit OwnershipTransferred(address(0), _owner);
        emit UpdaterChanged(address(0), _updater);
        emit MaxAgeChanged(0, _maxAge);
    }

    // ─────────────────────────────────────────────────────────────────────
    // IAICore
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Current risk status as seen by consuming contracts.
     * @return _riskScore   Fixed-point ×100 risk, or `MAX_RISK_SCORE` if stale.
     * @return _isPanicMode Panic flag, forced to `false` while stale.
     */
    function getGlobalRiskStatus()
        external
        view
        returns (uint256 _riskScore, bool _isPanicMode)
    {
        if (_isStale()) {
            // Strongest armor, but no lock-out. See the contract-level note.
            return (MAX_RISK_SCORE, false);
        }
        return (riskScore, panicMode);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Updates
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Push a fresh risk reading. Called by the off-chain guardian.
     * @param _riskScore   Fixed-point ×100, must be <= `MAX_RISK_SCORE`.
     * @param _panicMode   Whether the guardian wants panic mode enforced.
     */
    function updateRiskStatus(uint256 _riskScore, bool _panicMode)
        external
        onlyUpdater
    {
        require(_riskScore <= MAX_RISK_SCORE, "QAdaptiveAICore: risk out of range");

        riskScore  = _riskScore;
        panicMode  = _panicMode;
        lastUpdate = block.timestamp;

        emit RiskStatusUpdated(_riskScore, _panicMode, block.timestamp);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Views
    // ─────────────────────────────────────────────────────────────────────

    /// @notice True when the stored reading is older than `maxAge`.
    function isStale() external view returns (bool) {
        return _isStale();
    }

    /// @notice Seconds since the last push. `type(uint256).max` before the
    ///         first one, so callers cannot mistake "never updated" for "just
    ///         updated at timestamp 0".
    function age() external view returns (uint256) {
        // slither-disable-next-line incorrect-equality
        if (lastUpdate == 0) {
            return type(uint256).max;
        }
        return block.timestamp - lastUpdate;
    }

    /**
     * @dev Slither `incorrect-equality` — bilinçli ve güvenli.
     *
     *      Dedektör, `block.timestamp` gibi oynatılabilir ya da atlanabilir
     *      değerlerle KATI EŞİTLİK kurulmasına karşı uyarır. Buradaki
     *      karşılaştırma bir zaman damgası karşılaştırması değil, bir
     *      **ilklendirme nöbetçisi**: `lastUpdate` yalnızca hiç
     *      `updateRiskStatus` çağrılmamışsa 0 kalır. Canlı bir zincirde
     *      `block.timestamp` asla 0 olmadığı için bu durum başka türlü
     *      oluşamaz; yani "eşitliği kaçırma" riski yok.
     *
     *      Dal neden gerekli: canlı zincirde teknik olarak gereksizdir —
     *      `block.timestamp - 0` zaten her `maxAge`'den (azami 7 gün)
     *      büyüktür. Ama zincirin ilk saniyelerinde ve testlerde öyle
     *      değildir: `vm.warp(1)` ile `1 > 3600` yanlış çıkar ve hiç
     *      güncellenmemiş bir oracle TAZE görünürdü. Bu yüzden nöbetçi
     *      kontrolü duruyor; `test_hic_guncellenmemis_oracle_BAYATTIR`
     *      tam olarak bunu sabitliyor.
     *
     *      Dedektörün tamamı kapatılmadı — yalnızca bu iki satır.
     *
     *      Yönerge yerleşimi: `slither-disable-next-line` bir sonraki KAYNAK
     *      SATIRINI susturur ve Slither bulguyu alt maddede `#207`, yani
     *      `if` satırında bildiriyor — fonksiyon bildiriminde değil. Bu ayrım
     *      koşu #13'te bir kez öğrenildi (bkz. SLITHER_TRIYAJI.md).
     */
    function _isStale() internal view returns (bool) {
        // slither-disable-next-line incorrect-equality
        if (lastUpdate == 0) {
            return true;
        }
        return block.timestamp - lastUpdate > maxAge;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Administration
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Rotate the guardian hot key. Zero is rejected: an oracle with
    ///         no updater can never leave the stale state.
    function setUpdater(address newUpdater) external onlyOwner {
        require(newUpdater != address(0), "QAdaptiveAICore: updater is zero");
        emit UpdaterChanged(updater, newUpdater);
        updater = newUpdater;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "QAdaptiveAICore: newOwner is zero");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setMaxAge(uint256 newMaxAge) external onlyOwner {
        require(
            newMaxAge >= MIN_MAX_AGE && newMaxAge <= MAX_MAX_AGE,
            "QAdaptiveAICore: maxAge out of range"
        );
        emit MaxAgeChanged(maxAge, newMaxAge);
        maxAge = newMaxAge;
    }
}
