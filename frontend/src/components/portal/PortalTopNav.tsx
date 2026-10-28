"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Bell, Shield, Wallet, CheckCircle2, Terminal } from "lucide-react";
import { useState } from "react";

export function PortalTopNav() {
  const pathname = usePathname();
  const [copied, setCopied] = useState(false);

  // Dynamic breadcrumb matching
  const getPageTitle = () => {
    if (pathname.includes("/stress")) return "STRESS_SIMULATION";
    if (pathname.includes("/claims")) return "BONDED_CLAIMS_REGISTRY";
    if (pathname.includes("/vault")) return "CIRCUIT_BREAKER_DEFENSE";
    if (pathname.includes("/feed")) return "REACTIVE_TELEMETRY_FEED";
    if (pathname.includes("/graph")) return "EXPOSURE_GRAPH";
    return "RISK_COMMAND_CENTER";
  };

  const handleCopyDemoAccount = () => {
    navigator.clipboard.writeText("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <header className="h-16 px-4 sm:px-6 flex items-center justify-between bg-card border-b-2 border-border sticky top-0 z-40 font-mono">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center gap-2 text-xs font-mono pl-10 lg:pl-0 uppercase tracking-wider">
        <Link
          href="/dashboard"
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          SYS.RISK
        </Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-foreground font-bold tracking-widest text-[#ea580c] truncate max-w-[180px] sm:max-w-none">
          {getPageTitle()}
        </span>
      </div>

      {/* Right Action Icons & Badges */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Live Oracle Telemetry Beacon */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1 border border-border bg-background text-xs">
          <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
          <span className="text-[11px] font-bold text-foreground tracking-wider">ORACLE:</span>
          <span className="text-[11px] text-[#ea580c] font-bold">$3,000 WETH</span>
        </div>

        {/* Network Badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 border border-border bg-secondary text-xs text-foreground tracking-wider">
          <span className="h-1.5 w-1.5 bg-emerald-400" />
          <span>BASE_SEPOLIA</span>
        </div>

        {/* Protocol Test Account Copy */}
        <button
          onClick={handleCopyDemoAccount}
          title="Click to copy demo address"
          className="flex items-center gap-2 px-3 py-1.5 border border-border bg-background hover:border-foreground transition-all text-xs text-foreground shadow-[2px_2px_0px_0px_hsl(var(--border))]"
        >
          <Wallet className="h-3.5 w-3.5 text-[#ea580c]" />
          <span className="text-[11px] font-mono hidden sm:inline">
            {copied ? (
              <span className="text-emerald-400 font-bold flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> COPIED
              </span>
            ) : (
              "0xf39F...2266"
            )}
          </span>
        </button>
      </div>
    </header>
  );
}
