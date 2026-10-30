import { verifyBytes } from "@/lib/validation/verify";
import { readGraphCaseFile } from "./caseFile";
import { parseReplayOutputs } from "./replayOutputs";
import type { GraphCaseFile, ParseIssue, ReplayOutputRow } from "./types";

export const EVIDENCE_HASH = /^0x[0-9a-f]{64}$/;

export type GraphLoadResult =
  | { status: "ok"; outputs: ReplayOutputRow[]; caseFile: GraphCaseFile; outputBytes: number }
  | { status: "invalidHash" }
  | { status: "caseFileMissing" }
  | { status: "outputsMissing"; caseFile: GraphCaseFile }
  | { status: "error"; message: string; issues?: ParseIssue[] };

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

function describe(err: unknown): string {
  return err instanceof Error ? err.message : "unknown network error";
}

async function getBytes(fetchImpl: FetchLike, url: string): Promise<{ status: number; bytes?: Uint8Array }> {
  const res = await fetchImpl(url, { cache: "no-store" });
  if (!res.ok) return { status: res.status };
  return { status: res.status, bytes: new Uint8Array(await res.arrayBuffer()) };
}

async function loadCaseFile(fetchImpl: FetchLike, base: string, hash: string): Promise<GraphLoadResult | GraphCaseFile> {
  const res = await getBytes(fetchImpl, `${base}/case-files/${hash}`);
  if (res.status === 404) return { status: "caseFileMissing" };
  if (!res.bytes) return { status: "error", message: `Case file request failed: HTTP ${res.status}` };
  const verified = verifyBytes(res.bytes, hash);
  if (!verified.valid) {
    return {
      status: "error",
      message: `Case file bytes hash to ${verified.computedHash || "?"}, not ${hash}. The graph is not drawn from unverified data.`,
    };
  }
  const parsed = readGraphCaseFile(verified.rawJson);
  if (!parsed.ok) return { status: "error", message: "The case file is missing fields the graph needs.", issues: parsed.issues };
  return parsed.value;
}

/**
 * Load the two sources for one evidenceHash: the case file (bytes must hash to the evidenceHash) and the
 * replay outputs written by /stress/run. Read-only; no writes and no wallet.
 */
export async function loadGraphData(
  evidenceHash: string,
  backendUrl: string,
  fetchImpl: FetchLike = fetch,
): Promise<GraphLoadResult> {
  const hash = evidenceHash.trim();
  if (!EVIDENCE_HASH.test(hash)) return { status: "invalidHash" };
  const base = backendUrl.replace(/\/+$/, "");
  try {
    const caseFile = await loadCaseFile(fetchImpl, base, hash);
    if ("status" in caseFile) return caseFile;
    const out = await getBytes(fetchImpl, `${base}/replay-outputs/${hash}`);
    if (out.status === 404) return { status: "outputsMissing", caseFile };
    if (!out.bytes) return { status: "error", message: `Replay outputs request failed: HTTP ${out.status}` };
    const parsed = parseReplayOutputs(new TextDecoder("utf-8", { fatal: false }).decode(out.bytes));
    if (!parsed.ok) return { status: "error", message: "The replay outputs file is malformed.", issues: parsed.issues };
    return { status: "ok", outputs: parsed.value, caseFile, outputBytes: out.bytes.length };
  } catch (err: unknown) {
    return { status: "error", message: `Backend unreachable: ${describe(err)}` };
  }
}
