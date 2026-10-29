"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAccount, usePublicClient, useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { parseClaimStruct, OnChainClaim, calculateBlockTimeCountdown } from "@/lib/claims";
import { verifyEvidenceUri, VerificationResult, resolveUri } from "@/lib/validation/verify";
import { decodeContractError } from "@/lib/web3/errors";
import { txPhase, txPhaseLabel } from "@/lib/web3/txStatus";
import { formatUsd8, formatAddress } from "@/lib/format";
import {
  formatLtvBps,
  formatPaused,
  formatThreshold,
  ltvStatusLabel,
  parseVaultReading,
  vaultConfig,
  type VaultReading,
} from "@/lib/vaultDisplay";
import {
  Shield,
  CheckCircle2,
  AlertTriangle,
  ArrowLeft,
  Terminal,
  Cpu,
  RefreshCw,
  ExternalLink,
  Clock,
  Lock,
  Loader2,
  FileText,
} from "lucide-react";

export default function ClaimDetailPage({ params }: { params: { id: string } }) {
  const claimId = BigInt(params.id || "1");
  const { isConnected, chainId: currentChainId } = useAccount();
  const effectiveChainId = currentChainId || ACTIVE_CHAIN_ID;
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: effectiveChainId });

  // On-chain claim state
  const [claim, setClaim] = useState<OnChainClaim | null>(null);
  const [blockTimestamp, setBlockTimestamp] = useState<number>(0);
  const [isLoadingClaim, setIsLoadingClaim] = useState<boolean>(true);
  const [claimError, setClaimError] = useState<string | null>(null);

  // Verification results (run automatically with no manual input per Criteria 1, 7)
  const [isVerifyingCaseFile, setIsVerifyingCaseFile] = useState<boolean>(false);
  const [caseFileResult, setCaseFileResult] = useState<VerificationResult | null>(null);

  const [isVerifyingReport, setIsVerifyingReport] = useState<boolean>(false);
  const [reportResult, setReportResult] = useState<VerificationResult | null>(null);

  // Vault state: null until a read succeeds, and again after a failed read (never defaults as live state)
  const limits = useMemo(() => vaultConfig(effectiveChainId), [effectiveChainId]);
  const [vault, setVault] = useState<VaultReading | null>(null);
  const [vaultError, setVaultError] = useState<string | null>(null);
  const [applySimulationPassed, setApplySimulationPassed] = useState<boolean>(false);

  // Write contract for applying claim to DemoVault
  const {
    data: applyTxHash,
    writeContract: writeApply,
    isPending: isApplyPending,
    error: applyWriteError,
    reset: resetApply,
  } = useWriteContract();

  const { data: applyReceipt, isLoading: isApplyConfirming, isSuccess: isApplyConfirmed } =
    useWaitForTransactionReceipt({ hash: applyTxHash });
  const applyPhase = txPhase({
    simulationPassed: applySimulationPassed,
    awaitingSignature: isApplyPending,
    hash: applyTxHash,
    receiptStatus: applyReceipt?.status,
  });

  // Borrow Simulation states
  const [collateralUsdInput, setCollateralUsdInput] = useState<string>("10000");
  const [borrowUsdInput, setBorrowUsdInput] = useState<string>("7000");
  const [isSimulatingBorrow, setIsSimulatingBorrow] = useState<boolean>(false);
  const [borrowOutcome, setBorrowOutcome] = useState<{
    success: boolean;
    message: string;
    errorName?: string;
  } | null>(null);

  // Load claim and vault data from chain
  const loadData = useCallback(async () => {
    if (!publicClient) return;
    try {
      setClaimError(null);
      const [rawClaim, block, maxLtv, paused, lastApplied] = await Promise.all([
        publicClient.readContract({
          address: config.registry.address,
          abi: config.registry.abi,
          functionName: "claim",
          args: [claimId],
        }),
        publicClient.getBlock(),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "maxLtvBps",
        }),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "borrowPaused",
        }),
        publicClient.readContract({
          address: config.vault.address,
          abi: config.vault.abi,
          functionName: "lastAppliedClaimId",
        }),
      ]);

      const parsed = parseClaimStruct(claimId, rawClaim);
      setClaim(parsed);
      setBlockTimestamp(Number(block.timestamp));
      setVault(parseVaultReading(maxLtv, paused, lastApplied));
      setIsLoadingClaim(false);

      // Trigger automatic verification of caseFileURI without manual input
      if (parsed.caseFileURI && parsed.evidenceHash) {
        setIsVerifyingCaseFile(true);
        verifyEvidenceUri(parsed.caseFileURI, parsed.evidenceHash).then((res) => {
          setCaseFileResult(res);
          setIsVerifyingCaseFile(false);
        });
      }

      // If challenged or replay report exists, verify replay report
      if (parsed.replayReportURI && parsed.replayReportHash && parsed.replayReportHash !== "0x0000000000000000000000000000000000000000000000000000000000000000") {
        setIsVerifyingReport(true);
        verifyEvidenceUri(parsed.replayReportURI, parsed.replayReportHash).then((res) => {
          setReportResult(res);
          setIsVerifyingReport(false);
        });
      }
    } catch (err: any) {
      console.error("Failed to load claim detail from RPC:", err);
      setVault(null);
      setClaimError(err?.message || "Failed to load claim from chain");
      setIsLoadingClaim(false);
    }
  }, [publicClient, config, claimId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (isApplyConfirmed) {
      loadData();
    }
  }, [isApplyConfirmed, loadData]);

  // Apply claim to DemoVault: the vault contract decides (eth_call first), then the wallet sends
  async function handleApplyToVault() {
    resetApply();
    setVaultError(null);
    setApplySimulationPassed(false);
    if (!claim || !publicClient) return;

    try {
      await publicClient.simulateContract({
        address: config.vault.address,
        abi: config.vault.abi,
        functionName: "applyClaim",
        args: [claim.id],
      });
    } catch (err: unknown) {
      const decoded = decodeContractError(err);
      setVaultError(`REVERT ${decoded.errorName}: ${decoded.userMessage}`);
      return;
    }
    setApplySimulationPassed(true);
    if (!isConnected) {
      setVaultError("Simulation passed, nothing sent: connect a wallet to send applyClaim.");
      return;
    }

    try {
      writeApply({
        address: config.vault.address,
        abi: config.vault.abi,
        functionName: "applyClaim",
        args: [claim.id],
      });
    } catch (err: any) {
      const decoded = decodeContractError(err);
      setVaultError(decoded.userMessage);
    }
  }

  // Simulate borrow against real MockLendingMarket contract via RPC eth_call
  async function handleTestBorrow() {
    if (!publicClient) return;
    setIsSimulatingBorrow(true);
    setBorrowOutcome(null);

    try {
      // USD values in contract are 8 decimals: $10,000 = 1000000000000n; $7,000 = 700000000000n
      const colUsd = BigInt(Math.floor(Number(collateralUsdInput || "0"))) * 100000000n;
      const amtUsd = BigInt(Math.floor(Number(borrowUsdInput || "0"))) * 100000000n;

      await publicClient.simulateContract({
        address: config.market.address,
        abi: config.market.abi,
        functionName: "borrow",
        args: [colUsd, amtUsd],
      });

      setBorrowOutcome({
        success: true,
        message: `SUCCESS: Borrow of $${Number(borrowUsdInput).toLocaleString()} against $${Number(collateralUsdInput).toLocaleString()} collateral simulated successfully on chain.`,
      });
    } catch (err: any) {
      const decoded = decodeContractError(err);
      setBorrowOutcome({
        success: false,
        errorName: decoded.errorName,
        message: `REVERT: ${decoded.userMessage}`,
      });
    } finally {
      setIsSimulatingBorrow(false);
    }
  }

  const countdown = claim
    ? calculateBlockTimeCountdown(claim.challengeDeadline, blockTimestamp, 0)
    : { text: "—", isExpired: true };

  return (
    <div className="space-y-6 font-mono max-w-5xl">
      {/* Top Back Link */}
      <Link
        href="/claims"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground uppercase tracking-widest transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        <span>BACK_TO_CLAIMS_REGISTRY</span>
      </Link>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              CLAIM_DOSSIER_#{claimId.toString()}
            </h1>
            {claim && (
              <span
                className={`px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                  claim.stateName === "Finalized"
                    ? "border-emerald-500 bg-emerald-950/40 text-emerald-400"
                    : claim.stateName === "Rejected"
                    ? "border-rose-500 bg-rose-950/40 text-rose-400"
                    : claim.stateName === "Challenged"
                    ? "border-[#ea580c] bg-orange-950/40 text-[#ea580c]"
                    : "border-amber-500 bg-amber-950/40 text-amber-400"
                }`}
              >
                [{claim.stateName}]
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1 uppercase break-all">
            REGISTRY: {formatAddress(config.registry.address)} &bull; ATTESTER:{" "}
            {claim ? formatAddress(claim.attester) : "..."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadData()}
            title="Refresh claim"
            className="p-2 border border-border bg-card hover:border-foreground text-muted-foreground hover:text-foreground transition-all"
          >
            <RefreshCw className={`h-4 w-4 ${isLoadingClaim ? "animate-spin text-[#ea580c]" : ""}`} />
          </button>
          <button
            disabled={isApplyPending || isApplyConfirming || !claim}
            onClick={handleApplyToVault}
            className="w-full sm:w-auto px-4 py-2 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground shrink-0 disabled:opacity-50"
          >
            {isApplyPending || isApplyConfirming ? "APPLYING..." : "APPLY_TO_DEMOVAULT"}
          </button>
        </div>
      </div>

      {applyPhase !== "idle" && (
        <div
          className={`p-3 border-2 text-xs flex items-center justify-between ${
            applyPhase === "mined-reverted"
              ? "border-red-500 bg-red-950/40 text-red-300"
              : "border-emerald-500 bg-emerald-950/40 text-emerald-300"
          }`}
        >
          <span>{applyTxHash ? `TX_HASH: ${applyTxHash}` : "APPLY_CLAIM"}</span>
          <span className="font-bold uppercase text-[10px]">{txPhaseLabel(applyPhase)}</span>
        </div>
      )}

      {(vaultError || applyWriteError) && (
        <div className="p-3 border-2 border-red-500 bg-red-950/40 text-red-300 text-xs flex items-center justify-between">
          <span>{vaultError || decodeContractError(applyWriteError).userMessage}</span>
          <button onClick={() => setVaultError(null)} className="text-red-400 font-bold uppercase text-[10px]">
            [DISMISS]
          </button>
        </div>
      )}

      {claimError && (
        <div className="p-4 border-2 border-red-500 bg-red-950/40 text-red-300 text-xs space-y-1">
          <div className="flex items-center gap-2 font-bold uppercase">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            RPC_FETCH_ERROR
          </div>
          <p className="text-[11px] uppercase">{claimError}</p>
        </div>
      )}

      {/* Main Claim Metadata Grid */}
      {claim && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-card border-2 border-border p-4 space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-widest block">
              // CLAIMED_BAD_DEBT
            </span>
            <p className="text-2xl font-black text-foreground">
              {formatUsd8(claim.claimedResidualBadDebt)}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              REDUCED_LTV_TRIGGER: {formatThreshold(limits.ltvThresholdUsd8)}
            </span>
          </div>

          <div className="bg-card border-2 border-border p-4 space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-widest block">
              // CHALLENGE_DEADLINE
            </span>
            <p className="text-2xl font-black text-[#ea580c] flex items-center gap-2">
              <Clock className="h-5 w-5" />
              {countdown.text}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              STATUS: {countdown.isExpired ? "WINDOW_CLOSED" : "DISPUTE_OPEN"}
            </span>
          </div>

          <div className="bg-card border-2 border-border p-4 space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-widest block">
              // MARKET_ID_TOPOLOGY
            </span>
            <p className="text-xs font-bold text-foreground font-mono break-all pt-1">
              {claim.marketId}
            </p>
            <span className="text-[10px] text-emerald-400 font-bold uppercase block pt-1">
              AAVE_V3_ETH_WETH_STABLE
            </span>
          </div>
        </div>
      )}

      {/* Evidence Integrity Verification Box (Criterion 1 & 7) */}
      <div className="border-2 border-border bg-card p-6 space-y-5">
        <div className="flex items-center justify-between border-b-2 border-border pb-3">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-[#ea580c]" />
            <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">
              IN_BROWSER_EVIDENCE_HASH_VERIFICATION (§19.3)
            </h3>
          </div>
          {isVerifyingCaseFile ? (
            <span className="text-[10px] text-[#ea580c] font-bold flex items-center gap-1 uppercase">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> HASHING_RAW_BYTES...
            </span>
          ) : caseFileResult?.valid ? (
            <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1 uppercase border border-emerald-500/40 bg-emerald-950/40 px-2 py-0.5">
              <CheckCircle2 className="h-3.5 w-3.5" /> KECCAK-256_INTEGRITY_VERIFIED
            </span>
          ) : (
            <span className="text-[10px] text-rose-400 font-bold flex items-center gap-1 uppercase border border-rose-500/40 bg-rose-950/40 px-2 py-0.5">
              <AlertTriangle className="h-3.5 w-3.5" /> INTEGRITY_CHECK_FAILED
            </span>
          )}
        </div>

        <div className="space-y-4 text-xs">
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
              CASE_FILE_URI (READ_ONLY_IMMUTABLE_SOURCE)
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={claim?.caseFileURI || ""}
                className="w-full bg-secondary border border-border p-2 text-xs text-foreground font-mono select-all cursor-text outline-none"
              />
              {claim?.caseFileURI && (
                <a
                  href={resolveUri(claim.caseFileURI)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 border border-border bg-background hover:border-foreground text-muted-foreground hover:text-foreground"
                  title="Open raw case file bytes"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                EXPECTED_ON_CHAIN_EVIDENCE_HASH
              </label>
              <div className="p-2 bg-secondary border border-border font-mono text-[11px] break-all select-all text-foreground">
                {claim?.evidenceHash || "—"}
              </div>
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                BROWSER_COMPUTED_KECCAK-256_HASH
              </label>
              <div
                className={`p-2 border font-mono text-[11px] break-all select-all ${
                  caseFileResult?.valid
                    ? "bg-emerald-950/30 border-emerald-500 text-emerald-300 font-bold"
                    : "bg-rose-950/30 border-rose-500 text-rose-300"
                }`}
              >
                {caseFileResult?.computedHash || (isVerifyingCaseFile ? "COMPUTING..." : "—")}
              </div>
            </div>
          </div>

          {caseFileResult?.error && (
            <div className="p-3 border border-rose-500 bg-rose-950/40 text-rose-300 text-[11px]">
              ERROR: {caseFileResult.error}
            </div>
          )}

          {caseFileResult?.rawJson && (
            <div className="border border-border bg-background p-3 space-y-1">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider block">
                EXTRACTED_CASE_FILE_METADATA:
              </span>
              <pre className="text-[10px] text-muted-foreground overflow-x-auto max-h-32">
                {JSON.stringify(caseFileResult.rawJson, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>

      {/* If challenged, show Replay Report Verification */}
      {claim && (claim.stateName === "Challenged" || claim.replayReportURI) && (
        <div className="border-2 border-[#ea580c] bg-card p-6 space-y-4">
          <div className="flex items-center justify-between border-b-2 border-border pb-3">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-[#ea580c]" />
              <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">
                DISPUTE_REPLAY_REPORT_INTEGRITY (§19.3)
              </h3>
            </div>
            {isVerifyingReport ? (
              <span className="text-[10px] text-[#ea580c] font-bold flex items-center gap-1 uppercase">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> VERIFYING_REPORT...
              </span>
            ) : reportResult?.valid ? (
              <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1 uppercase border border-emerald-500/40 bg-emerald-950/40 px-2 py-0.5">
                <CheckCircle2 className="h-3.5 w-3.5" /> REPLAY_REPORT_HASH_MATCH
              </span>
            ) : (
              <span className="text-[10px] text-rose-400 font-bold uppercase border border-rose-500/40 px-2 py-0.5">
                REPORT_MISMATCH
              </span>
            )}
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-[10px] text-muted-foreground uppercase block mb-1">
                DISPUTE_REASON: {claim.reasonName}
              </span>
              <span className="text-[10px] text-muted-foreground uppercase block">
                ASSERTED_COUNTER_DEBT: {formatUsd8(claim.counterResidualBadDebt)}
              </span>
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-widest block mb-1">
                REPLAY_REPORT_URI (READ_ONLY)
              </label>
              <input
                type="text"
                readOnly
                value={claim.replayReportURI}
                className="w-full bg-secondary border border-border p-2 text-xs text-foreground font-mono select-all outline-none"
              />
            </div>
          </div>
        </div>
      )}

      {/* DemoVault & Lending Market Controls (Task F4) */}
      <div className="border-2 border-border bg-card p-6 space-y-6">
        <div className="flex items-center justify-between border-b-2 border-border pb-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-[#ea580c]" />
            <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">
              DEMOVAULT_CIRCUIT_BREAKER_DEFENSE (§19.4)
            </h3>
          </div>
          <span className="text-[10px] text-muted-foreground uppercase">
            LAST_APPLIED_CLAIM: {vault === null ? "UNAVAILABLE" : `#${vault.lastAppliedClaimId.toString()}`}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="p-4 bg-secondary border border-border">
            <span className="text-[10px] text-muted-foreground uppercase block">ACTIVE_MAX_LTV</span>
            <p className="text-2xl font-black text-[#ea580c]">
              {formatLtvBps(vault?.maxLtvBps ?? null)}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              {ltvStatusLabel(vault?.maxLtvBps ?? null, limits)}
            </span>
          </div>

          <div className="p-4 bg-secondary border border-border">
            <span className="text-[10px] text-muted-foreground uppercase block">BORROW_PAUSED</span>
            <p className="text-2xl font-black text-foreground">
              {formatPaused(vault?.borrowPaused ?? null, "HALTED", "OPERATIONAL")}
            </p>
            <span className="text-[10px] text-muted-foreground uppercase">
              CIRCUIT_BREAKER_TRIGGER: {formatThreshold(limits.pauseThresholdUsd8)}
            </span>
          </div>
        </div>

        {/* Live On-Chain Borrow Simulator (F4) */}
        <div className="border border-border p-4 bg-muted/20 space-y-4">
          <span className="text-xs font-bold uppercase tracking-wider text-foreground block">
            // SIMULATE_ON_CHAIN_BORROW (MOCKLENDINGMARKET.BORROW)
          </span>
          <p className="text-[11px] text-muted-foreground uppercase">
            Executes a real <code>eth_call</code> against <code>MockLendingMarket</code> to simulate strict LTV bounds.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] text-muted-foreground uppercase block mb-1">
                COLLATERAL (USD)
              </label>
              <input
                type="number"
                value={collateralUsdInput}
                onChange={(e) => setCollateralUsdInput(e.target.value)}
                className="w-full bg-background border border-border p-2 text-xs font-mono text-foreground focus:border-foreground outline-none"
              />
            </div>

            <div>
              <label className="text-[10px] text-muted-foreground uppercase block mb-1">
                BORROW_AMOUNT (USD)
              </label>
              <input
                type="number"
                value={borrowUsdInput}
                onChange={(e) => setBorrowUsdInput(e.target.value)}
                className="w-full bg-background border border-border p-2 text-xs font-mono text-foreground focus:border-foreground outline-none"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-[10px] text-muted-foreground uppercase">
              CALCULATED_LTV:{" "}
              {Number(collateralUsdInput) > 0
                ? ((Number(borrowUsdInput) / Number(collateralUsdInput)) * 100).toFixed(2)
                : 0}
              %
            </span>

            <button
              type="button"
              disabled={isSimulatingBorrow}
              onClick={handleTestBorrow}
              className="px-4 py-2 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground disabled:opacity-50"
            >
              {isSimulatingBorrow ? "SIMULATING_ETH_CALL..." : "EXECUTE_BORROW_SIMULATION"}
            </button>
          </div>

          {borrowOutcome && (
            <div
              className={`p-3 border-2 text-xs font-mono ${
                borrowOutcome.success
                  ? "border-emerald-500 bg-emerald-950/40 text-emerald-300"
                  : "border-rose-500 bg-rose-950/40 text-rose-300"
              }`}
            >
              {borrowOutcome.message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
