"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePublicClient } from "wagmi";
import { fetchFeed } from "@/lib/api/client";
import { ACTIVE_CHAIN_ID, getContractConfig } from "@/lib/contracts";
import { parseClaimStruct, type OnChainClaim } from "@/lib/claims";
import type { FeedEntry } from "@/types";

/** Read at most this many of the newest claims for the evidence picker. */
const MAX_CLAIMS_READ = 50;

export interface EvidenceSources {
  claims: OnChainClaim[];
  feed: FeedEntry[];
  claimsError: string | null;
  feedError: string | null;
  loading: boolean;
  reload: () => void;
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message.split("\n")[0] : fallback;
}

/** Read-only: claims from the registry (deployment chain, never the wallet's) and the backend feed. */
export function useEvidenceSources(): EvidenceSources {
  const config = useMemo(() => getContractConfig(ACTIVE_CHAIN_ID), []);
  const publicClient = usePublicClient({ chainId: ACTIVE_CHAIN_ID });
  const [claims, setClaims] = useState<OnChainClaim[]>([]);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [claimsError, setClaimsError] = useState<string | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadClaims = useCallback(async (): Promise<void> => {
    if (!publicClient) {
      setClaimsError("No RPC client for the deployment chain.");
      return;
    }
    try {
      const { address, abi } = config.registry;
      const count = Number(await publicClient.readContract({ address, abi, functionName: "claimCount" }) as bigint);
      const first = Math.max(1, count - MAX_CLAIMS_READ + 1);
      const ids = Array.from({ length: Math.max(0, count - first + 1) }, (_, i) => BigInt(first + i));
      const raws = await Promise.all(ids.map((id) => publicClient.readContract({ address, abi, functionName: "claim", args: [id] })));
      setClaims(raws.map((raw, i) => parseClaimStruct(ids[i], raw)));
      setClaimsError(null);
    } catch (err: unknown) {
      setClaimsError(message(err, "Could not read claims from the chain."));
    }
  }, [publicClient, config]);

  const loadFeed = useCallback(async (): Promise<void> => {
    try {
      setFeed((await fetchFeed(0, 200)).entries);
      setFeedError(null);
    } catch (err: unknown) {
      setFeedError(message(err, "Could not read the backend feed."));
    }
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    void Promise.all([loadClaims(), loadFeed()]).finally(() => setLoading(false));
  }, [loadClaims, loadFeed]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { claims, feed, claimsError, feedError, loading, reload };
}
