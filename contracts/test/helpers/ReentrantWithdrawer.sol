// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IStressRegistry} from "../../src/IStressRegistry.sol";

contract ReentrantWithdrawer {
    IStressRegistry public immutable registry;
    uint256 public reentrancyAttempts;

    constructor(IStressRegistry registry_) {
        registry = registry_;
    }

    receive() external payable {
        if (reentrancyAttempts < 2) {
            reentrancyAttempts++;
            registry.withdraw();
        }
    }
}
