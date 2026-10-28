// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {StressRegistry} from "../src/StressRegistry.sol";
import {IStressRegistry} from "../src/IStressRegistry.sol";
import {RegistryFixture} from "./helpers/RegistryFixture.sol";

/// @notice postClaim, challenge and finalize tests. Test IDs refer to implementationplan.md §21.2.
/// Resolution, expiry, withdrawal and lifecycle tests are in StressRegistryResolution.t.sol.
contract StressRegistryTest is RegistryFixture {
    // ================================================================ postClaim

    /// T-C-01
    function test_postClaim_happyPath() public {
        uint64 expectedDeadline = uint64(START_TS) + CW;
        vm.expectEmit(true, true, true, true, address(registry));
        emit IStressRegistry.ClaimPosted(1, attester, MARKET_ID, INFLATED, EVIDENCE_HASH, URI, expectedDeadline);
        uint256 id = _post();

        assertEq(id, 1);
        assertEq(registry.claimCount(), 1);
        _assertState(id, IStressRegistry.State.Pending);
        IStressRegistry.Claim memory c = registry.claim(id);
        assertEq(c.attester, attester);
        assertEq(c.challengeDeadline, expectedDeadline);
        assertEq(c.marketId, MARKET_ID);
        assertEq(c.evidenceHash, EVIDENCE_HASH);
        assertEq(c.claimedResidualBadDebt, INFLATED);
        assertEq(c.caseFileURI, URI);
        assertEq(c.challenger, address(0));
        assertEq(uint8(c.reason), uint8(IStressRegistry.Reason.NONE));
        assertEq(c.resolutionDeadline, 0);
        assertEq(registry.totalLocked(), BOND);
        assertEq(registry.totalCredited(), 0);
        _assertAccounting();
    }

    /// T-C-02 (fixed edge values)
    function test_postClaim_wrongBond_edgeValues() public {
        uint256[3] memory values = [uint256(0), BOND - 1, BOND + 1];
        for (uint256 i; i < values.length; ++i) {
            vm.prank(attester);
            vm.expectRevert(abi.encodeWithSelector(IStressRegistry.WrongBond.selector, values[i], BOND));
            registry.postClaim{value: values[i]}(MARKET_ID, INFLATED, EVIDENCE_HASH, URI);
        }
        assertEq(registry.claimCount(), 0);
        _assertDrained();
    }

    /// T-C-02 (fuzz)
    function testFuzz_postClaim_wrongBond(uint256 value) public {
        value = bound(value, 0, 1 ether);
        vm.assume(value != BOND);
        vm.prank(attester);
        vm.expectRevert(abi.encodeWithSelector(IStressRegistry.WrongBond.selector, value, BOND));
        registry.postClaim{value: value}(MARKET_ID, INFLATED, EVIDENCE_HASH, URI);
    }

    /// T-C-03
    function test_postClaim_zeroEvidenceHash() public {
        vm.prank(attester);
        vm.expectRevert(IStressRegistry.ZeroEvidenceHash.selector);
        registry.postClaim{value: BOND}(MARKET_ID, INFLATED, bytes32(0), URI);
    }

    /// T-C-03
    function test_postClaim_zeroMarketId() public {
        vm.prank(attester);
        vm.expectRevert(IStressRegistry.ZeroMarketId.selector);
        registry.postClaim{value: BOND}(bytes32(0), INFLATED, EVIDENCE_HASH, URI);
    }

    /// T-C-04: empty and 513-byte URIs revert, 1 and 512 bytes are accepted.
    function test_postClaim_uriLength() public {
        uint256 maxLen = registry.MAX_URI_LENGTH();
        assertEq(maxLen, 512);
        string memory maxUri = _repeat(maxLen);
        string memory tooLong = _repeat(maxLen + 1);

        vm.startPrank(attester);
        vm.expectRevert(IStressRegistry.BadURI.selector);
        registry.postClaim{value: BOND}(MARKET_ID, INFLATED, EVIDENCE_HASH, "");
        vm.expectRevert(IStressRegistry.BadURI.selector);
        registry.postClaim{value: BOND}(MARKET_ID, INFLATED, EVIDENCE_HASH, tooLong);
        uint256 a = registry.postClaim{value: BOND}(MARKET_ID, INFLATED, EVIDENCE_HASH, maxUri);
        uint256 b = registry.postClaim{value: BOND}(MARKET_ID, INFLATED, EVIDENCE_HASH, "x");
        vm.stopPrank();

        assertEq(registry.claim(a).caseFileURI, maxUri);
        assertEq(registry.claim(b).caseFileURI, "x");
        assertEq(registry.claimCount(), 2);
    }

    /// T-C-05
    function test_postClaim_twoClaimsIndependent() public {
        uint256 first = _post(HONEST_R);
        vm.warp(START_TS + 30);
        uint256 second = _postAs(other, OTHER_MARKET_ID, INFLATED);
        _challengeWrong(second);

        assertEq(first, 1);
        assertEq(second, 2);
        IStressRegistry.Claim memory a = registry.claim(first);
        IStressRegistry.Claim memory b = registry.claim(second);
        assertEq(a.attester, attester);
        assertEq(b.attester, other);
        assertEq(a.challengeDeadline, START_TS + CW);
        assertEq(b.challengeDeadline, START_TS + 30 + CW);
        assertEq(a.marketId, MARKET_ID);
        assertEq(b.marketId, OTHER_MARKET_ID);
        assertEq(a.claimedResidualBadDebt, HONEST_R);
        assertEq(a.challenger, address(0));
        _assertState(first, IStressRegistry.State.Pending);
        _assertState(second, IStressRegistry.State.Challenged);
        assertEq(registry.totalLocked(), 3 * BOND);
        _assertAccounting();
    }

    /// Extra (T-C-06 slot): the constructor rejects zero parameters, with empty revert data (audit A-2).
    function test_constructor_rejectsZeroParams() public {
        vm.expectRevert(bytes(""));
        this.deployRegistry(0, CW, RW, resolver);
        vm.expectRevert(bytes(""));
        this.deployRegistry(BOND, 0, RW, resolver);
        vm.expectRevert(bytes(""));
        this.deployRegistry(BOND, CW, 0, resolver);
        vm.expectRevert(bytes(""));
        this.deployRegistry(BOND, CW, RW, address(0));
        assertEq(address(this.deployRegistry(BOND, CW, RW, resolver)).code.length > 0, true);
    }

    /// External on purpose: in forge 1.8 a reverting `new` directly inside a test ends the test
    /// early, so later cases would silently not run. Through a call, expectRevert works normally.
    function deployRegistry(uint256 bond, uint64 cw, uint64 rw, address resolver_)
        external
        returns (StressRegistry)
    {
        return new StressRegistry(bond, cw, rw, 0, resolver_);
    }

    /// Extra (T-C-07 slot): constructor values are exposed unchanged.
    function test_constructor_storesParams() public view {
        assertEq(registry.BOND(), BOND);
        assertEq(registry.CHALLENGE_WINDOW(), CW);
        assertEq(registry.RESOLUTION_WINDOW(), RW);
        assertEq(registry.TOLERANCE_BPS(), 0);
        assertEq(registry.resolver(), resolver);
        assertEq(registry.claimCount(), 0);
    }

    /// Extra (T-C-08 slot, audit A-10): a claim of zero is accepted.
    function test_postClaim_zeroClaimAllowed() public {
        uint256 id = _post(0);
        _assertState(id, IStressRegistry.State.Pending);
        assertEq(registry.claim(id).claimedResidualBadDebt, 0);
    }

    /// Extra (T-C-09 slot): ids start at 1, and unknown ids read as None.
    function test_status_unknownIdIsNone() public {
        _post();
        _assertState(0, IStressRegistry.State.None);
        _assertState(2, IStressRegistry.State.None);
        assertEq(registry.claim(0).attester, address(0));
    }

    // ================================================================ challenge

    /// T-C-10
    function test_challenge_wrongResult_happyPath() public {
        uint256 id = _post();
        vm.warp(START_TS + 10);
        uint64 expectedDeadline = uint64(START_TS + 10) + RW;
        vm.expectEmit(true, true, false, true, address(registry));
        emit IStressRegistry.ClaimChallenged(
            id, watcher, IStressRegistry.Reason.WRONG_RESULT, HONEST_R, REPORT_URI, REPORT_HASH, expectedDeadline
        );
        _challengeWrong(id);

        _assertState(id, IStressRegistry.State.Challenged);
        IStressRegistry.Claim memory c = registry.claim(id);
        assertEq(c.challenger, watcher);
        assertEq(uint8(c.reason), uint8(IStressRegistry.Reason.WRONG_RESULT));
        assertEq(c.counterResidualBadDebt, HONEST_R);
        assertEq(c.replayReportURI, REPORT_URI);
        assertEq(c.replayReportHash, REPORT_HASH);
        assertEq(c.resolutionDeadline, expectedDeadline);
        assertEq(c.challengeDeadline, START_TS + CW);
        assertEq(registry.totalLocked(), 2 * BOND);
        _assertAccounting();
    }

    /// T-C-11 (fixed edge values)
    function test_challenge_wrongBond_edgeValues() public {
        uint256 id = _post();
        uint256[3] memory values = [uint256(0), BOND - 1, BOND + 1];
        for (uint256 i; i < values.length; ++i) {
            _expectChallengeRevert(
                watcher,
                id,
                IStressRegistry.Reason.WRONG_RESULT,
                HONEST_R,
                REPORT_URI,
                REPORT_HASH,
                values[i],
                abi.encodeWithSelector(IStressRegistry.WrongBond.selector, values[i], BOND)
            );
        }
        _assertState(id, IStressRegistry.State.Pending);
    }

    /// T-C-11 (fuzz)
    function testFuzz_challenge_wrongBond(uint256 value) public {
        value = bound(value, 0, 1 ether);
        vm.assume(value != BOND);
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            REPORT_URI,
            REPORT_HASH,
            value,
            abi.encodeWithSelector(IStressRegistry.WrongBond.selector, value, BOND)
        );
    }

    /// T-C-12
    function test_challenge_atDeadlineMinus1() public {
        uint256 id = _post();
        vm.warp(registry.claim(id).challengeDeadline - 1);
        _challengeWrong(id);
        _assertState(id, IStressRegistry.State.Challenged);
    }

    /// T-C-13: at the deadline and one second after.
    function test_challenge_atDeadline() public {
        uint256 id = _post();
        uint256 deadline = registry.claim(id).challengeDeadline;
        uint256[2] memory times = [deadline, deadline + 1];
        for (uint256 i; i < times.length; ++i) {
            vm.warp(times[i]);
            _expectChallengeRevert(
                watcher,
                id,
                IStressRegistry.Reason.WRONG_RESULT,
                HONEST_R,
                REPORT_URI,
                REPORT_HASH,
                BOND,
                _err(IStressRegistry.ChallengeWindowClosed.selector)
            );
        }
        _assertState(id, IStressRegistry.State.Pending);
    }

    /// T-C-14
    function test_challenge_byAttester() public {
        uint256 id = _post();
        _expectChallengeRevert(
            attester,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            REPORT_URI,
            REPORT_HASH,
            BOND,
            _err(IStressRegistry.AttesterCannotChallenge.selector)
        );
    }

    /// T-C-15
    function test_challenge_second() public {
        uint256 id = _post();
        _challengeWrong(id);
        _expectChallengeRevert(
            other,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            REPORT_URI,
            REPORT_HASH,
            BOND,
            _invalidState(IStressRegistry.State.Challenged)
        );
        assertEq(registry.claim(id).challenger, watcher);
    }

    /// T-C-16
    function test_challenge_counterEqualsClaim() public {
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            INFLATED,
            REPORT_URI,
            REPORT_HASH,
            BOND,
            _err(IStressRegistry.CounterEqualsClaim.selector)
        );
    }

    /// T-C-17
    function test_challenge_evidenceInvalid_zeroesCounter() public {
        uint256 id = _post();
        vm.expectEmit(true, true, false, true, address(registry));
        emit IStressRegistry.ClaimChallenged(
            id, watcher, IStressRegistry.Reason.EVIDENCE_INVALID, 0, REPORT_URI, REPORT_HASH, uint64(START_TS) + RW
        );
        _challengeAs(watcher, id, IStressRegistry.Reason.EVIDENCE_INVALID, 123);

        IStressRegistry.Claim memory c = registry.claim(id);
        assertEq(c.counterResidualBadDebt, 0);
        assertEq(uint8(c.reason), uint8(IStressRegistry.Reason.EVIDENCE_INVALID));
    }

    /// Extra: EVIDENCE_INVALID ignores the counter, so counter == claimed is allowed.
    function test_challenge_evidenceInvalid_counterEqualToClaimAllowed() public {
        uint256 id = _post();
        _challengeAs(watcher, id, IStressRegistry.Reason.EVIDENCE_INVALID, INFLATED);
        _assertState(id, IStressRegistry.State.Challenged);
        assertEq(registry.claim(id).counterResidualBadDebt, 0);
    }

    /// T-C-18
    function test_challenge_zeroReportHash() public {
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            REPORT_URI,
            bytes32(0),
            BOND,
            _err(IStressRegistry.ZeroReportHash.selector)
        );
    }

    /// T-C-18
    function test_challenge_reasonNone() public {
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.NONE,
            HONEST_R,
            REPORT_URI,
            REPORT_HASH,
            BOND,
            _err(IStressRegistry.BadReason.selector)
        );
    }

    /// T-C-18
    function test_challenge_emptyReportURI() public {
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            "",
            REPORT_HASH,
            BOND,
            _err(IStressRegistry.BadURI.selector)
        );
    }

    /// T-C-18
    function test_challenge_longReportURI() public {
        uint256 id = _post();
        _expectChallengeRevert(
            watcher,
            id,
            IStressRegistry.Reason.WRONG_RESULT,
            HONEST_R,
            _repeat(registry.MAX_URI_LENGTH() + 1),
            REPORT_HASH,
            BOND,
            _err(IStressRegistry.BadURI.selector)
        );
    }

    /// T-C-19: id 0 and an id that was never posted.
    function test_challenge_nonexistent() public {
        _post();
        uint256[2] memory ids = [uint256(0), 99];
        for (uint256 i; i < ids.length; ++i) {
            _expectChallengeRevert(
                watcher,
                ids[i],
                IStressRegistry.Reason.WRONG_RESULT,
                HONEST_R,
                REPORT_URI,
                REPORT_HASH,
                BOND,
                _invalidState(IStressRegistry.State.None)
            );
        }
    }

    /// Fuzz: at any time exactly one of challenge and finalize is valid (spec §8.3 strict </>=).
    function testFuzz_challengeXorFinalize(uint256 dt) public {
        dt = bound(dt, 0, 2 * uint256(CW));
        uint256 id = _post();
        vm.warp(START_TS + dt);
        uint256 snapshot = vm.snapshotState();

        vm.prank(watcher);
        (bool challenged,) = address(registry).call{value: BOND}(
            abi.encodeWithSelector(
                IStressRegistry.challenge.selector,
                id,
                IStressRegistry.Reason.WRONG_RESULT,
                HONEST_R,
                REPORT_URI,
                REPORT_HASH
            )
        );
        vm.revertToState(snapshot);
        (bool finalized,) = address(registry).call(abi.encodeWithSelector(IStressRegistry.finalize.selector, id));

        assertTrue(challenged != finalized, "exactly one transition is valid");
        assertEq(challenged, dt < CW);
    }

    // ================================================================= finalize

    /// T-C-20
    function test_finalize_atDeadline() public {
        uint256 id = _post(HONEST_R);
        _warpToChallengeDeadline(id);
        vm.expectEmit(true, false, false, true, address(registry));
        emit IStressRegistry.ClaimFinalized(id);
        vm.prank(other);
        registry.finalize(id);

        _assertState(id, IStressRegistry.State.Finalized);
        assertEq(registry.credits(attester), BOND);
        assertEq(registry.credits(other), 0);
        assertEq(registry.totalLocked(), 0);
        assertEq(registry.totalCredited(), BOND);
        _assertAccounting();
    }

    /// T-C-21
    function test_finalize_beforeDeadline() public {
        uint256 id = _post(HONEST_R);
        vm.warp(registry.claim(id).challengeDeadline - 1);
        vm.expectRevert(IStressRegistry.ChallengeWindowOpen.selector);
        registry.finalize(id);
        _assertState(id, IStressRegistry.State.Pending);
    }

    /// Extra: finalize only applies to Pending claims.
    function test_finalize_wrongStates() public {
        uint256 challenged = _challengedClaim(INFLATED);
        _warpToChallengeDeadline(challenged);
        vm.expectRevert(_invalidState(IStressRegistry.State.Challenged));
        registry.finalize(challenged);
        vm.expectRevert(_invalidState(IStressRegistry.State.None));
        registry.finalize(99);
    }
}
