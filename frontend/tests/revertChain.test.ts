import { describe, it, expect } from "vitest";
import {
  ContractFunctionExecutionError,
  ContractFunctionRevertedError,
  encodeErrorResult,
  parseAbi,
  type Hex,
} from "viem";
import { decodeContractError, revertDataFromViemError } from "../src/lib/web3/errors";

const MARKET = "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0";
const VAULT = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
const abi = parseAbi([
  "error LtvTooHigh(uint256 requestedBps, uint256 maxBps)",
  "error NotFinalized()",
  "function borrow(uint256 collateralUsd8, uint256 amountUsd8)",
  "function applyClaim(uint256 claimId)",
]);

// The error chain viem's simulateContract throws when the contract reverts.
function simulationError(data: Hex, functionName: "borrow" | "applyClaim", contractAddress: Hex) {
  const reverted = new ContractFunctionRevertedError({ abi, data, functionName });
  return new ContractFunctionExecutionError(reverted, { abi, functionName, args: [], contractAddress });
}

describe("decodeContractError with viem simulation errors", () => {
  it("decodes LtvTooHigh(7000, 5000) with its arguments from a simulateContract error", () => {
    const data = encodeErrorResult({ abi, errorName: "LtvTooHigh", args: [7000n, 5000n] });
    const decoded = decodeContractError(simulationError(data, "borrow", MARKET));
    expect(decoded.errorName).toBe("LtvTooHigh");
    expect(decoded.userMessage).toContain("LtvTooHigh(7000, 5000)");
    expect(decoded.rawHex?.startsWith("0x37e4c1c4")).toBe(true);
  });

  it("decodes NotFinalized() from an applyClaim simulation error", () => {
    const data = encodeErrorResult({ abi, errorName: "NotFinalized" });
    const decoded = decodeContractError(simulationError(data, "applyClaim", VAULT));
    expect(decoded.errorName).toBe("NotFinalized");
    expect(decoded.userMessage).toBe("Only finalized claims can change the vault");
    expect(decoded.rawHex).toBe("0x1bee0d5a");
  });

  it("returns no revert data for errors that are not viem contract reverts", () => {
    expect(revertDataFromViemError(new Error("network down"))).toBeUndefined();
    expect(revertDataFromViemError("0x1bee0d5a")).toBeUndefined();
  });
});
