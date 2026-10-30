import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { loadGraphData } from "@/lib/graph/loader";
import { buildEvidenceOptions } from "@/lib/graph/evidenceOptions";
import { IDENTITY, panBy, zoomAt, MAX_ZOOM, MIN_ZOOM } from "@/lib/graph/view";

const REPO = path.resolve(__dirname, "../..");
const CASE_BYTES = readFileSync(path.join(REPO, "data/fixtures/casefile_v1.json"));
const CASE_HASH = readFileSync(path.join(REPO, "data/fixtures/casefile_v1.keccak"), "utf8").trim();
const OUTPUTS = readFileSync(path.join(__dirname, "fixtures/replay_outputs_v1.jsonl"));
const BASE = "http://backend.test";

type Routes = Record<string, { status: number; body?: Uint8Array | string }>;

function fakeFetch(routes: Routes) {
  const calls: string[] = [];
  const impl = async (url: string) => {
    calls.push(url);
    const r = routes[url];
    if (!r) return new Response("missing", { status: 404 });
    return new Response((r.body ?? "") as BodyInit, { status: r.status });
  };
  return { impl, calls };
}

const ok = (): Routes => ({
  [`${BASE}/case-files/${CASE_HASH}`]: { status: 200, body: CASE_BYTES },
  [`${BASE}/replay-outputs/${CASE_HASH}`]: { status: 200, body: OUTPUTS },
});

describe("loadGraphData", () => {
  it("loads a hash-verified case file and its replay outputs", async () => {
    const { impl, calls } = fakeFetch(ok());
    const r = await loadGraphData(CASE_HASH, `${BASE}/`, impl);
    expect(r.status).toBe("ok");
    if (r.status === "ok") expect(r.outputs).toHaveLength(6);
    expect(calls).toEqual([`${BASE}/case-files/${CASE_HASH}`, `${BASE}/replay-outputs/${CASE_HASH}`]);
  });

  it.each(["", "0x123", CASE_HASH.toUpperCase(), CASE_HASH.slice(2), `${CASE_HASH}/../x`])(
    "rejects a malformed hash without any request (%s)",
    async (hash) => {
      const { impl, calls } = fakeFetch(ok());
      expect((await loadGraphData(hash, BASE, impl)).status).toBe("invalidHash");
      expect(calls).toEqual([]);
    },
  );

  it("refuses case-file bytes that do not hash to the evidenceHash", async () => {
    const routes = ok();
    routes[`${BASE}/case-files/${CASE_HASH}`] = { status: 200, body: Buffer.concat([CASE_BYTES, Buffer.from(" ")]) };
    const r = await loadGraphData(CASE_HASH, BASE, fakeFetch(routes).impl);
    expect(r.status).toBe("error");
    if (r.status === "error") expect(r.message).toMatch(/not drawn from unverified data/);
  });

  it("reports a missing case file", async () => {
    expect((await loadGraphData(CASE_HASH, BASE, fakeFetch({}).impl)).status).toBe("caseFileMissing");
  });

  it("reports missing replay outputs as unavailable, keeping the verified case file", async () => {
    const routes = ok();
    delete routes[`${BASE}/replay-outputs/${CASE_HASH}`];
    const r = await loadGraphData(CASE_HASH, BASE, fakeFetch(routes).impl);
    expect(r.status).toBe("outputsMissing");
  });

  it("reports malformed replay outputs with line numbers", async () => {
    const routes = ok();
    routes[`${BASE}/replay-outputs/${CASE_HASH}`] = { status: 200, body: "{bad}\n" };
    const r = await loadGraphData(CASE_HASH, BASE, fakeFetch(routes).impl);
    expect(r).toEqual({ status: "error", message: "The replay outputs file is malformed.", issues: [{ line: 1, message: "invalid JSON" }] });
  });

  it("reports server errors and network failures", async () => {
    const routes = ok();
    routes[`${BASE}/replay-outputs/${CASE_HASH}`] = { status: 503 };
    const r = await loadGraphData(CASE_HASH, BASE, fakeFetch(routes).impl);
    expect(r).toEqual({ status: "error", message: "Replay outputs request failed: HTTP 503" });
    const down = await loadGraphData(CASE_HASH, BASE, async () => { throw new TypeError("Failed to fetch"); });
    expect(down).toEqual({ status: "error", message: "Backend unreachable: Failed to fetch" });
  });
});

describe("zoom and pan", () => {
  it("zooms around the pointer and clamps the scale", () => {
    const t = zoomAt(IDENTITY, 2, 100, 50);
    expect(t).toEqual({ k: 2, x: -100, y: -50 });
    expect(zoomAt(t, 100, 0, 0).k).toBe(MAX_ZOOM);
    expect(zoomAt(t, 0.0001, 0, 0).k).toBe(MIN_ZOOM);
    expect(zoomAt(t, NaN, 0, 0)).toBe(t);
  });

  it("pans without changing the scale and ignores non-finite moves", () => {
    expect(panBy(IDENTITY, 10, -5)).toEqual({ k: 1, x: 10, y: -5 });
    expect(panBy(IDENTITY, Infinity, 0)).toBe(IDENTITY);
  });
});

describe("buildEvidenceOptions", () => {
  const H1 = "0x" + "a1".repeat(32);
  const H2 = "0x" + "b2".repeat(32);
  const claim = (id: number, evidenceHash: string) => ({
    id: BigInt(id), attester: `0x${"11".repeat(20)}`, challengeDeadline: BigInt(0), state: 1, stateName: "PENDING",
    reason: 0, reasonName: "NONE", challenger: `0x${"00".repeat(20)}`, resolutionDeadline: BigInt(0),
    marketId: `0x${"00".repeat(32)}`, evidenceHash, replayReportHash: `0x${"00".repeat(32)}`,
    claimedResidualBadDebt: BigInt(200000000001), counterResidualBadDebt: BigInt(0), caseFileURI: "", replayReportURI: "",
  }) as unknown as import("@/lib/claims").OnChainClaim;
  const feed = (seq: number, kind: string, evidenceHash: unknown) => ({ seq, ts: "", actor: "backend", kind, data: { evidenceHash } });

  it("lists claim-linked hashes first, grouping claims that share a hash", () => {
    const opts = buildEvidenceOptions([claim(1, H1), claim(2, H2), claim(3, H1.toUpperCase().replace("0X", "0x"))], []);
    expect(opts.map((o) => [o.hash, o.label])).toEqual([[H1, "Claims #3, #1"], [H2, "Claims #2"]]);
    expect(opts[0].claims.map((c) => c.id)).toEqual(["3", "1"]);
  });

  it("adds stress runs from the feed, newest first, ignoring malformed and non-run entries", () => {
    const opts = buildEvidenceOptions([claim(1, H1)], [
      feed(1, "CLAIM_BUILT", H2), feed(2, "CLAIM_BUILT", H1), feed(3, "CLAIM_BUILT", "<img src=x>"),
      feed(4, "CLAIM_POSTED", "0x" + "c3".repeat(32)), feed(5, "CLAIM_BUILT", 42),
    ]);
    expect(opts.map((o) => o.label)).toEqual(["Claims #1", "Stress run, feed #1"]);
  });
});
