// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {DemoVault} from "../src/DemoVault.sol";
import {StressRegistry} from "../src/StressRegistry.sol";
import {IStressRegistry} from "../src/IStressRegistry.sol";

abstract contract Test {
    function assertEq(uint256 a, uint256 b) internal virtual {
        require(a == b, "assertEq uint256 failed");
    }
    function assertTrue(bool condition) internal virtual {
        require(condition, "assertTrue failed");
    }
}

contract DemoVaultTest is Test {
    StressRegistry registry;
    DemoVault vault;
    bytes32 constant MARKET_ID = keccak256("aave-v3-eth-weth-stable");

    function setUp() public {
        registry = new StressRegistry(0.01 ether, 120, 300, 0, address(0x123));
        vault = new DemoVault(registry, MARKET_ID, 400_000_000_002, 100_000_000_000, 5000, 8000);
    }

    function test_InitialVaultState() public {
        assertTrue(!vault.borrowPaused());
        assertEq(vault.maxLtvBps(), 8000);
    }
}
