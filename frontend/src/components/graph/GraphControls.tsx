"use client";

import { useState, type FormEvent } from "react";
import { RefreshCw, Search } from "lucide-react";
import type { EvidenceOption } from "@/lib/graph/evidenceOptions";
import type { OutcomeFilter } from "@/lib/graph/view";

interface EvidencePickerProps {
  options: EvidenceOption[];
  activeHash: string | null;
  loading: boolean;
  onOpen: (hash: string) => void;
  onReload: () => void;
}

const INPUT = "w-full bg-background border-2 border-border px-2 py-1.5 text-xs text-foreground font-mono focus:outline-none focus:border-[#ea580c]";
const BUTTON = "px-3 py-1.5 border-2 border-foreground bg-foreground text-background text-[11px] font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white disabled:opacity-50";

export function EvidencePicker({ options, activeHash, loading, onOpen, onReload }: EvidencePickerProps) {
  const [manual, setManual] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onOpen(manual.trim().toLowerCase());
  };
  return (
    <div className="bg-card border-2 border-border p-4 grid gap-3 md:grid-cols-2">
      <label className="space-y-1 min-w-0">
        <span className="text-[10px] font-bold uppercase text-muted-foreground flex items-center justify-between">
          Evidence from claims and stress runs
          <button type="button" onClick={onReload} disabled={loading} aria-label="Reload evidence list" className="text-muted-foreground hover:text-foreground">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </span>
        <select className={INPUT} value={activeHash && options.some((o) => o.hash === activeHash) ? activeHash : ""}
          onChange={(e) => e.target.value && onOpen(e.target.value)} disabled={options.length === 0}>
          <option value="">{options.length === 0 ? (loading ? "Loading…" : "No evidence hashes found") : "Choose an evidence hash"}</option>
          {options.map((o) => (
            <option key={o.hash} value={o.hash}>{`${o.label} · ${o.hash.slice(0, 10)}…${o.hash.slice(-6)}`}</option>
          ))}
        </select>
      </label>
      <form onSubmit={submit} className="space-y-1 min-w-0">
        <label htmlFor="evidence-hash" className="text-[10px] font-bold uppercase text-muted-foreground block">Or paste an evidenceHash</label>
        <div className="flex gap-2">
          <input id="evidence-hash" className={INPUT} placeholder="0x… (64 hex characters)" value={manual} spellCheck={false}
            autoComplete="off" maxLength={80} onChange={(e) => setManual(e.target.value)} />
          <button type="submit" className={BUTTON} disabled={manual.trim() === ""}>Open</button>
        </div>
      </form>
    </div>
  );
}

const OUTCOMES: Array<{ value: OutcomeFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "badDebt", label: "Bad debt" },
  { value: "liquidated", label: "Liquidated" },
  { value: "safe", label: "Safe" },
];

interface FilterBarProps {
  outcome: OutcomeFilter;
  query: string;
  shown: number;
  total: number;
  onOutcome: (o: OutcomeFilter) => void;
  onQuery: (q: string) => void;
}

export function FilterBar({ outcome, query, shown, total, onOutcome, onQuery }: FilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
      <div role="group" aria-label="Filter accounts by outcome" className="flex flex-wrap gap-1">
        {OUTCOMES.map((o) => (
          <button key={o.value} type="button" aria-pressed={outcome === o.value} onClick={() => onOutcome(o.value)}
            className={`px-2.5 py-1 border-2 text-[11px] font-bold uppercase ${outcome === o.value ? "border-[#ea580c] bg-[#ea580c]/15 text-[#ea580c]" : "border-border text-muted-foreground hover:text-foreground"}`}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="relative sm:ml-auto sm:w-64">
        <Search className="h-3.5 w-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input aria-label="Search accounts" className={`${INPUT} pl-7`} placeholder="Search account id" value={query}
          maxLength={128} onChange={(e) => onQuery(e.target.value)} />
      </div>
      <span className="text-[10px] uppercase text-muted-foreground whitespace-nowrap">{shown} / {total} accounts</span>
    </div>
  );
}
