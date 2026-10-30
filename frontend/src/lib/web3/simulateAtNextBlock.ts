import { encodeFunctionData, type Abi, type Address, type PublicClient } from "viem";
import { nextBlockTimeSec } from "@/lib/claims";

export interface NextBlockCall {
  account: Address;
  address: Address;
  abi: Abi;
  functionName: string;
  args: readonly unknown[];
  value?: bigint;
}

type CallClient = Pick<PublicClient, "getBlock" | "call">;

/**
 * Simulate a time-sensitive write (challenge, finalize, expire) at the timestamp the next block will carry,
 * not at the latest block's. Throws the RPC error on revert, so decodeContractError can explain it.
 * Falls back to a plain eth_call when the node does not support block overrides.
 */
export async function simulateAtNextBlock(client: CallClient, req: NextBlockCall, wallNowSec = Date.now() / 1000): Promise<void> {
  const latest = await client.getBlock();
  const data = encodeFunctionData({ abi: req.abi, functionName: req.functionName, args: req.args } as never);
  const base = { account: req.account, to: req.address, data, value: req.value };
  const time = BigInt(nextBlockTimeSec(Number(latest.timestamp), wallNowSec));
  try {
    await client.call({ ...base, blockOverrides: { time } } as never);
  } catch (err: unknown) {
    const text = err instanceof Error ? err.message.toLowerCase() : "";
    const unsupported = text.includes("blockoverrides") || text.includes("invalid params") || text.includes("too many arguments");
    if (!unsupported) throw err;
    await client.call(base as never);
  }
}
