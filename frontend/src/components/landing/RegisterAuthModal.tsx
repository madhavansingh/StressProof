"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Shield, Key, User, Check, ArrowRight, Lock, Radio, LogOut, CheckCircle2 } from "lucide-react";

export interface OperatorSession {
  handle: string;
  role: string;
  pubKey: string;
  isRegistered: boolean;
}

const STORAGE_KEY = "stressproof_operator_session";

const DEMO_PRESETS = [
  {
    handle: "attester-node-01",
    role: "AI_RISK_ATTESTER",
    pubKey: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  },
  {
    handle: "watcher-sentinel",
    role: "INDEPENDENT_WATCHER",
    pubKey: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
  },
  {
    handle: "vault-guardian-node",
    role: "CIRCUIT_BREAKER_GUARDIAN",
    pubKey: "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
  },
];

export function RegisterAuthModal({
  isOpen,
  onClose,
  session,
  onUpdateSession,
}: {
  isOpen: boolean;
  onClose: () => void;
  session: OperatorSession | null;
  onUpdateSession: (newSession: OperatorSession | null) => void;
}) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [handle, setHandle] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("AI_RISK_ATTESTER");
  const [pubKey, setPubKey] = useState("");
  const [stakeCommitted, setStakeCommitted] = useState(true);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Close on ESC
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleQuickFill = () => {
    const preset = DEMO_PRESETS[Math.floor(Math.random() * DEMO_PRESETS.length)];
    setHandle(preset.handle);
    setRole(preset.role);
    setPubKey(preset.pubKey);
    setPassword("demo_secret_2026");
    setStatusMsg("DEMO CREDENTIALS LOADED");
    setTimeout(() => setStatusMsg(null), 2500);
  };

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault();
    if (!handle.trim()) {
      setStatusMsg("ERROR: OPERATOR_HANDLE_REQUIRED");
      return;
    }
    setIsLoading(true);
    setStatusMsg("REGISTERING NODE ON BASE SEPOLIA TESTNET...");

    setTimeout(() => {
      const generatedKey = pubKey || `0x${Array.from({ length: 40 }, () => Math.floor(Math.random() * 16).toString(16)).join("")}`;
      const newSession: OperatorSession = {
        handle: handle.trim(),
        role,
        pubKey: generatedKey,
        isRegistered: true,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newSession));
      onUpdateSession(newSession);
      setIsLoading(false);
      setStatusMsg("NODE_REGISTERED_SUCCESSFULLY");
      setTimeout(() => {
        onClose();
        setStatusMsg(null);
      }, 900);
    }, 700);
  };

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!handle.trim()) {
      setStatusMsg("ERROR: OPERATOR_CREDENTIALS_REQUIRED");
      return;
    }
    setIsLoading(true);
    setStatusMsg("AUTHENTICATING OPERATOR SESSION...");

    setTimeout(() => {
      const newSession: OperatorSession = {
        handle: handle.trim(),
        role: "AI_RISK_ATTESTER",
        pubKey: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        isRegistered: true,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newSession));
      onUpdateSession(newSession);
      setIsLoading(false);
      setStatusMsg("SESSION_INITIALIZED");
      setTimeout(() => {
        onClose();
        setStatusMsg(null);
      }, 800);
    }, 600);
  };

  const handleLogout = () => {
    localStorage.removeItem(STORAGE_KEY);
    onUpdateSession(null);
    setStatusMsg("LOGGED_OUT");
    setTimeout(() => {
      onClose();
      setStatusMsg(null);
    }, 700);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-sm font-mono">
          {/* Backdrop Click */}
          <div className="absolute inset-0" onClick={onClose} />

          {/* Modal Container */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 15 }}
            transition={{ duration: 0.2 }}
            className="relative w-full max-w-lg border-2 border-foreground bg-card text-foreground shadow-[8px_8px_0px_0px_#ea580c] overflow-hidden z-10"
          >
            {/* Terminal Top Window Bar */}
            <div className="flex items-center justify-between border-b-2 border-foreground px-4 py-3 bg-secondary">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 bg-[#ea580c]" />
                <span className="h-3 w-3 bg-foreground" />
                <span className="text-xs uppercase font-bold tracking-widest text-foreground">
                  OPERATOR_AUTH // V1.0
                </span>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="p-1 hover:bg-foreground hover:text-background text-muted-foreground transition-colors border border-transparent hover:border-foreground"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content Area */}
            <div className="p-6 space-y-6">
              {/* If Already Logged In */}
              {session?.isRegistered ? (
                <div className="space-y-4">
                  <div className="p-4 border border-emerald-500 bg-emerald-950/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider">
                        SESSION_AUTHENTICATED
                      </span>
                      <span className="h-2 w-2 bg-emerald-400 animate-pulse" />
                    </div>
                    <p className="text-sm font-bold text-foreground uppercase">
                      OPERATOR: {session.handle}
                    </p>
                    <p className="text-xs text-muted-foreground uppercase">
                      ASSIGNED ROLE: <span className="text-foreground">{session.role}</span>
                    </p>
                    <p className="text-[10px] text-muted-foreground font-mono truncate">
                      PUBKEY: {session.pubKey}
                    </p>
                  </div>

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="flex-1 py-2.5 border-2 border-rose-500 bg-rose-950/40 text-rose-300 text-xs font-bold uppercase hover:bg-rose-500 hover:text-white transition-all flex items-center justify-center gap-2"
                    >
                      <LogOut size={14} />
                      DISCONNECT NODE
                    </button>
                    <button
                      type="button"
                      onClick={onClose}
                      className="flex-1 py-2.5 bg-foreground text-background text-xs font-bold uppercase hover:bg-[#ea580c] hover:text-white transition-all"
                    >
                      CONTINUE TO PROTOCOL
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {/* Mode Selector Tabs */}
                  <div className="grid grid-cols-2 border border-border">
                    <button
                      type="button"
                      onClick={() => setMode("register")}
                      className={`py-2 text-xs font-bold uppercase tracking-wider transition-all ${
                        mode === "register"
                          ? "bg-foreground text-background"
                          : "bg-background text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      REGISTER NODE
                    </button>
                    <button
                      type="button"
                      onClick={() => setMode("login")}
                      className={`py-2 text-xs font-bold uppercase tracking-wider transition-all ${
                        mode === "login"
                          ? "bg-foreground text-background"
                          : "bg-background text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      OPERATOR LOGIN
                    </button>
                  </div>

                  {/* Mode Forms */}
                  {mode === "register" ? (
                    <form onSubmit={handleRegister} className="space-y-4">
                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                          OPERATOR HANDLE / NODE ID
                        </label>
                        <input
                          type="text"
                          required
                          value={handle}
                          onChange={(e) => setHandle(e.target.value)}
                          placeholder="e.g. attester-node-alpha"
                          className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                        />
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                            NETWORK ROLE
                          </label>
                          <select
                            value={role}
                            onChange={(e) => setRole(e.target.value)}
                            className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                          >
                            <option value="AI_RISK_ATTESTER">AI Risk Attester</option>
                            <option value="INDEPENDENT_WATCHER">Independent Watcher</option>
                            <option value="CIRCUIT_BREAKER_GUARDIAN">Vault Guardian</option>
                            <option value="LIQUIDATOR_KEEPER">Liquidator Keeper</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                            ACCESS PHRASE
                          </label>
                          <input
                            type="password"
                            required
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••••••"
                            className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                          WALLET ADDRESS (OPTIONAL)
                        </label>
                        <input
                          type="text"
                          value={pubKey}
                          onChange={(e) => setPubKey(e.target.value)}
                          placeholder="0x... (leave empty for auto-generated testnet key)"
                          className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                        />
                      </div>

                      <label className="flex items-center gap-2 cursor-pointer text-[11px] text-muted-foreground uppercase">
                        <input
                          type="checkbox"
                          checked={stakeCommitted}
                          onChange={(e) => setStakeCommitted(e.target.checked)}
                          className="accent-[#ea580c] h-3.5 w-3.5"
                        />
                        <span>PLEDGE 0.01 ETH DEMO BOND REQUIREMENT</span>
                      </label>

                      {statusMsg && (
                        <div className="p-2 border border-[#ea580c] bg-orange-950/40 text-[#ea580c] text-[10px] uppercase font-bold">
                          {statusMsg}
                        </div>
                      )}

                      <div className="flex items-center gap-3 pt-2">
                        <button
                          type="button"
                          onClick={handleQuickFill}
                          className="px-3 py-2 border border-border text-[10px] uppercase hover:border-foreground text-muted-foreground hover:text-foreground transition-all"
                        >
                          [QUICK_DEMO_FILL]
                        </button>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="flex-1 py-2 bg-foreground text-background text-xs font-bold uppercase hover:bg-[#ea580c] hover:text-white transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                        >
                          <span>{isLoading ? "PROCESSING..." : "REGISTER_NODE"}</span>
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    </form>
                  ) : (
                    <form onSubmit={handleLogin} className="space-y-4">
                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                          OPERATOR ID OR ETH ADDRESS
                        </label>
                        <input
                          type="text"
                          required
                          value={handle}
                          onChange={(e) => setHandle(e.target.value)}
                          placeholder="e.g. attester-node-01 or 0x7099..."
                          className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                        />
                      </div>

                      <div>
                        <label className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                          ACCESS KEY / PASSWORD
                        </label>
                        <input
                          type="password"
                          required
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="••••••••••••"
                          className="w-full bg-background border border-border px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-foreground"
                        />
                      </div>

                      {statusMsg && (
                        <div className="p-2 border border-[#ea580c] bg-orange-950/40 text-[#ea580c] text-[10px] uppercase font-bold">
                          {statusMsg}
                        </div>
                      )}

                      <div className="flex items-center gap-3 pt-2">
                        <button
                          type="button"
                          onClick={handleQuickFill}
                          className="px-3 py-2 border border-border text-[10px] uppercase hover:border-foreground text-muted-foreground hover:text-foreground transition-all"
                        >
                          [QUICK_DEMO_FILL]
                        </button>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="flex-1 py-2 bg-foreground text-background text-xs font-bold uppercase hover:bg-[#ea580c] hover:text-white transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                        >
                          <span>{isLoading ? "AUTHENTICATING..." : "LOGIN_OPERATOR"}</span>
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    </form>
                  )}
                </>
              )}
            </div>

            {/* Modal Footer Note */}
            <div className="px-6 py-2.5 border-t border-border bg-background text-[10px] text-muted-foreground uppercase flex items-center justify-between">
              <span>DEMO_SYSTEM // LOCAL_STORAGE_SESSION</span>
              <span className="text-emerald-400 font-bold">FRONTEND_ONLY</span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

