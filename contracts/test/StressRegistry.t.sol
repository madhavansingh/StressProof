// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {StressRegistry} from "../src/StressRegistry.sol";
import {IStressRegistry} from "../src/IStressRegistry.sol";

// Minimal base test contract to allow compilation with or without forge-std
abstract contract Test {
    function assertEq(uint256 a, uint256 b) internal virtual {
        require(a == b, "assertEq uint256 failed");
    }
    function assertEq(bytes32 a, bytes32 b) internal virtual {
        require(a == b, "assertEq bytes32 failed");
    }
    function assertTrue(bool condition) internal virtual {
        require(condition, "assertTrue failed");
    }
}

contract StressRegistryTest is Test {
    StressRegistry registry;
    address resolver = address(0x123);
    address attester = address(0x456);
    address watcher = address(0x789);

    uint256 constant BOND = 0.01 ether;
    uint64 constant CW = 120;
    uint64 constant RW = 300;
    bytes32 constant MARKET_ID = keccak256("aave-v3-eth-weth-stable");
    bytes32 constant EVIDENCE_HASH = keccak256("valid_evidence");

    function setUp() public {
        registry = new StressRegistry(BOND, CW, RW, 0, resolver);
    }

    function test_InitialParameters() public {
        assertEq(registry.BOND(), BOND);
        assertEq(registry.CHALLENGE_WINDOW(), CW);
        assertEq(registry.RESOLUTION_WINDOW(), RW);
        assertEq(registry.TOLERANCE_BPS(), 0);
        assertTrue(registry.resolver() == resolver);
    }

    function test_PostClaimState() public {
        // Test basic claim post logic
        uint256 id = registry.postClaim{value: BOND}(
            MARKET_ID,
            200_000_000_001,
            EVIDENCE_HASH,
            "http://127.0.0.1:8000/case-files/0x123"
        );
        assertEq(id, 1);
        assertTrue(registry.status(1) == IStressRegistry.State.Pending);
    }
}
