// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./interfaces/IUserOperation.sol";

/**
 * @title QAdaptivePaymaster
 * @dev ERC-4337 Security Sponsor vault. It sponsors (pays gas for) critical
 * defensive operations, specifically `updateQuantumArmor`, to ensure the user
 * is never blocked from upgrading their quantum defense due to a lack of gas.
 */
contract QAdaptivePaymaster {

    // ─────────────────────────────────────────────────────────────────────────────
    // State Variables
    // ─────────────────────────────────────────────────────────────────────────────

    // ReentrancyGuard status variables
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status;

    /// @notice Address of the EntryPoint contract.
    address public immutable entryPoint;

    /// @notice The contract owner (corporate vault manager).
    address public owner;

    // ─────────────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────────────

    event DefensiveOperationSponsored(address indexed user, uint256 gasCostSponsored);
    event PaymasterFunded(uint256 amount);

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
        require(msg.sender == entryPoint, "QAdaptivePaymaster: caller must be EntryPoint");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "QAdaptivePaymaster: caller must be owner");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @param _entryPoint The trusted ERC-4337 EntryPoint address.
     */
    constructor(address _entryPoint) {
        _status = _NOT_ENTERED;
        entryPoint = _entryPoint;
        owner = msg.sender;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Core ERC-4337 Functions
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Validates if the Paymaster is willing to pay for this UserOperation.
     * @param userOp The UserOperation structure.
     * @param userOpHash The hash of the UserOperation.
     * @param maxCost The maximum cost of this transaction.
     * @return context Data context passed to postOp.
     * @return validationData 0 for valid, 1 for invalid.
     */
    function validatePaymasterUserOp(
        UserOperation calldata userOp,
        bytes32 userOpHash,
        uint256 maxCost
    ) external onlyEntryPoint returns (bytes memory context, uint256 validationData) {
        // We ensure there's enough data to check the function selector (first 4 bytes).
        require(userOp.callData.length >= 4, "QAdaptivePaymaster: Invalid callData");

        // Extract the 4-byte function selector from callData
        bytes4 selector;
        bytes calldata callData = userOp.callData;
        assembly {
            selector := calldataload(callData.offset)
        }

        // The exact selector for `updateQuantumArmor(string,bytes32)`
        // Expected value: bytes4(keccak256("updateQuantumArmor(string,bytes32)"))
        // Using a generalized check for any defensive selector if we had multiple,
        // but for now, we hardcode the target defensive function:
        bytes4 updateQuantumArmorSelector = bytes4(keccak256("updateQuantumArmor(string,bytes32)"));

        if (selector == updateQuantumArmorSelector) {
            // SPONSORED: We return 0 indicating success and willingness to pay.
            emit DefensiveOperationSponsored(userOp.sender, maxCost);
            return ("", 0);
        }

        // NOT SPONSORED: We reject operations that are not part of the security rotation.
        return ("", 1); 
    }

    /**
     * @notice Optional post-operation hook called by the EntryPoint.
     */
    function postOp(
        PostOpMode mode,
        bytes calldata context,
        uint256 actualGasCost
    ) external onlyEntryPoint {
        // Logic for tracking exact gas spent can be implemented here.
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Admin Functions
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Allows the owner to fund this paymaster directly via EntryPoint.
     */
    function depositToEntryPoint() external payable onlyOwner nonReentrant {
        // In a real implementation, this would call IEntryPoint(entryPoint).depositTo{value: msg.value}(address(this));
        emit PaymasterFunded(msg.value);
    }

    /**
     * @notice Enums required by standard Paymaster interfaces.
     */
    enum PostOpMode { opSucceeded, opReverted, postOpReverted }

    // ─────────────────────────────────────────────────────────────────────────────
    // Receive
    // ─────────────────────────────────────────────────────────────────────────────

    receive() external payable {}
}
