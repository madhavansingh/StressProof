import type { GraphCaseFile, ParseIssue, ParseResult, SnapshotAccount } from "./types";

const UINT = /^(0|[1-9][0-9]{0,77})$/;
const SHORT_TEXT = /^[\x20-\x7e]{1,128}$/; // printable ASCII; rendered as text only

type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null;
}

class Reader {
  issues: ParseIssue[] = [];

  fail(path: string, message: string): void {
    this.issues.push({ line: 0, message: `${path}: ${message}` });
  }

  text(o: Obj | null, key: string, path: string): string {
    const v = o?.[key];
    if (typeof v === "string" && SHORT_TEXT.test(v)) return v;
    this.fail(`${path}.${key}`, "missing or not short printable text");
    return "";
  }

  uint(o: Obj | null, key: string, path: string): string {
    const v = o?.[key];
    if (typeof v === "string" && UINT.test(v)) return v;
    this.fail(`${path}.${key}`, "missing or not a non-negative integer string");
    return "0";
  }

  int(o: Obj | null, key: string, path: string): number {
    const v = o?.[key];
    if (typeof v === "number" && Number.isSafeInteger(v)) return v;
    this.fail(`${path}.${key}`, "missing or not an integer");
    return 0;
  }
}

function readAccounts(r: Reader, snapshot: Obj | null): SnapshotAccount[] {
  const list = snapshot?.accounts;
  if (!Array.isArray(list)) {
    r.fail("snapshot.accounts", "missing or not a list");
    return [];
  }
  return list.map((raw, i) => {
    const a = obj(raw);
    const path = `snapshot.accounts[${i}]`;
    return {
      id: r.text(a, "id", path),
      origin: r.text(a, "origin", path),
      collateralAmount: r.uint(a, "collateralAmount", path),
      debtUsd8: r.uint(a, "debtUsd8", path),
    };
  });
}

/**
 * Read the fields the graph needs from a parsed case file. The caller must have checked that the raw bytes
 * hash to the evidenceHash first; this only checks shape. Missing fields are reported, never guessed.
 */
export function readGraphCaseFile(value: unknown): ParseResult<GraphCaseFile> {
  const root = obj(value);
  if (!root) return { ok: false, issues: [{ line: 0, message: "case file is not a JSON object" }] };
  const r = new Reader();
  const dataset = obj(root.dataset);
  const scenario = obj(root.scenario);
  const results = obj(root.results);
  const model = obj(root.model);
  const snapshot = obj(root.snapshot);

  const scenarioAsset = r.text(scenario, "asset", "scenario");
  const assets = obj(snapshot?.assets);
  const collateralRaw = obj(assets?.[scenarioAsset]);
  if (!collateralRaw) r.fail(`snapshot.assets.${scenarioAsset || "?"}`, "scenario asset has no parameters");

  const allowlist = dataset?.stablecoinAllowlist;
  const stablecoins = Array.isArray(allowlist)
    ? allowlist.map((s, i) => r.text(obj(s), "symbol", `dataset.stablecoinAllowlist[${i}]`))
    : [];
  if (stablecoins.length === 0) r.fail("dataset.stablecoinAllowlist", "missing or empty");

  const parsed: GraphCaseFile = {
    dataClass: r.text(root, "dataClass", "case file"),
    marketId: r.text(root, "marketId", "case file"),
    network: r.text(dataset, "network", "dataset"),
    datasetId: r.text(dataset, "datasetId", "dataset"),
    modelId: r.text(model, "id", "model"),
    scenario: { asset: scenarioAsset, shockBps: r.int(scenario, "shockBps", "scenario") },
    results: {
      liquidatableAccounts: r.int(results, "liquidatableAccounts", "results"),
      residualBadDebtUsd8: r.uint(results, "residualBadDebtUsd8", "results"),
      liquidationVolumeUsd8: r.uint(results, "liquidationVolumeUsd8", "results"),
      debtAtRiskUsd8: r.uint(results, "debtAtRiskUsd8", "results"),
    },
    collateral: {
      symbol: scenarioAsset,
      decimals: r.int(collateralRaw, "decimals", "collateral"),
      priceUsd8: r.uint(collateralRaw, "priceUsd8", "collateral"),
      ltBps: r.int(collateralRaw, "ltBps", "collateral"),
      bonusBps: r.int(collateralRaw, "bonusBps", "collateral"),
    },
    stablecoins,
    accounts: readAccounts(r, snapshot),
  };
  return r.issues.length > 0 ? { ok: false, issues: r.issues.slice(0, 20) } : { ok: true, value: parsed };
}
