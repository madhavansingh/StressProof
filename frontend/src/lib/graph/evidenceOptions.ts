import type { FeedEntry } from "@/types";
import type { OnChainClaim } from "@/lib/claims";
import { EVIDENCE_HASH } from "./loader";
import type { GraphClaimRef } from "./types";

export interface EvidenceOption {
  hash: string;
  label: string;
  claims: GraphClaimRef[];
}

export const MAX_EVIDENCE_OPTIONS = 50;

export function toClaimRef(claim: OnChainClaim): GraphClaimRef {
  return {
    id: claim.id.toString(),
    stateName: claim.stateName,
    attester: claim.attester,
    claimedResidualBadDebtUsd8: claim.claimedResidualBadDebt.toString(),
  };
}

/** Claims that commit to `hash` (the on-chain evidenceHash link). */
export function claimsForEvidence(claims: OnChainClaim[], hash: string): GraphClaimRef[] {
  const h = hash.toLowerCase();
  return claims.filter((c) => typeof c.evidenceHash === "string" && c.evidenceHash.toLowerCase() === h).map(toClaimRef);
}

function feedHash(entry: FeedEntry): string | null {
  const v = entry.kind === "CLAIM_BUILT" ? entry.data?.evidenceHash : undefined;
  return typeof v === "string" && EVIDENCE_HASH.test(v) ? v : null;
}

/**
 * Evidence hashes the user can open: those committed by on-chain claims (newest claim first), then those of
 * recent backend stress runs from the feed. Feed data is untrusted, so only well-formed hashes are kept.
 */
export function buildEvidenceOptions(claims: OnChainClaim[], feed: FeedEntry[]): EvidenceOption[] {
  const options = new Map<string, EvidenceOption>();
  const newestFirst = [...claims].sort((a, b) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0));
  for (const c of newestFirst) {
    const hash = typeof c.evidenceHash === "string" ? c.evidenceHash.toLowerCase() : "";
    if (!EVIDENCE_HASH.test(hash) || options.has(hash)) continue;
    const refs = claimsForEvidence(newestFirst, hash);
    options.set(hash, { hash, label: `Claims ${refs.map((r) => `#${r.id}`).join(", ")}`, claims: refs });
  }
  for (const entry of [...feed].sort((a, b) => b.seq - a.seq)) {
    const hash = feedHash(entry);
    if (!hash || options.has(hash)) continue;
    options.set(hash, { hash, label: `Stress run, feed #${entry.seq}`, claims: [] });
  }
  return [...options.values()].slice(0, MAX_EVIDENCE_OPTIONS);
}
