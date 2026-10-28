// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockLendingMarket} from "../src/MockLendingMarket.sol";
import {DemoVault} from "../src/DemoVault.sol";
import {StressRegistry} from "../src/StressRegistry.sol";

abstract contract Test {
    function assertTrue(bool condition) internal virtual {
        require(condition, "assertTrue failed");
    }
}

contract MockLendingMarketTest is Test {
    StressRegistry registry;
    DemoVault vault;
    MockLendingMarket market;

    function setUp() public {
        registry = new StressRegistry(0.01 ether, 120, 300, 0, address(0x123));
        vault = new DemoVault(registry, keccak256("test"), 400, 100, 5000, 8000);
        market = new MockLendingMarket(vault);
    }

    function test_InitialBorrowPermitted() public {
        // Collateral $1000, borrow $700 -> LTV 70% <= maxLtvBps 80%
        market.borrow(1000, 700);
        assertTrue(market.debtUsd8(address(this)) == 700);
    }
}
