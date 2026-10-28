// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface IStressRegistry {
    enum State {
        None,
        Pending,
        Challenged,
        Finalized,
        Rejected,
        Expired
    }

    enum Reason {
        NONE,
        WRONG_RESULT,
        EVIDENCE_INVALID
    }

    struct Claim {
        address attester;
        uint64 challengeDeadline;
        State state;
        Reason reason;
        address challenger;
        uint64 resolutionDeadline;
        bytes32 marketId;
        bytes32 evidenceHash;
        bytes32 replayReportHash;
        uint256 claimedResidualBadDebt; // USD * 1e8
        uint256 counterResidualBadDebt; // USD * 1e8, 0 for EVIDENCE_INVALID
        string caseFileURI;
        string replayReportURI;
    }

    event ClaimPosted(
        uint256 indexed claimId,
        address indexed attester,
        bytes32 indexed marketId,
        uint256 claimedResidualBadDebt,
        bytes32 evidenceHash,
        string caseFileURI,
        uint64 challengeDeadline
    );

    event ClaimChallenged(
        uint256 indexed claimId,
        address indexed challenger,
        Reason reason,
        uint256 counterResidualBadDebt,
        string replayReportURI,
        bytes32 replayReportHash,
        uint64 resolutionDeadline
    );

    event ClaimResolved(
        uint256 indexed claimId,
        bool challengeUpheld,
        address indexed winner,
        uint256 amountCredited
    );

    event ClaimFinalized(uint256 indexed claimId);
    event ClaimExpired(uint256 indexed claimId);
    event Withdrawn(address indexed account, uint256 amount);

    error WrongBond(uint256 sent, uint256 required);
    error ZeroMarketId();
    error ZeroEvidenceHash();
    error BadURI();
    error InvalidState(State current);
    error ChallengeWindowClosed();
    error ChallengeWindowOpen();
    error ResolutionWindowClosed();
    error ResolutionWindowOpen();
    error AttesterCannotChallenge();
    error ZeroReportHash();
    error BadReason();
    error CounterEqualsClaim();
    error NotResolver();
    error ResolverIsParty();
    error NothingToWithdraw();
    error TransferFailed();

    function postClaim(
        bytes32 marketId,
        uint256 claimedResidualBadDebt,
        bytes32 evidenceHash,
        string calldata caseFileURI
    ) external payable returns (uint256 claimId);

    function challenge(
        uint256 claimId,
        Reason reason,
        uint256 counterResidualBadDebt,
        string calldata replayReportURI,
        bytes32 replayReportHash
    ) external payable;

    function resolve(uint256 claimId, bool challengeUpheld) external;
    function finalize(uint256 claimId) external;
    function expireUnresolved(uint256 claimId) external;
    function withdraw() external;

    function status(uint256 claimId) external view returns (State);
    function claim(uint256 claimId) external view returns (Claim memory);
    function credits(address account) external view returns (uint256);
    function claimCount() external view returns (uint256);

    function BOND() external view returns (uint256);
    function CHALLENGE_WINDOW() external view returns (uint64);
    function RESOLUTION_WINDOW() external view returns (uint64);
    function TOLERANCE_BPS() external view returns (uint16);
    function resolver() external view returns (address);
}
