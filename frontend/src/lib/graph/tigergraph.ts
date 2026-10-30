/**
 * Client for GET /graph/exposure (WP-5). The backend queries TigerGraph; this module only validates the reply.
 * A reply is shown as a TigerGraph result only when the backend says it came from TigerGraph. Nothing local is
 * ever substituted for it.
 */

import { EVIDENCE_HASH } from "./loader";

export interface TigerGraphExposureRow {
  accountId: string;
  origin: string;
  dataClass: string;
  liquidatable: boolean;
  debtUsd8: string;
  collateralValueUsd8: string;
  repaidUsd8: string;
  residualUsd8: string;
}

export interface TigerGraphCheck {
  name: string;
  tigergraph: string;
  caseFile: string;
  matches: boolean;
}

export interface TigerGraphExposure {
  host: string;
  graph: string;
  query: string;
  dataClass: string;
  totals: Record<"accounts" | "liquidatable_accounts" | "residual_bad_debt_usd8" | "liquidation_volume_usd8" | "debt_at_risk_usd8", string>;
  rows: TigerGraphExposureRow[];
  reconciliation: { status: "matched" | "mismatch" | "notChecked"; checks: TigerGraphCheck[] };
}

export type TigerGraphResult =
  | { status: "live"; data: TigerGraphExposure }
  | { status: "notLoaded" }
  | { status: "unavailable"; detail: string };

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

const UINT = /^(0|[1-9][0-9]{0,77})$/;
const TEXT = /^[\x20-\x7e]{0,200}$/;
const TOTAL_KEYS = ["accounts", "liquidatable_accounts", "residual_bad_debt_usd8", "liquidation_volume_usd8", "debt_at_risk_usd8"] as const;
const MAX_ROWS = 50;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): string | null => (typeof v === "string" && TEXT.test(v) ? v : null);
const uint = (v: unknown): string | null => (typeof v === "string" && UINT.test(v) ? v : null);

function parseRow(v: unknown): TigerGraphExposureRow | null {
  if (!isObj(v) || typeof v.liquidatable !== "boolean") return null;
  const row = {
    accountId: text(v.account_id), origin: text(v.origin), dataClass: text(v.data_class),
    debtUsd8: uint(v.debt_usd8), collateralValueUsd8: uint(v.collateral_value_usd8),
    repaidUsd8: uint(v.repaid_usd8), residualUsd8: uint(v.residual_usd8),
  };
  if (Object.values(row).some((x) => x === null)) return null;
  return { ...(row as Omit<TigerGraphExposureRow, "liquidatable">), liquidatable: v.liquidatable };
}

function parseChecks(v: unknown): TigerGraphExposure["reconciliation"] | null {
  if (!isObj(v) || !["matched", "mismatch", "notChecked"].includes(String(v.status)) || !Array.isArray(v.checks)) return null;
  const checks = v.checks.map((c) =>
    isObj(c) && text(c.name) && text(c.tigergraph) !== null && text(c.caseFile) !== null && typeof c.matches === "boolean"
      ? { name: c.name as string, tigergraph: c.tigergraph as string, caseFile: c.caseFile as string, matches: c.matches }
      : null,
  );
  if (checks.some((c) => c === null)) return null;
  return { status: v.status as TigerGraphExposure["reconciliation"]["status"], checks: checks as TigerGraphCheck[] };
}

/** Validate a 200 reply. Returns null when it is not a well-formed TigerGraph result. */
export function parseExposure(body: unknown): TigerGraphExposure | null {
  if (!isObj(body) || body.status !== "ok" || body.source !== "tigergraph" || !isObj(body.totals)) return null;
  const totals: Partial<TigerGraphExposure["totals"]> = {};
  for (const k of TOTAL_KEYS) {
    const v = uint((body.totals as Obj)[k]);
    if (v === null) return null;
    totals[k] = v;
  }
  const rawRows = Array.isArray(body.topExposures) ? body.topExposures.slice(0, MAX_ROWS) : null;
  const rows = rawRows?.map(parseRow);
  const reconciliation = parseChecks(body.reconciliation);
  const host = text(body.host), graph = text(body.graph), query = text(body.query), dataClass = text(body.dataClass);
  if (!rows || rows.some((r) => r === null) || !reconciliation || !host || !graph || !query || !dataClass) return null;
  return { host, graph, query, dataClass, totals: totals as TigerGraphExposure["totals"], rows: rows as TigerGraphExposureRow[], reconciliation };
}

export async function fetchTigerGraphExposure(evidenceHash: string, backendUrl: string, fetchImpl: FetchLike = fetch): Promise<TigerGraphResult> {
  if (!EVIDENCE_HASH.test(evidenceHash)) return { status: "unavailable", detail: "Not an evidence hash." };
  const url = `${backendUrl.replace(/\/+$/, "")}/graph/exposure?evidenceHash=${evidenceHash}&top=10`;
  try {
    const res = await fetchImpl(url, { cache: "no-store" });
    const body: unknown = await res.json().catch(() => null);
    if (res.status === 404 && isObj(body) && body.status === "notLoaded") return { status: "notLoaded" };
    if (res.ok) {
      const data = parseExposure(body);
      return data ? { status: "live", data } : { status: "unavailable", detail: "The backend reply was not a valid TigerGraph result." };
    }
    const detail = isObj(body) && text(body.detail) ? (body.detail as string) : `HTTP ${res.status}`;
    return { status: "unavailable", detail };
  } catch (err: unknown) {
    return { status: "unavailable", detail: `Backend unreachable: ${err instanceof Error ? err.message : "network error"}` };
  }
}

/** The headline label. "REAL TIGERGRAPH RESULTS" means the numbers came from a live TigerGraph query. */
export function tigerGraphLabels(result: TigerGraphResult): { source: string; dataClass: string | null } {
  if (result.status === "notLoaded") return { source: "TIGERGRAPH CONNECTED: CASE FILE NOT LOADED", dataClass: null };
  if (result.status !== "live") return { source: "TIGERGRAPH UNAVAILABLE", dataClass: null };
  return { source: "REAL TIGERGRAPH RESULTS", dataClass: result.data.dataClass === "SYNTHETIC" ? "SYNTHETIC FIXTURE DATA" : result.data.dataClass };
}
