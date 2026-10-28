// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {StressRegistry} from "../src/StressRegistry.sol";
import {RegistryHandler} from "./handlers/RegistryHandler.sol";

/// @notice T-INV-1: random sequences of every registry call and time warps keep the
/// accounting, payout and state-machine properties (implementationplan.md §12.3, §21.2).
contract InvariantTest is Test {
    uint256 internal constant BOND = 0.01 ether;

    StressRegistry internal registry;
    RegistryHandler internal handler;

    function setUp() public {
        vm.warp(1_700_000_000);
        address resolver = makeAddr("resolver");
        registry = new StressRegistry(BOND, 120, 300, 0, resolver);
        handler = new RegistryHandler(registry, resolver);

        bytes4[] memory selectors = new bytes4[](7);
        selectors[0] = RegistryHandler.postClaim.selector;
        selectors[1] = RegistryHandler.challenge.selector;
        selectors[2] = RegistryHandler.finalize.selector;
        selectors[3] = RegistryHandler.resolve.selector;
        selectors[4] = RegistryHandler.expireUnresolved.selector;
        selectors[5] = RegistryHandler.withdraw.selector;
        selectors[6] = RegistryHandler.warp.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
        targetContract(address(handler));
    }

    // ============================================================== invariants

    function invariant_balanceEqualsAccounting() public view {
        assertEq(address(registry).balance, registry.totalLocked() + registry.totalCredited());
    }

    /// Audit A-5: the property that still holds even if ETH is force-sent to the registry.
    function invariant_balanceCoversAccounting() public view {
        assertGe(address(registry).balance, registry.totalLocked() + registry.totalCredited());
    }

    function invariant_lockedMatchesOpenClaims() public view {
        assertEq(registry.totalLocked(), handler.expectedLocked());
    }

    function invariant_terminalStatesNeverChange() public view {
        assertFalse(handler.terminalChanged());
    }

    function invariant_payoutsMatchSpec() public view {
        assertFalse(handler.payoutMismatch(), "credit differs from spec 8.4");
        assertFalse(handler.unexpectedFailure(), "valid call reverted");
        assertFalse(handler.unauthorizedSuccess(), "non-resolver resolved");
    }

    function invariant_noOverWithdrawal() public view {
        assertFalse(handler.withdrawMismatch());
        uint256 sumCredits;
        for (uint256 i; i < handler.actorCount(); ++i) {
            address actor = handler.actorAt(i);
            uint256 credited = handler.ghostCredited(actor);
            uint256 withdrawn = handler.ghostWithdrawn(actor);
            assertLe(withdrawn, credited);
            assertEq(registry.credits(actor), credited - withdrawn);
            sumCredits += registry.credits(actor);
        }
        assertEq(registry.totalCredited(), sumCredits);
    }

    function invariant_claimCountMonotonic() public view {
        assertFalse(handler.claimCountBroken());
        assertEq(registry.claimCount(), handler.claimIdCount());
    }

    // ======================================================== handler self-test

    /// Drives the handler through one of every successful path, to show its bookkeeping
    /// accepts correct behaviour. Seeds: actors[i % 5] (index 4 is the resolver) and
    /// each action first looks for a claim in the state it needs, starting at claimIds[seed % n].
    function test_handlerReachesEveryPath() public {
        handler.postClaim(0, 100); // id 1 by actor-1
        handler.postClaim(1, 200); // id 2 by actor-2
        handler.postClaim(2, 300); // id 3 by actor-3
        handler.postClaim(3, 400); // id 4 by actor-4
        handler.challenge(1, 0, 1, 999); // id 2, WRONG_RESULT by actor-1
        handler.challenge(2, 0, 2, 0); // id 3, EVIDENCE_INVALID by actor-1
        handler.challenge(3, 0, 1, 1); // id 4, WRONG_RESULT by actor-1
        handler.resolve(1, true, 1); // id 2 upheld -> Rejected
        handler.resolve(2, false, 1); // id 3 not upheld -> Finalized
        handler.warp(302); // 302 % 8 == 6 selects the long jump: past both windows
        handler.finalize(4, 2); // id 1 -> Finalized
        handler.expireUnresolved(3, 0); // id 4 -> Expired
        handler.withdraw(0); // actor-1: BOND + 2 BOND + BOND
        handler.withdraw(1); // actor-2: nothing, reverts
        handler.withdraw(2); // actor-3: 2 BOND
        handler.withdraw(3); // actor-4: BOND

        assertEq(handler.posts(), 4);
        assertEq(handler.challenges(), 3);
        assertEq(handler.upheldResolutions(), 1);
        assertEq(handler.rejectedResolutions(), 1);
        assertEq(handler.finalizes(), 1);
        assertEq(handler.expiries(), 1);
        assertEq(handler.withdrawals(), 3);
        assertEq(handler.reverts(), 1);
        assertEq(handler.ghostWithdrawn(handler.actorAt(0)), 4 * BOND);
        assertEq(address(registry).balance, 0);
        invariant_payoutsMatchSpec();
        invariant_noOverWithdrawal();
        invariant_terminalStatesNeverChange();
        invariant_claimCountMonotonic();
        invariant_lockedMatchesOpenClaims();
    }
}
