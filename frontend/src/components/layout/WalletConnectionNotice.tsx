"use client";

import { AlertTriangle, X } from "lucide-react";
import { useWalletDiagnostic } from "@/lib/web3/useWalletDiagnostic";
import { clearWalletDiagnostic, isConnectionErrorStage, type WalletStage } from "@/lib/web3/walletDiagnostics";

const STAGE_LABEL: Record<WalletStage, string> = {
  connected: "CONNECTED",
  "wrong-network": "WRONG_NETWORK",
  "no-session": "NO_SESSION_APPROVED",
  expired: "CONNECTION_EXPIRED",
  "no-evm-namespace": "NO_EVM_NAMESPACE",
  "no-account": "PAIRED_WITHOUT_ACCOUNT",
  rejected: "CONNECTION_REJECTED",
  timeout: "CONNECTION_TIMED_OUT",
  disconnected: "SESSION_ENDED",
  error: "CONNECTION_FAILED",
};

/** Explains why the last wallet connection did not finish, with a Close action. */
export function WalletConnectionNotice() {
  const diagnostic = useWalletDiagnostic();
  // Successful and wrong-network results are shown by the header and the wrong-chain banner.
  if (!diagnostic || !isConnectionErrorStage(diagnostic.stage)) return null;

  return (
    <div
      role="status"
      className="w-full bg-amber-950/90 border-b-2 border-amber-500 text-amber-100 px-4 py-2 font-mono text-xs flex items-start justify-between gap-3 z-50"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <span>
          <strong className="font-bold uppercase">{STAGE_LABEL[diagnostic.stage]}:</strong> {diagnostic.message}
        </span>
      </div>
      <button
        type="button"
        onClick={clearWalletDiagnostic}
        aria-label="Close wallet notice"
        className="flex items-center gap-1 px-2 py-1 border border-amber-500 hover:bg-amber-900 text-[11px] font-bold uppercase shrink-0"
      >
        <X className="h-3 w-3" /> CLOSE
      </button>
    </div>
  );
}
