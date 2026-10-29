import { BaseError } from "viem";

export type SwitchErrorKind = "rejected" | "unsupported" | "error";

export type SwitchOutcome =
  | { status: "switched" }
  | { status: "unsupported" }
  | { status: "rejected"; message: string }
  | { status: "no-answer"; message: string }
  | { status: "error"; message: string };

// EIP-1193 4902 is "unrecognized chain"; the phrases cover WalletConnect's "chain is not approved"
// error, wagmi's ChainNotConfiguredError and the WalletConnect guard's refusal.
const UNSUPPORTED_CODE = 4902;
const UNSUPPORTED_TEXT =
  /unrecognized chain|not approved|does not support|unsupported chain|cannot switch to chain|chain not configured|wallet_addEthereumChain/i;
const REJECTED_TEXT = /user rejected|user denied/i;
const DEFAULT_SWITCH_TIMEOUT_MS = 60_000;

interface ErrorLike {
  name?: string;
  code?: number;
  message?: string;
  details?: string;
  cause?: unknown;
}

function causeChain(error: unknown): ErrorLike[] {
  const chain: ErrorLike[] = [];
  let current: unknown = error;
  for (let depth = 0; current && typeof current === "object" && depth < 8; depth += 1) {
    chain.push(current as ErrorLike);
    current = (current as ErrorLike).cause;
  }
  return chain;
}

/**
 * Classifies a failed switch from the error itself. Unsupported wins over rejected because
 * wagmi's WalletConnect connector reports a failed add-chain fallback as a user rejection.
 */
export function classifySwitchError(error: unknown): SwitchErrorKind {
  const chain = causeChain(error);
  const text = (e: ErrorLike) => `${e.message ?? ""} ${e.details ?? ""}`;
  if (chain.some((e) => e.code === UNSUPPORTED_CODE || UNSUPPORTED_TEXT.test(text(e)))) return "unsupported";
  if (chain.some((e) => e.code === 4001 || e.name === "UserRejectedRequestError" || REJECTED_TEXT.test(text(e)))) {
    return "rejected";
  }
  return "error";
}

function shortMessage(error: unknown): string {
  const raw = error instanceof BaseError ? error.shortMessage : error instanceof Error ? error.message : "Unknown error";
  return raw.split("\n")[0].slice(0, 160);
}

type SwitchFn = (params: { chainId: number }) => Promise<unknown>;

/**
 * Asks the connected wallet to switch once and reports what actually happened. A wallet that
 * never answers is reported as no-answer (retryable), not as unsupported.
 */
export async function requestChainSwitch(
  switchChain: SwitchFn | undefined,
  chainId: number,
  timeoutMs: number = DEFAULT_SWITCH_TIMEOUT_MS
): Promise<SwitchOutcome> {
  if (!switchChain) return { status: "unsupported" };
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<"timeout">((resolve) => {
    timer = setTimeout(() => resolve("timeout"), timeoutMs);
  });
  try {
    const result = await Promise.race([switchChain({ chainId }).then(() => "done" as const), timeout]);
    if (result === "timeout") {
      return {
        status: "no-answer",
        message: `The wallet did not answer the network switch to chain ${chainId}. Check the wallet, then try again.`,
      };
    }
    return { status: "switched" };
  } catch (error: unknown) {
    const kind = classifySwitchError(error);
    if (kind === "unsupported") return { status: "unsupported" };
    if (kind === "rejected") {
      return {
        status: "rejected",
        message: `Network switch rejected in the wallet. Transactions stay disabled until the wallet is on chain ${chainId}.`,
      };
    }
    return { status: "error", message: `Network switch failed: ${shortMessage(error)}` };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

interface ConnectorLabel {
  name?: string;
  rkDetails?: { name?: string };
}

/**
 * A display name only (never used to decide what a wallet can do). RainbowKit keeps the wallet's
 * own name in rkDetails; wagmi's connector name for any WalletConnect wallet is "WalletConnect".
 */
export function walletLabel(connector: ConnectorLabel | undefined): string {
  return connector?.rkDetails?.name || connector?.name || "Your wallet";
}

export function unsupportedSwitchMessage(walletName: string, chainName: string): string {
  return `${walletName} cannot switch to ${chainName}. Use a browser wallet for local testing, or connect ${walletName} to a supported deployment network.`;
}

/**
 * "switch" keeps offering a network switch; "browse-only" means the wallet showed it cannot
 * switch to the deployment chain, so the banner stops asking and only explains.
 */
export function wrongChainBannerMode(outcome: SwitchOutcome | null): "switch" | "browse-only" {
  return outcome?.status === "unsupported" ? "browse-only" : "switch";
}
