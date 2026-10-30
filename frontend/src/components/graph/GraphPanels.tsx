"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import type { ConsistencyCheck, GraphNode } from "@/lib/graph/types";
import { outcomeLabel } from "@/lib/graph/buildGraph";
import { EDGE_STYLE, KIND_COLOR, KIND_LABEL, OUTCOME_COLOR, SOURCE_LABEL } from "./graphStyle";

const PANEL = "bg-card border-2 border-border p-4 space-y-3";
const HEADING = "text-[11px] font-bold uppercase tracking-wider text-foreground";

/** Values are rendered as React text only, never as HTML (plan WP-6 security note). */
export function GraphInfoPanel({ node }: { node: GraphNode | null }) {
  if (!node) {
    return (
      <section className={PANEL} aria-live="polite">
        <h2 className={HEADING}>Details</h2>
        <p className="text-xs text-muted-foreground">Select a node to see its values and where each one comes from.</p>
      </section>
    );
  }
  return (
    <section className={PANEL} aria-live="polite">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] uppercase text-muted-foreground">{KIND_LABEL[node.kind]}</p>
          <h2 className="text-sm font-bold text-foreground break-all">{node.label}</h2>
        </div>
        {node.synthetic && (
          <span className="shrink-0 text-[10px] font-bold uppercase border border-amber-500 text-amber-300 bg-amber-950/60 px-1.5 py-0.5">
            SYNTHETIC
          </span>
        )}
      </div>
      {node.outcome && (
        <p className="text-xs font-bold" style={{ color: OUTCOME_COLOR[node.outcome] }}>{outcomeLabel(node.outcome)}</p>
      )}
      <dl className="space-y-2">
        {node.details.map((d) => (
          <div key={d.label} className="border-t border-border/60 pt-2">
            <dt className="flex items-center justify-between gap-2 text-[10px] uppercase text-muted-foreground">
              <span>{d.label}</span>
              <span className="border border-border px-1 text-[9px]">{SOURCE_LABEL[d.source]}</span>
            </dt>
            <dd className="text-xs text-foreground break-all mt-0.5">{d.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function GraphLegend() {
  const swatch = (color: string) => <span className="inline-block h-3 w-3 border-2 shrink-0" style={{ borderColor: color, background: `${color}40` }} />;
  return (
    <section className={PANEL} aria-label="Legend">
      <h2 className={HEADING}>Legend</h2>
      <ul className="grid grid-cols-1 gap-1.5 text-[11px] text-foreground">
        {(Object.keys(OUTCOME_COLOR) as Array<keyof typeof OUTCOME_COLOR>).map((o) => (
          <li key={o} className="flex items-center gap-2">{swatch(OUTCOME_COLOR[o])}Account: {outcomeLabel(o)}</li>
        ))}
        {(Object.keys(KIND_COLOR) as Array<keyof typeof KIND_COLOR>).map((k) => (
          <li key={k} className="flex items-center gap-2">{swatch(KIND_COLOR[k])}{KIND_LABEL[k]}</li>
        ))}
      </ul>
      <ul className="grid grid-cols-1 gap-1.5 text-[11px] text-foreground border-t border-border/60 pt-2">
        {Object.values(EDGE_STYLE).map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <svg width="28" height="6" aria-hidden="true"><line x1="0" y1="3" x2="28" y2="3" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} /></svg>
            {s.label}
          </li>
        ))}
      </ul>
      <p className="text-[10px] text-muted-foreground leading-relaxed">
        No account-to-account edges are drawn: the replay records none. Debt is one stablecoin total per account.
      </p>
    </section>
  );
}

export function ConsistencyPanel({ checks, warnings }: { checks: ConsistencyCheck[]; warnings: string[] }) {
  const allMatch = checks.every((c) => c.matches) && warnings.length === 0;
  return (
    <section className={PANEL} aria-label="Consistency checks">
      <h2 className={HEADING}>Outputs vs case-file totals</h2>
      <p className={`text-[11px] font-bold ${allMatch ? "text-emerald-400" : "text-red-400"}`}>
        {allMatch ? "Per-account outputs reproduce every committed total." : "Mismatch: the outputs do not reproduce the case file."}
      </p>
      <ul className="space-y-1.5">
        {checks.map((c) => (
          <li key={c.name} className="text-[11px] flex items-start gap-2">
            {c.matches ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-px" /> : <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-px" />}
            <span className="text-foreground">
              {c.name}: {c.fromOutputs}
              {!c.matches && <span className="text-red-300"> (case file: {c.fromCaseFile})</span>}
            </span>
          </li>
        ))}
      </ul>
      {warnings.map((w) => (
        <p key={w} className="text-[11px] text-amber-300 border-t border-border/60 pt-2">{w}</p>
      ))}
      <p className="text-[10px] text-muted-foreground">Informational only. Verdicts come from deterministic replay, never from this graph.</p>
    </section>
  );
}
