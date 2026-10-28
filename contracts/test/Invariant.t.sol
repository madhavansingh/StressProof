// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {StressRegistry} from "../src/StressRegistry.sol";

abstract contract Test {
    function assertEq(uint256 a, uint256 b) internal virtual {
        require(a == b, "assertEq uint256 failed");
    }
}

contract InvariantTest is Test {
    StressRegistry registry;

    function setUp() public {
        registry = new StressRegistry(0.01 ether, 120, 300, 0, address(0x123));
    }

    function invariant_BalanceMatchesAccounting() public view {
        assertEq(
            address(registry).balance,
            registry.totalLocked() + registry.totalCredited()
        );
    }
}
