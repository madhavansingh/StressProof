"use client";

import { useEffect, useState, useMemo } from "react";
import { CheckCircle2, Clock, ShieldAlert, ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useAccount, usePublicClient } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { parseClaimStruct, OnChainClaim } from "@/lib/claims";
import { formatUsd8, formatAddress } from "@/lib/format";

export function RecentAttestationsWidget({ className = "" }: { className?: string }) {
  const { chainId } = useAccount();
  const effectiveChainId = chainId || ACTIVE_CHAIN_ID;
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  const [claims, setClaims] = useState<OnChainClaim[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    async function fetchLatestClaims() {
      if (!publicClient) return;
      try {
        const countRaw = await publicClient.readContract({
          address: config.registry.address,
          abi: config.registry.abi,
          functionName: "claimCount",
        });
        const count = Number(countRaw as bigint);
        if (count === 0) {
          if (mounted) {
            setClaims([]);
            setLoading(false);
          }
          return;
        }

        // Read up to last 4 claims in reverse
        const start = Math.max(1, count - 3);
        const promises = [];
        for (let i = count; i >= start; i--) {
          promises.push(
            publicClient
              .readContract({
                address: config.registry.address,
                abi: config.registry.abi,
                functionName: "claim",
                args: [BigInt(i)],
              })
              .then((raw) => parseClaimStruct(BigInt(i), raw))
          );
        }

        const items = await Promise.all(promises);
        if (mounted) {
          setClaims(items);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) setLoading(false);
      }
    }

    fetchLatestClaims();
    const interval = setInterval(fetchLatestClaims, 4000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [publicClient, config]);

  return (
    <div className={`w-full flex flex-col justify-between space-y-4 font-mono ${className}`}>
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b-2 border-border">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 shrink-0 border border-border bg-secondary flex items-center justify-center text-[#ea580c]">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground block">
              {"// REGISTRY_INTEGRITY"}
            </span>
            <p className="text-base sm:text-lg md:text-xl font-bold tracking-tight text-foreground mt-0.5 truncate">
              RECENT_CLAIMS_FEED
            </p>
          </div>
        </div>

        <Link
          href="/claims"
          className="text-xs uppercase font-bold text-muted-foreground hover:text-foreground flex items-center gap-1 group shrink-0"
        >
          <span>VIEW_ALL_CLAIMS</span>
          <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>

      {/* Attestation Events Ledger */}
      <div className="border-2 border-border bg-card divide-y-2 divide-border">
        {loading ? (
          <div className="p-8 text-center text-xs text-muted-foreground uppercase flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-[#ea580c]" />
            <span>READING_REGISTRY_LEDGER...</span>
          </div>
        ) : claims.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground uppercase space-y-1">
            <p className="text-foreground font-bold">NO ON-CHAIN CLAIMS YET</p>
            <p className="text-[10px]">Execute a simulation on /stress to publish bonded claims.</p>
          </div>
        ) : (
          claims.map((att) => {
            const isFinalized = att.stateName === "Finalized";
            const isChallenged = att.stateName === "Challenged";
            const isPending = att.stateName === "Pending";

            return (
              <div
                key={att.id.toString()}
                className="p-3 sm:p-4 hover:bg-secondary/40 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="flex items-start sm:items-center gap-3 min-w-0">
                  <div className="shrink-0 mt-0.5 sm:mt-0">
                    {isFinalized ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    ) : isChallenged ? (
                      <ShieldAlert className="h-4 w-4 text-[#ea580c]" />
                    ) : (
                      <Clock className="h-4 w-4 text-amber-400" />
                    )}
                  </div>

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs sm:text-sm font-bold text-foreground truncate">
                        CLAIM_#{att.id.toString()} // AAVE_V3
                      </span>
                      <span
                        className={`px-1.5 py-0.2 border text-[9px] font-bold uppercase ${
                          isFinalized
                            ? "border-emerald-500 bg-emerald-950/40 text-emerald-400"
                            : isChallenged
                            ? "border-[#ea580c] bg-orange-950/40 text-[#ea580c]"
                            : "border-amber-500 bg-amber-950/40 text-amber-400"
                        }`}
                      >
                        [{att.stateName}]
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                      <span>ATTESTER: {formatAddress(att.attester)}</span>
                      <span>&bull;</span>
                      <span className="font-mono">
                        HASH: {att.evidenceHash ? `${att.evidenceHash.slice(0, 10)}...` : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0 border-t sm:border-t-0 pt-2 sm:pt-0 border-border">
                  <div className="text-left sm:text-right">
                    <span className="text-xs sm:text-sm font-bold text-foreground block">
                      {formatUsd8(att.claimedResidualBadDebt)}
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase">BAD_DEBT</span>
                  </div>

                  <Link
                    href={`/claims/${att.id.toString()}`}
                    className="p-1.5 border border-border bg-background hover:border-foreground text-foreground transition-all shrink-0"
                    title="View claim dossier"
                  >
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
