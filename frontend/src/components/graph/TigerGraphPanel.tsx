"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Database, Loader2, XCircle } from "lucide-react";
import { BACKEND_URL } from "@/lib/api/client";
import { formatUsd8 } from "@/lib/format";
import { fetchTigerGraphExposure, tigerGraphLabels, type TigerGraphResult } from "@/lib/graph/tigergraph";

const TOTAL_LABELS: Array<[keyof Extract<TigerGraphResult, { status: "live" }>["data"]["totals"], string, boolean]> = [
  ["accounts", "Accounts", false],
  ["liquidatable_accounts", "Liquidatable", false],
  ["residual_bad_debt_usd8", "Residual bad debt", true],
  ["liquidation_volume_usd8", "Liquidation volume", true],
  ["debt_at_risk_usd8", "Debt at risk", true],
];

function Badge({ text, tone }: { text: string; tone: "live" | "synthetic" | "off" }) {
  const cls = tone === "live" ? "border-emerald-500 text-emerald-300 bg-emerald-950/50"
    : tone === "synthetic" ? "border-amber-500 text-amber-300 bg-amber-950/50" : "border-border text-muted-foreground bg-secondary";
  return <span className={`text-[10px] font-bold uppercase border px-1.5 py-0.5 ${cls}`}>{text}</span>;
}

/** Live TigerGraph exposure for the selected evidence hash. Separate from, and never replacing, the local graph. */
export function TigerGraphPanel({ evidenceHash }: { evidenceHash: string }) {
  const [result, setResult] = useState<TigerGraphResult | null>(null);

  useEffect(() => {
    let current = true;
    setResult(null);
    void fetchTigerGraphExposure(evidenceHash, BACKEND_URL).then((r) => current && setResult(r));
    return () => { current = false; };
  }, [evidenceHash]);

  const labels = result ? tigerGraphLabels(result) : null;
  return (
    <section aria-label="TigerGraph exposure" className="bg-card border-2 border-border p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Database className="h-4 w-4 text-[#ea580c]" />
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-foreground">TigerGraph exposure query</h2>
        {!result && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        {labels && <Badge text={labels.source} tone={result?.status === "live" ? "live" : "off"} />}
        {labels?.dataClass && <Badge text={labels.dataClass} tone="synthetic" />}
      </div>

      {result?.status === "unavailable" && (
        <p className="text-xs text-muted-foreground">{result.detail} The local graph above does not depend on TigerGraph.</p>
      )}
      {result?.status === "notLoaded" && (
        <p className="text-xs text-muted-foreground">TigerGraph answered, but this case file has not been loaded into the graph.</p>
      )}
      {result?.status === "live" && (
        <>
          <p className="text-[11px] text-muted-foreground break-all">
            Installed query <span className="text-foreground">{result.data.query}</span> on graph {result.data.graph} at {result.data.host}.
            Estimated exposure; informational only, never part of a verdict.
          </p>
          <dl className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {TOTAL_LABELS.map(([key, label, usd]) => (
              <div key={key} className="border border-border p-2">
                <dt className="text-[10px] uppercase text-muted-foreground">{label}</dt>
                <dd className="text-xs text-foreground">{usd ? formatUsd8(result.data.totals[key]) : result.data.totals[key]}</dd>
              </div>
            ))}
          </dl>
          <p className={`text-[11px] flex items-center gap-1.5 ${result.data.reconciliation.status === "matched" ? "text-emerald-400" : result.data.reconciliation.status === "mismatch" ? "text-red-400" : "text-muted-foreground"}`}>
            {result.data.reconciliation.status === "matched" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
            {result.data.reconciliation.status === "matched" && "TigerGraph totals match the stored case file exactly."}
            {result.data.reconciliation.status === "mismatch" && "TigerGraph totals differ from the stored case file: " +
              result.data.reconciliation.checks.filter((c) => !c.matches).map((c) => c.name).join(", ")}
            {result.data.reconciliation.status === "notChecked" && "Not reconciled: the case file is not stored on this backend."}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] text-left">
              <caption className="sr-only">Top accounts by residual bad debt, from TigerGraph</caption>
              <thead className="text-[10px] uppercase text-muted-foreground border-b border-border">
                <tr>{["Account", "Class", "Liquidatable", "Debt", "Repaid", "Residual"].map((h) => <th key={h} className="px-2 py-1.5 whitespace-nowrap">{h}</th>)}</tr>
              </thead>
              <tbody>
                {result.data.rows.map((r) => (
                  <tr key={r.accountId} className="border-b border-border/50">
                    <td className="px-2 py-1">{r.accountId}</td>
                    <td className="px-2 py-1">{r.dataClass}</td>
                    <td className="px-2 py-1">{r.liquidatable ? "Yes" : "No"}</td>
                    <td className="px-2 py-1">{formatUsd8(r.debtUsd8)}</td>
                    <td className="px-2 py-1">{formatUsd8(r.repaidUsd8)}</td>
                    <td className="px-2 py-1">{formatUsd8(r.residualUsd8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
