import { isAddressEqual, parseAbiItem, parseEventLogs, type Address, type Hex, type TransactionReceipt } from "viem";

/**
 * The StressRegistry ClaimPosted event, typed for viem inference. It mirrors the entry in
 * src/abi/IStressRegistry.json (a JSON import, which TypeScript cannot narrow to literal types);
 * tests/claimPosted.test.ts fails if the two ever differ.
 */
export const CLAIM_POSTED_EVENT = parseAbiItem(
  "event ClaimPosted(uint256 indexed claimId, address indexed attester, bytes32 indexed marketId, uint256 claimedResidualBadDebt, bytes32 evidenceHash, string caseFileURI, uint64 challengeDeadline)"
);

export type PostedClaimResult =
  | { ok: true; claimId: bigint; evidenceHash: Hex }
  | { ok: false; reason: string };

/**
 * Reads the claim id from a postClaim receipt. Only a ClaimPosted event emitted by the registry
 * itself counts, there must be exactly one, and it must carry the evidence hash that was published.
 */
export function extractPostedClaim(
  receipt: Pick<TransactionReceipt, "status" | "logs">,
  registry: Address,
  expectedEvidenceHash: Hex
): PostedClaimResult {
  if (receipt.status !== "success") {
    return { ok: false, reason: "The transaction reverted; no claim was posted." };
  }
  const fromRegistry = receipt.logs.filter((log) => isAddressEqual(log.address, registry));
  const events = parseEventLogs({ abi: [CLAIM_POSTED_EVENT], eventName: "ClaimPosted", logs: fromRegistry });
  if (events.length === 0) {
    return { ok: false, reason: "The receipt has no ClaimPosted event from the registry." };
  }
  if (events.length > 1) {
    return { ok: false, reason: `Expected one ClaimPosted event from the registry, found ${events.length}.` };
  }
  const { claimId, evidenceHash } = events[0].args;
  if (evidenceHash.toLowerCase() !== expectedEvidenceHash.toLowerCase()) {
    return { ok: false, reason: "The posted claim's evidence hash does not match the published case file." };
  }
  return { ok: true, claimId, evidenceHash };
}
