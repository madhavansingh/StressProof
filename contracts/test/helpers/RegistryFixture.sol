// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {StressRegistry} from "../../src/StressRegistry.sol";
import {IStressRegistry} from "../../src/IStressRegistry.sol";

/// @notice Shared setup, actions and assertions for the registry, vault and market tests.
/// Constants mirror the MVP values in implementationplan.md §6.3 and the Appendix A fixture.
abstract contract RegistryFixture is Test {
    uint256 internal constant BOND = 0.01 ether;
    uint64 internal constant CW = 120;
    uint64 internal constant RW = 300;
    uint256 internal constant START_TS = 1_700_000_000;

    bytes32 internal constant MARKET_ID = keccak256("aave-v3-eth-weth-stable");
    bytes32 internal constant OTHER_MARKET_ID = keccak256("some-other-market");
    bytes32 internal constant EVIDENCE_HASH = keccak256("case-file-bytes");
    bytes32 internal constant REPORT_HASH = keccak256("replay-report-bytes");

    /// Honest residual bad debt R from the Appendix A fixture, and the malicious 3R claim.
    uint256 internal constant HONEST_R = 200_000_000_001;
    uint256 internal constant INFLATED = 3 * HONEST_R;

    string internal constant URI = "http://127.0.0.1:8000/case-files/0xabc";
    string internal constant REPORT_URI = "http://127.0.0.1:8000/replay-reports/0xdef";

    address internal resolver = makeAddr("resolver");
    address internal attester = makeAddr("attester");
    address internal watcher = makeAddr("watcher");
    address internal other = makeAddr("other");

    StressRegistry internal registry;

    function setUp() public virtual {
        vm.warp(START_TS);
        registry = new StressRegistry(BOND, CW, RW, 0, resolver);
        vm.deal(attester, 1 ether);
        vm.deal(watcher, 1 ether);
        vm.deal(other, 1 ether);
        vm.deal(resolver, 1 ether);
    }

    // ---------------------------------------------------------------- actions

    function _postAs(address who, bytes32 marketId, uint256 claimed) internal returns (uint256 id) {
        vm.prank(who);
        id = registry.postClaim{value: BOND}(marketId, claimed, EVIDENCE_HASH, URI);
    }

    function _post(uint256 claimed) internal returns (uint256) {
        return _postAs(attester, MARKET_ID, claimed);
    }

    function _post() internal returns (uint256) {
        return _post(INFLATED);
    }

    function _challengeAs(address who, uint256 id, IStressRegistry.Reason reason, uint256 counter) internal {
        vm.prank(who);
        registry.challenge{value: BOND}(id, reason, counter, REPORT_URI, REPORT_HASH);
    }

    /// Watcher challenges with the honest value, as in the malicious-attester demo.
    function _challengeWrong(uint256 id) internal {
        _challengeAs(watcher, id, IStressRegistry.Reason.WRONG_RESULT, HONEST_R);
    }

    /// Expects `challenge` from `who` to revert with exactly `expectedError`.
    function _expectChallengeRevert(
        address who,
        uint256 id,
        IStressRegistry.Reason reason,
        uint256 counter,
        string memory reportUri,
        bytes32 reportHash,
        uint256 value,
        bytes memory expectedError
    ) internal {
        vm.prank(who);
        vm.expectRevert(expectedError);
        registry.challenge{value: value}(id, reason, counter, reportUri, reportHash);
    }

    function _resolve(uint256 id, bool upheld) internal {
        vm.prank(resolver);
        registry.resolve(id, upheld);
    }

    function _withdrawAs(address who) internal {
        vm.prank(who);
        registry.withdraw();
    }

    function _warpToChallengeDeadline(uint256 id) internal {
        vm.warp(registry.claim(id).challengeDeadline);
    }

    function _warpToResolutionDeadline(uint256 id) internal {
        vm.warp(registry.claim(id).resolutionDeadline);
    }

    // ------------------------------------------------- claims in a given state

    function _challengedClaim(uint256 claimed) internal returns (uint256 id) {
        id = _post(claimed);
        _challengeAs(watcher, id, IStressRegistry.Reason.WRONG_RESULT, claimed + 1);
    }

    function _finalizedClaim(bytes32 marketId, uint256 claimed) internal returns (uint256 id) {
        id = _postAs(attester, marketId, claimed);
        _warpToChallengeDeadline(id);
        registry.finalize(id);
    }

    function _finalizedClaim(uint256 claimed) internal returns (uint256) {
        return _finalizedClaim(MARKET_ID, claimed);
    }

    /// Finalized through an unsuccessful challenge, i.e. resolve(false).
    function _finalizedByResolver(uint256 claimed) internal returns (uint256 id) {
        id = _challengedClaim(claimed);
        _resolve(id, false);
    }

    function _rejectedClaim(uint256 claimed) internal returns (uint256 id) {
        id = _challengedClaim(claimed);
        _resolve(id, true);
    }

    function _expiredClaim(uint256 claimed) internal returns (uint256 id) {
        id = _challengedClaim(claimed);
        _warpToResolutionDeadline(id);
        registry.expireUnresolved(id);
    }

    // ------------------------------------------------------------- assertions

    function _assertState(uint256 id, IStressRegistry.State expected) internal view {
        assertEq(uint8(registry.status(id)), uint8(expected), "claim state");
    }

    function _assertAccounting() internal view {
        assertEq(
            address(registry).balance,
            registry.totalLocked() + registry.totalCredited(),
            "balance == totalLocked + totalCredited"
        );
    }

    function _assertDrained() internal view {
        assertEq(address(registry).balance, 0, "registry balance");
        assertEq(registry.totalLocked(), 0, "totalLocked");
        assertEq(registry.totalCredited(), 0, "totalCredited");
    }

    function _invalidState(IStressRegistry.State s) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(IStressRegistry.InvalidState.selector, s);
    }

    function _err(bytes4 selector) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(selector);
    }

    function _repeat(uint256 n) internal pure returns (string memory) {
        bytes memory b = new bytes(n);
        for (uint256 i; i < n; ++i) {
            b[i] = "a";
        }
        return string(b);
    }
}
