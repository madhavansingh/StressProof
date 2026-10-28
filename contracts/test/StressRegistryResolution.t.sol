// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Vm} from "forge-std/Vm.sol";
import {IStressRegistry} from "../src/IStressRegistry.sol";
import {RegistryFixture} from "./helpers/RegistryFixture.sol";
import {ReentrantWithdrawer} from "./helpers/ReentrantWithdrawer.sol";
import {RejectingReceiver} from "./helpers/RejectingReceiver.sol";

/// @notice resolve, expireUnresolved, withdraw and full-lifecycle payout tests.
/// Test IDs refer to implementationplan.md §21.2; payouts follow spec §8.4.
contract StressRegistryResolutionTest is RegistryFixture {
    // ================================================================== resolve

    /// T-C-22: only the resolver may resolve, and that check comes before the state check.
    function test_resolve_notResolver() public {
        uint256 challenged = _challengedClaim(INFLATED);
        uint256 pending = _post(HONEST_R);
        address[3] memory callers = [attester, watcher, other];
        for (uint256 i; i < callers.length; ++i) {
            vm.prank(callers[i]);
            vm.expectRevert(IStressRegistry.NotResolver.selector);
            registry.resolve(challenged, true);
        }
        vm.prank(other);
        vm.expectRevert(IStressRegistry.NotResolver.selector);
        registry.resolve(pending, true);
        _assertState(challenged, IStressRegistry.State.Challenged);
    }

    /// T-C-23
    function test_resolve_onPending() public {
        uint256 id = _post();
        vm.prank(resolver);
        vm.expectRevert(_invalidState(IStressRegistry.State.Pending));
        registry.resolve(id, true);
    }

    /// T-C-24: unsuccessful challenge, at the last valid second.
    function test_resolve_false_atDeadlineMinus1() public {
        uint256 id = _challengedClaim(HONEST_R);
        vm.warp(registry.claim(id).resolutionDeadline - 1);

        vm.expectEmit(true, true, false, true, address(registry));
        emit IStressRegistry.ClaimResolved(id, false, attester, 2 * BOND);
        vm.expectEmit(true, false, false, true, address(registry));
        emit IStressRegistry.ClaimFinalized(id);
        _resolve(id, false);

        _assertState(id, IStressRegistry.State.Finalized);
        assertEq(registry.credits(attester), 2 * BOND);
        assertEq(registry.credits(watcher), 0);
        assertEq(registry.totalLocked(), 0);
        _assertAccounting();
    }

    /// Extra: upheld challenge credits the challenger and emits no ClaimFinalized.
    function test_resolve_true_happyPath() public {
        uint256 id = _post(INFLATED);
        _challengeWrong(id);
        vm.recordLogs();
        _resolve(id, true);

        Vm.Log[] memory logs = vm.getRecordedLogs();
        assertEq(logs.length, 1, "only ClaimResolved");
        assertEq(logs[0].topics[0], IStressRegistry.ClaimResolved.selector);
        assertEq(logs[0].topics[2], bytes32(uint256(uint160(watcher))), "winner is challenger");
        _assertState(id, IStressRegistry.State.Rejected);
        assertEq(registry.credits(watcher), 2 * BOND);
        assertEq(registry.credits(attester), 0);
        _assertAccounting();
    }

    /// T-C-25: no resolution at or after the deadline, either way.
    function test_resolve_atDeadline() public {
        uint256 id = _challengedClaim(INFLATED);
        _warpToResolutionDeadline(id);
        bool[2] memory outcomes = [true, false];
        for (uint256 i; i < outcomes.length; ++i) {
            vm.prank(resolver);
            vm.expectRevert(IStressRegistry.ResolutionWindowClosed.selector);
            registry.resolve(id, outcomes[i]);
        }
        _assertState(id, IStressRegistry.State.Challenged);
    }

    /// T-C-28: a resolver that posted the claim cannot resolve it; the expiry path still works.
    function test_resolverIsAttester_cannotResolve_canExpire() public {
        uint256 id = _postAs(resolver, MARKET_ID, INFLATED);
        _challengeWrong(id);
        vm.prank(resolver);
        vm.expectRevert(IStressRegistry.ResolverIsParty.selector);
        registry.resolve(id, true);

        _warpToResolutionDeadline(id);
        registry.expireUnresolved(id);
        _assertState(id, IStressRegistry.State.Expired);
        assertEq(registry.credits(resolver), BOND);
        assertEq(registry.credits(watcher), BOND);
    }

    /// Extra: a resolver that challenged the claim cannot resolve it either.
    function test_resolverIsChallenger_cannotResolve() public {
        uint256 id = _post(INFLATED);
        _challengeAs(resolver, id, IStressRegistry.Reason.WRONG_RESULT, HONEST_R);
        vm.prank(resolver);
        vm.expectRevert(IStressRegistry.ResolverIsParty.selector);
        registry.resolve(id, false);
    }

    // =================================================================== expire

    /// T-C-26
    function test_expire_atDeadline() public {
        uint256 id = _challengedClaim(INFLATED);
        _warpToResolutionDeadline(id);
        vm.expectEmit(true, false, false, true, address(registry));
        emit IStressRegistry.ClaimExpired(id);
        vm.prank(other);
        registry.expireUnresolved(id);

        _assertState(id, IStressRegistry.State.Expired);
        assertEq(registry.credits(attester), BOND);
        assertEq(registry.credits(watcher), BOND);
        assertEq(registry.totalLocked(), 0);
        _assertAccounting();
    }

    /// T-C-27
    function test_expire_beforeDeadline() public {
        uint256 id = _challengedClaim(INFLATED);
        vm.warp(registry.claim(id).resolutionDeadline - 1);
        vm.expectRevert(IStressRegistry.ResolutionWindowOpen.selector);
        registry.expireUnresolved(id);

        uint256 pending = _post(HONEST_R);
        vm.warp(block.timestamp + 10_000);
        vm.expectRevert(_invalidState(IStressRegistry.State.Pending));
        registry.expireUnresolved(pending);
    }

    /// Fuzz: after a challenge, exactly one of resolve and expire is valid at any time.
    function testFuzz_resolveXorExpire(uint256 dt, bool upheld) public {
        dt = bound(dt, 0, 2 * uint256(RW));
        uint256 id = _challengedClaim(INFLATED);
        uint256 challengedAt = block.timestamp;
        vm.warp(challengedAt + dt);
        uint256 snapshot = vm.snapshotState();

        vm.prank(resolver);
        (bool resolved,) =
            address(registry).call(abi.encodeWithSelector(IStressRegistry.resolve.selector, id, upheld));
        vm.revertToState(snapshot);
        (bool expired,) =
            address(registry).call(abi.encodeWithSelector(IStressRegistry.expireUnresolved.selector, id));

        assertTrue(resolved != expired, "exactly one transition is valid");
        assertEq(resolved, dt < RW);
    }

    /// Extra: no transition can leave Finalized, Rejected or Expired.
    function test_terminalStatesImmutable() public {
        uint256[3] memory ids = [_finalizedClaim(HONEST_R), _rejectedClaim(INFLATED), _expiredClaim(INFLATED)];
        IStressRegistry.State[3] memory states =
            [IStressRegistry.State.Finalized, IStressRegistry.State.Rejected, IStressRegistry.State.Expired];
        vm.warp(block.timestamp + 10_000);

        for (uint256 i; i < ids.length; ++i) {
            bytes memory err = _invalidState(states[i]);
            _expectChallengeRevert(
                other, ids[i], IStressRegistry.Reason.WRONG_RESULT, 1, REPORT_URI, REPORT_HASH, BOND, err
            );
            vm.expectRevert(err);
            registry.finalize(ids[i]);
            vm.prank(resolver);
            vm.expectRevert(err);
            registry.resolve(ids[i], true);
            vm.expectRevert(err);
            registry.expireUnresolved(ids[i]);
            _assertState(ids[i], states[i]);
        }
    }

    // ================================================================= withdraw

    /// T-C-29
    function test_withdraw_zero() public {
        vm.prank(other);
        vm.expectRevert(IStressRegistry.NothingToWithdraw.selector);
        registry.withdraw();
    }

    /// Extra: a normal withdrawal pays the full credit once and emits Withdrawn.
    function test_withdraw_happyPath() public {
        uint256 id = _finalizedClaim(HONEST_R);
        uint256 before = attester.balance;
        vm.expectEmit(true, false, false, true, address(registry));
        emit IStressRegistry.Withdrawn(attester, BOND);
        _withdrawAs(attester);

        assertEq(attester.balance, before + BOND);
        assertEq(registry.credits(attester), 0);
        _assertState(id, IStressRegistry.State.Finalized);
        vm.prank(attester);
        vm.expectRevert(IStressRegistry.NothingToWithdraw.selector);
        registry.withdraw();
    }

    /// T-C-30 (a): a reentrant receiver that lets the inner revert bubble fails the whole payout.
    function test_withdraw_reentrantCallRevertsWholeWithdrawal() public {
        ReentrantWithdrawer attacker = _attackerWithCredit(false);
        vm.expectRevert(IStressRegistry.TransferFailed.selector);
        attacker.withdraw();

        assertEq(registry.credits(address(attacker)), BOND, "credit kept");
        assertEq(address(attacker).balance, 0);
        assertEq(attacker.reentrancyAttempts(), 0, "rolled back");
        _assertAccounting();
    }

    /// T-C-30 (b): a reentrant receiver that swallows the inner revert gets its credit once only,
    /// and cannot touch other people's locked bonds.
    function test_withdraw_reentryGetsNothingExtra() public {
        _post(HONEST_R); // someone else's bond stays locked in the registry
        ReentrantWithdrawer attacker = _attackerWithCredit(true);
        attacker.withdraw();

        assertEq(address(attacker).balance, BOND, "paid exactly once");
        assertEq(registry.credits(address(attacker)), 0);
        assertEq(attacker.reentrancyAttempts(), 1);
        assertFalse(attacker.reentrySucceeded(), "second entry reverted");
        assertEq(address(registry).balance, BOND, "other bond untouched");
        _assertAccounting();
    }

    /// T-C-31: if the payout transfer fails, the whole call reverts and the credit is restored.
    function test_withdraw_rejectingReceiverKeepsCredit() public {
        RejectingReceiver receiver = new RejectingReceiver(registry);
        uint256 id = receiver.postClaim{value: BOND}(MARKET_ID, HONEST_R, EVIDENCE_HASH, URI);
        _warpToChallengeDeadline(id);
        registry.finalize(id);
        uint256 creditedBefore = registry.totalCredited();

        vm.expectRevert(IStressRegistry.TransferFailed.selector);
        receiver.withdraw();

        assertEq(registry.credits(address(receiver)), BOND);
        assertEq(registry.totalCredited(), creditedBefore);
        assertEq(address(registry).balance, BOND);
        _assertAccounting();
    }

    /// Audit A-5: force-sent ETH breaks only the strict balance equality; nobody is short-changed.
    function test_forcedEther_onlyBreaksStrictEquality() public {
        uint256 id = _post(HONEST_R);
        vm.deal(address(registry), address(registry).balance + 1); // like selfdestruct or a block reward
        assertGt(address(registry).balance, registry.totalLocked() + registry.totalCredited());

        _warpToChallengeDeadline(id);
        registry.finalize(id);
        _withdrawAs(attester);
        assertEq(registry.totalLocked() + registry.totalCredited(), 0);
        assertEq(address(registry).balance, 1, "only the forced wei remains");
    }

    // =========================================================== T-C-32 lifecycles

    /// Honest claim, no challenge: attester gets its bond back.
    function test_lifecycle_unchallenged() public {
        uint256 a0 = attester.balance;
        uint256 id = _post(HONEST_R);
        _warpToChallengeDeadline(id);
        registry.finalize(id);
        _withdrawAs(attester);

        assertEq(attester.balance, a0);
        _assertDrained();
    }

    /// Honest claim, unsuccessful challenge: attester +BOND, challenger -BOND.
    function test_lifecycle_failedChallenge() public {
        uint256 a0 = attester.balance;
        uint256 w0 = watcher.balance;
        uint256 id = _post(HONEST_R);
        _challengeAs(watcher, id, IStressRegistry.Reason.WRONG_RESULT, HONEST_R + 1);
        _resolve(id, false);
        _withdrawAs(attester);
        _expectNothingToWithdraw(watcher);

        assertEq(attester.balance, a0 + BOND);
        assertEq(watcher.balance, w0 - BOND);
        _assertDrained();
    }

    /// Incorrect claim, successful challenge: attester -BOND, challenger +BOND.
    function test_lifecycle_upheldChallenge() public {
        uint256 a0 = attester.balance;
        uint256 w0 = watcher.balance;
        uint256 id = _post(INFLATED);
        _challengeWrong(id);
        _resolve(id, true);
        _withdrawAs(watcher);
        _expectNothingToWithdraw(attester);

        assertEq(attester.balance, a0 - BOND);
        assertEq(watcher.balance, w0 + BOND);
        _assertDrained();
    }

    /// Challenged, resolver does not act in time: both bonds refunded.
    function test_lifecycle_expired() public {
        uint256 a0 = attester.balance;
        uint256 w0 = watcher.balance;
        uint256 id = _challengedClaim(INFLATED);
        _warpToResolutionDeadline(id);
        registry.expireUnresolved(id);
        _withdrawAs(attester);
        _withdrawAs(watcher);

        assertEq(attester.balance, a0);
        assertEq(watcher.balance, w0);
        _assertDrained();
    }

    // ================================================================== helpers

    function _attackerWithCredit(bool catchReentry) internal returns (ReentrantWithdrawer attacker) {
        attacker = new ReentrantWithdrawer(registry, catchReentry);
        uint256 id = attacker.postClaim{value: BOND}(MARKET_ID, HONEST_R, EVIDENCE_HASH, URI);
        _warpToChallengeDeadline(id);
        registry.finalize(id);
        assertEq(registry.credits(address(attacker)), BOND);
    }

    function _expectNothingToWithdraw(address who) internal {
        vm.prank(who);
        vm.expectRevert(IStressRegistry.NothingToWithdraw.selector);
        registry.withdraw();
    }
}
