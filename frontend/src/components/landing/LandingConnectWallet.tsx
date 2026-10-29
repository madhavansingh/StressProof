"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConnectButton, useConnectModal } from "@rainbow-me/rainbowkit";
import { useAccount } from "wagmi";
import { AlertTriangle, ArrowRight, Loader2, RotateCcw, Wallet } from "lucide-react";
import { TARGET_CHAIN_ID } from "@/lib/web3/wagmi";
import { landingConnectOutcome, walletButtonState, type WalletButtonState } from "@/lib/web3/walletButtonState";
import { useWalletButtonContext, useWalletDiagnostic } from "@/lib/web3/useWalletDiagnostic";

const DASHBOARD_PATH = "/dashboard";
const NOT_CONNECTED_NOTICE = "NOT CONNECTED: the request was rejected or closed. Nothing was sent.";

const SHELL =
  "group flex shrink-0 items-center gap-0 whitespace-nowrap text-xs font-bold uppercase tracking-wider border-2 transition-all shadow-[2px_2px_0px_0px_hsl(var(--border))]";
const PRIMARY = `${SHELL} bg-foreground text-background border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white disabled:opacity-60 disabled:hover:bg-foreground disabled:hover:border-foreground disabled:hover:text-background`;
const ICON_BOX =
  "flex items-center justify-center w-7 h-7 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors";

interface ButtonViewProps {
  state: WalletButtonState;
  onConnect: () => void;
  onEnter: () => void;
  onWrongNetwork: () => void;
}

function ButtonView({ state, onConnect, onEnter, onWrongNetwork }: ButtonViewProps) {
  switch (state.kind) {
    case "loading":
      return <div aria-hidden className="h-[32px] w-[150px]" />;
    case "connecting":
      return (
        <button type="button" disabled className={PRIMARY}>
          <span className={ICON_BOX}>
            <Loader2 size={14} className="animate-spin" />
          </span>
          <span className="px-3 py-1.5">CONNECTING...</span>
        </button>
      );
    case "connection-error":
      return (
        <button
          type="button"
          onClick={onConnect}
          title={state.message}
          aria-label="Retry wallet connection"
          className={`${SHELL} bg-background text-amber-300 border-amber-500 hover:border-amber-300`}
        >
          <span className="flex items-center justify-center w-7 h-7 bg-amber-500 text-background">
            <RotateCcw size={14} />
          </span>
          <span className="px-3 py-1.5">
            RETRY<span className="hidden sm:inline"> CONNECT</span>
          </span>
        </button>
      );
    case "wrong-network":
      return (
        <button
          type="button"
          onClick={onWrongNetwork}
          title={`Your wallet is on chain ${state.chainId}; StressProof runs on chain ${TARGET_CHAIN_ID}. Transactions stay disabled until it matches.`}
          className={`${SHELL} bg-background text-amber-300 border-amber-500 hover:border-amber-300`}
        >
          <span className="flex items-center justify-center w-7 h-7 bg-amber-500 text-background">
            <AlertTriangle size={14} />
          </span>
          <span className="px-3 py-1.5">WRONG NETWORK ({state.chainId})</span>
        </button>
      );
    case "connected":
      return (
        <button type="button" onClick={onEnter} title="Open the dashboard with this wallet account" className={PRIMARY}>
          <span className={ICON_BOX}>
            <ArrowRight size={14} />
          </span>
          <span className="px-3 py-1.5 normal-case font-mono">{state.displayName}</span>
        </button>
      );
    case "disconnected":
      return (
        <button type="button" onClick={onConnect} aria-label="Connect wallet" className={PRIMARY}>
          <span className={ICON_BOX}>
            <Wallet size={14} />
          </span>
          {/* Phones show CONNECT next to the wallet icon so the header stays on one line. */}
          <span className="px-3 py-1.5">
            CONNECT<span className="hidden sm:inline"> WALLET</span>
          </span>
        </button>
      );
  }
}

/**
 * Landing-page wallet entry. It opens the shared RainbowKit connect modal (the same one the
 * dashboard uses, Cake Wallet included) and, once a connection the visitor started here
 * succeeds, moves to the dashboard. Connecting never sends a transaction.
 */
export function LandingConnectWallet() {
  const router = useRouter();
  const { address, chainId } = useAccount();
  const { status, error } = useWalletButtonContext();
  const { connectModalOpen } = useConnectModal();
  const clickedRef = useRef(false);
  const [requested, setRequested] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // A specific reason from the WalletConnect guard is shown by the global notice instead.
  const diagnostic = useWalletDiagnostic();

  // Count a request only once the modal has actually opened from our click.
  useEffect(() => {
    if (connectModalOpen && clickedRef.current) {
      clickedRef.current = false;
      setRequested(true);
    }
  }, [connectModalOpen]);

  const hookState = walletButtonState({
    mounted: true,
    status,
    account: address ? { displayName: address } : undefined,
    chain: chainId ? { id: chainId } : undefined,
    targetChainId: TARGET_CHAIN_ID,
    error,
  });

  useEffect(() => {
    const outcome = landingConnectOutcome({ requested, modalOpen: connectModalOpen, state: hookState });
    if (outcome === "enter-dashboard") {
      setRequested(false);
      router.push(DASHBOARD_PATH);
    } else if (outcome === "not-connected") {
      setRequested(false);
      setNotice(NOT_CONNECTED_NOTICE);
    }
    // hookState is rebuilt each render; its kind is what matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested, connectModalOpen, hookState.kind, router]);

  return (
    <ConnectButton.Custom>
      {({ account, chain, mounted, openConnectModal, openChainModal }) => {
        const state = walletButtonState({ mounted, status, account, chain, targetChainId: TARGET_CHAIN_ID, error });
        return (
          <div className="relative">
            <ButtonView
              state={state}
              onConnect={() => {
                setNotice(null);
                clickedRef.current = true;
                openConnectModal();
              }}
              onEnter={() => router.push(DASHBOARD_PATH)}
              onWrongNetwork={openChainModal}
            />
            {notice && !diagnostic && state.kind === "disconnected" && (
              <p
                role="status"
                className="absolute right-0 top-full mt-2 w-64 border border-border bg-background px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground shadow-[2px_2px_0px_0px_hsl(var(--border))]"
              >
                {notice}
              </p>
            )}
          </div>
        );
      }}
    </ConnectButton.Custom>
  );
}
