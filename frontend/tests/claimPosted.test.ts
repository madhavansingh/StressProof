import { describe, it, expect } from "vitest";
import {
  encodeAbiParameters,
  numberToHex,
  pad,
  parseAbiItem,
  parseAbiParameters,
  toEventSelector,
  type Address,
  type Hex,
  type Log,
} from "viem";
import IStressRegistryAbi from "../src/abi/IStressRegistry.json";
import { CLAIM_POSTED_EVENT, extractPostedClaim } from "../src/lib/web3/claimPosted";

const REGISTRY: Address = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
const OTHER_CONTRACT: Address = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
const ATTESTER: Address = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const MARKET_ID: Hex = "0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026";
const EVIDENCE: Hex = "0x9b0f9c87fb81f5624639685d12812678db22e76f35dcf8394d7afeee1bd0f3a6";
const OTHER_EVIDENCE: Hex = "0xfecc348c8824538fe1a29d74a183cc6fa8237f121be5c8b1f913c22f2b713631";

function makeLog(address: Address, topics: [Hex, ...Hex[]], data: Hex, logIndex: number): Log<bigint, number, false> {
  return {
    address,
    topics,
    data,
    blockHash: `0x${"11".repeat(32)}`,
    blockNumber: 3n,
    logIndex,
    transactionHash: `0x${"22".repeat(32)}`,
    transactionIndex: 0,
    removed: false,
  };
}

function claimPostedLog(address: Address, claimId: bigint, evidenceHash: Hex, logIndex = 0): Log<bigint, number, false> {
  const topics: [Hex, ...Hex[]] = [
    toEventSelector(CLAIM_POSTED_EVENT),
    numberToHex(claimId, { size: 32 }),
    pad(ATTESTER),
    MARKET_ID,
  ];
  const data = encodeAbiParameters(parseAbiParameters("uint256, bytes32, string, uint64"), [
    200000000001n,
    evidenceHash,
    `http://127.0.0.1:8000/case-files/${evidenceHash}`,
    1793246294n,
  ]);
  return makeLog(address, topics, data, logIndex);
}

function withdrawnLog(address: Address): Log<bigint, number, false> {
  const event = parseAbiItem("event Withdrawn(address indexed account, uint256 amount)");
  const topics: [Hex, ...Hex[]] = [toEventSelector(event), pad(ATTESTER)];
  return makeLog(address, topics, encodeAbiParameters(parseAbiParameters("uint256"), [10n ** 16n]), 0);
}

describe("ClaimPosted receipt decoding", () => {
  it("matches the ClaimPosted event in the generated StressRegistry ABI", () => {
    const abi: ReadonlyArray<{
      type: string;
      name?: string;
      inputs?: ReadonlyArray<{ name: string; type: string; indexed?: boolean }>;
    }> = IStressRegistryAbi;
    const generated = abi.find((item) => item.type === "event" && item.name === "ClaimPosted");
    expect(generated).toBeDefined();
    const shape = (inputs: ReadonlyArray<{ name?: string; type: string; indexed?: boolean }>) =>
      inputs.map(({ name, type, indexed }) => ({ name, type, indexed: indexed ?? false }));
    expect(shape(CLAIM_POSTED_EVENT.inputs)).toEqual(shape(generated?.inputs ?? []));
  });

  it("returns the claim id from the registry's ClaimPosted event", () => {
    const result = extractPostedClaim(
      { status: "success", logs: [withdrawnLog(OTHER_CONTRACT), claimPostedLog(REGISTRY, 7n, EVIDENCE, 1)] },
      REGISTRY,
      EVIDENCE
    );
    expect(result).toEqual({ ok: true, claimId: 7n, evidenceHash: EVIDENCE });
  });

  it("compares the registry address case-insensitively", () => {
    const result = extractPostedClaim(
      { status: "success", logs: [claimPostedLog(REGISTRY, 12n, EVIDENCE)] },
      "0x5fbdb2315678afecb367f032d93f642f64180aa3",
      EVIDENCE
    );
    expect(result.ok && result.claimId).toBe(12n);
  });

  it("fails when the receipt has no logs", () => {
    const result = extractPostedClaim({ status: "success", logs: [] }, REGISTRY, EVIDENCE);
    expect(result.ok).toBe(false);
  });

  it("ignores a ClaimPosted event emitted by another contract", () => {
    const result = extractPostedClaim(
      { status: "success", logs: [claimPostedLog(OTHER_CONTRACT, 7n, EVIDENCE)] },
      REGISTRY,
      EVIDENCE
    );
    expect(result).toEqual({ ok: false, reason: "The receipt has no ClaimPosted event from the registry." });
  });

  it("fails when the registry emitted only an unrelated event", () => {
    const result = extractPostedClaim({ status: "success", logs: [withdrawnLog(REGISTRY)] }, REGISTRY, EVIDENCE);
    expect(result.ok).toBe(false);
  });

  it("fails for a reverted transaction even if a matching log is present", () => {
    const result = extractPostedClaim(
      { status: "reverted", logs: [claimPostedLog(REGISTRY, 7n, EVIDENCE)] },
      REGISTRY,
      EVIDENCE
    );
    expect(result).toEqual({ ok: false, reason: "The transaction reverted; no claim was posted." });
  });

  it("fails when the posted evidence hash is not the published case file", () => {
    const result = extractPostedClaim(
      { status: "success", logs: [claimPostedLog(REGISTRY, 7n, OTHER_EVIDENCE)] },
      REGISTRY,
      EVIDENCE
    );
    expect(result.ok).toBe(false);
  });

  it("fails when the registry emitted more than one ClaimPosted event", () => {
    const result = extractPostedClaim(
      { status: "success", logs: [claimPostedLog(REGISTRY, 7n, EVIDENCE, 0), claimPostedLog(REGISTRY, 8n, EVIDENCE, 1)] },
      REGISTRY,
      EVIDENCE
    );
    expect(result).toEqual({ ok: false, reason: "Expected one ClaimPosted event from the registry, found 2." });
  });
});
