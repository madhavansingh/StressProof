"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { motion, useInView } from "framer-motion";
import {
  ArrowRight,
  Cpu,
  Shield,
  Layers,
  Terminal as TerminalIcon,
  Activity,
  CheckCircle2,
  Lock,
  Radio,
  FileCheck2,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";
import { RegisterAuthModal, type OperatorSession } from "./RegisterAuthModal";
import { CommandCenterSection } from "./CommandCenterSection";

const ease = [0.22, 1, 0.36, 1] as const;

/* ── Scramble Text Effect ── */
function ScrambleText({ text, className }: { text: string; className?: string }) {
  const [display, setDisplay] = useState(text);
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-50px" });
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:";

  useEffect(() => {
    if (!inView) return;
    let iteration = 0;
    const interval = setInterval(() => {
      setDisplay(
        text
          .split("")
          .map((char, i) => {
            if (char === " ") return " ";
            if (i < iteration) return text[i];
            return chars[Math.floor(Math.random() * chars.length)];
          })
          .join("")
      );
      iteration += 0.5;
      if (iteration >= text.length) {
        setDisplay(text);
        clearInterval(interval);
      }
    }, 25);
    return () => clearInterval(interval);
  }, [inView, text]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}

/* ── Workflow Diagram Component ── */
function WorkflowDiagram() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <div className="h-[200px] w-full" />;

  const stages = [
    { name: "AAVE_FORK", desc: "Block #19500000" },
    { name: "PRICE_SHOCK", desc: "-3000 BPS" },
    { name: "WASM_REPLAY", desc: "Deterministic" },
    { name: "BONDED_CLAIM", desc: "0.01 ETH Stake" },
    { name: "CHALLENGE_WIN", desc: "120s Optimistic" },
    { name: "VAULT_DEFENSE", desc: "Max LTV 50%" },
  ];

  return (
    <div className="w-full max-w-4xl mx-auto my-6 p-4 border-2 border-foreground bg-card">
      <div className="flex items-center justify-between border-b border-border pb-2 mb-4">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
          {"// ARCHITECTURE_PIPELINE: DETERMINISTIC_SETTLEMENT"}
        </span>
        <span className="text-[10px] text-[#ea580c] font-mono font-bold">[100%_DETERMINISTIC]</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {stages.map((stage, idx) => (
          <div
            key={stage.name}
            className="p-3 border border-border bg-background flex flex-col justify-between hover:border-foreground transition-all"
          >
            <div className="flex items-center justify-between text-[9px] text-muted-foreground font-mono">
              <span>0{idx + 1}</span>
              {idx < stages.length - 1 && <span className="text-[#ea580c]">&rarr;</span>}
            </div>
            <div className="mt-2">
              <span className="text-xs font-bold text-foreground block font-mono">
                {stage.name}
              </span>
              <span className="text-[10px] text-muted-foreground block font-mono">
                {stage.desc}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Live Terminal Simulation Component ── */
const TERMINAL_LOGS = [
  "> [INITIALIZE] Loading Ethereum mainnet fork block #19500000...",
  "> [DATASET] 5 monitored borrower accounts loaded into replayer memory",
  "> [ORACLE] Applying simulated price shock: WETH -3000 bps ($3,000 -> $2,100)",
  "> [EXECUTE] Deterministic replayer pass 1: Calculating liquidation thresholds",
  "> [LIQUIDATION] Borrower 0x3d4... health factor breached: 0.82 HF",
  "> [WATERFALL] Liquidating collateral: 50.0 WETH seized",
  "> [CALCULATION] Residual unhedged bad debt: $2,000.00 (200000000001 USD8)",
  "> [HASH] Generating content-addressed case file: SHA-256 0x7f427d...25f0",
  "> [REGISTRY] Bonded claim #1 posted on Base Sepolia (Stake: 0.01 ETH)",
  "> [OPTIMISTIC] 120s dispute window opened. Zero counter-bonds submitted",
  "> [SETTLEMENT] Claim #1 finalized. Attester credited 0.01 ETH bond",
  "> [VAULT] DemoVault tripped: Max LTV restricted from 80% -> 50%",
  "> [STATUS] Protocol solvency protected. Cycle complete.",
];

function TerminalCard() {
  const [lines, setLines] = useState<string[]>([]);
  const [currentLine, setCurrentLine] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentLine((prev) => {
        const next = prev + 1;
        if (next >= TERMINAL_LOGS.length) {
          setLines([]);
          return 0;
        }
        setLines((l) => [...l.slice(-7), TERMINAL_LOGS[next]]);
        return next;
      });
    }, 700);

    setLines([TERMINAL_LOGS[0]]);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full bg-card">
      <div className="flex items-center gap-2 border-b-2 border-foreground px-4 py-2.5 bg-secondary">
        <span className="h-2.5 w-2.5 bg-[#ea580c]" />
        <span className="h-2.5 w-2.5 bg-foreground" />
        <span className="h-2.5 w-2.5 border border-foreground" />
        <span className="ml-auto text-[10px] font-mono tracking-widest text-muted-foreground uppercase">
          REPLAYER_KERNEL.SYS
        </span>
      </div>
      <div className="flex-1 bg-background p-4 overflow-hidden flex flex-col justify-end min-h-[240px]">
        <div className="flex flex-col gap-1.5 font-mono">
          {lines.map((line, i) => (
            <span
              key={`${currentLine}-${i}`}
              className="text-xs text-foreground/90 block leading-relaxed"
              style={{ opacity: i === lines.length - 1 ? 1 : 0.65 }}
            >
              {line}
            </span>
          ))}
          <span className="text-xs text-[#ea580c] font-mono animate-blink">{"_"}</span>
        </div>
      </div>
    </div>
  );
}

/* ── Stat Block ── */
const PROTOCOL_STATS = [
  { label: "MONITORED_TVL", value: "$31.4M" },
  { label: "FORK_BLOCK", value: "#19500000" },
  { label: "BOND_REQUIREMENT", value: "0.01 ETH" },
  { label: "REPLAY_LATENCY", value: "4.2ms" },
];

export function LandingPage() {
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [session, setSession] = useState<OperatorSession | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("stressproof_operator_session");
      if (stored) {
        setSession(JSON.parse(stored));
      }
    } catch (e) {
      // Ignore local storage error
    }
  }, []);

  return (
    <div className="w-full min-h-screen bg-background text-foreground dot-grid-bg font-mono flex flex-col selection:bg-[#ea580c] selection:text-white">
      {/* ── Brutalist Top Navbar ── */}
      <header className="w-full px-4 pt-4 lg:px-8 lg:pt-6 sticky top-0 z-50">
        <nav className="w-full border-2 border-foreground bg-background/95 backdrop-blur-md px-5 py-3 lg:px-8 flex items-center justify-between shadow-[4px_4px_0px_0px_hsl(var(--border))]">
          {/* Brand */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="h-8 w-8 bg-[#ea580c] flex items-center justify-center text-background font-bold text-xs tracking-wider">
              SP
            </div>
            <div className="flex flex-col">
              <span className="text-xs font-bold tracking-[0.2em] uppercase text-foreground">
                STRESSPROOF
              </span>
            </div>
          </Link>

          {/* Center Links */}
          <div className="hidden md:flex items-center gap-6 lg:gap-8 text-xs uppercase tracking-widest text-muted-foreground font-bold">
            <Link href="#architecture" className="hover:text-foreground transition-colors">
              ARCHITECTURE
            </Link>
            <Link href="#telemetry" className="hover:text-foreground transition-colors">
              TELEMETRY
            </Link>
            <Link href="#command-center" className="hover:text-foreground transition-colors flex items-center gap-1">
              COMMAND_CENTER
            </Link>
            <Link href="#roles" className="hover:text-foreground transition-colors">
              ROLES
            </Link>
          </div>

          {/* Right CTAs */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsAuthModalOpen(true)}
              className="hidden sm:inline-flex items-center gap-1.5 border border-border px-3 py-1.5 text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground hover:border-foreground transition-all"
            >
              {session?.isRegistered ? (
                <>
                  <span className="h-1.5 w-1.5 bg-emerald-400 animate-pulse" />
                  <span className="max-w-[120px] truncate">{session.handle}</span>
                </>
              ) : (
                <span>REGISTER</span>
              )}
            </button>
            <Link
              href="/dashboard"
              className="group flex items-center gap-0 bg-foreground text-background text-xs font-bold uppercase tracking-wider border-2 border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[2px_2px_0px_0px_hsl(var(--border))]"
            >
              <span className="flex items-center justify-center w-7 h-7 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors">
                <ArrowRight size={14} />
              </span>
              <span className="px-3 py-1.5">ENTER APP</span>
            </Link>
          </div>
        </nav>
      </header>

      {/* ── Hero Section ── */}
      <section className="relative w-full px-6 pt-12 pb-16 lg:px-16 lg:pt-16 lg:pb-20 text-center">
        <div className="max-w-5xl mx-auto flex flex-col items-center">
          {/* Top Tag */}
          <div className="inline-flex items-center gap-2 px-3 py-1 border border-border bg-card text-[11px] uppercase tracking-widest text-muted-foreground mb-6">
            <span className="h-2 w-2 bg-[#ea580c] animate-blink" />
            <span>AN OPEN, CHALLENGEABLE LAYER FOR AI RISK CLAIMS</span>
          </div>

          {/* Top Big Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease }}
            className="text-4xl sm:text-6xl lg:text-7xl xl:text-8xl font-black tracking-tight text-foreground select-none"
          >
            STRESS. CHALLENGE.
          </motion.h1>

          {/* Central Workflow Diagram */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.15, ease }}
            className="w-full my-4"
          >
            <WorkflowDiagram />
          </motion.div>

          {/* Bottom Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25, ease }}
            className="text-4xl sm:text-6xl lg:text-7xl xl:text-8xl font-black tracking-tight text-foreground mb-6 select-none"
          >
            DEFEND.
          </motion.h1>

          {/* Subtitle */}
          <p className="text-xs sm:text-sm text-muted-foreground max-w-2xl leading-relaxed mb-8 uppercase">
            StressProof guarantees AI-generated lending-market risk claims through bonded stakes, deterministic Wasm replayers, and on-chain circuit breakers. No hallucinations. Slashed stakes. Full protocol defense.
          </p>

          {/* Action Button Row */}
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/dashboard"
              className="group flex items-center gap-0 bg-foreground text-background text-sm font-bold uppercase tracking-wider border-2 border-foreground hover:bg-[#ea580c] hover:border-[#ea580c] hover:text-white transition-all shadow-[4px_4px_0px_0px_#ea580c]"
            >
              <span className="flex items-center justify-center w-10 h-10 bg-[#ea580c] text-background group-hover:bg-foreground group-hover:text-background transition-colors">
                <ArrowRight size={18} />
              </span>
              <span className="px-6 py-2.5">LAUNCH RISK COMMAND CENTER</span>
            </Link>

            <Link
              href="/stress"
              className="px-6 py-2.5 border-2 border-foreground bg-card text-foreground text-sm font-bold uppercase tracking-wider hover:bg-secondary transition-all shadow-[4px_4px_0px_0px_hsl(var(--border))]"
            >
              RUN PRICE SHOCK SIMULATION
            </Link>
          </div>
        </div>
      </section>

      {/* ── Glitch Marquee Ticker ── */}
      <div className="w-full border-y-2 border-foreground bg-foreground text-background py-2.5 overflow-hidden select-none">
        <div className="flex whitespace-nowrap animate-marquee">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="flex items-center gap-8 text-xs font-bold uppercase tracking-widest mr-8">
              <span>[FORK_FIXTURE: AAVE_V3_ETH]</span>
              <span>&bull;</span>
              <span>[FORK_BLOCK: #19,500,000]</span>
              <span>&bull;</span>
              <span>[ORACLE_INDEX: $3,000.00 WETH]</span>
              <span>&bull;</span>
              <span>[CLAIMED_BAD_DEBT: $2,000.00 USD8]</span>
              <span>&bull;</span>
              <span>[CIRCUIT_BREAKER: LTV 80% &rarr; 50%]</span>
              <span>&bull;</span>
              <span>[BOND_REQUIREMENT: 0.01 ETH]</span>
              <span>&bull;</span>
              <span>[CHALLENGE_WINDOW: 120S]</span>
              <span>&bull;</span>
              <span>[STATUS: 100% DETERMINISTIC PASS]</span>
              <span>&bull;</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Bento Feature Grid (2x2) ── */}
      <section id="telemetry" className="w-full px-6 py-20 lg:px-16">
        <div className="max-w-6xl mx-auto">
          {/* Section Marker */}
          <div className="flex items-center gap-4 mb-8">
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              {"// SECTION: CONSENSUS_TELEMETRY"}
            </span>
            <div className="flex-1 border-t-2 border-border" />
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              002
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 border-2 border-foreground bg-card">
            {/* Bento 1: Live Terminal Card */}
            <div className="border-b-2 md:border-b-0 md:border-r-2 border-foreground min-h-[300px]">
              <TerminalCard />
            </div>

            {/* Bento 2: Liquidation Waterfall / Risk Curve */}
            <div className="border-b-2 md:border-b-0 border-foreground p-6 flex flex-col justify-between bg-card">
              <div>
                <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
                  <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                    {"// WATERFALL_CASCADE_ANALYSIS"}
                  </span>
                  <span className="text-[10px] text-emerald-400 font-bold uppercase">
                    [EVALUATION_OK]
                  </span>
                </div>
                <h3 className="text-base font-bold text-foreground uppercase tracking-wider mb-2">
                  DETERMINISTIC COLLATERAL LIQUIDATION
                </h3>
                <p className="text-xs text-muted-foreground uppercase leading-relaxed mb-4">
                  Replayer computes exact insolvent borrower positions without state approximation. If collateral auctions fail to cover liabilities, unhedged residual bad debt is bonded on-chain.
                </p>
              </div>

              <div className="border border-border p-4 bg-background space-y-2 font-mono text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">COLLATERAL_DROP:</span>
                  <span className="text-[#ea580c] font-bold">-30.00% (-3000 BPS)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">INSOLVENT_BORROWERS:</span>
                  <span className="text-foreground font-bold">1 / 5 ACCOUNTS</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">UNCOVERED_DEFICIT:</span>
                  <span className="text-foreground font-bold">$2,000.00 USD8</span>
                </div>
              </div>
            </div>

            {/* Bento 3: Metrics Card */}
            <div className="border-b-2 md:border-b-0 md:border-r-2 border-foreground p-6 flex flex-col justify-between bg-card">
              <div>
                <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
                  <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                    {"// ON_CHAIN_VERIFICATION"}
                  </span>
                  <span className="text-[10px] text-[#ea580c] font-bold uppercase">
                    [SLASHABLE_BOND]
                  </span>
                </div>
                <h3 className="text-base font-bold text-foreground uppercase tracking-wider mb-2">
                  OPTIMISTIC DISPUTE SETTLEMENT
                </h3>
                <p className="text-xs text-muted-foreground uppercase leading-relaxed mb-4">
                  Claims require 0.01 ETH bond. Anyone can challenge within 120s with a counter-bond. If a claim is falsified, 100% of the bond is slashed and awarded to the challenger.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 font-mono">
                <div className="border border-border p-3 bg-background">
                  <span className="text-[9px] text-muted-foreground uppercase block">
                    ATTESTATION_BOND
                  </span>
                  <span className="text-lg font-bold text-foreground">0.01 ETH</span>
                </div>
                <div className="border border-border p-3 bg-background">
                  <span className="text-[9px] text-muted-foreground uppercase block">
                    DISPUTE_WINDOW
                  </span>
                  <span className="text-lg font-bold text-[#ea580c]">120 SECONDS</span>
                </div>
              </div>
            </div>

            {/* Bento 4: Status Card */}
            <div className="p-6 flex flex-col justify-between bg-card">
              <div>
                <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
                  <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                    {"// DEFENSE_CIRCUIT_BREAKER"}
                  </span>
                  <span className="text-[10px] text-emerald-400 font-bold uppercase">
                    [AUTOMATION_ACTIVE]
                  </span>
                </div>
                <h3 className="text-base font-bold text-foreground uppercase tracking-wider mb-2">
                  AUTONOMOUS LENDING PROTOCOL DEFENSE
                </h3>
                <p className="text-xs text-muted-foreground uppercase leading-relaxed mb-4">
                  Finalized claims trigger DemoVault risk handlers: dynamically reducing Max LTV from 80% to 50% or pausing borrows when bad debt exceeds thresholds.
                </p>
              </div>

              <div className="border border-border p-4 bg-background space-y-2 font-mono text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">CIRCUIT_BREAKER:</span>
                  <span className="text-emerald-400 font-bold">ARMED &amp; MONITORING</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">LTV_DEFENSE_ACTION:</span>
                  <span className="text-[#ea580c] font-bold">80% &rarr; 50% (TRIPPED)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground uppercase">EMERGENCY_PAUSE:</span>
                  <span className="text-foreground font-bold">THRESHOLD: $4,000</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Architecture & Live Stats Section ── */}
      <section id="architecture" className="w-full px-6 py-20 lg:px-16 border-t-2 border-foreground bg-secondary/30">
        <div className="max-w-6xl mx-auto space-y-12">
          {/* Section Marker */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              {"// SECTION: PROTOCOL_ARCHITECTURE"}
            </span>
            <div className="flex-1 border-t-2 border-border" />
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              003
            </span>
          </div>

          {/* Stat Blocks */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {PROTOCOL_STATS.map((stat, idx) => (
              <div
                key={stat.label}
                className="border-2 border-foreground bg-card p-4 flex flex-col justify-between shadow-[3px_3px_0px_0px_hsl(var(--border))]"
              >
                <span className="text-[10px] tracking-widest uppercase text-muted-foreground mb-2">
                  {stat.label}
                </span>
                <span className="text-xl sm:text-2xl font-bold text-foreground">
                  <ScrambleText text={stat.value} />
                </span>
              </div>
            ))}
          </div>

          {/* 3 Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="border-2 border-border bg-card p-6 space-y-3">
              <div className="h-8 w-8 bg-[#ea580c] text-background flex items-center justify-center font-bold text-xs">
                01
              </div>
              <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">
                DETERMINISTIC WASM REPLAY
              </h3>
              <p className="text-xs text-muted-foreground uppercase leading-relaxed">
                Liquidation cascades are evaluated using pure state transition functions over block fixtures, ensuring reproducible output down to the single cent.
              </p>
            </div>

            <div className="border-2 border-border bg-card p-6 space-y-3">
              <div className="h-8 w-8 bg-foreground text-background flex items-center justify-center font-bold text-xs">
                02
              </div>
              <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">
                CONTENT-ADDRESSED EVIDENCE
              </h3>
              <p className="text-xs text-muted-foreground uppercase leading-relaxed">
                Every claim commits to a SHA-256 evidence hash covering the entire execution trace, parameter set, and borrower portfolio snapshot.
              </p>
            </div>

            <div className="border-2 border-border bg-card p-6 space-y-3">
              <div className="h-8 w-8 bg-border text-foreground flex items-center justify-center font-bold text-xs">
                03
              </div>
              <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">
                OPTIMISTIC ECONOMIC CONSENSUS
              </h3>
              <p className="text-xs text-muted-foreground uppercase leading-relaxed">
                Attesters stake real capital (0.01 ETH). Malicious claims are caught by automated watcher bots and permanently slashed.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Protocol Roles Section ── */}
      <section id="roles" className="w-full px-6 py-20 lg:px-16 border-t-2 border-foreground">
        <div className="max-w-6xl mx-auto space-y-8">
          <div className="flex items-center gap-4">
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              {"// SECTION: NETWORK_PARTICIPANTS"}
            </span>
            <div className="flex-1 border-t-2 border-border" />
            <span className="text-[10px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
              004
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Role 1 */}
            <div className="border-2 border-border bg-card p-6 flex flex-col justify-between space-y-4 hover:border-foreground transition-all">
              <div>
                <span className="text-[10px] text-[#ea580c] font-bold uppercase tracking-widest block mb-1">
                  ROLE // ATTESTER
                </span>
                <h3 className="text-base font-bold text-foreground uppercase">
                  AI RISK ATTESTER
                </h3>
                <p className="text-xs text-muted-foreground uppercase mt-2 leading-relaxed">
                  Generates stress simulations, builds content-addressed case files, and stakes 0.01 ETH to register risk claims on-chain.
                </p>
              </div>
              <Link
                href="/stress"
                className="w-full py-2 border border-foreground bg-background text-xs font-bold uppercase text-center hover:bg-foreground hover:text-background transition-colors block"
              >
                POST ATTESTATION &rarr;
              </Link>
            </div>

            {/* Role 2 */}
            <div className="border-2 border-foreground bg-card p-6 flex flex-col justify-between space-y-4 shadow-[4px_4px_0px_0px_#ea580c]">
              <div>
                <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-widest block mb-1">
                  ROLE // WATCHER
                </span>
                <h3 className="text-base font-bold text-foreground uppercase">
                  INDEPENDENT WATCHER
                </h3>
                <p className="text-xs text-muted-foreground uppercase mt-2 leading-relaxed">
                  Monitors incoming claims, verifies evidence hashes via independent replayers, and disputes invalid claims to claim slashed bonds.
                </p>
              </div>
              <Link
                href="/claims"
                className="w-full py-2 bg-[#ea580c] text-white text-xs font-bold uppercase text-center hover:bg-foreground hover:text-background transition-colors block"
              >
                CHALLENGE CLAIMS &rarr;
              </Link>
            </div>

            {/* Role 3 */}
            <div className="border-2 border-border bg-card p-6 flex flex-col justify-between space-y-4 hover:border-foreground transition-all">
              <div>
                <span className="text-[10px] text-purple-400 font-bold uppercase tracking-widest block mb-1">
                  ROLE // DEFENSE
                </span>
                <h3 className="text-base font-bold text-foreground uppercase">
                  DEFI LENDING VAULT
                </h3>
                <p className="text-xs text-muted-foreground uppercase mt-2 leading-relaxed">
                  Connects DemoVault or custom lending markets to auto-trip circuit breakers and dynamically safeguard liquidity pools.
                </p>
              </div>
              <Link
                href="/vault"
                className="w-full py-2 border border-foreground bg-background text-xs font-bold uppercase text-center hover:bg-foreground hover:text-background transition-colors block"
              >
                INSPECT VAULT &rarr;
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Risk Command Center Section ── */}
      <CommandCenterSection />

      {/* ── Brutalist Footer ── */}
      <footer className="w-full border-t-2 border-foreground bg-background px-6 py-12 lg:px-16 text-xs text-muted-foreground font-mono">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-6 border-b border-border pb-8 mb-8">
          <div className="flex items-center gap-3">
            <div className="h-7 w-7 bg-[#ea580c] flex items-center justify-center text-background font-bold text-xs">
              SP
            </div>
            <div>
              <span className="text-xs font-bold uppercase text-foreground">
                STRESSPROOF PROTOCOL
              </span>
              <p className="text-[10px] text-muted-foreground uppercase">
                DETERMINISTIC RISK SETTLEMENT FOR LENDING MARKETS
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-6 text-xs uppercase font-bold text-muted-foreground items-center">
            <Link href="/dashboard" className="hover:text-foreground">
              DASHBOARD
            </Link>
            <Link href="#command-center" className="hover:text-foreground">
              COMMAND_CENTER
            </Link>
            <Link href="/stress" className="hover:text-foreground">
              SIMULATION
            </Link>
            <button
              type="button"
              onClick={() => setIsAuthModalOpen(true)}
              className="hover:text-foreground uppercase font-bold text-left"
            >
              {session?.isRegistered ? "OPERATOR_NODE" : "REGISTER"}
            </button>
            <Link href="/vault" className="hover:text-foreground">
              CIRCUIT_BREAKER
            </Link>
            <Link href="/feed" className="hover:text-foreground">
              TELEMETRY
            </Link>
          </div>
        </div>

        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-[10px] uppercase">
          <span>&copy; 2026 SUPERCONSCIOUS / STRESSPROOF. ALL RIGHTS RESERVED.</span>
        </div>
      </footer>

      {/* ── Demo Frontend Auth / Register Modal ── */}
      <RegisterAuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        session={session}
        onUpdateSession={setSession}
      />
    </div>
  );
}
