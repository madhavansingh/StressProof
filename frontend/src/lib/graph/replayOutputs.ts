import type { ParseIssue, ParseResult, ReplayOutputRow } from "./types";

/** Hard limits so a hostile or corrupt file cannot freeze the page. */
export const MAX_OUTPUT_BYTES = 5_000_000;
export const MAX_OUTPUT_ROWS = 20_000;
const MAX_REPORTED_ISSUES = 20;

const UINT = /^(0|[1-9][0-9]{0,77})$/;
const ACCOUNT_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const KEYS = ["collateralValueUsd8", "id", "liquidatable", "repaidUsd8", "residualUsd8"] as const;

function checkRow(value: unknown): string | ReplayOutputRow {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "not a JSON object";
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  if (keys.length !== KEYS.length || keys.some((k, i) => k !== KEYS[i])) {
    return `expected exactly the keys ${KEYS.join(", ")}`;
  }
  if (typeof obj.id !== "string" || !ACCOUNT_ID.test(obj.id)) return "id must be 1-128 characters of [A-Za-z0-9._:-]";
  if (typeof obj.liquidatable !== "boolean") return "liquidatable must be true or false";
  for (const k of ["collateralValueUsd8", "repaidUsd8", "residualUsd8"] as const) {
    if (typeof obj[k] !== "string" || !UINT.test(obj[k] as string)) return `${k} must be a non-negative integer string`;
  }
  return {
    id: obj.id,
    collateralValueUsd8: obj.collateralValueUsd8 as string,
    repaidUsd8: obj.repaidUsd8 as string,
    residualUsd8: obj.residualUsd8 as string,
    liquidatable: obj.liquidatable,
  };
}

/**
 * Parse replay outputs JSONL strictly. Any malformed line or duplicate account id fails the whole file:
 * a partial graph would silently misrepresent the replay. An empty file parses to zero rows.
 */
export function parseReplayOutputs(text: string): ParseResult<ReplayOutputRow[]> {
  if (typeof text !== "string") return { ok: false, issues: [{ line: 0, message: "input is not text" }] };
  if (text.length > MAX_OUTPUT_BYTES) {
    return { ok: false, issues: [{ line: 0, message: `file is larger than ${MAX_OUTPUT_BYTES} bytes` }] };
  }
  const lines = text.split("\n");
  if (lines[lines.length - 1] === "") lines.pop(); // single trailing newline
  if (lines.length > MAX_OUTPUT_ROWS) {
    return { ok: false, issues: [{ line: 0, message: `more than ${MAX_OUTPUT_ROWS} rows` }] };
  }

  const issues: ParseIssue[] = [];
  const rows: ReplayOutputRow[] = [];
  const seen = new Map<string, number>();
  lines.forEach((raw, idx) => {
    if (issues.length >= MAX_REPORTED_ISSUES) return;
    const line = idx + 1;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      issues.push({ line, message: raw.trim() === "" ? "blank line" : "invalid JSON" });
      return;
    }
    const row = checkRow(parsed);
    if (typeof row === "string") {
      issues.push({ line, message: row });
      return;
    }
    const first = seen.get(row.id);
    if (first !== undefined) {
      issues.push({ line, message: `duplicate account id ${row.id} (first on line ${first})` });
      return;
    }
    seen.set(row.id, line);
    rows.push(row);
  });

  return issues.length > 0 ? { ok: false, issues } : { ok: true, value: rows };
}
