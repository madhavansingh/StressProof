// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {StressRegistry} from "../../src/StressRegistry.sol";
import {IStressRegistry} from "../../src/IStressRegistry.sol";

/// @notice Drives random sequences of registry calls for T-INV-1 and records what happened.
/// Calls may be valid or invalid; invalid ones are expected to revert and are counted.
/// Failed assertions inside a handler would be swallowed (fail_on_revert = false), so the
/// handler sets violation flags instead, and the invariant functions check those flags.
contract RegistryHandler is Test {
    uint256 internal constant MAX_CLAIMS = 40;
    uint256 internal constant MAX_WARP = 400;
    uint256 internal constant SHORT_WARP = 60;
    /// Seed remainder that selects a deliberately invalid choice (bad id, NONE reason,
    /// attester as challenger, non-resolver, long warp). The fuzzer favours edge values
    /// such as 0 and type(uint256).max, so its remainders (mod 4, 5, 8, 10) must differ from
    /// both: max-uint gives 3, 0, 7 and 5. 6 gives 2, 1, 6 and 6.
    uint256 internal constant INVALID_PICK = 6;
    uint256 internal constant MAX_AMOUNT = 1e20;
    bytes32 internal constant MARKET_ID = keccak256("aave-v3-eth-weth-stable");
    bytes32 internal constant EVIDENCE_HASH = keccak256("case-file-bytes");
    bytes32 internal constant REPORT_HASH = keccak256("replay-report-bytes");
    string internal constant URI = "ipfs://case-file";
    string internal constant REPORT_URI = "ipfs://replay-report";

    StressRegistry public immutable registry;
    uint256 public immutable bond;
    address public immutable resolver;

    address[] internal actors;
    uint256[] internal claimIds;
    uint256 public currentTime;

    // Ghost accounting, independent of the contract's own bookkeeping.
    mapping(address => uint256) public ghostCredited;
    mapping(address => uint256) public ghostWithdrawn;
    mapping(uint256 => uint8) internal recordedTerminal; // 0 = not terminal yet
    uint256 internal lastClaimCount;

    // Violation flags.
    bool public payoutMismatch;
    bool public withdrawMismatch;
    bool public terminalChanged;
    bool public claimCountBroken;
    bool public unexpectedFailure;
    bool public unauthorizedSuccess;

    // Successful-call counters, to show the campaign reaches every path.
    uint256 public posts;
    uint256 public challenges;
    uint256 public finalizes;
    uint256 public upheldResolutions;
    uint256 public rejectedResolutions;
    uint256 public expiries;
    uint256 public withdrawals;
    uint256 public reverts;

    constructor(StressRegistry registry_, address resolver_) {
        registry = registry_;
        bond = registry_.BOND();
        resolver = resolver_;
        currentTime = block.timestamp;
        actors.push(makeAddr("actor-1"));
        actors.push(makeAddr("actor-2"));
        actors.push(makeAddr("actor-3"));
        actors.push(makeAddr("actor-4"));
        actors.push(resolver_); // explores ResolverIsParty paths
        for (uint256 i; i < actors.length; ++i) {
            vm.deal(actors[i], 1_000 ether);
        }
    }

    /// Keeps time under the handler's control across calls in a run.
    modifier useTime() {
        vm.warp(currentTime);
        _;
        _afterAction();
    }

    // ================================================================ actions

    function postClaim(uint256 actorSeed, uint256 claimed) external useTime {
        if (claimIds.length >= MAX_CLAIMS) return;
        address actor = _actor(actorSeed);
        claimed = bound(claimed, 0, MAX_AMOUNT);
        vm.prank(actor);
        try registry.postClaim{value: bond}(MARKET_ID, claimed, EVIDENCE_HASH, URI) returns (uint256 id) {
            claimIds.push(id);
            posts++;
        } catch {
            unexpectedFailure = true; // a well-formed post must always succeed
        }
    }

    function challenge(uint256 idSeed, uint256 actorSeed, uint256 reasonSeed, uint256 counter)
        external
        useTime
    {
        uint256 id = _pickClaim(idSeed, IStressRegistry.State.Pending);
        IStressRegistry.Reason reason = _reason(reasonSeed);
        counter = bound(counter, 0, MAX_AMOUNT);
        address actor = _actor(actorSeed);
        // Usually avoid the attester so the call can succeed; sometimes keep it to hit the revert.
        if (actorSeed % 5 != INVALID_PICK % 5 && actor == registry.claim(id).attester) {
            actor = _actor(actorSeed % actors.length + 1);
        }
        vm.prank(actor);
        try registry.challenge{value: bond}(id, reason, counter, REPORT_URI, REPORT_HASH) {
            challenges++;
        } catch {
            reverts++;
        }
    }

    function finalize(uint256 idSeed, uint256 callerSeed) external useTime {
        uint256 id = _pickClaim(idSeed, IStressRegistry.State.Pending);
        address attester = registry.claim(id).attester;
        uint256 before = registry.credits(attester);
        vm.prank(_actor(callerSeed));
        try registry.finalize(id) {
            finalizes++;
            _expectCredit(attester, before, bond);
        } catch {
            reverts++;
        }
    }

    function resolve(uint256 idSeed, bool upheld, uint256 callerSeed) external useTime {
        uint256 id = _pickClaim(idSeed, IStressRegistry.State.Challenged);
        IStressRegistry.Claim memory c = registry.claim(id);
        // Mostly the resolver, sometimes anyone, to exercise NotResolver.
        address caller = callerSeed % 4 == INVALID_PICK % 4 ? _actor(callerSeed / 4) : resolver;
        address winner = upheld ? c.challenger : c.attester;
        uint256 before = registry.credits(winner);
        vm.prank(caller);
        try registry.resolve(id, upheld) {
            if (caller != resolver) unauthorizedSuccess = true;
            if (upheld) upheldResolutions++;
            else rejectedResolutions++;
            _expectCredit(winner, before, 2 * bond);
        } catch {
            reverts++;
        }
    }

    function expireUnresolved(uint256 idSeed, uint256 callerSeed) external useTime {
        uint256 id = _pickClaim(idSeed, IStressRegistry.State.Challenged);
        IStressRegistry.Claim memory c = registry.claim(id);
        uint256 attesterBefore = registry.credits(c.attester);
        uint256 challengerBefore = registry.credits(c.challenger);
        vm.prank(_actor(callerSeed));
        try registry.expireUnresolved(id) {
            expiries++;
            _expectCredit(c.attester, attesterBefore, bond);
            _expectCredit(c.challenger, challengerBefore, bond);
        } catch {
            reverts++;
        }
    }

    function withdraw(uint256 actorSeed) external useTime {
        address actor = _actor(actorSeed);
        uint256 credit = registry.credits(actor);
        uint256 balanceBefore = actor.balance;
        vm.prank(actor);
        try registry.withdraw() {
            withdrawals++;
            uint256 received = actor.balance - balanceBefore;
            if (received != credit || registry.credits(actor) != 0) withdrawMismatch = true;
            ghostWithdrawn[actor] += received;
        } catch {
            reverts++;
            if (credit != 0) withdrawMismatch = true; // actors are EOAs and always accept ETH
        }
    }

    /// Mostly short steps so challenge windows stay reachable; one in eight can jump up to 400 s.
    function warp(uint256 dt) external useTime {
        currentTime += bound(dt, 1, dt % 8 == INVALID_PICK % 8 ? MAX_WARP : SHORT_WARP);
        vm.warp(currentTime);
    }

    // =========================================================== views for tests

    /// Bonds that should be locked: BOND per Pending claim, 2 x BOND per Challenged claim.
    function expectedLocked() external view returns (uint256 locked) {
        for (uint256 i; i < claimIds.length; ++i) {
            IStressRegistry.State s = registry.status(claimIds[i]);
            if (s == IStressRegistry.State.Pending) locked += bond;
            else if (s == IStressRegistry.State.Challenged) locked += 2 * bond;
        }
    }

    function actorCount() external view returns (uint256) {
        return actors.length;
    }

    function actorAt(uint256 i) external view returns (address) {
        return actors[i];
    }

    function claimIdCount() external view returns (uint256) {
        return claimIds.length;
    }

    // ================================================================ internals

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    /// Mostly an existing claim; one call in ten picks from 0..n+1, which includes
    /// id 0 and a never-posted id.
    function _claimId(uint256 seed) internal view returns (uint256) {
        uint256 n = claimIds.length;
        if (n == 0 || seed % 10 == INVALID_PICK) return seed % (n + 2);
        return claimIds[seed % n];
    }

    /// Four calls in five look for a claim in `wanted` state (starting at a seed-chosen offset);
    /// otherwise, or if none is found, fall back to `_claimId`, which can pick any claim.
    function _pickClaim(uint256 seed, IStressRegistry.State wanted) internal view returns (uint256) {
        uint256 n = claimIds.length;
        if (n > 0 && seed % 5 != INVALID_PICK % 5) {
            uint256 start = seed % n; // reduce first: seed + i could overflow for large seeds
            for (uint256 i; i < n; ++i) {
                uint256 id = claimIds[(start + i) % n];
                if (registry.status(id) == wanted) return id;
            }
        }
        return _claimId(seed);
    }

    /// One in ten picks the invalid NONE reason; otherwise odd seeds are WRONG_RESULT, even EVIDENCE_INVALID.
    function _reason(uint256 seed) internal pure returns (IStressRegistry.Reason) {
        if (seed % 10 == INVALID_PICK) return IStressRegistry.Reason.NONE;
        return seed % 2 == 1 ? IStressRegistry.Reason.WRONG_RESULT : IStressRegistry.Reason.EVIDENCE_INVALID;
    }

    function _expectCredit(address who, uint256 before, uint256 amount) internal {
        if (registry.credits(who) != before + amount) payoutMismatch = true;
        ghostCredited[who] += amount;
    }

    function _afterAction() internal {
        uint256 count = registry.claimCount();
        if (count < lastClaimCount || count != claimIds.length) claimCountBroken = true;
        lastClaimCount = count;

        for (uint256 i; i < claimIds.length; ++i) {
            uint256 id = claimIds[i];
            uint8 s = uint8(registry.status(id));
            uint8 recorded = recordedTerminal[id];
            if (recorded != 0) {
                if (s != recorded) terminalChanged = true;
            } else if (s >= uint8(IStressRegistry.State.Finalized)) {
                recordedTerminal[id] = s;
            }
        }
    }
}
