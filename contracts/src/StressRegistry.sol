// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IStressRegistry} from "./IStressRegistry.sol";

contract StressRegistry is IStressRegistry {
    uint256 public immutable override BOND;
    uint64 public immutable override CHALLENGE_WINDOW;
    uint64 public immutable override RESOLUTION_WINDOW;
    uint16 public immutable override TOLERANCE_BPS;
    address public immutable override resolver;
    uint256 public constant MAX_URI_LENGTH = 512;

    uint256 public override claimCount;
    uint256 public totalLocked;
    uint256 public totalCredited;
    mapping(uint256 => Claim) private _claims;
    mapping(address => uint256) public override credits;

    constructor(
        uint256 bond,
        uint64 cw,
        uint64 rw,
        uint16 tol,
        address resolver_
    ) {
        require(bond > 0 && cw > 0 && rw > 0 && resolver_ != address(0));
        BOND = bond;
        CHALLENGE_WINDOW = cw;
        RESOLUTION_WINDOW = rw;
        TOLERANCE_BPS = tol;
        resolver = resolver_;
    }

    function postClaim(
        bytes32 marketId,
        uint256 claimed,
        bytes32 evidenceHash,
        string calldata uri
    ) external payable override returns (uint256 id) {
        if (msg.value != BOND) revert WrongBond(msg.value, BOND);
        if (marketId == bytes32(0)) revert ZeroMarketId();
        if (evidenceHash == bytes32(0)) revert ZeroEvidenceHash();
        uint256 len = bytes(uri).length;
        if (len == 0 || len > MAX_URI_LENGTH) revert BadURI();

        id = ++claimCount;
        Claim storage c = _claims[id];
        c.attester = msg.sender;
        c.challengeDeadline = uint64(block.timestamp) + CHALLENGE_WINDOW;
        c.state = State.Pending;
        c.marketId = marketId;
        c.evidenceHash = evidenceHash;
        c.claimedResidualBadDebt = claimed;
        c.caseFileURI = uri;
        totalLocked += BOND;

        emit ClaimPosted(
            id,
            msg.sender,
            marketId,
            claimed,
            evidenceHash,
            uri,
            c.challengeDeadline
        );
    }

    function challenge(
        uint256 id,
        Reason reason,
        uint256 counter,
        string calldata reportURI,
        bytes32 reportHash
    ) external payable override {
        Claim storage c = _claims[id];
        if (c.state != State.Pending) revert InvalidState(c.state);
        if (block.timestamp >= c.challengeDeadline) revert ChallengeWindowClosed();
        if (msg.sender == c.attester) revert AttesterCannotChallenge();
        if (msg.value != BOND) revert WrongBond(msg.value, BOND);
        if (reason == Reason.NONE) revert BadReason();
        if (reportHash == bytes32(0)) revert ZeroReportHash();
        uint256 len = bytes(reportURI).length;
        if (len == 0 || len > MAX_URI_LENGTH) revert BadURI();

        if (reason == Reason.WRONG_RESULT) {
            if (counter == c.claimedResidualBadDebt) revert CounterEqualsClaim();
        } else {
            counter = 0;
        }

        c.challenger = msg.sender;
        c.reason = reason;
        c.counterResidualBadDebt = counter;
        c.replayReportURI = reportURI;
        c.replayReportHash = reportHash;
        c.resolutionDeadline = uint64(block.timestamp) + RESOLUTION_WINDOW;
        c.state = State.Challenged;
        totalLocked += BOND;

        emit ClaimChallenged(
            id,
            msg.sender,
            reason,
            counter,
            reportURI,
            reportHash,
            c.resolutionDeadline
        );
    }

    function finalize(uint256 id) external override {
        Claim storage c = _claims[id];
        if (c.state != State.Pending) revert InvalidState(c.state);
        if (block.timestamp < c.challengeDeadline) revert ChallengeWindowOpen();

        c.state = State.Finalized;
        _move(c.attester, BOND);
        emit ClaimFinalized(id);
    }

    function resolve(uint256 id, bool upheld) external override {
        if (msg.sender != resolver) revert NotResolver();
        Claim storage c = _claims[id];
        if (c.state != State.Challenged) revert InvalidState(c.state);
        if (block.timestamp >= c.resolutionDeadline) revert ResolutionWindowClosed();
        if (msg.sender == c.attester || msg.sender == c.challenger) revert ResolverIsParty();

        address winner = upheld ? c.challenger : c.attester;
        c.state = upheld ? State.Rejected : State.Finalized;
        _move(winner, 2 * BOND);

        emit ClaimResolved(id, upheld, winner, 2 * BOND);
        if (!upheld) emit ClaimFinalized(id);
    }

    function expireUnresolved(uint256 id) external override {
        Claim storage c = _claims[id];
        if (c.state != State.Challenged) revert InvalidState(c.state);
        if (block.timestamp < c.resolutionDeadline) revert ResolutionWindowOpen();

        c.state = State.Expired;
        _move(c.attester, BOND);
        _move(c.challenger, BOND);
        emit ClaimExpired(id);
    }

    function withdraw() external override {
        uint256 amt = credits[msg.sender];
        if (amt == 0) revert NothingToWithdraw();

        credits[msg.sender] = 0;
        totalCredited -= amt;
        // Emit before the external call so the log order cannot be affected by the receiver.
        // If the transfer fails, the whole call reverts and the event is discarded too.
        emit Withdrawn(msg.sender, amt);

        (bool ok, ) = msg.sender.call{value: amt}("");
        if (!ok) revert TransferFailed();
    }

    function _move(address to, uint256 amt) private {
        totalLocked -= amt;
        credits[to] += amt;
        totalCredited += amt;
    }

    function status(uint256 id) external view override returns (State) {
        return _claims[id].state;
    }

    function claim(uint256 id) external view override returns (Claim memory) {
        return _claims[id];
    }
}
