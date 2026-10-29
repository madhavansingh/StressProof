/** wagmi's account status. */
export type AccountStatus = "connected" | "connecting" | "reconnecting" | "disconnected";

export interface WalletButtonInput {
  mounted: boolean;
  status: AccountStatus;
  /** From RainbowKit's ConnectButton.Custom; present only for an authorized wallet account. */
  account?: { displayName: string };
  chain?: { id: number; unsupported?: boolean };
  targetChainId: number;
  /** Why the last connection attempt failed; shown only while no wallet is connected or connecting. */
  error?: { message: string };
}

export type WalletButtonState =
  | { kind: "loading" }
  | { kind: "disconnected" }
  | { kind: "connecting" }
  | { kind: "connection-error"; message: string }
  | { kind: "wrong-network"; chainId: number }
  | { kind: "connected"; displayName: string };

/**
 * The single source for what a wallet button shows. The only account it ever names is the one
 * the wallet authorized; with no account there is no address at all.
 */
export function walletButtonState(input: WalletButtonInput): WalletButtonState {
  if (!input.mounted) return { kind: "loading" };
  if (!input.account || !input.chain) {
    if (input.status === "connecting" || input.status === "reconnecting") return { kind: "connecting" };
    return input.error ? { kind: "connection-error", message: input.error.message } : { kind: "disconnected" };
  }
  if (input.chain.unsupported || input.chain.id !== input.targetChainId) {
    return { kind: "wrong-network", chainId: input.chain.id };
  }
  return { kind: "connected", displayName: input.account.displayName };
}

/** wagmi's status, held at "connecting" while the newest WalletConnect attempt is still pending. */
export function effectiveAccountStatus(status: AccountStatus, attemptPending: boolean): AccountStatus {
  return attemptPending && status !== "connected" ? "connecting" : status;
}

export type LandingConnectOutcome = "idle" | "enter-dashboard" | "not-connected";

export interface LandingConnectInput {
  /** The visitor pressed CONNECT WALLET on the landing page and has not been routed yet. */
  requested: boolean;
  modalOpen: boolean;
  state: WalletButtonState;
}

/**
 * The landing page moves to the dashboard only after a connection the visitor started there,
 * so a returning visitor whose wallet reconnects silently can still read the landing page.
 * A wallet on the wrong chain still enters (reads use the deployment chain, and the dashboard
 * shows WRONG_NETWORK and blocks writes). Connecting never sends a transaction.
 */
export function landingConnectOutcome({ requested, modalOpen, state }: LandingConnectInput): LandingConnectOutcome {
  if (!requested) return "idle";
  if (state.kind === "connected" || state.kind === "wrong-network") return "enter-dashboard";
  if (!modalOpen && (state.kind === "disconnected" || state.kind === "connection-error")) return "not-connected";
  return "idle";
}
