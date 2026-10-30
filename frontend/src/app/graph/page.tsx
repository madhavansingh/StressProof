"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { BACKEND_URL } from "@/lib/api/client";
import { buildExposureGraph, outcomeLabel } from "@/lib/graph/buildGraph";
import { buildEvidenceOptions, claimsForEvidence } from "@/lib/graph/evidenceOptions";
import { EVIDENCE_HASH, loadGraphData } from "@/lib/graph/loader";
import { filterGraph, resolveSelection, type GraphFilter } from "@/lib/graph/view";
import type { ExposureGraph, GraphNode } from "@/lib/graph/types";
import { formatBps, formatUsd8 } from "@/lib/format";
import { ExposureGraphCanvas } from "@/components/graph/ExposureGraphCanvas";
import { ConsistencyPanel, GraphInfoPanel, GraphLegend } from "@/components/graph/GraphPanels";
import { EvidencePicker, FilterBar } from "@/components/graph/GraphControls";
import { GraphStateNotice, type GraphViewState } from "@/components/graph/GraphStateNotice";
import { OUTCOME_COLOR } from "@/components/graph/graphStyle";
import { useEvidenceSources } from "@/components/graph/useEvidenceSources";
import { TigerGraphPanel } from "@/components/graph/TigerGraphPanel";

const QUERY_KEY = "evidence";

function readHashFromUrl(): string | null {
  const v = new URLSearchParams(window.location.search).get(QUERY_KEY);
  return v ? v.trim().toLowerCase() : null;
}

function writeHashToUrl(hash: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(QUERY_KEY, hash);
  window.history.replaceState(null, "", url.toString());
}

function DataClassBanner({ dataClass }: { dataClass: string }) {
  if (dataClass === "REAL") return null;
  return (
    <div className="w-full bg-amber-950/80 border-2 border-amber-500 text-amber-200 px-4 py-2.5 text-xs flex items-center gap-2">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
      <span>
        <strong className="text-amber-100 uppercase">{dataClass === "SYNTHETIC" ? "SYNTHETIC_DATASET_BANNER:" : "MIXED_DATASET_BANNER:"}</strong>{" "}
        {dataClass === "SYNTHETIC" ? "Synthetic accounts. This graph does not describe real Aave positions." : "Includes synthetic accounts. Results do not describe real Aave."}
      </span>
    </div>
  );
}

function SourceBar({ graph, scenario, model, outputBytes }: { graph: ExposureGraph; scenario: string; model: string; outputBytes: number }) {
  const items: Array<[string, string]> = [
    ["Graph source", "Local deterministic replay · not TigerGraph"],
    ["Evidence hash", graph.evidenceHash],
    ["Case file", "keccak256 verified"],
    ["Replay outputs", `${graph.nodes.filter((n) => n.kind === "account").length} rows · ${outputBytes} bytes · derived, not on chain`],
    ["Scenario", scenario],
    ["Model", model],
  ];
  return (
    <dl className="bg-card border-2 border-border p-3 grid gap-x-4 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-3 text-[11px]">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[10px] uppercase text-muted-foreground flex items-center gap-1">
            {k === "Case file" && <ShieldCheck className="h-3 w-3 text-emerald-400" />}{k}
          </dt>
          <dd className="text-foreground break-all">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function AccountTable({ nodes, selectedId, onSelect }: { nodes: GraphNode[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const accounts = nodes.filter((n) => n.kind === "account");
  if (accounts.length === 0) return null;
  const value = (n: GraphNode, label: string) => n.details.find((d) => d.label === label)?.value ?? "—";
  return (
    <div className="bg-card border-2 border-border overflow-x-auto">
      <table className="w-full text-[11px] text-left">
        <caption className="sr-only">Accounts shown in the graph</caption>
        <thead className="text-[10px] uppercase text-muted-foreground border-b-2 border-border">
          <tr>{["Account", "Outcome", "Debt", "Repaid", "Residual bad debt"].map((h) => <th key={h} className="px-3 py-2 font-bold whitespace-nowrap">{h}</th>)}</tr>
        </thead>
        <tbody>
          {accounts.map((n) => (
            <tr key={n.id} onClick={() => onSelect(n.id)} className={`border-b border-border/50 cursor-pointer hover:bg-secondary ${n.id === selectedId ? "bg-secondary" : ""}`}>
              <td className="px-3 py-1.5"><button type="button" className="underline-offset-2 hover:underline" onClick={() => onSelect(n.id)}>{n.label}</button></td>
              <td className="px-3 py-1.5 whitespace-nowrap" style={{ color: OUTCOME_COLOR[n.outcome ?? "safe"] }}>{outcomeLabel(n.outcome ?? "safe")}</td>
              <td className="px-3 py-1.5">{value(n, "Debt")}</td>
              <td className="px-3 py-1.5">{value(n, "Repaid by liquidation")}</td>
              <td className="px-3 py-1.5">{value(n, "Residual bad debt")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GraphPage() {
  const sources = useEvidenceSources();
  const options = useMemo(() => buildEvidenceOptions(sources.claims, sources.feed), [sources.claims, sources.feed]);
  const [activeHash, setActiveHash] = useState<string | null>(null);
  const [state, setState] = useState<GraphViewState>({ status: "idle" });
  const [filter, setFilter] = useState<GraphFilter>({ outcome: "all", query: "" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const urlChecked = useRef(false);
  const requestSeq = useRef(0);

  const open = useCallback((hash: string) => {
    setActiveHash(hash);
    setSelectedId(null);
    if (EVIDENCE_HASH.test(hash)) writeHashToUrl(hash);
  }, []);

  // ?evidence=<hash> wins; otherwise open the newest claim's evidence once the list arrives.
  useEffect(() => {
    if (urlChecked.current) return;
    const fromUrl = readHashFromUrl();
    if (fromUrl) {
      urlChecked.current = true;
      open(fromUrl);
    } else if (!sources.loading) {
      urlChecked.current = true;
      if (options.length > 0) open(options[0].hash);
    }
  }, [sources.loading, options, open]);

  useEffect(() => {
    if (!activeHash) return;
    const seq = ++requestSeq.current; // ignore answers to superseded requests
    setState({ status: "loading" });
    void loadGraphData(activeHash, BACKEND_URL).then((r) => {
      if (seq === requestSeq.current) setState(r);
    });
  }, [activeHash]);

  const graph = useMemo(() => {
    if (state.status !== "ok" || !activeHash) return null;
    return buildExposureGraph({ evidenceHash: activeHash, outputs: state.outputs, caseFile: state.caseFile, claims: claimsForEvidence(sources.claims, activeHash) });
  }, [state, activeHash, sources.claims]);
  const visible = useMemo(() => (graph ? filterGraph(graph, filter) : null), [graph, filter]);
  const selected = visible ? resolveSelection(visible.nodes, selectedId) : null;
  const totalAccounts = graph ? graph.nodes.filter((n) => n.kind === "account").length : 0;
  const caseFile = state.status === "ok" || state.status === "outputsMissing" ? state.caseFile : null;

  return (
    <div className="space-y-5 font-mono">
      {caseFile && <DataClassBanner dataClass={caseFile.dataClass} />}
      <header className="border-b-2 border-border pb-5">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">EXPOSURE_GRAPH</h1>
          <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider">REPLAY_OUTPUTS</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1 max-w-3xl leading-relaxed">
          Accounts, assets and claims from one deterministic replay. Every node and edge comes from the replay outputs, the hash-verified case file or an on-chain claim.
          The graph is informational: verdicts come from deterministic replay and are never read from here.
        </p>
      </header>

      <EvidencePicker options={options} activeHash={activeHash} loading={sources.loading} onOpen={open} onReload={sources.reload} />
      {(sources.claimsError || sources.feedError) && (
        <p className="text-[11px] text-amber-300">
          {sources.claimsError && <>On-chain claims unavailable ({sources.claimsError}). </>}
          {sources.feedError && <>Backend feed unavailable ({sources.feedError}). </>}
          You can still paste an evidenceHash.
        </p>
      )}

      {!graph || !visible || !caseFile ? (
        <GraphStateNotice state={state} />
      ) : (
        <>
          <SourceBar graph={graph} model={caseFile.modelId} outputBytes={state.status === "ok" ? state.outputBytes : 0}
            scenario={`${caseFile.scenario.asset} ${formatBps(caseFile.scenario.shockBps)} · bad debt ${formatUsd8(caseFile.results.residualBadDebtUsd8)}`} />
          <FilterBar outcome={filter.outcome} query={filter.query} shown={visible.matchedAccounts} total={totalAccounts}
            onOutcome={(outcome) => setFilter((f) => ({ ...f, outcome }))} onQuery={(query) => setFilter((f) => ({ ...f, query }))} />
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-2 min-w-0">
              {totalAccounts === 0 && <p role="status" className="text-xs text-amber-300">The replay outputs file is empty: no accounts to draw.</p>}
              {totalAccounts > 0 && visible.matchedAccounts === 0 && <p role="status" className="text-xs text-muted-foreground">No accounts match this filter.</p>}
              {visible.hiddenByCap > 0 && <p role="status" className="text-xs text-amber-300">Showing the first {visible.matchedAccounts - visible.hiddenByCap} matching accounts; {visible.hiddenByCap} more are hidden. Narrow the filter to see them.</p>}
              <ExposureGraphCanvas nodes={visible.nodes} edges={visible.edges} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
            </div>
            <aside className="grid gap-4 md:grid-cols-2 xl:grid-cols-1 xl:content-start">
              <GraphInfoPanel node={selected} />
              <ConsistencyPanel checks={graph.checks} warnings={graph.warnings} />
              <GraphLegend />
            </aside>
          </div>
          <TigerGraphPanel evidenceHash={graph.evidenceHash} />
          <AccountTable nodes={visible.nodes} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
        </>
      )}
    </div>
  );
}
