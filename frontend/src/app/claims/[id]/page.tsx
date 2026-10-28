"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { verifyEvidenceUri, VerificationResult } from "@/lib/validation/verify";
import { formatUsd8, formatBps } from "@/lib/format";
import { Shield, CheckCircle2, AlertTriangle, ArrowLeft, Terminal, Cpu } from "lucide-react";

export default function ClaimDetailPage({ params }: { params: { id: string } }) {
  const isClaimOne = params.id === "1";
  const isRejectedClaim = params.id === "2";

  const claim = {
    id: params.id,
    attester: isClaimOne
      ? "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
      : "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    marketId: "aave-v3-eth-weth-stable",
    claimedBadDebt: isClaimOne ? "200000000001" : "600000000003",
    status: isClaimOne ? "Finalized" : isRejectedClaim ? "Rejected" : "Pending",
    evidenceUri: isClaimOne
      ? "http://127.0.0.1:8000/case-files/0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0"
      : "http://127.0.0.1:8000/case-files/0x9b31d8e9c60014a717706d17a25d0070d67c16f69cd1ae9f3777a25f1",
    evidenceHash: isClaimOne
      ? "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0"
      : "0x9b31d8e9c60014a717706d17a25d0070d67c16f69cd1ae9f3777a25f1",
  };

  const [evidenceUri, setEvidenceUri] = useState<string>(claim.evidenceUri);
  const [expectedHash, setExpectedHash] = useState<string>(claim.evidenceHash);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [result, setResult] = useState<VerificationResult | null>(null);

  const [vaultApplied, setVaultApplied] = useState<boolean>(isClaimOne);
  const [vaultMaxLtvBps, setVaultMaxLtvBps] = useState<number>(isClaimOne ? 5000 : 8000);
  const [vaultPaused, setVaultPaused] = useState<boolean>(false);
  const [vaultActionMsg, setVaultActionMsg] = useState<string | null>(null);

  const [collateralUsd, setCollateralUsd] = useState<number>(10000);
  const [borrowUsd, setBorrowUsd] = useState<number>(7000);
  const [borrowOutcome, setBorrowOutcome] = useState<string | null>(null);

  async function handleVerify() {
    setVerifying(true);
    const res = await verifyEvidenceUri(evidenceUri, expectedHash);
    setResult(res);
    setVerifying(false);
  }

  function handleApplyToVault() {
    if (claim.status !== "Finalized") {
      setVaultActionMsg("REVERT: NotFinalized() — Only Finalized claims can alter DemoVault risk parameters.");
      return;
    }
    setVaultApplied(true);
    setVaultMaxLtvBps(5000);
    setVaultActionMsg(`SUCCESS: Claim #${claim.id} applied to DemoVault! Max LTV tightened to 50.00%.`);
  }

  function handleTestBorrow() {
    if (vaultPaused) {
      setBorrowOutcome("REVERT: BorrowPaused() — Emergency pause active.");
      return;
    }
    const reqLtvBps = Math.ceil((borrowUsd * 10000) / collateralUsd);
    if (reqLtvBps > vaultMaxLtvBps) {
      setBorrowOutcome(
        `REVERT: LtvTooHigh(requested: ${reqLtvBps} bps [${(reqLtvBps / 100).toFixed(
          2
        )}%], max: ${vaultMaxLtvBps} bps [${(vaultMaxLtvBps / 100).toFixed(2)}%])`
      );
    } else {
      setBorrowOutcome(
        `SUCCESS: Borrowed $${borrowUsd.toLocaleString()} against $${collateralUsd.toLocaleString()} collateral.`
      );
    }
  }

  return (
    <div className="space-y-6 font-mono max-w-5xl">
      {/* Top Back Link */}
      <Link
        href="/claims"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground uppercase tracking-widest"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        <span>&larr; BACK_TO_CLAIMS_REGISTRY</span>
      </Link>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground uppercase">
              CLAIM_DOSSIER_#{claim.id}
            </h1>
            <span
              className={`px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider ${
                claim.status === "Finalized"
                  ? "border-emerald-500 bg-emerald-950/40 text-emerald-400"
                  : claim.status === "Rejected"
                  ? "border-rose-500 bg-rose-950/40 text-rose-400"
                  : "border-amber-500 bg-amber-950/40 text-amber-400"
              }`}
            >
              [{claim.status}]
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 uppercase">
            MARKET: {claim.marketId} &bull; ATTESTER: {claim.attester}
          </p>
        </div>

        <button
          onClick={handleApplyToVault}
          className="px-4 py-2 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground"
        >
          APPLY_TO_DEMOVAULT
        </button>
      </div>

      {vaultActionMsg && (
        <div className="p-3 border-2 border-border bg-secondary text-xs text-foreground">
          {vaultActionMsg}
        </div>
      )}

      {/* Grid: Claim Attributes & Evidence Verification */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: Parameters */}
        <div className="bg-card border-2 border-border p-5 space-y-4">
          <h2 className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-border pb-2">
            // CLAIM_METRICS
          </h2>
          <div className="space-y-3 text-xs">
            <div className="flex justify-between border-b border-border pb-1">
              <span className="text-muted-foreground uppercase">CLAIMED_BAD_DEBT:</span>
              <span className="font-bold text-foreground">{formatUsd8(claim.claimedBadDebt)}</span>
            </div>
            <div className="flex justify-between border-b border-border pb-1">
              <span className="text-muted-foreground uppercase">STAKED_BOND:</span>
              <span className="text-foreground">0.01 ETH</span>
            </div>
            <div className="flex justify-between border-b border-border pb-1">
              <span className="text-muted-foreground uppercase">EVIDENCE_HASH:</span>
              <span className="text-xs text-[#ea580c] font-mono break-all">{claim.evidenceHash}</span>
            </div>
          </div>
        </div>

        {/* Card 2: Deterministic Replayer Verification */}
        <div className="bg-card border-2 border-border p-5 space-y-4">
          <h2 className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-border pb-2">
            // EVIDENCE_INTEGRITY_CHECK
          </h2>
          <p className="text-[11px] text-muted-foreground uppercase leading-relaxed">
            Verify SHA-256 evidence integrity against the content-addressed case file.
          </p>
          <div className="space-y-3">
            <input
              type="text"
              value={evidenceUri}
              onChange={(e) => setEvidenceUri(e.target.value)}
              className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
            />
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="w-full py-2 bg-[#ea580c] text-white text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background transition-all border-2 border-[#ea580c]"
            >
              {verifying ? "VERIFYING_SHA256..." : "VERIFY_EVIDENCE_HASH"}
            </button>
          </div>

          {result && (
            <div
              className={`p-3 border text-xs ${
                result.valid
                  ? "border-emerald-500 bg-emerald-950/40 text-emerald-300"
                  : "border-rose-500 bg-rose-950/40 text-rose-300"
              }`}
            >
              <p className="font-bold uppercase">
                {result.valid ? "[HASH_MATCH_VERIFIED]" : "[HASH_MISMATCH_DISCREPANCY]"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">
                COMPUTED: {result.computedHash}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Borrow Simulation Test Bench */}
      <div className="bg-card border-2 border-border p-5 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-border pb-2">
          // DEMOVAULT_DEFENSE_TEST_BENCH
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              COLLATERAL_DEPOSIT ($)
            </label>
            <input
              type="number"
              value={collateralUsd}
              onChange={(e) => setCollateralUsd(Number(e.target.value))}
              className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
            />
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              BORROW_REQUEST ($)
            </label>
            <input
              type="number"
              value={borrowUsd}
              onChange={(e) => setBorrowUsd(Number(e.target.value))}
              className="w-full bg-background border-2 border-border p-2 text-xs text-foreground font-mono focus:border-foreground outline-none"
            />
          </div>
        </div>

        <button
          onClick={handleTestBorrow}
          className="px-4 py-2 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground"
        >
          EXECUTE_TEST_BORROW
        </button>

        {borrowOutcome && (
          <div className="p-3 border-2 border-border bg-background text-xs text-foreground">
            {borrowOutcome}
          </div>
        )}
      </div>
    </div>
  );
}
