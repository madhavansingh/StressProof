import { describe, it, expect, vi } from "vitest";
import { encodeAbiParameters, numberToHex, pad, parseAbiParameters, toEventSelector, type Abi, type Hex, type Log } from "viem";
import { CLAIM_POSTED_EVENT } from "../src/lib/web3/claimPosted";
import {
  buildPostClaimRequest,
  settlePublishReceipt,
  verifyRegistryBeforeSigning,
  type RegistryReader,
} from "../src/lib/web3/postClaimRequest";
import deployment from "../../deployments/31337.json";

const REGISTRY = deployment.registry as `0x${string}`;
const MARKET_ID = deployment.marketId as Hex;
const BOND = BigInt(deployment.bondWei);
const EVIDENCE: Hex = "0x9b0f9c87fb81f5624639685d12812678db22e76f35dcf8394d7afeee1bd0f3a6";
const ABI: Abi = [{ type: "function", name: "BOND", inputs: [], outputs: [{ type: "uint256" }], stateMutability: "view" }];

const input = {
  chainId: 31337,
  registry: REGISTRY,
  marketId: MARKET_ID,
  bondWei: BOND,
  residualBadDebtUsd8: "200000000001",
  evidenceHash: EVIDENCE,
  caseFileURI: `http://127.0.0.1:8000/case-files/${EVIDENCE}`,
};

describe("buildPostClaimRequest: destination, bond and chain before signing", () => {
  it("targets the deployment's registry with the deployment's 0.01 ETH bond on the pinned chain", () => {
    const req = buildPostClaimRequest(input);
    expect(req.address).toBe(REGISTRY);
    expect(req.value).toBe(10_000_000_000_000_000n);
    expect(req.chainId).toBe(31337);
    expect(req.functionName).toBe("postClaim");
    expect(req.args).toEqual([MARKET_ID, 200000000001n, EVIDENCE, input.caseFileURI]);
  });

  it("refuses a zero registry, zero bond, malformed hashes or amounts", () => {
    expect(() => buildPostClaimRequest({ ...input, registry: "0x0000000000000000000000000000000000000000" })).toThrow(/registry/);
    expect(() => buildPostClaimRequest({ ...input, bondWei: 0n })).toThrow(/Bond/);
    expect(() => buildPostClaimRequest({ ...input, evidenceHash: "0x1234" })).toThrow(/evidenceHash/);
    expect(() => buildPostClaimRequest({ ...input, marketId: "0x00" as Hex })).toThrow(/marketId/);
    expect(() => buildPostClaimRequest({ ...input, residualBadDebtUsd8: "1.5" })).toThrow(/residual/);
    expect(() => buildPostClaimRequest({ ...input, caseFileURI: "" })).toThrow(/caseFileURI/);
  });
});

function reader(code: Hex | undefined, bond: unknown, fail?: "code" | "bond"): RegistryReader {
  return {
    getCode: vi.fn(async () => {
      if (fail === "code") throw new Error("rpc down");
      return code;
    }),
    readContract: vi.fn(async () => {
      if (fail === "bond") throw new Error("revert");
      return bond;
    }),
  };
}

describe("verifyRegistryBeforeSigning: on-chain check of destination and bond", () => {
  it("passes when the registry has code and BOND() equals the value to send", async () => {
    const r = reader("0x6080", BOND);
    expect(await verifyRegistryBeforeSigning(r, REGISTRY, ABI, BOND)).toEqual({ ok: true });
    expect(r.readContract).toHaveBeenCalledWith({ address: REGISTRY, abi: ABI, functionName: "BOND" });
  });

  it("refuses when there is no contract at the destination", async () => {
    expect(await verifyRegistryBeforeSigning(reader("0x", BOND), REGISTRY, ABI, BOND)).toMatchObject({ ok: false });
    expect(await verifyRegistryBeforeSigning(reader(undefined, BOND), REGISTRY, ABI, BOND)).toMatchObject({ ok: false });
  });

  it("refuses when the on-chain bond differs from the configured bond", async () => {
    const r = await verifyRegistryBeforeSigning(reader("0x6080", BOND * 2n), REGISTRY, ABI, BOND);
    expect(r).toMatchObject({ ok: false });
    if (!r.ok) expect(r.reason).toContain("BOND()");
  });

  it("refuses when the chain cannot be read", async () => {
    expect(await verifyRegistryBeforeSigning(reader("0x6080", BOND, "code"), REGISTRY, ABI, BOND)).toMatchObject({ ok: false });
    expect(await verifyRegistryBeforeSigning(reader("0x6080", BOND, "bond"), REGISTRY, ABI, BOND)).toMatchObject({ ok: false });
  });
});

function claimPostedLog(claimId: bigint): Log<bigint, number, false> {
  const topics: [Hex, ...Hex[]] = [
    toEventSelector(CLAIM_POSTED_EVENT),
    numberToHex(claimId, { size: 32 }),
    pad("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"),
    MARKET_ID,
  ];
  const data = encodeAbiParameters(parseAbiParameters("uint256, bytes32, string, uint64"), [
    200000000001n,
    EVIDENCE,
    input.caseFileURI,
    1793246294n,
  ]);
  return {
    address: REGISTRY, topics, data, blockHash: `0x${"11".repeat(32)}`, blockNumber: 3n, logIndex: 0,
    transactionHash: `0x${"22".repeat(32)}`, transactionIndex: 0, removed: false,
  };
}

describe("settlePublishReceipt: verify the receipt, then refresh claim and feed data", () => {
  it("refreshes only after a successful receipt with the registry's ClaimPosted event", () => {
    const refresh = vi.fn();
    const r = settlePublishReceipt({ status: "success", logs: [claimPostedLog(5n)] }, REGISTRY, EVIDENCE, refresh);
    expect(r).toEqual({ ok: true, claimId: 5n, evidenceHash: EVIDENCE });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh or report a claim for a reverted transaction", () => {
    const refresh = vi.fn();
    const r = settlePublishReceipt({ status: "reverted", logs: [claimPostedLog(5n)] }, REGISTRY, EVIDENCE, refresh);
    expect(r.ok).toBe(false);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not refresh when the receipt lacks the event", () => {
    const refresh = vi.fn();
    expect(settlePublishReceipt({ status: "success", logs: [] }, REGISTRY, EVIDENCE, refresh).ok).toBe(false);
    expect(refresh).not.toHaveBeenCalled();
  });
});
