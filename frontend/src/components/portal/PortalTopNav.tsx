"use client";

import { Wallet, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { useAccount } from "wagmi";
import { ACTIVE_CHAIN_ID } from "@/lib/contracts";

export function PortalTopNav() {
  const [copied, setCopied] = useState(false);
  const { isConnected, address, chainId } = useAccount();

  const effectiveChainId = chainId || ACTIVE_CHAIN_ID;
  const chainName = effectiveChainId === 84532 ? "BASE_SEPOLIA // 84532" : "ANVIL_LOCAL // 31337";

  const handleCopyDemoAccount = () => {
    const targetAddress = isConnected && address ? address : "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
    navigator.clipboard.writeText(targetAddress);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const displayAddr = isConnected && address
    ? `${address.slice(0, 6)}...${address.slice(-4)}`
    : "0xf39F...2266";

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

        {/* Live Oracle Telemetry Beacon */}
        <div className="hidden lg:flex items-center gap-2 px-3 py-1 border border-border bg-background text-xs">
          <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
          <span className="text-[11px] font-bold text-foreground tracking-wider">ORACLE:</span>
          <span className="text-[11px] text-[#ea580c] font-bold">$3,000 WETH</span>
        </div>

        {/* Network Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-xs text-foreground tracking-wider">
          <span className="h-1.5 w-1.5 bg-emerald-400" />
          <span>{chainName}</span>
        </div>

        {/* Protocol Test Account Copy */}
        <button
          onClick={handleCopyDemoAccount}
          title="Click to copy wallet address"
          className="flex items-center gap-2 px-3 py-1.5 border border-border bg-background hover:border-foreground transition-all text-xs text-foreground shadow-[2px_2px_0px_0px_hsl(var(--border))]"
        >
          <Wallet className="h-3.5 w-3.5 text-[#ea580c]" />
          <span className="text-[11px] font-mono hidden sm:inline">
            {copied ? (
              <span className="text-emerald-400 font-bold flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> COPIED
              </span>
            ) : (
              displayAddr
            )}
          </span>
        </button>
      </div>
    </header>
  );
}
