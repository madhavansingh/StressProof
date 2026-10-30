"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  ShieldAlert,
  FileCheck2,
  Lock,
  Radio,
  Menu,
  X,
  ExternalLink,
  Cpu,
  Layers,
  ArrowLeft,
  Waypoints,
} from "lucide-react";
import { BACKEND_URL } from "@/lib/api/client";

const HEALTH_POLL_MS = 15_000;

type BackendStatus = "checking" | "online" | "offline";

/** Polls the backend /health endpoint so the sidebar status is real, not a fixed "ONLINE". */
function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");
  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { cache: "no-store" });
        const body: unknown = await res.json().catch(() => null);
        const ok = res.ok && !!body && typeof body === "object" && (body as { ok?: unknown }).ok === true;
        if (active) setStatus(ok ? "online" : "offline");
      } catch {
        if (active) setStatus("offline");
      }
    };
    void check();
    const timer = setInterval(check, HEALTH_POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  return status;
}

export function PortalSidebar() {
  const pathname = usePathname();
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const navItems = [
    {
      label: "OVERVIEW",
      href: "/dashboard",
      icon: BarChart3,
      tag: "001",
      badge: "LIVE",
    },
    {
      label: "STRESS_SIMULATION",
      href: "/stress",
      icon: ShieldAlert,
      tag: "002",
      badge: "FORK",
    },
    {
      label: "BONDED_CLAIMS",
      href: "/claims",
      icon: FileCheck2,
      tag: "003",
      badge: "REGISTRY",
    },
    {
      label: "CIRCUIT_BREAKER",
      href: "/vault",
      icon: Lock,
      tag: "004",
      badge: "DEFENSE",
    },
    {
      label: "REACTIVE_FEED",
      href: "/feed",
      icon: Radio,
      tag: "005",
      badge: "STREAM",
    },
    {
      label: "EXPOSURE_GRAPH",
      href: "/graph",
      icon: Waypoints,
      tag: "006",
      badge: "REPLAY",
    },
  ];
  const backendStatus = useBackendStatus();

  return (
    <>
      {/* Mobile Drawer Open Button */}
      {!isMobileOpen && (
        <button
          type="button"
          aria-label="Open Navigation Menu"
          onClick={() => setIsMobileOpen(true)}
          className="lg:hidden fixed top-3.5 left-4 z-[50] p-2 bg-card border-2 border-foreground text-foreground shadow-sm hover:bg-foreground hover:text-background transition-colors"
        >
          <Menu className="h-5 w-5" />
        </button>
      )}

      {/* Mobile Overlay */}
      {isMobileOpen && (
        <div
          onClick={() => setIsMobileOpen(false)}
          className="lg:hidden fixed inset-0 bg-black/80 backdrop-blur-sm z-[65]"
        />
      )}

      {/* Brutalist Sidebar Shell */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-[66] w-72 h-screen bg-card border-r-2 border-border flex flex-col justify-between transition-transform duration-200 ease-in-out font-mono shrink-0 select-none
          lg:translate-x-0 lg:static lg:h-screen lg:shrink-0
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">
          {/* Brand Header with Close Button on Right */}
          <div className="h-16 px-5 flex items-center justify-between border-b-2 border-border bg-card shrink-0">
            <Link
              href="/"
              className="flex items-center gap-3 group"
              onClick={() => setIsMobileOpen(false)}
            >
              <div className="h-8 w-8 bg-[#ea580c] flex items-center justify-center text-white font-bold text-xs tracking-wider shadow-[3px_3px_0px_0px_#ffffff] shrink-0">
                SP
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold tracking-widest uppercase text-foreground">
                  STRESSPROOF
                </span>
              </div>
            </Link>

            {/* Mobile Close Button on the Right */}
            <button
              type="button"
              aria-label="Close Navigation Menu"
              onClick={() => setIsMobileOpen(false)}
              className="lg:hidden p-1.5 border border-border text-muted-foreground hover:text-foreground hover:border-foreground hover:bg-secondary transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Section Marker */}
          <div className="px-5 py-3 border-b border-border bg-muted/20 flex items-center justify-between shrink-0">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              {"// NAVIGATION"}
            </span>
            <span className="text-[10px] text-[#ea580c] font-bold">{navItems.length} PAGES</span>
          </div>

          {/* Navigation Links */}
          <nav className="p-3 space-y-1.5">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setIsMobileOpen(false)}
                  className={`
                    group flex items-center justify-between gap-3 px-3.5 py-2.5 text-xs font-mono tracking-wider transition-all border
                    ${
                      isActive
                        ? "bg-foreground text-background font-bold border-foreground shadow-[2px_2px_0px_0px_#ea580c]"
                        : "text-muted-foreground hover:text-foreground hover:bg-secondary border-transparent hover:border-border"
                    }
                  `}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-[#ea580c]" : "group-hover:text-foreground"}`} />
                    <span className="truncate">{item.label}</span>
                  </div>
                  <span
                    className={`shrink-0 text-[9px] px-1.5 py-0.5 border ${
                      isActive
                        ? "border-background text-background bg-foreground/10"
                        : "border-border text-muted-foreground group-hover:text-foreground"
                    }`}
                  >
                    {item.badge}
                  </span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer & Operational Status */}
        <div className="p-4 border-t-2 border-border bg-card space-y-3 shrink-0">
          <div className="border border-border p-3 space-y-2 bg-background/50">
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase">
              <span>BACKEND</span>
              <span
                role="status"
                className={`font-bold flex items-center gap-1 ${backendStatus === "online" ? "text-emerald-400" : backendStatus === "offline" ? "text-red-400" : "text-muted-foreground"}`}
              >
                <span className={`h-1.5 w-1.5 ${backendStatus === "online" ? "bg-emerald-400" : backendStatus === "offline" ? "bg-red-400" : "bg-muted-foreground"}`} />
                {backendStatus === "online" ? "ONLINE" : backendStatus === "offline" ? "OFFLINE" : "CHECKING"}
              </span>
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase">
              <span>FORK_BLOCK</span>
              <span className="text-foreground font-mono">#19,000,000</span>
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase">
              <span title="WETH price in the SYNTHETIC fixture snapshot; not a live oracle">SNAPSHOT_PRICE</span>
              <span className="text-[#ea580c] font-mono font-bold">$3,000.00</span>
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase">
              <span>DATASET</span>
              <span className="text-amber-400 font-mono font-bold">SYNTHETIC</span>
            </div>
          </div>

          <Link
            href="/"
            className="flex items-center justify-center gap-2 w-full py-2 border border-border text-[11px] font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground hover:border-foreground hover:bg-secondary transition-all"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>BACK_TO_LANDING</span>
          </Link>
        </div>
      </aside>
    </>
  );
}
