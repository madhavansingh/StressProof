"use client";

import { useEffect, useState } from "react";
import { fetchFeed } from "@/lib/api/client";
import { FeedEntry } from "@/types";

export default function FeedPage() {
  const [entries, setEntries] = useState<FeedEntry[]>([
    {
      seq: 1,
      ts: new Date().toISOString(),
      actor: "attester",
      kind: "CLAIM_POSTED",
      claimId: "1",
      txHash: "0x123...abc",
      data: { claimedBadDebt: "200000000001" },
    },
    {
      seq: 2,
      ts: new Date().toISOString(),
      actor: "watcher",
      kind: "REPLAY_MATCH",
      claimId: "1",
      txHash: null,
      data: { status: "Verified exactly" },
    },
  ]);

  useEffect(() => {
    fetchFeed()
      .then((res) => {
        if (res.entries && res.entries.length > 0) {
          setEntries(res.entries);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Agent Activity Feed</h1>
        <p className="text-zinc-500">
          Real-time decentralized telemetry from attesters, watchers, and resolvers.
        </p>
      </div>

      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.seq} className="rounded-xl border bg-white p-4 shadow-sm dark:bg-zinc-950 flex gap-4">
            <span className="font-mono text-xs text-zinc-400">#{entry.seq}</span>
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold uppercase text-xs tracking-wider text-indigo-600 dark:text-indigo-400">
                  {entry.actor}
                </span>
                <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] dark:bg-zinc-800">
                  {entry.kind}
                </span>
                <span className="text-xs text-zinc-400 ml-auto">{entry.ts}</span>
              </div>
              {entry.claimId && <p className="text-xs">Claim: #{entry.claimId}</p>}
              {entry.txHash && <p className="font-mono text-[10px] text-zinc-500">Tx: {entry.txHash}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
