import { createConnector, type CreateConnectorFn } from "@wagmi/core";
import { SwitchChainError } from "viem";
import {
  clearWalletDiagnostic,
  diagnoseConnectError,
  diagnoseConnected,
  noteSessionApproved,
  noteSessionValidated,
  PROPOSAL_EXPIRED,
  reportWalletDiagnostic,
  resetWalletTiming,
  setWalletAttemptPending,
  summarizeSession,
  WalletConnectionError,
  type SessionSummary,
} from "./walletDiagnostics";

export interface WalletConnectGuardOptions {
  walletName: string;
  /** The deployment chain; only used to describe the result, never to force a switch. */
  targetChainId: number;
  /**
   * Chains the wallet is documented to support. A switch goes ahead when the chain is approved in
   * the live session or listed here; any other request fails at once instead of waiting forever.
   */
  canSwitchTo?: (chainId: number) => boolean;
  /** How long setup may take after the wallet approved the session. */
  setupTimeoutMs?: number;
  /**
   * Extra chains offered as optional in the WalletConnect proposal, so a wallet that does not
   * support the app's chains can still share an account. They never become app chains: reads
   * and writes stay pinned to the deployment chain, and the UI shows WRONG_NETWORK.
   */
  extraOptionalChains?: readonly number[];
  /**
   * When to withdraw an unanswered proposal. Just under WalletConnect's 5-minute TTL, so the
   * clean expiry path runs before its own timer (which leaves an unhandled rejection behind).
   */
  proposalLifetimeMs?: number;
}

const DEFAULT_SETUP_TIMEOUT_MS = 30_000;
const DEFAULT_PROPOSAL_LIFETIME_MS = 5 * 60_000 - 5_000;

type Listener = (...args: unknown[]) => void;
interface Emitter {
  on?: (event: string, listener: Listener) => unknown;
  removeListener?: (event: string, listener: Listener) => unknown;
}
interface ProposalOptions {
  optionalChains?: number[];
}
/** The parts of WalletConnect's SignClient used here: events and the pending-proposal store. */
interface SignClientLike extends Emitter {
  events?: { emit?: (event: string, payload: unknown) => unknown };
  proposal?: { getAll?: () => ReadonlyArray<{ id?: unknown }> };
}
interface WalletConnectProviderLike extends Emitter {
  session?: unknown;
  connect?: (options?: ProposalOptions) => Promise<unknown>;
  /** WalletConnect's UniversalProvider; its sign client emits session_expire. */
  signer?: { client?: SignClientLike };
}

type Connector = ReturnType<CreateConnectorFn>;
type ConnectParams = Parameters<Connector["connect"]>[0];
type ConnectResult = Awaited<ReturnType<Connector["connect"]>>;

const now = (): number => (typeof performance !== "undefined" ? performance.now() : Date.now());

function sessionTopic(provider: WalletConnectProviderLike | null): string | null {
  const topic = (provider?.session as { topic?: unknown } | null | undefined)?.topic;
  return typeof topic === "string" ? topic : null;
}

const extendedProviders = new WeakSet<object>();

// Cancel functions of every attempt still waiting for a wallet, across connectors.
const pendingAttempts = new Set<() => void>();

/**
 * Marks every pending attempt as cancelled (the connect modal closed). WalletConnect cannot
 * withdraw a proposal in this version, so the old QR stays valid until it expires; when it does,
 * the cancelled attempt reports nothing and changes no state.
 */
export function cancelPendingWalletConnectAttempts(): void {
  [...pendingAttempts].forEach((cancel) => cancel());
}

/**
 * Withdraws this provider's pending proposals through WalletConnect's own expiry event: the sign
 * client rejects each waiting approval with "Proposal expired" and clears its 5-minute timer, so
 * no stray rejection is left behind (its timer path stores an unawaited Promise.reject). The old
 * QR codes can then no longer complete a session in this app.
 */
function withdrawPendingProposals(provider: WalletConnectProviderLike | null): void {
  const client = provider?.signer?.client;
  const pending = client?.proposal?.getAll?.() ?? [];
  pending.forEach(({ id }) => {
    if (typeof id === "number") client?.events?.emit?.("proposal_expire", { id });
  });
}

/** The pairing ended without approval: the proposal expired or the request was reset. */
function isPairingEnd(error: unknown): boolean {
  const message = error instanceof Error ? error.message : "";
  return message === PROPOSAL_EXPIRED || /request reset/i.test(message);
}

/**
 * Appends chains to every proposal this provider sends. wagmi builds the proposal only from the
 * app's chains, and the instance is WalletConnect's, so its connect method is wrapped once.
 */
function extendProposalChains(provider: WalletConnectProviderLike | null, extra: readonly number[]): void {
  const original = provider?.connect;
  if (!provider || !original || !extra.length || extendedProviders.has(provider)) return;
  extendedProviders.add(provider);
  provider.connect = (options?: ProposalOptions) => {
    const requested = options?.optionalChains ?? [];
    const optionalChains = [...requested, ...extra.filter((id) => !requested.includes(id))];
    return original.call(provider, { ...options, optionalChains });
  };
}

/** Chain ids the live WalletConnect session approved (from its eip155 accounts and chains). */
function sessionChainIds(provider: WalletConnectProviderLike | null): number[] {
  const namespaces = (provider?.session as { namespaces?: Record<string, { accounts?: unknown; chains?: unknown }> } | null)
    ?.namespaces;
  const eip155 = namespaces?.eip155;
  const entries = [
    ...(Array.isArray(eip155?.accounts) ? eip155.accounts : []),
    ...(Array.isArray(eip155?.chains) ? eip155.chains : []),
  ];
  const ids = entries
    .map((entry) => (typeof entry === "string" ? Number(entry.split(":")[1]) : Number.NaN))
    .filter((id) => Number.isInteger(id));
  return [...new Set(ids)];
}

async function readProvider(connector: Connector): Promise<WalletConnectProviderLike | null> {
  try {
    const provider = await connector.getProvider();
    return provider && typeof provider === "object" ? (provider as WalletConnectProviderLike) : null;
  } catch {
    return null;
  }
}

/**
 * Runs the connector's connect. Waiting for the QR scan has no limit here (WalletConnect expires
 * the proposal itself), but once the wallet approves, setup must finish within `timeoutMs`.
 */
function runWithSetupTimeout(
  start: () => Promise<ConnectResult>,
  provider: WalletConnectProviderLike | null,
  timeoutMs: number,
  walletName: string
): Promise<ConnectResult> {
  return new Promise<ConnectResult>((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onApproved: Listener = () => {
      if (timer) return;
      noteSessionApproved(now());
      timer = setTimeout(() => {
        reject(
          new WalletConnectionError({
            stage: "timeout",
            walletName,
            summary: summarizeSession(provider?.session),
            message: `${walletName} approved the session but setup timed out after ${Math.round(timeoutMs / 1000)}s. Not connected; nothing was sent.`,
          })
        );
      }, timeoutMs);
    };
    provider?.on?.("connect", onApproved);
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      provider?.removeListener?.("connect", onApproved);
    };
    start().then(
      (result) => {
        cleanup();
        resolve(result);
      },
      (error: unknown) => {
        cleanup();
        reject(error);
      }
    );
  });
}

function accountsOf(result: ConnectResult): string[] {
  return (result.accounts as readonly unknown[]).map((entry) =>
    typeof entry === "object" && entry !== null ? String((entry as { address: string }).address) : String(entry)
  );
}

/**
 * Wraps a WalletConnect connector so a connection always finishes and reports what it really
 * authorized:
 * - connect never asks the wallet to switch chains (RainbowKit passes the app chain, and a
 *   wallet that cannot use that chain would leave the request, and the UI, pending forever);
 *   the session's own chain is reported and the app shows WRONG_NETWORK when it differs;
 * - a session that exposes no EVM account is disconnected and reported, never shown as connected;
 * - setup after approval has a timeout; switches to chains the wallet cannot use fail at once;
 * - a wallet-side disconnect or a session expiry ends the connection at once;
 * - one QR code at a time: a new attempt, a closed modal or the end of a proposal's lifetime
 *   withdraws pending proposals, and only the newest attempt may update the UI.
 * Nothing here sends a transaction or relaxes the write guard.
 */
export function withWalletConnectGuards(base: CreateConnectorFn, options: WalletConnectGuardOptions): CreateConnectorFn {
  const timeoutMs = options.setupTimeoutMs ?? DEFAULT_SETUP_TIMEOUT_MS;
  const { walletName, targetChainId, canSwitchTo, extraOptionalChains = [] } = options;
  const proposalLifetimeMs = options.proposalLifetimeMs ?? DEFAULT_PROPOSAL_LIFETIME_MS;

  return createConnector((config) => {
    const inner = base(config);
    // Per connector instance: the session being watched and the connector that owns it.
    // Only the newest attempt on this connector may update the UI.
    let latestAttempt = 0;
    const watched = {
      provider: null as WalletConnectProviderLike | null,
      topic: null as string | null,
      owner: null as Connector | null,
    };

    const onSessionDelete: Listener = () => {
      // wagmi's own listener already disconnects; this only explains why.
      reportWalletDiagnostic({
        stage: "disconnected",
        walletName,
        summary: null,
        message: `${walletName} ended the session (disconnected in the wallet). Connect again to continue.`,
      });
    };

    const onSessionExpire: Listener = (event) => {
      const topic = (event as { topic?: unknown } | null)?.topic;
      if (!watched.topic || topic !== watched.topic || !watched.owner) return;
      const owner = watched.owner;
      watched.topic = null;
      reportWalletDiagnostic({
        stage: "disconnected",
        walletName,
        summary: null,
        message: `The ${walletName} session expired. Connect again to continue.`,
      });
      owner.onDisconnect();
      void inner.disconnect.call(owner).catch(() => undefined);
    };

    /** Subscribes once per provider instance, so reconnects never stack listeners. */
    const watch = (provider: WalletConnectProviderLike | null, owner: Connector) => {
      watched.owner = owner;
      watched.topic = sessionTopic(provider);
      if (!provider || watched.provider === provider) return;
      watched.provider = provider;
      provider.on?.("session_delete", onSessionDelete);
      provider.signer?.client?.on?.("session_expire", onSessionExpire);
    };

    const guardedSetup = async function (this: Connector): Promise<void> {
      await inner.setup?.call(this);
      // A session restored after a reload is watched too.
      const provider = await readProvider(this);
      if (sessionTopic(provider)) watch(provider, this);
    };

    const guardedConnect = async function (this: Connector, params?: ConnectParams): Promise<ConnectResult> {
      const { chainId: _requestedChain, ...rest } = (params ?? {}) as { chainId?: number };
      clearWalletDiagnostic();
      resetWalletTiming();
      const attemptId = ++latestAttempt;
      setWalletAttemptPending(true);
      const provider = await readProvider(this);
      // One QR at a time: a new attempt withdraws the proposals of earlier ones.
      withdrawPendingProposals(provider);
      extendProposalChains(provider, extraOptionalChains);

      let cancelled = false;
      const isCurrent = () => !cancelled && attemptId === latestAttempt;
      const cancel = () => {
        cancelled = true;
        pendingAttempts.delete(cancel);
        if (attemptId === latestAttempt) setWalletAttemptPending(false);
        withdrawPendingProposals(provider);
      };
      pendingAttempts.add(cancel);
      const lifetimeTimer = setTimeout(() => {
        if (isCurrent()) withdrawPendingProposals(provider);
      }, proposalLifetimeMs);
      let summary: SessionSummary | null = null;
      try {
        const result = await runWithSetupTimeout(
          () => inner.connect.call(this, rest as ConnectParams) as Promise<ConnectResult>,
          provider,
          timeoutMs,
          walletName
        );
        summary = summarizeSession(provider?.session);
        const diagnostic = diagnoseConnected({
          walletName,
          targetChainId,
          accounts: accountsOf(result),
          chainId: Number(result.chainId),
          summary,
        });
        if (diagnostic.stage === "no-account" || diagnostic.stage === "no-evm-namespace") {
          throw new WalletConnectionError(diagnostic);
        }
        noteSessionValidated(now());
        watch(provider, this);
        // A real approval wins even from an older QR code; newer attempts become stale.
        setWalletAttemptPending(false);
        reportWalletDiagnostic(diagnostic);
        return result;
      } catch (error: unknown) {
        // A superseded or cancelled attempt, or a newer QR expiring after another one was
        // approved, must not report, close anything or drop the live session.
        const stale =
          !(error instanceof WalletConnectionError) &&
          (!isCurrent() || (isPairingEnd(error) && sessionTopic(provider) !== null));
        if (stale) throw error;
        const diagnostic = diagnoseConnectError(error, { walletName, summary: summary ?? summarizeSession(provider?.session) });
        // Drop a session that cannot be used so the wallet and the app agree it is closed.
        if (provider?.session) await inner.disconnect.call(this).catch(() => undefined);
        reportWalletDiagnostic(diagnostic);
        throw error;
      } finally {
        clearTimeout(lifetimeTimer);
        pendingAttempts.delete(cancel);
        if (attemptId === latestAttempt && !cancelled) setWalletAttemptPending(false);
      }
    };

    const innerSwitch = inner.switchChain;
    const guardedSwitch =
      innerSwitch && canSwitchTo
        ? async function (this: Connector, params: Parameters<NonNullable<Connector["switchChain"]>>[0]) {
            const approved = sessionChainIds(await readProvider(this));
            if (!approved.includes(params.chainId) && !canSwitchTo(params.chainId)) {
              throw new SwitchChainError(
                new Error(`${walletName} cannot switch to chain ${params.chainId}: it does not support that network.`)
              );
            }
            return innerSwitch.call(this, params);
          }
        : innerSwitch;

    // wagmi's connect type is generic over withCapabilities; the guard returns the inner result unchanged.
    return {
      ...inner,
      setup: guardedSetup,
      connect: guardedConnect as Connector["connect"],
      switchChain: guardedSwitch,
    };
  });
}
