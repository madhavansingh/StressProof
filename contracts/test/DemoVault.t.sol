// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {DemoVault} from "../src/DemoVault.sol";
import {VaultFixture} from "./helpers/VaultFixture.sol";

/// @notice DemoVault tests. Test IDs refer to implementationplan.md §21.2; rules follow plan §12.4.
contract DemoVaultTest is VaultFixture {
    /// Extra: initial controls and wiring.
    function test_initialState() public view {
        _assertControls(false, DEFAULT_MAX_LTV_BPS);
        assertEq(vault.lastAppliedClaimId(), 0);
        assertEq(address(vault.registry()), address(registry));
        assertEq(vault.MARKET_ID(), MARKET_ID);
        assertEq(vault.owner(), address(this));
        assertEq(vault.PAUSE_THRESHOLD(), PAUSE_THRESHOLD);
        assertEq(vault.LTV_THRESHOLD(), LTV_THRESHOLD);
    }

    /// T-V-01: Pending, Challenged, Rejected, Expired and unknown claims cannot be applied.
    function test_apply_notFinalized_eachState() public {
        uint256 pending = _post(PAUSE_THRESHOLD);
        uint256 challenged = _challengedClaim(PAUSE_THRESHOLD);
        uint256 rejected = _rejectedClaim(PAUSE_THRESHOLD);
        uint256 expired = _expiredClaim(PAUSE_THRESHOLD);
        uint256[5] memory ids = [pending, challenged, rejected, expired, uint256(99)];

        for (uint256 i; i < ids.length; ++i) {
            vm.prank(other);
            vm.expectRevert(DemoVault.NotFinalized.selector);
            vault.applyClaim(ids[i]);
        }
        _assertControls(false, DEFAULT_MAX_LTV_BPS);
    }

    /// T-V-02
    function test_apply_wrongMarket() public {
        uint256 id = _finalizedClaim(OTHER_MARKET_ID, PAUSE_THRESHOLD);
        vm.expectRevert(DemoVault.WrongMarket.selector);
        vault.applyClaim(id);
        assertFalse(vault.applied(id));
    }

    /// T-V-03: a claim exactly at PAUSE_THRESHOLD pauses borrowing.
    function test_apply_atPauseThreshold() public {
        uint256 id = _finalizedClaim(PAUSE_THRESHOLD);
        vm.expectEmit(true, false, false, true, address(vault));
        emit DemoVault.ClaimApplied(id, PAUSE_THRESHOLD, true, DEFAULT_MAX_LTV_BPS);
        vm.prank(other); // anyone may apply
        vault.applyClaim(id);

        _assertControls(true, DEFAULT_MAX_LTV_BPS);
        assertTrue(vault.applied(id));
        assertEq(vault.lastAppliedClaimId(), id);
    }

    /// Extra: the malicious 3R claim would have paused borrowing had it finalized (plan §12.5).
    function test_apply_inflatedClaimWouldPause() public {
        _applyFinalized(INFLATED);
        _assertControls(true, DEFAULT_MAX_LTV_BPS);
    }

    /// T-V-04: LTV_THRESHOLD <= value < PAUSE_THRESHOLD reduces max LTV, including the honest R.
    function test_apply_ltvBand() public {
        uint256[3] memory values = [LTV_THRESHOLD, HONEST_R, PAUSE_THRESHOLD - 1];
        for (uint256 i; i < values.length; ++i) {
            vault.resetControls();
            uint256 id = _finalizedClaim(values[i]);
            vm.expectEmit(true, false, false, true, address(vault));
            emit DemoVault.ClaimApplied(id, values[i], false, REDUCED_LTV_BPS);
            vault.applyClaim(id);
            _assertControls(false, REDUCED_LTV_BPS);
        }
    }

    /// T-V-05: below LTV_THRESHOLD reverts and leaves no trace.
    function test_apply_belowLtv() public {
        uint256[2] memory values = [LTV_THRESHOLD - 1, uint256(0)];
        for (uint256 i; i < values.length; ++i) {
            uint256 id = _finalizedClaim(values[i]);
            vm.expectRevert(DemoVault.BelowThreshold.selector);
            vault.applyClaim(id);
            assertFalse(vault.applied(id));
        }
        assertEq(vault.lastAppliedClaimId(), 0);
        _assertControls(false, DEFAULT_MAX_LTV_BPS);
    }

    /// T-V-06
    function test_apply_twice() public {
        uint256 id = _applyFinalized(HONEST_R);
        vm.expectRevert(DemoVault.AlreadyApplied.selector);
        vault.applyClaim(id);
    }

    /// T-V-07: only the owner may reset.
    function test_reset_nonOwner() public {
        _applyFinalized(PAUSE_THRESHOLD);
        vm.prank(other);
        vm.expectRevert(DemoVault.NotOwner.selector);
        vault.resetControls();
        _assertControls(true, DEFAULT_MAX_LTV_BPS);
    }

    /// T-V-07: reset restores defaults and clears lastAppliedClaimId (audit A-4), but keeps
    /// `applied`, so a claim cannot be replayed.
    function test_reset_owner() public {
        uint256 pauseId = _applyFinalized(PAUSE_THRESHOLD);
        uint256 ltvId = _applyFinalized(HONEST_R);
        vm.expectEmit(false, false, false, true, address(vault));
        emit DemoVault.ControlsReset();
        vault.resetControls();

        _assertControls(false, DEFAULT_MAX_LTV_BPS);
        assertTrue(vault.applied(pauseId));
        assertTrue(vault.applied(ltvId));
        assertEq(vault.lastAppliedClaimId(), 0, "A-4: cleared by reset");
        vm.expectRevert(DemoVault.AlreadyApplied.selector);
        vault.applyClaim(pauseId);

        // A fresh claim after the reset becomes the triggering claim again.
        uint256 freshId = _applyFinalized(HONEST_R);
        assertEq(vault.lastAppliedClaimId(), freshId);
        _assertControls(false, REDUCED_LTV_BPS);
    }

    /// T-V-08: applying a claim never loosens controls.
    function test_apply_neverLoosens() public {
        _applyFinalized(PAUSE_THRESHOLD);
        _applyFinalized(HONEST_R);
        _assertControls(true, REDUCED_LTV_BPS); // still paused after an LTV-band claim

        _applyFinalized(LTV_THRESHOLD); // maxLtv already at the reduced value: unchanged
        _assertControls(true, REDUCED_LTV_BPS);
    }

    /// Extra: a claim finalized through resolve(false) is applied like any other.
    function test_apply_claimFinalizedByResolver() public {
        uint256 id = _finalizedByResolver(HONEST_R);
        vault.applyClaim(id);
        _assertControls(false, REDUCED_LTV_BPS);
    }

    /// Extra: constructor parameter checks, each with empty revert data (bare require).
    function test_constructor_rejectsBadParams() public {
        vm.expectRevert(bytes("")); // LTV threshold zero
        this.deployVault(PAUSE_THRESHOLD, 0, REDUCED_LTV_BPS, DEFAULT_MAX_LTV_BPS);
        vm.expectRevert(bytes("")); // pause below LTV threshold
        this.deployVault(LTV_THRESHOLD - 1, LTV_THRESHOLD, REDUCED_LTV_BPS, DEFAULT_MAX_LTV_BPS);
        vm.expectRevert(bytes("")); // reduced not below default
        this.deployVault(PAUSE_THRESHOLD, LTV_THRESHOLD, DEFAULT_MAX_LTV_BPS, DEFAULT_MAX_LTV_BPS);
        vm.expectRevert(bytes("")); // default above 100%
        this.deployVault(PAUSE_THRESHOLD, LTV_THRESHOLD, REDUCED_LTV_BPS, 10_001);
        // Boundary: pause == LTV threshold and default == 100% are allowed.
        this.deployVault(LTV_THRESHOLD, LTV_THRESHOLD, REDUCED_LTV_BPS, 10_000);
    }

    /// External on purpose: in forge 1.8 a reverting `new` directly inside a test ends the test
    /// early, so later cases would silently not run. Through a call, expectRevert works normally.
    function deployVault(uint256 pause, uint256 ltv, uint16 reduced, uint16 defaultMax)
        external
        returns (DemoVault)
    {
        return new DemoVault(registry, MARKET_ID, pause, ltv, reduced, defaultMax);
    }

    /// Fuzz: the threshold rule of spec §8.7 for any finalized claim value.
    function testFuzz_apply_thresholdRule(uint256 claimed) public {
        claimed = bound(claimed, 0, 10 * PAUSE_THRESHOLD);
        uint256 id = _finalizedClaim(claimed);
        if (claimed < LTV_THRESHOLD) {
            vm.expectRevert(DemoVault.BelowThreshold.selector);
            vault.applyClaim(id);
            _assertControls(false, DEFAULT_MAX_LTV_BPS);
        } else {
            vault.applyClaim(id);
            bool paused = claimed >= PAUSE_THRESHOLD;
            _assertControls(paused, paused ? DEFAULT_MAX_LTV_BPS : REDUCED_LTV_BPS);
        }
    }
}
