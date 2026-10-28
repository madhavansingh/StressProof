import Link from "next/link";

export default function MarketsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight">Lending Markets</h1>
        <p className="text-zinc-500">
          Monitored lending markets backed by bonded risk claims and verifiable evidence.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Aave v3 Ethereum Fork
            </span>
            <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              Active
            </span>
          </div>
          <h2 className="mt-2 text-xl font-bold">WETH / Stablecoins</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Market ID: <code className="font-mono text-zinc-700 dark:text-zinc-300">aave-v3-eth-weth-stable</code>
          </p>

          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg bg-zinc-50 p-2 dark:bg-zinc-900">
              <span className="text-xs text-zinc-500">Default Max LTV</span>
              <p className="font-semibold">80.00%</p>
            </div>
            <div className="rounded-lg bg-zinc-50 p-2 dark:bg-zinc-900">
              <span className="text-xs text-zinc-500">Borrow Status</span>
              <p className="font-semibold text-emerald-600">Open</p>
            </div>
          </div>

          <div className="mt-6 flex gap-2">
            <Link
              href="/stress"
              className="flex-1 rounded-lg bg-indigo-600 px-3 py-2 text-center text-sm font-semibold text-white hover:bg-indigo-500"
            >
              Run Stress Test
            </Link>
            <Link
              href="/vault"
              className="rounded-lg border px-3 py-2 text-sm font-semibold hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              Vault Controls
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
