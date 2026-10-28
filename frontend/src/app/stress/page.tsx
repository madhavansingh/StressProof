"use client";

import { useState } from "react";
import { runStressTest } from "@/lib/api/client";

export default function StressPage() {
  const [shockBps, setShockBps] = useState<number>(-3000);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const res = await runStressTest("weth-stable-fixture-v1", shockBps);
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Failed to execute stress test");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Stress Test Simulation</h1>
        <p className="text-zinc-500">
          Simulate market liquidation dynamics using deterministic static-liquidation-v1.
        </p>
      </div>

      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-semibold">
            WETH Price Shock: {shockBps / 100}% ({shockBps} bps)
          </label>
          <input
            type="range"
            min="-9000"
            max="-500"
            step="500"
            value={shockBps}
            onChange={(e) => setShockBps(Number(e.target.value))}
            className="w-full cursor-pointer accent-indigo-600"
          />
          <div className="flex justify-between text-xs text-zinc-400">
            <span>-90%</span>
            <span>-50%</span>
            <span>-30%</span>
            <span>-5%</span>
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={loading}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Replaying Liquidation Model..." : "Run Simulation"}
        </button>

        {error && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}
      </div>

      {result && (
        <div className="space-y-4">
          <h2 className="text-xl font-bold">Simulation Results</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-xl border bg-white p-4 shadow-sm dark:bg-zinc-950">
              <span className="text-xs font-medium text-zinc-500 uppercase">Liquidatable Accounts</span>
              <p className="mt-2 text-2xl font-bold">{result.results.liquidatableAccounts}</p>
            </div>
            <div className="rounded-xl border bg-white p-4 shadow-sm dark:bg-zinc-950">
              <span className="text-xs font-medium text-zinc-500 uppercase">Debt at Risk</span>
              <p className="mt-2 text-2xl font-bold">${(Number(result.results.debtAtRiskUsd8) / 1e8).toLocaleString()}</p>
            </div>
            <div className="rounded-xl border bg-white p-4 shadow-sm dark:bg-zinc-950">
              <span className="text-xs font-medium text-zinc-500 uppercase">Liquidation Volume</span>
              <p className="mt-2 text-2xl font-bold">${(Number(result.results.liquidationVolumeUsd8) / 1e8).toLocaleString()}</p>
            </div>
            <div className="rounded-xl border bg-white p-4 shadow-sm dark:bg-zinc-950 border-amber-300 dark:border-amber-700">
              <span className="text-xs font-medium text-amber-600 dark:text-amber-400 uppercase font-semibold">
                Residual Bad Debt
              </span>
              <p className="mt-2 text-2xl font-bold text-amber-600 dark:text-amber-400">
                ${(Number(result.results.residualBadDebtUsd8) / 1e8).toLocaleString()}
              </p>
            </div>
          </div>

          <div className="rounded-xl border bg-zinc-50 p-4 text-xs dark:bg-zinc-950 font-mono space-y-1">
            <p><strong>Evidence Hash:</strong> {result.evidenceHash}</p>
            <p><strong>Case File URI:</strong> {result.caseFileURI}</p>
          </div>
        </div>
      )}

      <div className="rounded-xl border bg-amber-50/50 p-4 text-xs text-amber-900 dark:bg-amber-950/20 dark:text-amber-200 space-y-1">
        <h3 className="font-bold">Model Assumptions (static-liquidation-v1)</h3>
        <ul className="list-disc pl-4 space-y-0.5">
          <li>One collateral asset per account (WETH); unshocked stablecoin debt.</li>
          <li>One liquidation pass; full liquidation (close factor 100%) at shocked price.</li>
          <li>No slippage, price impact, or liquidator gas constraints.</li>
          <li>Results are deterministic estimates for the filtered subset, not whole market forecasts.</li>
        </ul>
      </div>
    </div>
  );
}
