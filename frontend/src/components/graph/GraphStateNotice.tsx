"use client";

import Link from "next/link";
import { AlertTriangle, Loader2, SearchX, Waypoints } from "lucide-react";
import type { GraphLoadResult } from "@/lib/graph/loader";

type Tone = "info" | "warn" | "error";

const TONE: Record<Tone, string> = {
  info: "border-border text-muted-foreground",
  warn: "border-amber-500 text-amber-200",
  error: "border-red-500 text-red-200",
};

function Notice({ tone, title, children, icon: Icon }: { tone: Tone; title: string; children: React.ReactNode; icon: typeof AlertTriangle }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`bg-card border-2 ${TONE[tone]} min-h-[300px] p-8 flex flex-col items-center justify-center text-center gap-3`}>
      <Icon className="h-7 w-7" />
      <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">{title}</h2>
      <div className="text-xs max-w-lg leading-relaxed space-y-2">{children}</div>
    </div>
  );
}

export type GraphViewState = { status: "idle" } | { status: "loading" } | GraphLoadResult;

/** Every non-graph state: nothing chosen, loading, missing, unavailable or failed. */
export function GraphStateNotice({ state }: { state: GraphViewState }) {
  switch (state.status) {
    case "idle":
      return (
        <Notice tone="info" title="No evidence selected" icon={Waypoints}>
          <p>Choose an evidence hash above, or run a stress test to create one.</p>
          <Link href="/stress" className="inline-block underline hover:text-[#ea580c]">Go to stress test</Link>
        </Notice>
      );
    case "loading":
      return (
        <Notice tone="info" title="Loading replay outputs" icon={Loader2}>
          <p>Fetching the case file, checking its hash, then reading the replay outputs.</p>
        </Notice>
      );
    case "invalidHash":
      return (
        <Notice tone="warn" title="Not an evidence hash" icon={AlertTriangle}>
          <p>An evidenceHash is 0x followed by 64 lowercase hex characters.</p>
        </Notice>
      );
    case "caseFileMissing":
      return (
        <Notice tone="warn" title="Case file not found" icon={SearchX}>
          <p>This backend stores no case file for that hash. It may live on another backend or on IPFS only.</p>
        </Notice>
      );
    case "outputsMissing":
      return (
        <Notice tone="warn" title="Replay outputs unavailable" icon={SearchX}>
          <p>The case file is here and its hash checks out, but this backend has no per-account replay outputs for it.</p>
          <p>Outputs are written only when the backend runs the stress test (/stress/run). A case file uploaded directly has none, and the graph will not invent them.</p>
        </Notice>
      );
    case "error":
      return (
        <Notice tone="error" title="Graph not drawn" icon={AlertTriangle}>
          <p>{state.message}</p>
          {state.issues && state.issues.length > 0 && (
            <ul className="text-left font-mono text-[11px] space-y-0.5">
              {state.issues.map((i) => (
                <li key={`${i.line}:${i.message}`}>{i.line > 0 ? `line ${i.line}: ` : ""}{i.message}</li>
              ))}
            </ul>
          )}
        </Notice>
      );
    default:
      return null;
  }
}
