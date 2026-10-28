"use client";

import { useState } from "react";
import { verifyEvidenceUri, VerificationResult } from "@/lib/validation/verify";

export default function ClaimDetailPage({ params }: { params: { id: string } }) {
  const [evidenceUri, setEvidenceUri] = useState<string>("http://127.0.0.1:8000/case-files/0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0");
  const [expectedHash, setExpectedHash] = useState<string>("0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0");
  const [verifying, setVerifying] = useState<boolean>(false);
  const [result, setResult] = useState<VerificationResult | null>(null);

  async function handleVerify() {
    setVerifying(true);
    const res = await verifyEvidenceUri(evidenceUri, expectedHash);
    setResult(res);
    setVerifying(false);
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Claim #{params.id} Verification</h1>
        <p className="text-zinc-500">
          Independent in-browser raw-byte Keccak-256 evidence verification.
        </p>
      </div>

      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-zinc-950 space-y-4">
        <div>
          <label className="text-xs font-semibold uppercase text-zinc-500">Evidence URI</label>
          <input
            type="text"
            value={evidenceUri}
            onChange={(e) => setEvidenceUri(e.target.value)}
            className="mt-1 w-full rounded-lg border bg-zinc-50 p-2 font-mono text-xs dark:bg-zinc-900"
          />
        </div>

        <div>
          <label className="text-xs font-semibold uppercase text-zinc-500">On-Chain Evidence Hash</label>
          <input
            type="text"
            value={expectedHash}
            onChange={(e) => setExpectedHash(e.target.value)}
            className="mt-1 w-full rounded-lg border bg-zinc-50 p-2 font-mono text-xs dark:bg-zinc-900"
          />
        </div>

        <button
          onClick={handleVerify}
          disabled={verifying}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {verifying ? "Hashing Raw Bytes..." : "Verify Hash In-Browser"}
        </button>

        {result && (
          <div
            className={`rounded-xl border p-4 text-sm ${
              result.valid
                ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                : "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/30 dark:text-red-300"
            }`}
          >
            <p className="font-bold">
              {result.valid ? "✓ Cryptographic Evidence Hash Verified" : "✗ Hash Verification Failed"}
            </p>
            <p className="mt-1 text-xs font-mono">Computed: {result.computedHash || "N/A"}</p>
            {result.error && <p className="mt-1 text-xs">{result.error}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
