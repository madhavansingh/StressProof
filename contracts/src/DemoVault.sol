// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IStressRegistry} from "./IStressRegistry.sol";

contract DemoVault {
    IStressRegistry public immutable registry;
    bytes32 public immutable MARKET_ID;
    address public immutable owner;
    uint256 public immutable PAUSE_THRESHOLD; // USD * 1e8
    uint256 public immutable LTV_THRESHOLD; // USD * 1e8, 0 < LTV_THRESHOLD <= PAUSE_THRESHOLD
    uint16 public immutable REDUCED_LTV_BPS; // < DEFAULT_MAX_LTV_BPS
    uint16 public immutable DEFAULT_MAX_LTV_BPS;

    bool public borrowPaused;
    uint16 public maxLtvBps; // starts at DEFAULT_MAX_LTV_BPS
    uint256 public lastAppliedClaimId;
    mapping(uint256 => bool) public applied;

    event ClaimApplied(
        uint256 indexed claimId,
        uint256 residualBadDebt,
        bool paused,
        uint16 maxLtvBps
    );
    event ControlsReset();

    error NotFinalized();
    error WrongMarket();
    error AlreadyApplied();
    error BelowThreshold();
    error NotOwner();

    constructor(
        IStressRegistry registry_,
        bytes32 marketId_,
        uint256 pauseThreshold_,
        uint256 ltvThreshold_,
        uint16 reducedLtvBps_,
        uint16 defaultMaxLtvBps_
    ) {
        require(pauseThreshold_ >= ltvThreshold_ && ltvThreshold_ > 0);
        require(reducedLtvBps_ < defaultMaxLtvBps_ && defaultMaxLtvBps_ <= 10000);

        registry = registry_;
        MARKET_ID = marketId_;
        owner = msg.sender;
        PAUSE_THRESHOLD = pauseThreshold_;
        LTV_THRESHOLD = ltvThreshold_;
        REDUCED_LTV_BPS = reducedLtvBps_;
        DEFAULT_MAX_LTV_BPS = defaultMaxLtvBps_;
        maxLtvBps = defaultMaxLtvBps_;
    }

    function applyClaim(uint256 claimId) external {
        IStressRegistry.Claim memory c = registry.claim(claimId);
        if (c.state != IStressRegistry.State.Finalized) revert NotFinalized();
        if (c.marketId != MARKET_ID) revert WrongMarket();
        if (applied[claimId]) revert AlreadyApplied();

        if (c.claimedResidualBadDebt >= PAUSE_THRESHOLD) {
            borrowPaused = true;
        } else if (c.claimedResidualBadDebt >= LTV_THRESHOLD) {
            if (REDUCED_LTV_BPS < maxLtvBps) {
                maxLtvBps = REDUCED_LTV_BPS;
            }
        } else {
            revert BelowThreshold();
        }

        applied[claimId] = true;
        lastAppliedClaimId = claimId;
        emit ClaimApplied(claimId, c.claimedResidualBadDebt, borrowPaused, maxLtvBps);
    }

    function resetControls() external {
        if (msg.sender != owner) revert NotOwner();
        borrowPaused = false;
        maxLtvBps = DEFAULT_MAX_LTV_BPS;
        emit ControlsReset();
    }
}
