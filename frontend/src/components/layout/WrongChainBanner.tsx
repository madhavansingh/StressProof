"use client";

import { useAccount, useSwitchChain } from "wagmi";
import { TARGET_CHAIN_ID, localAnvilChain } from "@/lib/web3/wagmi";
import { baseSepolia } from "wagmi/chains";
import { AlertTriangle } from "lucide-react";

export function WrongChainBanner() {
  const { isConnected, chainId } = useAccount();
  const { switchChain, isPending } = useSwitchChain();

  if (!isConnected || !chainId || chainId === TARGET_CHAIN_ID) {
    return null;
  }

  const expectedName = TARGET_CHAIN_ID === 84532 ? baseSepolia.name : localAnvilChain.name;

  return (
    <div className="w-full bg-red-950/90 border-b-2 border-red-500 text-red-200 px-4 py-2 font-mono text-xs flex flex-wrap items-center justify-between gap-3 z-50">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 animate-pulse" />
        <span>
          <strong className="text-red-100 font-bold uppercase">WRONG_CHAIN_DETECTED:</strong> Connected to chain ID{" "}
          <code className="bg-red-900/60 px-1 py-0.5 text-white font-bold">{chainId}</code>. Expected target is{" "}
          <code className="bg-red-900/60 px-1 py-0.5 text-white font-bold">
            {TARGET_CHAIN_ID} ({expectedName})
          </code>
          .
        </span>
      </div>

      <button
        type="button"
        disabled={isPending}
        onClick={() => switchChain?.({ chainId: TARGET_CHAIN_ID })}
        className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white font-bold uppercase border border-red-400 transition-colors cursor-pointer text-[11px] disabled:opacity-50"
      >
        {isPending ? "SWITCHING..." : `[SWITCH_TO_${TARGET_CHAIN_ID}]`}
      </button>
    </div>
  );
}

