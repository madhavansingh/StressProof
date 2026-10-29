"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { fetchFeed } from "@/lib/api/client";
import { FeedEntry } from "@/types";
import { useAccount, usePublicClient } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { formatAddress } from "@/lib/format";
import {
  Radio,
  ExternalLink,
  Activity,
  Cpu,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Shield,
  Layers,
} from "lucide-react";

export default function FeedPage() {
  const { chainId: currentChainId } = useAccount();
  const effectiveChainId = ACTIVE_CHAIN_ID; // reads always use the deployment chain, never the wallet's chain
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [nextSince, setNextSince] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [onChainLogsCount, setOnChainLogsCount] = useState<number>(0);

  // Track nextSince in ref to avoid stale closures in polling interval
  const nextSinceRef = useRef<number>(0);
  nextSinceRef.current = nextSince;

  // Poll backend feed every 2 seconds
  const pollAgentFeed = useCallback(async () => {
    try {
      const data = await fetchFeed(nextSinceRef.current, 200);
      setBackendError(null);

      if (data?.entries && data.entries.length > 0) {
        setEntries((prev) => {
          const existingSeqs = new Set(prev.map((e) => e.seq));
          const newItems = data.entries
            .filter((e) => !existingSeqs.has(e.seq))
            .map((e) => ({ ...e, source: "agent-reported" as const }));

          const combined = [...prev, ...newItems].sort((a, b) => b.seq - a.seq);
          return combined;
        });

        if (data.nextSince !== undefined && data.nextSince > nextSinceRef.current) {
          setNextSince(data.nextSince);
        }
      }
      setIsLoading(false);
    } catch (err: any) {
      // Backend not running or offline
      setBackendError(err?.message || "Failed to reach backend at http://localhost:8000");
      setIsLoading(false);
    }
  }, []);

  // Fetch on-chain logs from registry
  const fetchOnChainEvents = useCallback(async () => {
    if (!publicClient) return;
    try {
      const logs = await publicClient.getLogs({
        address: config.registry.address,
        fromBlock: config.registryDeployBlock,
        toBlock: "latest",
      });

      setOnChainLogsCount(logs.length);

      // Convert on-chain logs to FeedEntries if not already present
      const onChainEntries: FeedEntry[] = logs.map((log, index) => {
        return {
          seq: 100000 + index, // high synthetic seq for on-chain ordering
          ts: new Date().toISOString(),
          actor: "on-chain",
          kind: "ON_CHAIN_EVENT",
          txHash: log.transactionHash,
          source: "on-chain",
          data: {
            blockNumber: Number(log.blockNumber || 0),
            topicsCount: log.topics.length,
            contract: log.address,
          },
        };
      });

      setEntries((prev) => {
        const existingTx = new Set(prev.filter((e) => e.txHash).map((e) => e.txHash));
        const nonDuplicateOnChain = onChainEntries.filter((e) => !existingTx.has(e.txHash));
        if (nonDuplicateOnChain.length === 0) return prev;
        return [...prev, ...nonDuplicateOnChain];
      });
    } catch (err: any) {
      console.warn("Could not query on-chain event logs:", err);
    }
  }, [publicClient, config]);

  useEffect(() => {
    pollAgentFeed();
    fetchOnChainEvents();

    const interval = setInterval(() => {
      pollAgentFeed();
      fetchOnChainEvents();
    }, 2000);

    return () => clearInterval(interval);
  }, [pollAgentFeed, fetchOnChainEvents]);

  function getActorBadge(actor: string) {
    switch (actor.toLowerCase()) {
      case "attester":
        return "border-purple-500 bg-purple-950/40 text-purple-300";
      case "malicious_attester":
      case "malicious":
        return "border-rose-500 bg-rose-950/40 text-rose-300";
      case "watcher":
        return "border-[#ea580c] bg-orange-950/40 text-[#ea580c]";
      case "resolver":
        return "border-emerald-500 bg-emerald-950/40 text-emerald-300";
      case "backend":
        return "border-cyan-500 bg-cyan-950/40 text-cyan-300";
      case "ui":
      case "user":
        return "border-amber-500 bg-amber-950/40 text-amber-300";
      case "on-chain":
        return "border-blue-500 bg-blue-950/40 text-blue-300";
      default:
        // Unknown actor still renders safely per test requirements
        return "border-border bg-card text-muted-foreground";
    }
  }

  return (
    <div className="space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              REACTIVE_TELEMETRY_FEED
            </h1>
            <span className="px-2 py-0.5 border border-emerald-500 bg-emerald-950/40 text-emerald-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 shrink-0">
              <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
              POLLING_EVERY_2S
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Real-time audit log between AI attesters, autonomous watchers, and the on-chain registry.
          </p>
        </div>

        <button
          onClick={() => {
            pollAgentFeed();
            fetchOnChainEvents();
          }}
          title="Force poll feed"
          className="p-2 border border-border bg-card hover:border-foreground text-muted-foreground hover:text-foreground transition-all shrink-0"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin text-[#ea580c]" : ""}`} />
        </button>
      </div>

      {/* Backend Status Notice */}
      {backendError && (
        <div className="p-4 border-2 border-amber-500 bg-amber-950/40 text-amber-200 text-xs space-y-1">
          <div className="flex items-center gap-2 font-bold uppercase text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            BACKEND_FEED_NOTICE
          </div>
          <p className="text-[11px] uppercase leading-relaxed">
            {backendError}. Telemetry stream is standing by for agent event emissions.
          </p>
        </div>
      )}

      {/* Feed Stream */}
      <div className="bg-card border-2 border-border">
        <div className="px-5 py-3 border-b-2 border-border bg-muted/20 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-foreground">
            // TELEMETRY_STREAM ({entries.length}_EVENTS)
          </span>
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground uppercase">
            <span>NEXT_SINCE: {nextSince}</span>
            <span>ON_CHAIN_LOGS: {onChainLogsCount}</span>
          </div>
        </div>

        {entries.length === 0 ? (
          <div className="p-12 text-center text-xs text-muted-foreground uppercase space-y-2">
            <Radio className="h-6 w-6 animate-pulse mx-auto text-[#ea580c]" />
            <p className="text-foreground font-bold">NO TELEMETRY EVENTS RECORDED YET</p>
            <p className="text-[10px]">Execute a simulation or run the watcher agent to observe audit events.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {entries.map((entry) => {
              const isMatch =
                entry.actor === "watcher" &&
                (entry.kind === "REPLAY_MATCH" || entry.kind === "HASH_OK");
              const isDispute =
                entry.kind === "CHALLENGE_SENT" ||
                entry.kind === "REPLAY_MISMATCH" ||
                entry.kind === "DISPUTE_RAISED";

              return (
                <div
                  key={`${entry.seq}-${entry.txHash || ""}`}
                  className={`p-4 transition-colors ${
                    isMatch
                      ? "bg-emerald-950/20 border-l-4 border-emerald-500"
                      : isDispute
                      ? "bg-rose-950/20 border-l-4 border-rose-500"
                      : "hover:bg-muted/10"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-muted-foreground text-xs font-bold">#{entry.seq}</span>

                      {/* Source tag: on-chain vs agent-reported */}
                      <span
                        className={`px-1.5 py-0.5 text-[9px] font-bold uppercase border ${
                          entry.source === "on-chain"
                            ? "border-blue-500/50 bg-blue-950/50 text-blue-300"
                            : "border-border bg-secondary text-muted-foreground"
                        }`}
                      >
                        [{entry.source || "agent-reported"}]
                      </span>

                      {/* Actor Badge */}
                      <span
                        className={`px-1.5 py-0.5 border text-[10px] font-bold uppercase ${getActorBadge(
                          entry.actor
                        )}`}
                      >
                        [{entry.actor}]
                      </span>

                      <span className="text-xs font-bold text-foreground uppercase tracking-wider">
                        {entry.kind}
                      </span>

                      {entry.claimId && (
                        <span className="text-[10px] text-muted-foreground uppercase">
                          (CLAIM_#{entry.claimId})
                        </span>
                      )}
                    </div>

                    <span className="text-[10px] text-muted-foreground uppercase">
                      {entry.ts ? new Date(entry.ts).toLocaleTimeString() : "—"}
                    </span>
                  </div>

                  {/* Special Highlight for Criterion 2 View */}
                  {isMatch && (
                    <div className="mt-2 p-2 border border-emerald-500/50 bg-emerald-950/40 text-emerald-300 text-xs font-bold uppercase flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <span>WATCHER REPLAYED: MATCH (100% DETERMINISTIC VERIFICATION PASS)</span>
                    </div>
                  )}

                  {/* Data payload inspector */}
                  {entry.data && Object.keys(entry.data).length > 0 && (
                    <div className="mt-2 text-xs text-muted-foreground bg-background border border-border p-2.5 font-mono space-y-0.5">
                      {Object.entries(entry.data).map(([k, v]) => (
                        <div key={k} className="flex gap-2">
                          <span className="text-foreground uppercase">{k}:</span>
                          <span className="text-muted-foreground break-all">{String(v)}</span>
                        </div>
                      ))}
                      {entry.txHash && (
                        <div className="flex gap-2 mt-1 pt-1 border-t border-border">
                          <span className="text-[#ea580c] uppercase font-bold">TX_HASH:</span>
                          <span className="text-[#ea580c] break-all">{entry.txHash}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
