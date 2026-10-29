import { DEPLOYMENTS } from "@/lib/contracts";
import { formatUsd8 } from "@/lib/format";

/** Shown wherever a vault value could not be read from the chain. Never a default value. */
export const UNAVAILABLE = "UNAVAILABLE";

const BPS = 10_000;

/** A successful read of DemoVault state. Components hold `VaultReading | null`: null = not read. */
export interface VaultReading {
  maxLtvBps: number;
  borrowPaused: boolean;
  lastAppliedClaimId: bigint;
}

/** Vault parameters from deployments/<chainId>.json; null when the deployment does not set them. */
export interface VaultConfig {
  defaultMaxLtvBps: number | null;
  reducedLtvBps: number | null;
  ltvThresholdUsd8: bigint | null;
  pauseThresholdUsd8: bigint | null;
}

function toBigInt(value: unknown, name: string): bigint {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  throw new Error(`${name}: expected an integer from the contract, got ${typeof value}`);
}

/** Validates raw readContract results for maxLtvBps(), borrowPaused() and lastAppliedClaimId(). */
export function parseVaultReading(maxLtv: unknown, paused: unknown, lastApplied: unknown): VaultReading {
  const ltv = toBigInt(maxLtv, "maxLtvBps");
  if (ltv < 0n || ltv > BigInt(BPS)) throw new Error(`maxLtvBps out of range: ${ltv}`);
  if (typeof paused !== "boolean") throw new Error(`borrowPaused: expected a boolean, got ${typeof paused}`);
  const applied = toBigInt(lastApplied, "lastAppliedClaimId");
  if (applied < 0n) throw new Error("lastAppliedClaimId is negative");
  return { maxLtvBps: Number(ltv), borrowPaused: paused, lastAppliedClaimId: applied };
}

function positiveUsd8(value: string | undefined): bigint | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const parsed = BigInt(value);
  return parsed > 0n ? parsed : null;
}

function positiveBps(value: number | undefined): number | null {
  return typeof value === "number" && value > 0 && value <= BPS ? value : null;
}

export function vaultConfig(chainId: number): VaultConfig {
  const deployment = DEPLOYMENTS[chainId];
  if (!deployment) {
    return { defaultMaxLtvBps: null, reducedLtvBps: null, ltvThresholdUsd8: null, pauseThresholdUsd8: null };
  }
  return {
    defaultMaxLtvBps: positiveBps(deployment.defaultMaxLtvBps),
    reducedLtvBps: positiveBps(deployment.reducedLtvBps),
    ltvThresholdUsd8: positiveUsd8(deployment.ltvThresholdUsd8),
    pauseThresholdUsd8: positiveUsd8(deployment.pauseThresholdUsd8),
  };
}

export function formatLtvBps(bps: number | null): string {
  return bps === null ? UNAVAILABLE : `${(bps / 100).toFixed(2)}%`;
}

export function formatPaused(paused: boolean | null, whenPaused: string, whenActive: string): string {
  if (paused === null) return UNAVAILABLE;
  return paused ? whenPaused : whenActive;
}

export function formatThreshold(usd8: bigint | null): string {
  return usd8 === null ? "not configured" : formatUsd8(usd8);
}

/** "DEFAULT" or "TIGHTENED (default x%)", judged against the deployment's default max LTV. */
export function ltvStatusLabel(bps: number | null, cfg: VaultConfig): string {
  if (bps === null) return UNAVAILABLE;
  if (cfg.defaultMaxLtvBps === null) return "CONFIG_UNKNOWN";
  if (bps < cfg.defaultMaxLtvBps) return `TIGHTENED (default ${formatLtvBps(cfg.defaultMaxLtvBps)})`;
  return "DEFAULT";
}
