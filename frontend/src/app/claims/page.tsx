"use client";

import Link from "next/link";
import { useState } from "react";
import { formatUsd8, formatAddress, formatCountdown } from "@/lib/format";
import { ShieldAlert, FileCheck2, ExternalLink, Clock, AlertTriangle, ArrowRight, X } from "lucide-react";

interface ClaimRow {
  id: string;
  attester: string;
  marketId: string;
  claimedResidualBadDebt: string;
  bond: string;
  status: "Pending" | "Challenged" | "Finalized" | "Rejected" | "Expired";
  challengeDeadline: number;
  resolutionDeadline: number;
  caseFileURI: string;
  evidenceHash: string;
}

export default function ClaimsPage() {
  const [claims] = useState<ClaimRow[]>([
    {
      id: "1",
      attester: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      marketId: "aave-v3-eth-weth-stable",
      claimedResidualBadDebt: "200000000001", // $2,000.00
      bond: "0.01 ETH",
      status: "Finalized",
      challengeDeadline: Math.floor(Date.now() / 1000) - 3600,
      resolutionDeadline: 0,
      caseFileURI: "http://127.0.0.1:8000/case-files/0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0",
      evidenceHash: "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0",
    },
    {
      id: "2",
      attester: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
      marketId: "aave-v3-eth-weth-stable",
      claimedResidualBadDebt: "600000000003", // $6,000.00 (3x inflated malicious claim)
      bond: "0.01 ETH",
      status: "Rejected",
      challengeDeadline: Math.floor(Date.now() / 1000) - 1800,
      resolutionDeadline: Math.floor(Date.now() / 1000) - 600,
      caseFileURI: "http://127.0.0.1:8000/case-files/0x9b31d8e9…",
      evidenceHash: "0x9b31d8e9c6…",
    },
    {
      id: "3",
      attester: "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
      marketId: "aave-v3-eth-weth-stable",
      claimedResidualBadDebt: "200000000001",
      bond: "0.01 ETH",
      status: "Pending",
      challengeDeadline: Math.floor(Date.now() / 1000) + 85, // 85s left
      resolutionDeadline: 0,
      caseFileURI: "http://127.0.0.1:8000/case-files/0x7f427d2c…",
      evidenceHash: "0x7f427d2c66…",
    },
  ]);

  const [activeModalClaim, setActiveModalClaim] = useState<ClaimRow | null>(null);
  const [challengeReason, setChallengeReason] = useState<"WRONG_RESULT" | "EVIDENCE_INVALID">("WRONG_RESULT");
  const [counterDebt, setCounterDebt] = useState<string>("200000000001");
  const [reportURI, setReportURI] = useState<string>("http://127.0.0.1:8000/replay-reports/0x123...");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  function getStatusBadge(status: ClaimRow["status"]) {
    switch (status) {
      case "Pending":
        return "border-amber-500 bg-amber-950/60 text-amber-400";
      case "Challenged":
        return "border-[#ea580c] bg-orange-950/60 text-[#ea580c]";
      case "Finalized":
        return "border-emerald-500 bg-emerald-950/60 text-emerald-400";
      case "Rejected":
        return "border-rose-500 bg-rose-950/60 text-rose-400";
      case "Expired":
        return "border-border bg-secondary text-muted-foreground";
    }
  }

  function handleFinalize(id: string) {
    setActionMessage(`TX_PREPARED: registry.finalize(${id}) — will credit attester 0.01 ETH bond.`);
  }

  function handleExpire(id: string) {
    setActionMessage(`TX_PREPARED: registry.expireUnresolved(${id}) — will refund both parties.`);
  }

  function submitChallenge() {
    if (!activeModalClaim) return;
    setActionMessage(
      `TX_PREPARED: registry.challenge(${activeModalClaim.id}, ${challengeReason}, ${counterDebt}) with 0.01 ETH counter-bond.`
    );
    setActiveModalClaim(null);
  }

  return (
    <div className="space-y-6 font-mono">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              BONDED_CLAIMS_REGISTRY
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              ISTRESSREGISTRY.SOL
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            All claims require a bonded stake (0.01 ETH) and enter an optimistic challenge window before finalization.
          </p>
        </div>

        <Link
          href="/stress"
          className="group flex items-center justify-center sm:justify-start w-full sm:w-auto gap-0 bg-foreground text-background text-xs font-mono tracking-wider uppercase border border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[3px_3px_0px_0px_hsl(var(--border))]"
        >
          <span className="flex items-center justify-center w-8 h-8 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors shrink-0">
            <ArrowRight className="h-4 w-4" />
          </span>
          <span className="px-3.5 py-1.5 font-bold">POST_NEW_CLAIM</span>
        </Link>
      </div>

      {actionMessage && (
        <div className="p-3 border-2 border-emerald-500 bg-emerald-950/40 text-emerald-300 text-xs flex items-center justify-between">
          <span>{actionMessage}</span>
          <button
            onClick={() => setActionMessage(null)}
            className="text-emerald-400 hover:text-white uppercase font-bold"
          >
            [DISMISS]
          </button>
        </div>
      )}

      {/* Claims Table / List */}
      <div className="bg-card border-2 border-border">
        <div className="px-5 py-3 border-b-2 border-border bg-muted/20 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-widest text-foreground">
            // REGISTRY_LEDGER ({claims.length}_RECORDS)
          </span>
          <span className="text-[10px] text-muted-foreground uppercase">
            CHALLENGE_WINDOW: 120S
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b-2 border-border bg-secondary/50 text-muted-foreground uppercase tracking-wider text-[10px]">
              <tr>
                <th className="p-4">CLAIM_ID</th>
                <th className="p-4">STATUS</th>
                <th className="p-4">MARKET_ID</th>
                <th className="p-4">CLAIMED_BAD_DEBT</th>
                <th className="p-4">BOND</th>
                <th className="p-4">WINDOW_TIMER</th>
                <th className="p-4">ATTESTER</th>
                <th className="p-4 text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {claims.map((c) => {
                const now = Math.floor(Date.now() / 1000);
                const isChallengeable = c.status === "Pending" && now < c.challengeDeadline;
                const canFinalize = c.status === "Pending" && now >= c.challengeDeadline;

                return (
                  <tr key={c.id} className="hover:bg-muted/10 transition-colors">
                    <td className="p-4 font-bold text-foreground">#{c.id}</td>
                    <td className="p-4">
                      <span className={`px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider ${getStatusBadge(c.status)}`}>
                        [{c.status}]
                      </span>
                    </td>
                    <td className="p-4 text-muted-foreground">{c.marketId}</td>
                    <td className="p-4 font-bold text-foreground">
                      {formatUsd8(c.claimedResidualBadDebt)}
                    </td>
                    <td className="p-4 text-foreground">{c.bond}</td>
                    <td className="p-4">
                      {c.status === "Pending" ? (
                        <span className="text-[#ea580c] font-bold flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          {formatCountdown(c.challengeDeadline).text}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">&mdash;</span>
                      )}
                    </td>
                    <td className="p-4 text-muted-foreground font-mono">
                      {formatAddress(c.attester)}
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/claims/${c.id}`}
                          className="px-2.5 py-1 border border-border text-[11px] font-bold text-foreground hover:bg-secondary uppercase"
                        >
                          DETAIL
                        </Link>
                        {isChallengeable && (
                          <button
                            onClick={() => setActiveModalClaim(c)}
                            className="px-2.5 py-1 border border-[#ea580c] bg-[#ea580c] text-background text-[11px] font-bold uppercase hover:bg-foreground hover:border-foreground transition-all"
                          >
                            CHALLENGE
                          </button>
                        )}
                        {canFinalize && (
                          <button
                            onClick={() => handleFinalize(c.id)}
                            className="px-2.5 py-1 border border-emerald-500 bg-emerald-950/60 text-emerald-300 text-[11px] font-bold uppercase hover:bg-emerald-900"
                          >
                            FINALIZE
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Challenge Modal Dialog */}
      {activeModalClaim && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-card border-2 border-foreground p-6 space-y-4 font-mono shadow-[8px_8px_0px_0px_#ea580c]">
            <div className="flex items-center justify-between border-b-2 border-border pb-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
                <h3 className="text-sm font-bold uppercase tracking-wider text-foreground">
                  CHALLENGE_CLAIM_#{activeModalClaim.id}
                </h3>
              </div>
              <button
                onClick={() => setActiveModalClaim(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-muted-foreground uppercase leading-relaxed">
              Submit a counter-bond (0.01 ETH). If the deterministic replayer reveals the claim is invalid or incorrect, the attester's bond is slashed and credited to you.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                  DISPUTE_REASON
                </label>
                <select
                  value={challengeReason}
                  onChange={(e: any) => setChallengeReason(e.target.value)}
                  className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                >
                  <option value="WRONG_RESULT">WRONG_RESULT (Bad debt mismatch)</option>
                  <option value="EVIDENCE_INVALID">EVIDENCE_INVALID (Corrupted or malformed hash)</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                  ASSERTED_COUNTER_DEBT (USD8)
                </label>
                <input
                  type="text"
                  value={counterDebt}
                  onChange={(e) => setCounterDebt(e.target.value)}
                  className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                />
              </div>

              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                  REPLAYER_REPORT_URI
                </label>
                <input
                  type="text"
                  value={reportURI}
                  onChange={(e) => setReportURI(e.target.value)}
                  className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t-2 border-border">
              <button
                onClick={() => setActiveModalClaim(null)}
                className="px-4 py-2 border border-border text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                CANCEL
              </button>
              <button
                onClick={submitChallenge}
                className="px-5 py-2 bg-[#ea580c] text-white border-2 border-[#ea580c] text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background hover:border-foreground transition-all"
              >
                SUBMIT_CHALLENGE (0.01 ETH)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
