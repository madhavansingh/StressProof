// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockLendingMarket} from "../src/MockLendingMarket.sol";
import {VaultFixture} from "./helpers/VaultFixture.sol";

/// @notice MockLendingMarket tests. Test IDs refer to implementationplan.md §21.2.
/// Amounts are USD with 8 decimals; the demo uses $10,000 collateral (plan §12.5).
contract MockLendingMarketTest is VaultFixture {
    uint256 internal constant USD = 1e8;
    uint256 internal constant COLLATERAL = 10_000 * USD;

    function _reduceLtv() internal {
        _applyFinalized(HONEST_R);
        _assertControls(false, REDUCED_LTV_BPS);
    }

    function _pause() internal {
        _applyFinalized(PAUSE_THRESHOLD);
        _assertControls(true, DEFAULT_MAX_LTV_BPS);
    }

    function _expectLtvTooHigh(uint256 requested, uint256 maxBps) internal {
        vm.expectRevert(abi.encodeWithSelector(MockLendingMarket.LtvTooHigh.selector, requested, maxBps));
    }

    /// Extra: before any claim, the demo's 70% borrow succeeds.
    function test_borrow_70pctBeforeClaim() public {
        vm.expectEmit(true, false, false, true, address(market));
        emit MockLendingMarket.Borrowed(other, COLLATERAL, 7_000 * USD, 7000);
        vm.prank(other);
        market.borrow(COLLATERAL, 7_000 * USD);
        assertEq(market.debtUsd8(other), 7_000 * USD);
    }

    /// T-M-01: paused borrowing reverts, and the pause is checked before zero collateral.
    function test_borrow_paused() public {
        _pause();
        vm.expectRevert(MockLendingMarket.BorrowPaused.selector);
        market.borrow(COLLATERAL, USD);
        vm.expectRevert(MockLendingMarket.BorrowPaused.selector);
        market.borrow(0, USD);
    }

    /// T-M-02: the demo "Try borrow" after the honest claim is applied.
    function test_borrow_70pctWhenMax50() public {
        _reduceLtv();
        _expectLtvTooHigh(7000, REDUCED_LTV_BPS);
        market.borrow(COLLATERAL, 7_000 * USD);
    }

    /// T-M-03: borrowing exactly at the max succeeds, at both the reduced and default limits.
    function test_borrow_exactMax() public {
        market.borrow(COLLATERAL, 8_000 * USD);
        _reduceLtv();
        market.borrow(COLLATERAL, 5_000 * USD);
        assertEq(market.debtUsd8(address(this)), 13_000 * USD);
    }

    /// T-M-03: LTV rounds up, so one unit above the max is rejected.
    function test_borrow_ceilRounding() public {
        _expectLtvTooHigh(8001, DEFAULT_MAX_LTV_BPS);
        market.borrow(COLLATERAL, 8_000 * USD + 1);
        _reduceLtv();
        _expectLtvTooHigh(5001, REDUCED_LTV_BPS);
        market.borrow(COLLATERAL, 5_000 * USD + 1);
    }

    /// T-M-04
    function test_borrow_zeroCollateral() public {
        vm.expectRevert(MockLendingMarket.ZeroCollateral.selector);
        market.borrow(0, USD);
    }

    /// Extra: a 40% borrow still works after the reduction (controls are bounded, not a blanket pause).
    function test_borrow_40pctAfterReduce() public {
        _reduceLtv();
        vm.prank(other);
        market.borrow(COLLATERAL, 4_000 * USD);
        assertEq(market.debtUsd8(other), 4_000 * USD);
    }

    /// Fuzz: the LTV the market enforces is the exact ceiling of amount / collateral.
    function testFuzz_borrow_ltvIsCeiling(uint256 collateral, uint256 amount) public {
        collateral = bound(collateral, 1, 1e30);
        amount = bound(amount, 0, collateral * 2);
        uint256 ltv = (amount * 10_000 + collateral - 1) / collateral;
        // ceiling property: ltv/10000 >= amount/collateral > (ltv-1)/10000
        assertGe(ltv * collateral, amount * 10_000);
        if (ltv > 0) assertLt((ltv - 1) * collateral, amount * 10_000);

        if (ltv > DEFAULT_MAX_LTV_BPS) {
            _expectLtvTooHigh(ltv, DEFAULT_MAX_LTV_BPS);
            market.borrow(collateral, amount);
        } else {
            market.borrow(collateral, amount);
            assertEq(market.debtUsd8(address(this)), amount);
        }
    }
}
