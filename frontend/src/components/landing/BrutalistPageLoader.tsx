"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, Shield, Cpu, Activity, Zap } from "lucide-react";

interface BrutalistPageLoaderProps {
  onComplete?: () => void;
}

const BOOT_LOGS = [
  "INITIALIZING STRESSPROOF KERNEL V1.0...",
  "VERIFYING KECCAK-256 CANONICAL HASH ENGINE...",
  "CONNECTING BASE SEPOLIA TESTNET [CHAIN ID: 84532]...",
  "LOADING FORK SNAPSHOT BLOCK #19,500,000...",
  "CALIBRATING OPTIMISTIC DISPUTE WINDOW [120 SECONDS]...",
  "ARMING VAULT DEFENSE CIRCUIT BREAKER [LTV 80% -> 50%]...",
  "SYSTEM CONSISTENCY VERIFIED: 100% DETERMINISTIC PASS.",
  "CLEARANCE GRANTED // ENTERING RISK COMMAND CENTER.",
];

export function BrutalistPageLoader({ onComplete }: BrutalistPageLoaderProps) {
  const [progress, setProgress] = useState(0);
  const [logIndex, setLogIndex] = useState(0);
  const [isFinished, setIsFinished] = useState(false);

  useEffect(() => {
    // Fast simulated boot sequence
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(() => {
            setIsFinished(true);
            onComplete?.();
          }, 300);
          return 100;
        }
        // Organic step increments
        const next = Math.min(100, prev + Math.floor(Math.random() * 8) + 4);
        const nextLog = Math.floor((next / 100) * BOOT_LOGS.length);
        setLogIndex(Math.min(BOOT_LOGS.length - 1, nextLog));
        return next;
      });
    }, 45);

    // Keyboard listener to allow skipping with Space or Enter
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "Enter" || e.key === "Escape") {
        clearInterval(interval);
        setProgress(100);
        setIsFinished(true);
        onComplete?.();
      }
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      clearInterval(interval);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onComplete]);

  function handleSkip() {
    setProgress(100);
    setIsFinished(true);
    onComplete?.();
  }

  return (
    <AnimatePresence>
      {!isFinished && (
        <motion.div
          key="system-preloader"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, y: -40, filter: "blur(8px)" }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          onClick={handleSkip}
          className="fixed inset-0 z-[100] bg-background text-foreground font-mono flex items-center justify-center p-6 sm:p-12 select-none border-b-4 border-foreground cursor-pointer"
        >
          {/* Central Diagnostic Console */}
          <div className="max-w-2xl mx-auto w-full space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-[#ea580c] animate-pulse" />
                <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                  PROTOCOL_BOOT_SEQUENCE
                </span>
              </div>
              <span className="text-2xl sm:text-3xl font-black text-[#ea580c]">
                {progress}%
              </span>
            </div>

            {/* Segmented Cyber Progress Bar */}
            <div className="w-full bg-card border-2 border-foreground p-1 shadow-[4px_4px_0px_0px_hsl(var(--border))]">
              <div
                className="h-4 bg-[#ea580c] transition-all duration-75"
                style={{ width: `${progress}%` }}
              />
            </div>

            {/* Active Telemetry Log Output */}
            <div className="border border-border bg-card p-4 space-y-2 min-h-[140px] flex flex-col justify-end">
              <div className="space-y-1 text-xs text-muted-foreground">
                {BOOT_LOGS.slice(0, logIndex + 1).slice(-4).map((log, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-[#ea580c] select-none">&gt;</span>
                    <span
                      className={
                        i === BOOT_LOGS.slice(0, logIndex + 1).slice(-4).length - 1
                          ? "text-foreground font-bold"
                          : "text-muted-foreground"
                      }
                    >
                      {log}
                    </span>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 text-xs text-[#ea580c] font-bold">
                <span className="animate-blink">_</span>
              </div>
            </div>

          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

