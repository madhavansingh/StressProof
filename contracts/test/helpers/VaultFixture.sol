// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {DemoVault} from "../../src/DemoVault.sol";
import {MockLendingMarket} from "../../src/MockLendingMarket.sol";
import {RegistryFixture} from "./RegistryFixture.sol";

/// @notice Adds a DemoVault and MockLendingMarket wired to the registry.
/// Thresholds follow implementationplan.md §12.5 using the fixture R:
/// LTV_THRESHOLD = R / 2, PAUSE_THRESHOLD = 2R.
abstract contract VaultFixture is RegistryFixture {
    uint256 internal constant LTV_THRESHOLD = HONEST_R / 2; // 100_000_000_000
    uint256 internal constant PAUSE_THRESHOLD = 2 * HONEST_R; // 400_000_000_002
    uint16 internal constant REDUCED_LTV_BPS = 5000;
    uint16 internal constant DEFAULT_MAX_LTV_BPS = 8000;

    DemoVault internal vault;
    MockLendingMarket internal market;

    function setUp() public virtual override {
        super.setUp();
        vault = new DemoVault(
            registry, MARKET_ID, PAUSE_THRESHOLD, LTV_THRESHOLD, REDUCED_LTV_BPS, DEFAULT_MAX_LTV_BPS
        );
        market = new MockLendingMarket(vault);
    }

    function _assertControls(bool paused, uint16 maxLtvBps) internal view {
        assertEq(vault.borrowPaused(), paused, "borrowPaused");
        assertEq(uint256(vault.maxLtvBps()), uint256(maxLtvBps), "maxLtvBps");
    }

    /// Finalizes a claim of `claimed` and applies it to the vault.
    function _applyFinalized(uint256 claimed) internal returns (uint256 id) {
        id = _finalizedClaim(claimed);
        vault.applyClaim(id);
    }
}
