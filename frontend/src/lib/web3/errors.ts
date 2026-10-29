import { decodeErrorResult } from "viem";
import { DemoVaultAbi, MockLendingMarketAbi, IStressRegistryAbi } from "@/lib/contracts";

const COMBINED_ABI = [
  ...(DemoVaultAbi as any[]),
  ...(MockLendingMarketAbi as any[]),
  ...(IStressRegistryAbi as any[]),
];

export interface DecodedContractError {
  errorName: string;
  args?: any[];
  userMessage: string;
  rawHex?: string;
}

/**
 * Decodes contract revert data or viem error object into human-readable spec sentences per §19.4.
 */
export function decodeContractError(err: any): DecodedContractError {
  // Extract hex error data if present
  let dataHex: `0x${string}` | undefined;

  if (typeof err === "string" && err.startsWith("0x")) {
    dataHex = err as `0x${string}`;
  } else if (err?.data && typeof err.data === "string" && err.data.startsWith("0x")) {
    dataHex = err.data;
  } else if (err?.cause?.data && typeof err.cause.data === "string" && err.cause.data.startsWith("0x")) {
    dataHex = err.cause.data;
  } else if (err?.error?.data && typeof err.error.data === "string" && err.error.data.startsWith("0x")) {
    dataHex = err.error.data;
  } else if (err?.info?.error?.data && typeof err.info.error.data === "string") {
    dataHex = err.info.error.data;
  }

  if (dataHex) {
    try {
      const decoded = decodeErrorResult({
        abi: COMBINED_ABI,
        data: dataHex,
      });

      const errorName = decoded.errorName;
      const args = decoded.args as any[] | undefined;

      let userMessage = `Reverted with ${errorName}`;

      switch (errorName) {
        case "LtvTooHigh": {
          const reqBps = args?.[0] !== undefined ? Number(args[0]) : 0;
          const maxBps = args?.[1] !== undefined ? Number(args[1]) : 0;
          userMessage = `LtvTooHigh(${reqBps}, ${maxBps}): Borrow would exceed vault max LTV of ${(maxBps / 100).toFixed(2)}% (requested ${(reqBps / 100).toFixed(2)}%)`;
          break;
        }
        case "NotFinalized":
          userMessage = "Only finalized claims can change the vault";
          break;
        case "BorrowPaused":
          userMessage = "Borrowing is paused by the circuit breaker";
          break;
        case "ZeroCollateral":
          userMessage = "Collateral must be greater than zero";
          break;
        case "WrongMarket":
          userMessage = "Claim market ID does not match vault market";
          break;
        case "AlreadyApplied":
          userMessage = "This claim has already been applied to the vault";
          break;
        case "BelowThreshold":
          userMessage = "Claim bad debt is below the minimum threshold";
          break;
        case "ChallengeWindowClosed":
          userMessage = "The 2-minute challenge window has ended";
          break;
        case "ChallengeWindowOpen":
          userMessage = "Challenge window is still open";
          break;
        case "WrongBond":
          userMessage = "Bond must be exactly 0.01 ETH";
          break;
        case "NotOwner":
          userMessage = "Only the vault owner can reset controls";
          break;
      }

      return {
        errorName,
        args,
        userMessage,
        rawHex: dataHex,
      };
    } catch {
      // Failed to decode with ABI, fall back to string inspection
    }
  }

  // Fallback to checking error messages
  const msg = err?.message || String(err || "Unknown error");
  if (msg.includes("LtvTooHigh")) {
    return {
      errorName: "LtvTooHigh",
      userMessage: "Borrow would exceed vault max LTV",
      rawHex: dataHex,
    };
  }
  if (msg.includes("NotFinalized")) {
    return {
      errorName: "NotFinalized",
      userMessage: "Only finalized claims can change the vault",
      rawHex: dataHex,
    };
  }
  if (msg.includes("BorrowPaused")) {
    return {
      errorName: "BorrowPaused",
      userMessage: "Borrowing is paused by the circuit breaker",
      rawHex: dataHex,
    };
  }

  return {
    errorName: "UnknownRevert",
    userMessage: msg.slice(0, 180),
    rawHex: dataHex,
  };
}

