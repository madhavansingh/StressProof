"use client";

import { useState } from "react";
import { useAccount, useDisconnect, useSwitchChain } from "wagmi";
import { baseSepolia } from "wagmi/chains";
import { Eye, Info } from "lucide-react";
import { TARGET_CHAIN_ID, isConfiguredChainId, localAnvilChain } from "@/lib/web3/wagmi";
import {
  requestChainSwitch,
  unsupportedSwitchMessage,
  walletLabel,
  wrongChainBannerMode,
  type SwitchOutcome,
} from "@/lib/web3/chainSwitch";

const BUTTON =
  "px-3 py-1 border border-amber-500 text-amber-200 hover:bg-amber-900/60 font-bold uppercase transition-colors cursor-pointer text-[11px] disabled:opacity-50 shrink-0";

/**
 * Shown while the wallet is on another chain. Writes stay blocked by the write guard either way;
 * this only explains and, while it can help, offers a switch. What it offers next depends on what
 * the switch request actually returned, not on the wallet's name: after an "unsupported" result it
 * becomes a quiet browse-only notice for this connection.
 */
export function WrongChainBanner() {
  const { isConnected, chainId, connector, address } = useAccount();
  const { switchChainAsync } = useSwitchChain();
  const { disconnect, isPending: isDisconnecting } = useDisconnect();
  // Results belong to one connection (connector + account); a new connection starts fresh.
  const [result, setResult] = useState<{ key: string; outcome: SwitchOutcome } | null>(null);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);

  if (!isConnected || !chainId || chainId === TARGET_CHAIN_ID) {
    return null;
  }

  const key = `${connector?.uid ?? "none"}:${address ?? ""}`;
  const outcome = result?.key === key ? result.outcome : null;
  const mode = wrongChainBannerMode(outcome);
  const switching = switchingKey === key;
  const expectedName = TARGET_CHAIN_ID === 84532 ? baseSepolia.name : localAnvilChain.name;
  const walletName = walletLabel(connector as { name?: string; rkDetails?: { name?: string } } | undefined);

  const onSwitch = async () => {
    setSwitchingKey(key);
    const canSwitch = Boolean(connector?.switchChain) && isConfiguredChainId(TARGET_CHAIN_ID);
    const next = await requestChainSwitch(
      canSwitch ? () => switchChainAsync({ chainId: TARGET_CHAIN_ID as Parameters<typeof switchChainAsync>[0]["chainId"] }) : undefined,
      TARGET_CHAIN_ID
    );
    setResult({ key, outcome: next });
    setSwitchingKey(null);
  };

  const followUp = outcome && "message" in outcome ? outcome.message : null;
  const Icon = mode === "browse-only" ? Eye : Info;

  return (
    <div className="w-full bg-amber-950/70 border-b border-amber-600/70 text-amber-100 px-4 py-2 font-mono text-xs flex flex-wrap items-center justify-between gap-3 z-50">
      <div className="flex items-start gap-2 min-w-0">
        <Icon className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <span>
          <strong className="font-bold uppercase text-amber-200">
            {mode === "browse-only" ? "BROWSE_ONLY:" : "WRONG_NETWORK:"}
          </strong>{" "}
          {walletName} is on chain <code className="text-white font-bold">{chainId}</code>; StressProof runs on{" "}
          <code className="text-white font-bold">
            {TARGET_CHAIN_ID} ({expectedName})
          </code>
          . You can browse; transactions are disabled.
          {mode === "browse-only" && (
            <span role="status" className="block mt-1 text-amber-200/90">
              {unsupportedSwitchMessage(walletName, expectedName)}
            </span>
          )}
          {followUp && (
            <span role="status" className="block mt-1 text-amber-200/90">
              {followUp}
            </span>
          )}
        </span>
      </div>

      {mode === "browse-only" ? (
        <button type="button" disabled={isDisconnecting} onClick={() => disconnect()} className={BUTTON}>
          {isDisconnecting ? "DISCONNECTING..." : "DISCONNECT"}
        </button>
      ) : (
        <button type="button" disabled={switching} onClick={onSwitch} className={BUTTON}>
          {switching ? "SWITCHING..." : `SWITCH_TO_${TARGET_CHAIN_ID}`}
        </button>
      )}
    </div>
  );
}
