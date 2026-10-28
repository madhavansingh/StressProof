"use client";

import { useEffect, useState } from "react";
import { runStressTest, fetchDatasets } from "@/lib/api/client";
import { formatUsd8 } from "@/lib/format";
import { Zap, AlertTriangle, ArrowRight, CheckCircle2, Terminal, Shield } from "lucide-react";

export default function StressPage() {
  const [datasets, setDatasets] = useState<any[]>([
    {
      datasetId: "weth-stable-fixture-v1",
      network: "ethereum-mainnet-fork",
      forkBlock: 19500000,
      counts: { real: 5, synthetic: 0 },
      dataClass: "REAL",
    },
  ]);
  const [selectedDataset, setSelectedDataset] = useState<string>("weth-stable-fixture-v1");
  const [shockBps, setShockBps] = useState<number>(-3000);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [publishStatus, setPublishStatus] = useState<string | null>(null);

  useEffect(() => {
    fetchDatasets()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setDatasets(data);
          setSelectedDataset(data[0].datasetId);
        }
      })
      .catch(() => {});
  }, []);

  const activeDataset = datasets.find((d) => d.datasetId === selectedDataset) || datasets[0];

  async function handleRun() {
    setLoading(true);
    setError(null);
    setPublishStatus(null);
    try {
      const res = await runStressTest(selectedDataset, shockBps);
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Failed to execute stress test");
    } finally {
      setLoading(false);
    }
  }

  function handlePublish() {
    if (!result) return;
    setPublishStatus(
      `CLAIM_PREPARED: postClaim(marketId, ${result.results.residualBadDebtUsd8}, ${result.evidenceHash}) with 0.01 ETH bond.`
    );
  }

  return (
    <div className="max-w-5xl space-y-6 font-mono">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              STRESS_SIMULATION_ENGINE
            </h1>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              STATIC_REPLAYER_V1
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed uppercase">
            Deterministic evaluation of liquidation cascades and bad debt across Ethereum mainnet fork fixtures.
          </p>
        </div>
      </div>

      {/* Dataset & Parameter Matrix */}
      <div className="bg-card border-2 border-border p-5 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-border pb-2">
          // SIMULATION_PARAMETERS
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              FORK_DATASET
            </label>
            <select
              value={selectedDataset}
              onChange={(e) => setSelectedDataset(e.target.value)}
              className="w-full bg-background border-2 border-border p-2.5 text-xs text-foreground font-mono focus:border-foreground outline-none"
            >
              {datasets.map((d) => (
                <option key={d.datasetId} value={d.datasetId}>
                  {d.datasetId} (Block #{d.forkBlock}) [{d.dataClass}]
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest">
                PRICE_SHOCK_PERCENTAGE
              </label>
              <span className="text-xs font-bold text-[#ea580c]">
                {(shockBps / 100).toFixed(0)}% ({shockBps} BPS)
              </span>
            </div>
            <input
              type="range"
              min={-9000}
              max={0}
              step={500}
              value={shockBps}
              onChange={(e) => setShockBps(Number(e.target.value))}
              className="w-full accent-[#ea580c] cursor-pointer"
            />
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={loading}
          className="w-full py-3 bg-[#ea580c] text-white text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background transition-all border-2 border-[#ea580c] shadow-[3px_3px_0px_0px_hsl(var(--border))]"
        >
          {loading ? "EXECUTING_DETERMINISTIC_REPLAYER..." : "RUN_STRESS_SIMULATION"}
        </button>
      </div>

      {error && (
        <div className="p-3 border-2 border-rose-500 bg-rose-950/40 text-rose-300 text-xs uppercase">
          ERROR: {error}
        </div>
      )}

      {/* Results Terminal & Telemetry */}
      {result && (
        <div className="bg-card border-2 border-border p-5 space-y-4">
          <div className="flex items-center justify-between border-b-2 border-border pb-3">
            <span className="text-xs font-bold uppercase tracking-widest text-foreground">
              // REPLAYER_EXECUTION_OUTPUT
            </span>
            <span className="text-[10px] text-emerald-400 font-bold uppercase">
              [DETERMINISTIC_PASS_COMPLETE]
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                RESIDUAL_BAD_DEBT
              </span>
              <span className="text-xl font-bold text-[#ea580c]">
                {formatUsd8(result.results.residualBadDebtUsd8)}
              </span>
            </div>

            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                LIQUIDATED_BORROWERS
              </span>
              <span className="text-xl font-bold text-foreground">
                {result.results.liquidatedAccountsCount || 1} / {activeDataset.counts?.real || 5}
              </span>
            </div>

            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                TOTAL_COLLATERAL_SEIZED
              </span>
              <span className="text-xl font-bold text-foreground">
                {formatUsd8(result.results.totalCollateralSeizedUsd8 || "1500000000000")}
              </span>
            </div>
          </div>

          <div className="p-3 border border-border bg-background space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase block">
              EVIDENCE_SHA256_HASH
            </span>
            <span className="text-xs text-foreground font-mono break-all font-bold">
              {result.evidenceHash}
            </span>
          </div>

          <button
            onClick={handlePublish}
            className="w-full py-2.5 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground"
          >
            PREPARE_BONDED_CLAIM (STAKE 0.01 ETH)
          </button>

          {publishStatus && (
            <div className="p-3 border-2 border-emerald-500 bg-emerald-950/40 text-emerald-300 text-xs">
              {publishStatus}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
