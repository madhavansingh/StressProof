import Link from "next/link";

export default function ClaimsPage() {
  const claims = [
    {
      id: "1",
      attester: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      marketId: "aave-v3-eth-weth-stable",
      claimedBadDebt: "$2,000.00",
      bond: "0.01 ETH",
      status: "Finalized",
      deadline: "Completed",
    },
    {
      id: "2",
      attester: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
      marketId: "aave-v3-eth-weth-stable",
      claimedBadDebt: "$6,000.00",
      bond: "0.01 ETH",
      status: "Rejected",
      deadline: "Dispute Upheld",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Bonded Risk Claims</h1>
          <p className="text-zinc-500">
            Registered claims on StressRegistry backed by 0.01 ETH bonds.
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border bg-white shadow-sm dark:bg-zinc-950">
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-zinc-50 text-xs font-semibold uppercase text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className="p-4">ID</th>
              <th className="p-4">Attester</th>
              <th className="p-4">Claimed Bad Debt</th>
              <th className="p-4">Bond</th>
              <th className="p-4">Status</th>
              <th className="p-4">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {claims.map((c) => (
              <tr key={c.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900">
                <td className="p-4 font-mono font-bold">#{c.id}</td>
                <td className="p-4 font-mono text-xs">{c.attester.slice(0, 8)}...{c.attester.slice(-6)}</td>
                <td className="p-4 font-semibold text-amber-600">{c.claimedBadDebt}</td>
                <td className="p-4">{c.bond}</td>
                <td className="p-4">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      c.status === "Finalized"
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                        : "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
                    }`}
                  >
                    {c.status}
                  </span>
                </td>
                <td className="p-4">
                  <Link
                    href={`/claims/${c.id}`}
                    className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    Verify & Details
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
