"use client";

import { Wallet, AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { TARGET_CHAIN_ID } from "@/lib/web3/wagmi";
import { walletButtonState } from "@/lib/web3/walletButtonState";
import { useWalletButtonContext } from "@/lib/web3/useWalletDiagnostic";

const BUTTON =
  "flex items-center gap-2 px-3 py-1.5 border bg-background transition-all text-xs shadow-[2px_2px_0px_0px_hsl(var(--border))]";

/**
 * The account shown here is always the authorized wallet account from wagmi (the same account
 * that signs). There is no fallback address: without a connection the button says CONNECT_WALLET.
 */
function WalletControl() {
  const { status, error } = useWalletButtonContext();
  return (
    <ConnectButton.Custom>
      {({ account, chain, mounted, openAccountModal, openChainModal, openConnectModal }) => {
        const state = walletButtonState({ mounted, status, account, chain, targetChainId: TARGET_CHAIN_ID, error });
        switch (state.kind) {
          case "loading":
            return <div aria-hidden className="h-[30px] w-[132px]" />;
          case "disconnected":
          case "connecting": {
            const connecting = state.kind === "connecting";
            return (
              <button
                onClick={openConnectModal}
                disabled={connecting}
                className={`${BUTTON} border-border text-foreground hover:border-foreground disabled:opacity-60`}
              >
                {connecting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#ea580c]" />
                ) : (
                  <Wallet className="h-3.5 w-3.5 text-[#ea580c]" />
                )}
                <span className="text-[11px] font-mono font-bold">{connecting ? "CONNECTING..." : "CONNECT_WALLET"}</span>
              </button>
            );
          }
          case "connection-error":
            return (
              <button
                onClick={openConnectModal}
                title={state.message}
                className={`${BUTTON} border-amber-500 text-amber-300 hover:border-amber-300`}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span className="text-[11px] font-mono font-bold">RETRY_CONNECT</span>
              </button>
            );
          case "wrong-network":
            return (
              <button onClick={openChainModal} className={`${BUTTON} border-amber-500 text-amber-300 hover:border-amber-300`}>
                <AlertTriangle className="h-3.5 w-3.5" />
                <span className="text-[11px] font-mono font-bold">WRONG_NETWORK ({state.chainId})</span>
              </button>
            );
          case "connected":
            return (
              <button
                onClick={openAccountModal}
                title="Connected wallet account (signs StressProof transactions)"
                className={`${BUTTON} border-border text-foreground hover:border-foreground`}
              >
                <span className="h-1.5 w-1.5 bg-emerald-400" />
                <span className="text-[11px] font-mono">{state.displayName}</span>
              </button>
            );
        }
      }}
    </ConnectButton.Custom>
  );
}

export function PortalTopNav() {
  const chainName = TARGET_CHAIN_ID === 84532 ? "BASE_SEPOLIA // 84532" : "ANVIL_LOCAL // 31337";

  return (
    <header className="h-16 px-3.5 sm:px-6 flex items-center justify-between bg-card border-b-2 border-border sticky top-0 z-40 font-mono shrink-0">
      {/* Spacer for mobile drawer button */}
      <div className="w-10 lg:hidden shrink-0" />

      {/* Right Action Icons & Badges */}
      <div className="flex items-center gap-2 sm:gap-3 ml-auto">
        {/* MOCK MARKET Badge (§19.1) */}
        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-xs text-foreground tracking-wider font-bold">
          <span>MOCK MARKET</span>
        </div>

        {/* Snapshot price of the fixture dataset (static, not a live oracle feed) */}
        <div
          className="hidden lg:flex items-center gap-2 px-3 py-1 border border-border bg-background text-xs"
          title="WETH price recorded in the weth-stable-fixture-v1 snapshot; not a live feed"
        >
          <span className="text-[11px] font-bold text-foreground tracking-wider">SNAPSHOT_PRICE:</span>
          <span className="text-[11px] text-[#ea580c] font-bold">$3,000 WETH</span>
        </div>

        {/* The chain this build of StressProof reads and writes (from NEXT_PUBLIC_CHAIN_ID) */}
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-xs text-foreground tracking-wider"
          title="StressProof's deployment chain"
        >
          <span className="h-1.5 w-1.5 bg-emerald-400" />
          <span>{chainName}</span>
        </div>

        <WalletControl />
      </div>
    </header>
  );
}
