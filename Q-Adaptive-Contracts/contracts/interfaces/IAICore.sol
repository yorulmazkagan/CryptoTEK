// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title IAICore
 * @dev Interface for the AI Guardian module that dictates the global risk status.
 * This is used to dynamically adjust security thresholds on-chain.
 */
interface IAICore {
    /**
     * @dev Retrieves the current systemic risk status determined by the AI Guardian.
     * @return riskScore The current anomaly risk score (scaled by 1e2, e.g., 9852 = 98.52%)
     * @return isPanicMode Boolean flag indicating if the system is under lockdown/panic mode.
     */
    function getGlobalRiskStatus() external view returns (uint256 riskScore, bool isPanicMode);
}
