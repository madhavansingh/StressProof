// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {DemoVault} from "./DemoVault.sol";

contract MockLendingMarket {
    DemoVault public immutable vault;
    mapping(address => uint256) public debtUsd8;

    event Borrowed(
        address indexed user,
        uint256 collateralUsd8,
        uint256 amountUsd8,
        uint256 ltvBps
    );

    error BorrowPaused();
    error ZeroCollateral();
    error LtvTooHigh(uint256 requestedBps, uint256 maxBps);

    constructor(DemoVault vault_) {
        vault = vault_;
    }

    function borrow(uint256 collateralUsd8, uint256 amountUsd8) external {
        if (vault.borrowPaused()) revert BorrowPaused();
        if (collateralUsd8 == 0) revert ZeroCollateral();

        // Ceil division for strict LTV checking
        uint256 ltv = (amountUsd8 * 10_000 + collateralUsd8 - 1) / collateralUsd8;
        if (ltv > vault.maxLtvBps()) {
            revert LtvTooHigh(ltv, vault.maxLtvBps());
        }

        debtUsd8[msg.sender] += amountUsd8;
        emit Borrowed(msg.sender, collateralUsd8, amountUsd8, ltv);
    }
}
