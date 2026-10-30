import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { parseReplayOutputs } from "@/lib/graph/replayOutputs";
import { readGraphCaseFile } from "@/lib/graph/caseFile";
import { accountOutcome, buildExposureGraph, consistencyChecks, nodeIds } from "@/lib/graph/buildGraph";
import { filterGraph, layoutGraph, MAX_RENDERED_ACCOUNTS, neighbours, resolveSelection } from "@/lib/graph/view";
import type { GraphCaseFile, ReplayOutputRow } from "@/lib/graph/types";

// Golden case file (committed) and the replay outputs the core replayer produces for it
// (frontend/tests/fixtures/replay_outputs_v1.jsonl, generated with stressproof_core.replay, not hand-written).
const REPO = path.resolve(__dirname, "../..");
const CASE_BYTES = readFileSync(path.join(REPO, "data/fixtures/casefile_v1.json"));
const CASE_HASH = readFileSync(path.join(REPO, "data/fixtures/casefile_v1.keccak"), "utf8").trim();
const OUTPUTS_TEXT = readFileSync(path.join(__dirname, "fixtures/replay_outputs_v1.jsonl"), "utf8");

function caseFile(): GraphCaseFile {
  const r = readGraphCaseFile(JSON.parse(CASE_BYTES.toString("utf8")));
  if (!r.ok) throw new Error(JSON.stringify(r.issues));
  return r.value;
}

function outputs(text = OUTPUTS_TEXT): ReplayOutputRow[] {
  const r = parseReplayOutputs(text);
  if (!r.ok) throw new Error(JSON.stringify(r.issues));
  return r.value;
}

const ROW = '{"collateralValueUsd8":"1","id":"a-1","liquidatable":false,"repaidUsd8":"0","residualUsd8":"0"}';

describe("parseReplayOutputs", () => {
  it("parses the replayer's canonical JSONL", () => {
    const rows = outputs();
    expect(rows).toHaveLength(6);
    expect(rows[1]).toEqual({
      id: "synth-0002", collateralValueUsd8: "1050000000000", repaidUsd8: "1000000000000",
      residualUsd8: "200000000000", liquidatable: true,
    });
  });

  it("treats an empty file as zero rows (empty state, not an error)", () => {
    expect(parseReplayOutputs("")).toEqual({ ok: true, value: [] });
  });

  it.each([
    ["invalid JSON", "{not json"],
    ["a blank line in the middle", `${ROW}\n\n${ROW.replace("a-1", "a-2")}`],
    ["a non-object", "[1,2]"],
    ["a missing key", '{"id":"a","liquidatable":true,"repaidUsd8":"0","residualUsd8":"0"}'],
    ["an extra key", ROW.replace("}", ',"extra":1}')],
    ["a number instead of an integer string", ROW.replace('"repaidUsd8":"0"', '"repaidUsd8":0')],
    ["a negative amount", ROW.replace('"repaidUsd8":"0"', '"repaidUsd8":"-5"')],
    ["a decimal amount", ROW.replace('"repaidUsd8":"0"', '"repaidUsd8":"1.5"')],
    ["a leading-zero amount", ROW.replace('"repaidUsd8":"0"', '"repaidUsd8":"01"')],
    ["a string boolean", ROW.replace("false", '"false"')],
    ["markup in the id", ROW.replace("a-1", "<script>")],
    ["an empty id", ROW.replace("a-1", "")],
  ])("rejects %s", (_name, text) => {
    const r = parseReplayOutputs(text);
    expect(r.ok).toBe(false);
  });

  it("rejects duplicate account ids and names both lines", () => {
    const r = parseReplayOutputs(`${ROW}\n${ROW}\n`);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.issues[0]).toEqual({ line: 2, message: "duplicate account id a-1 (first on line 1)" });
  });

  it("fails the whole file on one bad line instead of drawing a partial graph", () => {
    const r = parseReplayOutputs(`${OUTPUTS_TEXT}{oops}\n`);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.issues).toEqual([{ line: 7, message: "invalid JSON" }]);
  });

  it("rejects non-text input", () => {
    expect(parseReplayOutputs(undefined as unknown as string).ok).toBe(false);
  });
});

describe("readGraphCaseFile", () => {
  it("reads the golden case file", () => {
    const cf = caseFile();
    expect(cf.dataClass).toBe("SYNTHETIC");
    expect(cf.marketId).toBe("aave-v3-eth-weth-stable");
    expect(cf.collateral).toEqual({ symbol: "WETH", decimals: 18, priceUsd8: "300000000000", ltBps: 8300, bonusBps: 10500 });
    expect(cf.stablecoins).toEqual(["USDC"]);
    expect(cf.accounts).toHaveLength(6);
  });

  it("reports missing fields instead of guessing them", () => {
    const raw = JSON.parse(CASE_BYTES.toString("utf8"));
    delete raw.results.residualBadDebtUsd8;
    raw.snapshot.accounts[0].debtUsd8 = 5;
    const r = readGraphCaseFile(raw);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.map((i) => i.message)).toEqual([
        "results.residualBadDebtUsd8: missing or not a non-negative integer string",
        "snapshot.accounts[0].debtUsd8: missing or not a non-negative integer string",
      ]);
    }
  });

  it.each([null, [], "text", 7])("rejects a non-object case file (%s)", (value) => {
    expect(readGraphCaseFile(value).ok).toBe(false);
  });
});

describe("buildExposureGraph", () => {
  const graph = buildExposureGraph({ evidenceHash: CASE_HASH, outputs: outputs(), caseFile: caseFile() });

  it("creates typed nodes for the case file, market, both assets and every account", () => {
    const kinds = graph.nodes.map((n) => n.kind);
    expect(kinds.filter((k) => k === "account")).toHaveLength(6);
    expect(kinds.filter((k) => k !== "account")).toEqual(["evidence", "market", "collateralAsset", "debtAsset"]);
    expect(new Set(graph.nodes.map((n) => n.id)).size).toBe(graph.nodes.length);
  });

  it("draws only relationships the data records", () => {
    const accountEdges = graph.edges.filter((e) => e.source.startsWith("account:"));
    expect(accountEdges.every((e) => e.kind === "collateral" || e.kind === "debt")).toBe(true);
    expect(accountEdges.every((e) => e.dataSource === "caseFile")).toBe(true);
    // no account-to-account edges: the replay records none
    expect(graph.edges.some((e) => e.source.startsWith("account:") && e.target.startsWith("account:"))).toBe(false);
    const a1 = graph.edges.filter((e) => e.source === nodeIds.account("synth-0001"));
    expect(a1.map((e) => [e.kind, e.label])).toEqual([["collateral", "10 WETH"], ["debt", "$20,000.00"]]);
    const ids = new Set(graph.nodes.map((n) => n.id));
    expect(graph.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  });

  it("classifies outcomes from the replay outputs", () => {
    const outcomes = Object.fromEntries(graph.nodes.filter((n) => n.kind === "account").map((n) => [n.label, n.outcome]));
    expect(outcomes).toEqual({
      "synth-0001": "liquidated", "synth-0002": "badDebt", "synth-0003": "safe",
      "synth-0004": "safe", "synth-0005": "liquidated", "synth-0006": "badDebt",
    });
    expect(accountOutcome({ id: "x", collateralValueUsd8: "0", repaidUsd8: "0", residualUsd8: "0", liquidatable: false })).toBe("safe");
  });

  it("labels synthetic data as synthetic", () => {
    expect(graph.dataClass).toBe("SYNTHETIC");
    expect(graph.nodes.filter((n) => n.kind !== "claim").every((n) => n.synthetic)).toBe(true);
  });

  it("tags every displayed value with its source", () => {
    const acct = graph.nodes.find((n) => n.id === nodeIds.account("synth-0002"))!;
    const bySource = (s: string) => acct.details.filter((d) => d.source === s).map((d) => d.label);
    expect(bySource("caseFile")).toEqual(["Origin", "Collateral", "Debt"]);
    expect(bySource("replayOutput")).toContain("Residual bad debt");
    expect(acct.details.find((d) => d.label === "Residual bad debt")!.value).toBe("$2,000.00");
  });

  it("cross-checks per-account outputs against the case-file totals", () => {
    expect(graph.checks.map((c) => [c.name, c.matches])).toEqual([
      ["Liquidatable accounts", true], ["Residual bad debt", true],
      ["Liquidation volume", true], ["Debt at risk", true],
    ]);
    expect(graph.warnings).toEqual([]);
  });

  it("flags outputs that disagree with the case file", () => {
    const tampered = outputs().map((r) => (r.id === "synth-0002" ? { ...r, residualUsd8: "1" } : r));
    const checks = consistencyChecks(tampered, caseFile());
    expect(checks.find((c) => c.name === "Residual bad debt")!.matches).toBe(false);
  });

  it("warns about accounts present in only one source and draws no edges for them", () => {
    const extra = { id: "ghost-1", collateralValueUsd8: "0", repaidUsd8: "0", residualUsd8: "0", liquidatable: false };
    const g = buildExposureGraph({ evidenceHash: CASE_HASH, outputs: [...outputs().slice(1), extra], caseFile: caseFile() });
    expect(g.warnings).toEqual([
      "1 replay output account(s) have no case-file position: ghost-1",
      "1 case-file account(s) have no replay output: synth-0001",
    ]);
    expect(g.edges.some((e) => e.source === nodeIds.account("ghost-1"))).toBe(false);
  });

  it("links on-chain claims to the evidence once each", () => {
    const claim = { id: "1", stateName: "PENDING", attester: "0x" + "11".repeat(20), claimedResidualBadDebtUsd8: "200000000001" };
    const g = buildExposureGraph({ evidenceHash: CASE_HASH.toUpperCase().replace("0X", "0x"), outputs: outputs(), caseFile: caseFile(), claims: [claim, claim] });
    const attests = g.edges.filter((e) => e.kind === "attests");
    expect(attests).toEqual([expect.objectContaining({ source: "claim:1", target: nodeIds.evidence(CASE_HASH), dataSource: "onChain" })]);
    expect(g.nodes.find((n) => n.id === "claim:1")!.synthetic).toBe(false);
  });

  it("builds a context-only graph from empty outputs", () => {
    const g = buildExposureGraph({ evidenceHash: CASE_HASH, outputs: [], caseFile: caseFile() });
    expect(g.nodes.filter((n) => n.kind === "account")).toHaveLength(0);
    expect(g.checks.find((c) => c.name === "Liquidatable accounts")!.matches).toBe(false);
  });
});

describe("view helpers", () => {
  const graph = buildExposureGraph({ evidenceHash: CASE_HASH, outputs: outputs(), caseFile: caseFile() });
  const accountLabels = (v: ReturnType<typeof filterGraph>) => v.nodes.filter((n) => n.kind === "account").map((n) => n.label);

  it("filters accounts by outcome and keeps the context nodes", () => {
    const v = filterGraph(graph, { outcome: "badDebt", query: "" });
    expect(accountLabels(v)).toEqual(["synth-0002", "synth-0006"]);
    expect(v.nodes.filter((n) => n.kind !== "account")).toHaveLength(4);
    expect(v.edges.every((e) => v.nodes.some((n) => n.id === e.source) && v.nodes.some((n) => n.id === e.target))).toBe(true);
  });

  it("searches account ids case-insensitively", () => {
    expect(accountLabels(filterGraph(graph, { outcome: "all", query: "  SYNTH-0004 " }))).toEqual(["synth-0004"]);
    expect(filterGraph(graph, { outcome: "safe", query: "0001" }).matchedAccounts).toBe(0);
  });

  it("caps rendered accounts and says how many are hidden", () => {
    const many = Array.from({ length: MAX_RENDERED_ACCOUNTS + 5 }, (_, i) => ({
      id: `a-${i}`, collateralValueUsd8: "0", repaidUsd8: "0", residualUsd8: "0", liquidatable: false,
    }));
    const big = buildExposureGraph({ evidenceHash: CASE_HASH, outputs: many, caseFile: caseFile() });
    const v = filterGraph(big, { outcome: "all", query: "" });
    expect(v.hiddenByCap).toBe(5);
    expect(v.matchedAccounts).toBe(MAX_RENDERED_ACCOUNTS + 5);
  });

  it("lays out deterministically with a position for every visible node", () => {
    const v = filterGraph(graph, { outcome: "all", query: "" });
    const a = layoutGraph(v.nodes);
    expect(layoutGraph(v.nodes)).toEqual(a);
    expect(v.nodes.every((n) => a.positions[n.id] !== undefined)).toBe(true);
  });

  it("resolves the selection for the info panel and drops it when filtered out", () => {
    const id = nodeIds.account("synth-0002");
    const all = filterGraph(graph, { outcome: "all", query: "" });
    expect(resolveSelection(all.nodes, id)!.label).toBe("synth-0002");
    expect(resolveSelection(filterGraph(graph, { outcome: "safe", query: "" }).nodes, id)).toBeNull();
    expect(resolveSelection(all.nodes, null)).toBeNull();
    expect([...neighbours(all.edges, id)].sort()).toEqual([id, nodeIds.collateral("WETH"), nodeIds.debt()].sort());
  });
});
