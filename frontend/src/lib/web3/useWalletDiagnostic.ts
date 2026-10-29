"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAccount } from "wagmi";
import {
  getWalletDiagnostic,
  isConnectionErrorStage,
  isWalletAttemptPending,
  markWalletVisible,
  subscribeWalletDiagnostic,
  type WalletDiagnostic,
} from "./walletDiagnostics";
import { effectiveAccountStatus, type AccountStatus } from "./walletButtonState";

/** The latest wallet connection diagnostic (null on the server and before any attempt). */
export function useWalletDiagnostic(): WalletDiagnostic | null {
  return useSyncExternalStore(subscribeWalletDiagnostic, getWalletDiagnostic, () => null);
}

interface WalletButtonContext {
  status: AccountStatus;
  error?: { message: string };
}

/**
 * Shared by every wallet button: wagmi's account status, the last connection error (for the
 * retry state), and the moment the account first renders after a WalletConnect approval.
 */
export function useWalletButtonContext(): WalletButtonContext {
  const { status, address } = useAccount();
  const diagnostic = useWalletDiagnostic();
  const attemptPending = useSyncExternalStore(subscribeWalletDiagnostic, isWalletAttemptPending, () => false);

  useEffect(() => {
    if (status === "connected" && address) markWalletVisible(performance.now());
  }, [status, address]);

  const error = diagnostic && isConnectionErrorStage(diagnostic.stage) ? { message: diagnostic.message } : undefined;
  return { status: effectiveAccountStatus(status, attemptPending), error };
}
