import { formatUnits } from "viem";

/**
 * Format 8-decimal USD amounts into human-readable currency strings.
 * Implementation Plan §7.2: USD precision is 8 decimals matching Aave base-currency precision.
 *
 * Uses BigInt + formatUnits(raw, 8) with lossless string formatting
 * to prevent IEEE 754 precision loss on large financial figures.
 */
export function formatUsd8(val: string | bigint | number | undefined | null): string {
  if (val === undefined || val === null) return "$0.00";
  try {
    let raw: bigint;
    if (typeof val === "bigint") {
      raw = val;
    } else if (typeof val === "number") {
      raw = BigInt(Math.trunc(val));
    } else {
      const s = val.trim();
      if (!s) return "$0.00";
      raw = s.includes(".") ? BigInt(s.split(".")[0]) : BigInt(s);
    }

    const formatted = formatUnits(raw, 8);
    const isNegative = raw < BigInt(0);
    const [intPart, fracPart = ""] = formatted.split(".");
    const absInt = isNegative ? intPart.replace("-", "") : intPart;
    const formattedInt = BigInt(absInt).toLocaleString("en-US");
    const frac2 = (fracPart + "00").slice(0, 2);
    const sign = isNegative ? "-" : "";
    return `${sign}$${formattedInt}.${frac2}`;
  } catch {
    return "$0.00";
  }
}

/**
 * Format basis points into percentage string.
 * Example: -3000 -> "-30.00%", 8300 -> "83.00%"
 */
export function formatBps(bps: number | undefined | null): string {
  if (bps === undefined || bps === null) return "0.00%";
  const pct = (bps / 100).toFixed(2);
  return `${pct}%`;
}

/**
 * Shorten Ethereum address for display.
 */
export function formatAddress(addr: string | undefined | null): string {
  if (!addr) return "0x0000...0000";
  if (addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

/**
 * Format a Unix timestamp (seconds) into remaining countdown.
 */
export function formatCountdown(
  deadlineSec: number | bigint,
  nowSec: number = Math.floor(Date.now() / 1000)
): { isExpired: boolean; text: string; secondsLeft: number } {
  const deadline = Number(deadlineSec);
  const diff = deadline - nowSec;
  if (diff <= 0) {
    return { isExpired: true, text: "Expired", secondsLeft: 0 };
  }
  const mins = Math.floor(diff / 60);
  const secs = diff % 60;
  return {
    isExpired: false,
    text: `${mins}m ${secs.toString().padStart(2, "0")}s`,
    secondsLeft: diff,
  };
}
