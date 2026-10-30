import type { Hex, TransactionReceipt } from "viem";
import { decodeContractError } from "./errors";

/** The read-only client calls needed to settle a submitted transaction. */
export interface ReceiptClient {
  waitForTransactionReceipt(args: { hash: Hex }): Promise<TransactionReceipt>;
  getTransaction(args: { hash: Hex }): Promise<{ from: Hex; to: Hex | null; input: Hex; value: bigint }>;
  call(args: { account: Hex; to: Hex | null; data: Hex; value: bigint; blockNumber: bigint }): Promise<unknown>;
}

export interface ReceiptOutcome {
  status: "success" | "reverted";
  receipt: TransactionReceipt;
  /** Decoded contract error for a reverted transaction, when it can be recovered. */
  revertReason?: string;
}

/**
 * Waits for a transaction and reports how it actually ended.
 *
 * wagmi's waitForTransactionReceipt throws on a reverted receipt instead of returning it, which left
 * the UI showing "waiting for receipt" forever after a revert. viem's client call returns the
 * receipt either way; for a revert, the transaction is replayed read-only against the state just
 * before its block to recover the contract error.
 */
export async function fetchReceiptOutcome(client: ReceiptClient, hash: Hex): Promise<ReceiptOutcome> {
  const receipt = await client.waitForTransactionReceipt({ hash });
  if (receipt.status === "success") return { status: "success", receipt };

  let revertReason: string | undefined;
  try {
    const tx = await client.getTransaction({ hash });
    await client.call({
      account: tx.from,
      to: tx.to,
      data: tx.input,
      value: tx.value,
      blockNumber: receipt.blockNumber - 1n,
    });
    // The replay passes against the previous block, so the revert depended on what changed when it
    // was mined: the block time (a window closing) or another transaction in between.
    revertReason = "Reverted when mined, but passes against the previous block: the chain state or time changed between the check and mining (for example a window closed).";
  } catch (err: unknown) {
    const decoded = decodeContractError(err);
    if (decoded.errorName && decoded.errorName !== "UnknownRevert") {
      revertReason = decoded.userMessage || decoded.errorName;
    }
  }
  return { status: "reverted", receipt, revertReason };
}
