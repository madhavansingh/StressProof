"use client";

import { useEffect, useState } from "react";
import { fetchFeed } from "@/lib/api/client";
import { FeedEntry } from "@/types";
import { formatAddress } from "@/lib/format";
import { Radio, ExternalLink, Activity, Cpu } from "lucide-react";

export default function FeedPage() {
  const [entries, setEntries] = useState<FeedEntry[]>([
    {
      seq: 1,
      ts: new Date(Date.now() - 3600000).toISOString(),
      actor: "attester",
      kind: "CLAIM_POSTED",
      claimId: "1",
      txHash: "0x3f5c71a9e32a67bc4c498d41a7d65bce8971a1005a8f23d142cb1a8c991a01ef",
      data: {
        marketId: "aave-v3-eth-weth-stable",
        claimedResidualBadDebt: "200000000001",
        bond: "0.01 ETH",
      },
    },
    {
      seq: 2,
      ts: new Date(Date.now() - 3400000).toISOString(),
      actor: "watcher",
      kind: "FILE_FETCHED",
      claimId: "1",
      txHash: null,
      data: {
        source: "http://127.0.0.1:8000/case-files/0x7f427d…",
        status: "Raw bytes retrieved within 10s timeout",
      },
    },
    {
      seq: 3,
      ts: new Date(Date.now() - 3200000).toISOString(),
      actor: "watcher",
      kind: "HASH_OK",
      claimId: "1",
      txHash: null,
      data: {
        evidenceHash: "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0",
      },
    },
    {
      seq: 4,
      ts: new Date(Date.now() - 3000000).toISOString(),
      actor: "watcher",
      kind: "REPLAY_MATCH",
      claimId: "1",
      txHash: null,
      data: {
        status: "Verified exact match with static-liquidation-v1",
        recomputedResidual: "200000000001",
        discrepancyUsd8: "0",
      },
    },
    {
      seq: 5,
      ts: new Date(Date.now() - 1800000).toISOString(),
      actor: "watcher",
      kind: "DISPUTE_RAISED",
      claimId: "2",
      txHash: "0x89e27fa19c23bc987162fa9b47162901c876251bca89104fae109827361ab728",
      data: {
        reason: "WRONG_RESULT",
        assertedResidualBadDebt: "200000000001",
        counterBond: "0.01 ETH",
      },
    },
    {
      seq: 6,
      ts: new Date(Date.now() - 600000).toISOString(),
      actor: "resolver",
      kind: "CLAIM_FINALIZED",
      claimId: "1",
      txHash: "0x12bb7c66d28901aa81625ccbb8172901a8829910fbc882710189ab6621a71990",
      data: {
        winner: "attester",
        payoutEth: "0.01 ETH",
        slashedEth: "0",
      },
    },
  ]);

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
              STREAM_ACTIVE
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Real-time consensus audit log between AI attesters, autonomous watchers, and the on-chain registry.
          </p>
        </div>
      </div>

      {/* Feed Stream */}
      <div className="bg-card border-2 border-border">
        <div className="px-5 py-3 border-b-2 border-border bg-muted/20 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-widest text-foreground">
            // TELEMETRY_STREAM ({entries.length}_EVENTS)
          </span>
          <span className="text-[10px] text-muted-foreground uppercase">POLL_INTERVAL: 2000MS</span>
        </div>

        <div className="divide-y divide-border">
          {entries.map((entry) => {
            const isAttester = entry.actor === "attester";
            const isWatcher = entry.actor === "watcher";
            const isResolver = entry.actor === "resolver";

            return (
              <div key={entry.seq} className="p-4 hover:bg-muted/10 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="text-muted-foreground text-xs font-bold">#{entry.seq}</span>
                    <span
                      className={`px-1.5 py-0.5 border text-[10px] font-bold uppercase ${
                        isAttester
                          ? "border-purple-500 bg-purple-950/40 text-purple-300"
                          : isWatcher
                          ? "border-[#ea580c] bg-orange-950/40 text-[#ea580c]"
                          : "border-emerald-500 bg-emerald-950/40 text-emerald-300"
                      }`}
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
                    {new Date(entry.ts).toLocaleTimeString()}
                  </span>
                </div>

                <div className="mt-2 text-xs text-muted-foreground bg-background border border-border p-2.5 font-mono">
                  {Object.entries(entry.data || {}).map(([k, v]) => (
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
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
