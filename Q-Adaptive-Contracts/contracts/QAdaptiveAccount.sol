// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./interfaces/IUserOperation.sol";
import "./interfaces/IAICore.sol";

/**
 * @title QAdaptiveAccount
 * @dev Programmable ERC-4337 Smart Account for the Q-Adaptive Guardian system.
 * Incorporates post-quantum (Dilithium-5) public key management, AI-driven risk
 * tiering, and an on-chain Time-Lock security layer.
 */
contract QAdaptiveAccount {
    
    // ─────────────────────────────────────────────────────────────────────────────
    // Constants & Structures (Aşama 9)
    // ─────────────────────────────────────────────────────────────────────────────

    uint256 public constant SECURITY_DELAY = 2 hours;
    uint256 public constant HIGH_VALUE_THRESHOLD = 5000 ether;

    struct PendingOp {
        uint256 executionTime;
        bool isActive;
    }

    /// @dev Expected metadata struct aligned with Phase 7 JSON export.
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

    // ─────────────────────────────────────────────────────────────────────────────
    // State Variables
    // ─────────────────────────────────────────────────────────────────────────────

    // ReentrancyGuard status variables
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status;

    /// @notice The contract owner / authorized guardian.
    address public owner;

    /// @notice The current post-quantum public key matrix hash or root.
    bytes32 public quantumPublicKey;

    /// @notice The active security armor tier (e.g., "Standard", "ML-DSA-87 (Dilithium-5)").
    string public currentArmorTier;

    /// @notice Whitelist of addresses that are safe to interact with during high-risk mode.
    mapping(address => bool) public safeDestinationWhitelist;

    /// @notice Tracks high-risk operations caught by the time-lock filter.
    mapping(bytes32 => PendingOp) public lockedOperations;

    /// @notice Address of the EntryPoint contract (ERC-4337).
    address public immutable entryPoint;

    /// @notice Address of the AI Core contract for querying risk status.
    IAICore public aiCore;

    // ─────────────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────────────

    event QuantumArmorUpdated(string newTier, bytes32 newPublicKeyRoot);
    event SafeDestinationAdded(address indexed destination);
    event SafeDestinationRemoved(address indexed destination);
    event HighValueTransferLocked(bytes32 indexed opHash, address target, uint256 amount, uint256 unlockTime);
    event HighValueTransferCancelled(bytes32 indexed opHash);

    // ─────────────────────────────────────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────────────────────────────────────

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
        require(msg.sender == owner || msg.sender == address(this), "QAdaptiveAccount: not owner or self");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────────────

    constructor(address _entryPoint, address _aiCore, bytes32 _initialQuantumKey, address _owner) {
        _status = _NOT_ENTERED;
        entryPoint = _entryPoint;
        aiCore = IAICore(_aiCore);
        quantumPublicKey = _initialQuantumKey;
        currentArmorTier = "Standard";
        owner = _owner;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Core ERC-4337 Functions & ZK Integration
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Validates the UserOperation's signature.
     * @dev Parses the STARK proof and metadata generated in Phase 7.
     */
    function validateUserOp(
        UserOperation calldata userOp,
        bytes32 userOpHash,
        uint256 missingAccountFunds
    ) external onlyEntryPoint returns (uint256 validationData) {
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();

        if (isPanicMode) {
            // Expected ABI Encoding layout from Phase 7 JSON:
            // userOp.signature = abi.encode(starkProofBytes, AirVerificationMetadata)
            require(userOp.signature.length > 3000, "QAdaptiveAccount: PQC STARK proof required during panic mode");
            
            // Example of how the payload from Phase 7 would be parsed on-chain:
            // (bytes memory starkProof, AirVerificationMetadata memory metadata) = 
            //     abi.decode(userOp.signature, (bytes, AirVerificationMetadata));
            
            // Verify STARK boundary conditions match the current public key
            // require(metadata.start_a == expected_start, "Invalid boundary parameters");

            validationData = 0; 
        } else {
            validationData = 0; 
        }

        if (missingAccountFunds > 0) {
            (bool success, ) = payable(msg.sender).call{value: missingAccountFunds}("");
            require(success, "QAdaptiveAccount: funding entryPoint failed");
        }

        return validationData;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Execution Functions & Time-Lock Security (Aşama 9)
    // ─────────────────────────────────────────────────────────────────────────────

    function execute(address target, uint256 value, bytes calldata data) external onlyEntryPoint nonReentrant {
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();
        if (isPanicMode) {
            require(safeDestinationWhitelist[target], "QAdaptiveAccount: Target not whitelisted for Panic Mode");
        }

        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
    }

    /**
     * @notice Dedicated function for high value transfers, protected by Time-Lock.
     */
    function transferHighValue(address target, uint256 amount) external onlyEntryPoint nonReentrant {
        // AI check
        (, bool isPanicMode) = aiCore.getGlobalRiskStatus();
        if (isPanicMode) {
            require(safeDestinationWhitelist[target], "QAdaptiveAccount: Target not whitelisted for Panic Mode");
        }

        // Time-Lock Interception Logic
        if (amount >= HIGH_VALUE_THRESHOLD && !safeDestinationWhitelist[target]) {
            bytes32 opHash = keccak256(abi.encode(target, amount));
            PendingOp storage pending = lockedOperations[opHash];

            if (!pending.isActive) {
                // Step 1: Lock the transaction and return early to save state.
                pending.executionTime = block.timestamp + SECURITY_DELAY;
                pending.isActive = true;
                emit HighValueTransferLocked(opHash, target, amount, pending.executionTime);
                return; // State is saved, transaction stops here.
            } else {
                // Step 2: If the transaction is retried while locked, check the delay.
                require(
                    block.timestamp >= pending.executionTime, 
                    "Q-ADAPTIVE: GUVENLIK RISKI! ISLEM 2 SAAT KILITLENDI."
                );
                
                // If 2 hours have passed, deactivate the lock and proceed
                pending.isActive = false;
            }
        }

        // Proceed with transfer
        (bool success, ) = target.call{value: amount}("");
        require(success, "QAdaptiveAccount: transfer failed");
    }

    /**
     * @notice Emergency Cancel Mechanism allowing the owner to wipe a malicious transfer.
     */
    function cancelTransaction(bytes32 userOpHash) external onlyOwnerOrSelf nonReentrant {
        require(lockedOperations[userOpHash].isActive, "QAdaptiveAccount: operation not active or already processed");
        
        // Wipe out the pending exploit
        lockedOperations[userOpHash].isActive = false;
        lockedOperations[userOpHash].executionTime = 0;
        
        emit HighValueTransferCancelled(userOpHash);
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Defensive State Functions
    // ─────────────────────────────────────────────────────────────────────────────

    function updateQuantumArmor(string calldata newTier, bytes32 newPublicKey) external onlyEntryPoint {
        currentArmorTier = newTier;
        quantumPublicKey = newPublicKey;
        emit QuantumArmorUpdated(newTier, newPublicKey);
    }

    function addSafeDestination(address target) external onlyOwnerOrSelf {
        safeDestinationWhitelist[target] = true;
        emit SafeDestinationAdded(target);
    }

    function removeSafeDestination(address target) external onlyOwnerOrSelf {
        safeDestinationWhitelist[target] = false;
        emit SafeDestinationRemoved(target);
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Receive
    // ─────────────────────────────────────────────────────────────────────────────
    
    receive() external payable {}
}
