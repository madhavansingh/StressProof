// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {StressRegistry} from "../src/StressRegistry.sol";
import {DemoVault} from "../src/DemoVault.sol";
import {MockLendingMarket} from "../src/MockLendingMarket.sol";

// Minimal Script interface for standalone compilation without forge-std dependency
abstract contract Script {
    function vm_startBroadcast() internal virtual {}
    function vm_stopBroadcast() internal virtual {}
}

contract Deploy is Script {
    function run() external {
        uint256 bond = 0.01 ether;
        uint64 challengeWindow = 120;
        uint64 resolutionWindow = 300;
        uint16 toleranceBps = 0;
        address resolver = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;

        bytes32 marketId = keccak256(bytes("aave-v3-eth-weth-stable"));

        // Deploy contracts
        StressRegistry registry = new StressRegistry(
            bond,
            challengeWindow,
            resolutionWindow,
            toleranceBps,
            resolver
        );

        DemoVault vault = new DemoVault(
            registry,
            marketId,
            400_000_000_002, // PAUSE_THRESHOLD (2 * R)
            100_000_000_000, // LTV_THRESHOLD (R / 2)
            5000,            // REDUCED_LTV_BPS
            8000             // DEFAULT_MAX_LTV_BPS
        );

        MockLendingMarket market = new MockLendingMarket(vault);
    }
}
