"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Shield,
  Activity,
  AlertTriangle,
  Lock,
  ExternalLink,
  Cpu,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";

interface SimulationPreset {
  id: string;
  name: string;
  shockBps: number;
  priceDrop: string;
  oraclePrice: string;
  badDebt: string;
  circuitBreaker: string;
  breakerColor: string;
  accounts: {
    address: string;
    collateral: string;
    debt: string;
    hf: string;
    status: "HEALTHY" | "LIQUIDATED" | "INSOLVENT";
  }[];
}

const PRESETS: SimulationPreset[] = [
  {
    id: "mild",
    name: "WETH -15% // MILD CORRECTION",
    shockBps: 1500,
    priceDrop: "-1500 BPS",
    oraclePrice: "$2,550.00",
    badDebt: "$0.00",
    circuitBreaker: "ARMED // NO BREACH",
    breakerColor: "text-emerald-400 border-emerald-500 bg-emerald-950/40",
    accounts: [
      { address: "0x3d4...a81", collateral: "85.0 WETH", debt: "$180,000", hf: "1.20 HF", status: "HEALTHY" },
      { address: "0x9c2...b14", collateral: "120.0 WETH", debt: "$240,000", hf: "1.28 HF", status: "HEALTHY" },
      { address: "0x1e8...f02", collateral: "45.0 WETH", debt: "$95,000", hf: "1.21 HF", status: "HEALTHY" },
      { address: "0x8f0...d55", collateral: "310.0 WETH", debt: "$600,000", hf: "1.32 HF", status: "HEALTHY" },
    ],
  },
  {
    id: "medium",
    name: "WETH -30% // AAVE V3 STRESS (BENCHMARK)",
    shockBps: 3000,
    priceDrop: "-3000 BPS",
    oraclePrice: "$2,100.00",
    badDebt: "$2,000.00",
    circuitBreaker: "TRIPPED // LTV 80% → 50%",
    breakerColor: "text-[#ea580c] border-[#ea580c] bg-orange-950/40",
    accounts: [
      { address: "0x3d4...a81", collateral: "50.0 WETH", debt: "$107,000", hf: "0.82 HF", status: "INSOLVENT" },
      { address: "0x9c2...b14", collateral: "120.0 WETH", debt: "$240,000", hf: "1.05 HF", status: "HEALTHY" },
      { address: "0x1e8...f02", collateral: "45.0 WETH", debt: "$95,000", hf: "0.99 HF", status: "LIQUIDATED" },
      { address: "0x8f0...d55", collateral: "310.0 WETH", debt: "$600,000", hf: "1.08 HF", status: "HEALTHY" },
    ],
  },
  {
    id: "severe",
    name: "WETH -50% // BLACK SWAN DEEP SHOCK",
    shockBps: 5000,
    priceDrop: "-5000 BPS",
    oraclePrice: "$1,500.00",
    badDebt: "$18,450.00",
    circuitBreaker: "EMERGENCY_HALT // BORROWS PAUSED",
    breakerColor: "text-rose-400 border-rose-500 bg-rose-950/40",
    accounts: [
      { address: "0x3d4...a81", collateral: "0.0 WETH", debt: "$107,000", hf: "0.58 HF", status: "INSOLVENT" },
      { address: "0x9c2...b14", collateral: "65.0 WETH", debt: "$240,000", hf: "0.41 HF", status: "INSOLVENT" },
      { address: "0x1e8...f02", collateral: "0.0 WETH", debt: "$95,000", hf: "0.68 HF", status: "INSOLVENT" },
      { address: "0x8f0...d55", collateral: "180.0 WETH", debt: "$600,000", hf: "0.77 HF", status: "LIQUIDATED" },
    ],
  },
];

export function CommandCenterSection() {
  const [selectedPreset, setSelectedPreset] = useState<SimulationPreset>(PRESETS[1]);
  const [isSimulating, setIsSimulating] = useState(false);

  const handleSelectPreset = (preset: SimulationPreset) => {
    setIsSimulating(true);
    setSelectedPreset(preset);
    setTimeout(() => {
      setIsSimulating(false);
    }, 350);
  };

  return (
    <section id="command-center" className="w-full px-6 py-20 lg:px-16 border-t-2 border-foreground bg-card/60 font-mono">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Section Header */}
        <div className="flex items-center gap-4">
          <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground">
            {"// SECTION: RISK_COMMAND_CENTER"}
          </span>
          <div className="flex-1 border-t-2 border-border" />
          <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground">
            004
          </span>
        </div>

        {/* Section Title & Description */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div>
            <h2 className="text-3xl sm:text-4xl font-black uppercase tracking-tight text-foreground">
              DEFI RISK COMMAND CENTER
            </h2>
            <p className="text-xs text-muted-foreground uppercase mt-2 max-w-2xl leading-relaxed">
              Interactive protocol runtime preview. Select simulated oracle price shocks to test borrower solvency waterfalls, deterministic residual bad debt calculations, and automated DemoVault circuit-breaker defenses in real-time.
            </p>
          </div>

          <Link
            href="/dashboard"
            className="group inline-flex items-center gap-0 bg-foreground text-background text-xs font-bold uppercase tracking-wider border-2 border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[3px_3px_0px_0px_hsl(var(--border))] self-start lg:self-auto"
          >
            <span className="flex items-center justify-center w-8 h-8 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors">
              <ArrowRight size={14} />
            </span>
            <span className="px-4 py-2">LAUNCH FULL PORTAL</span>
          </Link>
        </div>

        {/* Interactive Command Center Console Grid */}
        <div className="border-2 border-foreground bg-background shadow-[6px_6px_0px_0px_hsl(var(--border))]">
          {/* Top Control Bar */}
          <div className="flex flex-col md:flex-row md:items-center justify-between border-b-2 border-foreground p-4 bg-secondary gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 bg-[#ea580c] animate-pulse" />
              <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                LIVE_SIMULATION_STATION // RUNTIME_V1.0
              </span>
            </div>

            {/* Shock Preset Pills */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] text-muted-foreground uppercase hidden sm:inline">
                SCENARIOS:
              </span>
              {PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectPreset(preset)}
                  className={`text-[10px] font-bold uppercase px-2.5 py-1 border transition-all ${
                    selectedPreset.id === preset.id
                      ? "bg-foreground text-background border-foreground shadow-[2px_2px_0px_0px_#ea580c]"
                      : "bg-background text-muted-foreground border-border hover:border-foreground hover:text-foreground"
                  }`}
                >
                  {preset.name.split("//")[0].trim()}
                </button>
              ))}
            </div>
          </div>

          {/* Metrics Overview Bar */}
          <div className="grid grid-cols-2 md:grid-cols-4 border-b-2 border-border bg-card">
            <div className="p-4 border-r border-border">
              <span className="text-[10px] text-muted-foreground uppercase block mb-1">
                SIMULATED_ORACLE_PRICE
              </span>
              <span className="text-lg sm:text-xl font-bold text-foreground">
                {selectedPreset.oraclePrice}
              </span>
              <span className="text-[10px] text-[#ea580c] font-bold block mt-0.5">
                {selectedPreset.priceDrop}
              </span>
            </div>

            <div className="p-4 border-r md:border-r border-border">
              <span className="text-[10px] text-muted-foreground uppercase block mb-1">
                MONITORED_POOL_TVL
              </span>
              <span className="text-lg sm:text-xl font-bold text-foreground">
                $31.39M
              </span>
              <span className="text-[10px] text-muted-foreground block mt-0.5">
                4 BORROWER ACCOUNTS
              </span>
            </div>

            <div className="p-4 border-r border-border">
              <span className="text-[10px] text-muted-foreground uppercase block mb-1">
                UNHEDGED_BAD_DEBT
              </span>
              <span className="text-lg sm:text-xl font-bold text-[#ea580c]">
                {selectedPreset.badDebt}
              </span>
              <span className="text-[10px] text-muted-foreground block mt-0.5">
                BONDED CLAIM ATTESTATION
              </span>
            </div>

            <div className="p-4">
              <span className="text-[10px] text-muted-foreground uppercase block mb-1">
                CIRCUIT_BREAKER_STATE
              </span>
              <span className={`text-[11px] font-bold uppercase px-2 py-0.5 border inline-block mt-1 ${selectedPreset.breakerColor}`}>
                {selectedPreset.circuitBreaker}
              </span>
            </div>
          </div>

          {/* Borrower Waterfall Live Status Table */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cpu size={14} className="text-[#ea580c]" />
                <span className="text-xs font-bold uppercase text-foreground tracking-wider">
                  DETERMINISTIC LIQUIDATION CASCADE WATERFALL
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground uppercase font-mono">
                BLOCK_FIXTURE: #19,500,000
              </span>
            </div>

            <div className="overflow-x-auto border border-border">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-muted/20 border-b border-border text-[10px] uppercase text-muted-foreground">
                  <tr>
                    <th className="p-2.5">ACCOUNT_HASH</th>
                    <th className="p-2.5">COLLATERAL</th>
                    <th className="p-2.5">BORROW_DEBT</th>
                    <th className="p-2.5">HEALTH_FACTOR</th>
                    <th className="p-2.5">CASCADE_STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border bg-background">
                  {selectedPreset.accounts.map((acc) => {
                    const isInsolvent = acc.status === "INSOLVENT";
                    const isLiquidated = acc.status === "LIQUIDATED";

                    return (
                      <tr key={acc.address} className="hover:bg-card/50 transition-colors">
                        <td className="p-2.5 font-bold text-foreground">{acc.address}</td>
                        <td className="p-2.5 text-muted-foreground">{acc.collateral}</td>
                        <td className="p-2.5 text-muted-foreground">{acc.debt}</td>
                        <td className="p-2.5">
                          <span
                            className={`font-bold ${
                              isInsolvent
                                ? "text-rose-400"
                                : isLiquidated
                                ? "text-[#ea580c]"
                                : "text-emerald-400"
                            }`}
                          >
                            {acc.hf}
                          </span>
                        </td>
                        <td className="p-2.5">
                          <span
                            className={`text-[9px] px-1.5 py-0.5 border font-bold uppercase ${
                              isInsolvent
                                ? "border-rose-500 bg-rose-950/60 text-rose-400"
                                : isLiquidated
                                ? "border-orange-500 bg-orange-950/60 text-[#ea580c]"
                                : "border-emerald-500 bg-emerald-950/60 text-emerald-400"
                            }`}
                          >
                            {acc.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Bottom Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-border">
              <div className="text-[10px] text-muted-foreground uppercase flex items-center gap-2">
                <span className="h-1.5 w-1.5 bg-emerald-400" />
                <span>WASM REPLAYER DETERMINISM: VERIFIED 0% VARIANCE</span>
              </div>

              <div className="flex items-center gap-3">
                <Link
                  href="/stress"
                  className="px-3.5 py-1.5 border border-border bg-secondary text-xs font-bold uppercase text-foreground hover:border-foreground hover:bg-foreground hover:text-background transition-all"
                >
                  CUSTOMIZE REPLAY PARAMETERS &rarr;
                </Link>
                <Link
                  href="/dashboard"
                  className="px-3.5 py-1.5 bg-[#ea580c] text-white text-xs font-bold uppercase hover:bg-foreground hover:text-background transition-all shadow-[2px_2px_0px_0px_hsl(var(--border))]"
                >
                  ENTER COMMAND CENTER &rarr;
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

