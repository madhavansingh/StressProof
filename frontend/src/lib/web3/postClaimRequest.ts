import { isAddress, zeroAddress, type Abi, type Address, type Hex, type TransactionReceipt } from "viem";
import { extractPostedClaim, type PostedClaimResult } from "@/lib/web3/claimPosted";

/**
 * After the receipt arrives: the claim counts only if the registry emitted exactly one matching
 * ClaimPosted event; only then are claim and feed queries refreshed.
 */
export function settlePublishReceipt(
  receipt: Pick<TransactionReceipt, "status" | "logs">,
  registry: Address,
  expectedEvidenceHash: Hex,
  refresh: () => void
): PostedClaimResult {
  const posted = extractPostedClaim(receipt, registry, expectedEvidenceHash);
  if (posted.ok) refresh();
  return posted;
}

const BYTES32 = /^0x[0-9a-fA-F]{64}$/;
const UINT = /^\d+$/;

export interface PostClaimInput {
  chainId: number;
  registry: Address;
  marketId: Hex;
  bondWei: bigint;
  residualBadDebtUsd8: string;
  evidenceHash: string;
  caseFileURI: string;
}

export interface PostClaimRequest {
  chainId: number;
  address: Address;
  functionName: "postClaim";
  args: readonly [Hex, bigint, Hex, string];
  value: bigint;
}

/**
 * The exact postClaim call shown to the wallet: the registry from deployments/<chainId>.json,
 * the deployment's bond as msg.value, and a pinned chainId. Invalid input throws before any
 * wallet prompt.
 */
export function buildPostClaimRequest(input: PostClaimInput): PostClaimRequest {
  if (!isAddress(input.registry) || input.registry.toLowerCase() === zeroAddress) {
    throw new Error("No registry deployed on this chain");
  }
  if (input.bondWei <= 0n) throw new Error("Bond must be positive");
  if (!BYTES32.test(input.marketId)) throw new Error("marketId is not a bytes32 value");
  if (!BYTES32.test(input.evidenceHash)) throw new Error("evidenceHash is not a bytes32 value");
  if (!UINT.test(input.residualBadDebtUsd8)) throw new Error("residualBadDebtUsd8 is not an unsigned integer");
  if (!input.caseFileURI) throw new Error("caseFileURI is empty");
  return {
    chainId: input.chainId,
    address: input.registry,
    functionName: "postClaim",
    args: [input.marketId, BigInt(input.residualBadDebtUsd8), input.evidenceHash as Hex, input.caseFileURI],
    value: input.bondWei,
  };
}

/** The read calls needed from a viem public client (kept minimal so tests can mock it). */
export interface RegistryReader {
  getCode(args: { address: Address }): Promise<Hex | undefined>;
  readContract(args: { address: Address; abi: Abi; functionName: "BOND" }): Promise<unknown>;
}

export type RegistryCheck = { ok: true } | { ok: false; reason: string };

/**
 * Before the signature request: the destination must hold contract code on the target chain and
 * its on-chain BOND() must equal the value about to be sent.
 */
export async function verifyRegistryBeforeSigning(
  reader: RegistryReader,
  registry: Address,
  abi: Abi,
  bondWei: bigint
): Promise<RegistryCheck> {
  let code: Hex | undefined;
  try {
    code = await reader.getCode({ address: registry });
  } catch {
    return { ok: false, reason: "Could not reach the chain to check the registry. Nothing was sent." };
  }
  if (!code || code === "0x") {
    return { ok: false, reason: `No contract at ${registry} on this chain. Nothing was sent.` };
  }
  let onChainBond: unknown;
  try {
    onChainBond = await reader.readContract({ address: registry, abi, functionName: "BOND" });
  } catch {
    return { ok: false, reason: "Could not read BOND() from the registry. Nothing was sent." };
  }
  if (typeof onChainBond !== "bigint" || onChainBond !== bondWei) {
    return { ok: false, reason: "The registry's BOND() does not match the configured bond. Nothing was sent." };
  }
  return { ok: true };
}
