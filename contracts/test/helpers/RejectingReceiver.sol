// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IStressRegistry} from "../../src/IStressRegistry.sol";

/// @notice Account that refuses ETH, for T-C-31 (a failed payout must keep the credit).
contract RejectingReceiver {
    IStressRegistry public immutable registry;

    error EtherRejected();

    constructor(IStressRegistry registry_) {
        registry = registry_;
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
        revert EtherRejected();
    }
}
