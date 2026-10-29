import { BaseError, isAddress } from "viem";

/** The lifecycle stage a wallet connection reached, as far as the app can verify it. */
export type WalletStage =
  | "connected"
  | "wrong-network"
  | "no-session"
  | "expired"
  | "no-evm-namespace"
  | "no-account"
  | "rejected"
  | "timeout"
  | "disconnected"
  | "error";

/**
 * A redacted view of a WalletConnect session: counts and chain ids only. It never holds the
 * session topic, pairing URI, symmetric key, peer metadata or account addresses.
 */
export interface SessionSummary {
  hasEip155: boolean;
  accountCount: number;
  invalidAccountCount: number;
  accountChainIds: number[];
  methodCount: number;
}

export interface WalletDiagnostic {
  stage: WalletStage;
  walletName: string;
  message: string;
  summary: SessionSummary | null;
}

const CAIP10_EIP155 = /^eip155:(\d+):(0x[0-9a-fA-F]{40})$/;

function readNamespace(session: unknown): { accounts: unknown[]; methods: unknown[] } | null | undefined {
  if (!session || typeof session !== "object") return undefined;
  const namespaces = (session as { namespaces?: unknown }).namespaces;
  if (!namespaces || typeof namespaces !== "object") return null;
  const eip155 = (namespaces as Record<string, unknown>).eip155;
  if (!eip155 || typeof eip155 !== "object") return null;
  const { accounts, methods } = eip155 as { accounts?: unknown; methods?: unknown };
  return { accounts: Array.isArray(accounts) ? accounts : [], methods: Array.isArray(methods) ? methods : [] };
}

/** Returns null when there is no session at all. */
export function summarizeSession(session: unknown): SessionSummary | null {
  const ns = readNamespace(session);
  if (ns === undefined) return null;
  if (ns === null) {
    return { hasEip155: false, accountCount: 0, invalidAccountCount: 0, accountChainIds: [], methodCount: 0 };
  }
  const chainIds = new Set<number>();
  let valid = 0;
  for (const entry of ns.accounts) {
    const match = typeof entry === "string" ? CAIP10_EIP155.exec(entry) : null;
    if (match && isAddress(match[2], { strict: false })) {
      valid += 1;
      chainIds.add(Number(match[1]));
    }
  }
  return {
    hasEip155: true,
    accountCount: valid,
    invalidAccountCount: ns.accounts.length - valid,
    accountChainIds: [...chainIds],
    methodCount: ns.methods.length,
  };
}

export function redactAddress(address: string): string {
  return address.length > 10 ? `${address.slice(0, 6)}…${address.slice(-4)}` : address;
}

interface ConnectedContext {
  walletName: string;
  targetChainId: number;
  accounts: readonly string[];
  chainId: number;
  summary: SessionSummary | null;
}

/** Classifies a connect call that returned: a real account, the wrong chain, or no usable account. */
export function diagnoseConnected(ctx: ConnectedContext): WalletDiagnostic {
  const base = { walletName: ctx.walletName, summary: ctx.summary };
  if (ctx.summary && !ctx.summary.hasEip155) {
    return {
      ...base,
      stage: "no-evm-namespace",
      message: `${ctx.walletName} paired but approved no EVM (eip155) namespace, so there is no Ethereum account to use. Disconnect it in the wallet and try another wallet.`,
    };
  }
  if (ctx.accounts.length === 0) {
    const elsewhere = ctx.summary?.accountChainIds.length
      ? ` It shared accounts only on chain(s) ${ctx.summary.accountChainIds.join(", ")}.`
      : "";
    return {
      ...base,
      stage: "no-account",
      message: `${ctx.walletName} paired but did not share an EVM account for this app.${elsewhere} Not connected; nothing was sent.`,
    };
  }
  if (ctx.chainId !== ctx.targetChainId) {
    return {
      ...base,
      stage: "wrong-network",
      message: `${ctx.walletName} connected ${redactAddress(ctx.accounts[0])} on chain ${ctx.chainId}, but StressProof runs on chain ${ctx.targetChainId}. You can browse; transactions stay disabled until the wallet is on chain ${ctx.targetChainId}.`,
    };
  }
  return { ...base, stage: "connected", message: `${ctx.walletName} connected ${redactAddress(ctx.accounts[0])}.` };
}

// Pairing URIs, symmetric keys and 32-hex project IDs must never reach the UI.
const SECRET_PATTERNS = [/wc:[^\s]+/gi, /symKey=[^\s&]+/gi, /\b[0-9a-f]{32}\b/gi];

function safeShortMessage(error: unknown): string {
  const raw =
    error instanceof BaseError ? error.shortMessage : error instanceof Error ? error.message : "Unknown wallet error";
  const redacted = SECRET_PATTERNS.reduce((text, pattern) => text.replace(pattern, "[redacted]"), raw);
  return redacted.split("\n")[0].slice(0, 160);
}

function hasRejection(error: unknown): boolean {
  let current: unknown = error;
  for (let depth = 0; current && depth < 6; depth += 1) {
    const e = current as { name?: string; code?: number; message?: string; cause?: unknown };
    if (e.name === "UserRejectedRequestError" || e.code === 4001 || /user rejected/i.test(e.message ?? "")) return true;
    current = e.cause;
  }
  return false;
}

interface ErrorContext {
  walletName: string;
  summary: SessionSummary | null;
}

/** WalletConnect's own message when a session proposal (QR code) outlives its 5-minute expiry. */
export const PROPOSAL_EXPIRED = "Proposal expired";
const EXPIRED_MESSAGE = "Connection request expired. Generate a new QR code and scan again.";

/** Classifies a failed connect call by lifecycle stage, with a redacted message. */
export function diagnoseConnectError(error: unknown, ctx: ErrorContext): WalletDiagnostic {
  const base = { walletName: ctx.walletName, summary: ctx.summary };
  const stage = (error as { stage?: WalletStage } | null)?.stage;
  if (stage && error instanceof Error) return { ...base, stage, message: error.message };
  if (hasRejection(error)) {
    return { ...base, stage: "rejected", message: `${ctx.walletName} rejected the connection. Nothing was sent.` };
  }
  const message = safeShortMessage(error);
  if (message === PROPOSAL_EXPIRED) {
    return { ...base, stage: "expired", message: EXPIRED_MESSAGE };
  }
  if (/request reset/i.test(message)) {
    return {
      ...base,
      stage: "no-session",
      message: `The QR pairing closed before ${ctx.walletName} approved a session. Not connected; scan a new code to retry.`,
    };
  }
  return { ...base, stage: "error", message: `${ctx.walletName} connection failed: ${message}` };
}

/** An error that already carries its diagnosed stage. */
export class WalletConnectionError extends Error {
  readonly stage: WalletStage;
  constructor(diagnostic: WalletDiagnostic) {
    super(diagnostic.message);
    this.name = "WalletConnectionError";
    this.stage = diagnostic.stage;
  }
}

// Tiny external store so any component can show the latest diagnostic (one subscription each).
let current: WalletDiagnostic | null = null;
const listeners = new Set<() => void>();

export function reportWalletDiagnostic(diagnostic: WalletDiagnostic): void {
  current = diagnostic;
  listeners.forEach((listener) => listener());
}

export function clearWalletDiagnostic(): void {
  current = null;
  listeners.forEach((listener) => listener());
}

export function getWalletDiagnostic(): WalletDiagnostic | null {
  return current;
}

export function subscribeWalletDiagnostic(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Connection timing from `performance.now()`: when the wallet approved the session, when the
 * guard validated the account, and when the header first rendered it. Numbers only.
 */
export interface WalletTiming {
  approvedAt?: number;
  validatedAt?: number;
  visibleAt?: number;
  approvalToVisibleMs?: number;
}

let timing: WalletTiming = {};

function publishTiming(): void {
  // Dev-only read-out for measuring the flow in a browser; holds no session data.
  if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
    (window as unknown as { __stressproofWalletTiming?: WalletTiming }).__stressproofWalletTiming = { ...timing };
  }
}

export function resetWalletTiming(): void {
  timing = {};
  publishTiming();
}

export function noteSessionApproved(at: number): void {
  timing = { approvedAt: at };
  publishTiming();
}

export function noteSessionValidated(at: number): void {
  if (timing.approvedAt === undefined) return;
  timing = { ...timing, validatedAt: at };
  publishTiming();
}

/** Called when the header first shows the account after an approval; later calls are ignored. */
export function markWalletVisible(at: number): void {
  if (timing.approvedAt === undefined || timing.visibleAt !== undefined) return;
  timing = { ...timing, visibleAt: at, approvalToVisibleMs: Math.round(at - timing.approvedAt) };
  publishTiming();
}

export function getWalletTiming(): WalletTiming {
  return timing;
}

/** Stages where the last attempt ended without a usable connection (shown with a retry). */
const CONNECTION_ERROR_STAGES: readonly WalletStage[] = [
  "no-session",
  "expired",
  "no-evm-namespace",
  "no-account",
  "rejected",
  "timeout",
  "disconnected",
  "error",
];

export function isConnectionErrorStage(stage: WalletStage): boolean {
  return CONNECTION_ERROR_STAGES.includes(stage);
}

// Whether a WalletConnect attempt (a live QR code) is still waiting for the wallet. wagmi's own
// status can drop to "disconnected" when an older, superseded attempt fails, so the buttons
// also read this flag to keep showing CONNECTING for the newest attempt.
let attemptPending = false;

export function setWalletAttemptPending(pending: boolean): void {
  if (attemptPending === pending) return;
  attemptPending = pending;
  listeners.forEach((listener) => listener());
}

export function isWalletAttemptPending(): boolean {
  return attemptPending;
}
