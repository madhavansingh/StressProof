export default function GraphPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">TigerGraph Exposure Graph</h1>
        <p className="text-zinc-500">
          Visualized borrower risk network and estimated collateral exposure.
        </p>
      </div>

      <div className="flex h-96 items-center justify-center rounded-xl border border-dashed bg-white dark:bg-zinc-950">
        <p className="text-sm text-zinc-400">
          Interactive TigerGraph 2D Force Graph (Phase 2 Integration)
        </p>
      </div>
    </div>
  );
}
