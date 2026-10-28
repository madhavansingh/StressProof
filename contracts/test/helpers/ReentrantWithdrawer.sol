// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IStressRegistry} from "../../src/IStressRegistry.sol";

/// @notice Attacker for T-C-30. When it receives its payout it calls `withdraw` again.
/// With `catchReentry` false the inner revert bubbles up and fails the whole payout.
/// With `catchReentry` true it swallows the inner revert, so the test can check that
/// the second entry received nothing.
contract ReentrantWithdrawer {
    IStressRegistry public immutable registry;
    bool public immutable catchReentry;
    uint256 public reentrancyAttempts;
    bool public reentrySucceeded;

    constructor(IStressRegistry registry_, bool catchReentry_) {
        registry = registry_;
        catchReentry = catchReentry_;
    }

    function postClaim(bytes32 marketId, uint256 claimed, bytes32 evidenceHash, string calldata uri)
        external
        payable
        returns (uint256)
    {
        return registry.postClaim{value: msg.value}(marketId, claimed, evidenceHash, uri);
    }

    function withdraw() external {
        registry.withdraw();
    }

    receive() external payable {
        if (reentrancyAttempts > 0) return;
        reentrancyAttempts++;
        if (catchReentry) {
            try registry.withdraw() {
                reentrySucceeded = true;
            } catch {}
        } else {
            registry.withdraw();
        }
    }
}
