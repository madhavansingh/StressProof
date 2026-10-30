"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { runStressTest, fetchDatasets } from "@/lib/api/client";
import { formatUsd8, formatAddress } from "@/lib/format";
import { useAccount, usePublicClient, useWriteContract } from "wagmi";
import { useTxReceipt } from "@/lib/web3/useTxReceipt";
import { getContractConfig, ACTIVE_CHAIN_ID } from "@/lib/contracts";
import { formatEther, type Abi, type Hex } from "viem";
import { useQueryClient } from "@tanstack/react-query";
import { checkWriteReadiness, describeWalletError } from "@/lib/web3/walletPolicy";
import { buildPostClaimRequest, settlePublishReceipt, verifyRegistryBeforeSigning } from "@/lib/web3/postClaimRequest";
import { isConfiguredChainId } from "@/lib/web3/wagmi";
import {
  Zap,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Terminal,
  Shield,
  Loader2,
  FileText,
  ExternalLink,
  Info,
} from "lucide-react";

export default function StressPage() {
  // The account and chain come from the authorized wallet session; the same account signs.
  const { isConnected, address, chainId: currentChainId } = useAccount();
  const effectiveChainId = ACTIVE_CHAIN_ID; // reads always use the deployment chain, never the wallet's chain
  const config = useMemo(() => getContractConfig(effectiveChainId), [effectiveChainId]);
  const publicClient = usePublicClient({ chainId: ACTIVE_CHAIN_ID });
  const queryClient = useQueryClient();
  const [isPreparing, setIsPreparing] = useState<boolean>(false);

  const [datasets, setDatasets] = useState<any[]>([
    {
      datasetId: "weth-stable-fixture-v1",
      network: "ethereum-mainnet-fork",
      forkBlock: 19000000,
      counts: { real: 0, synthetic: 5 },
      dataClass: "SYNTHETIC",
    },
  ]);
  const [selectedDataset, setSelectedDataset] = useState<string>("weth-stable-fixture-v1");
  const [shockBps, setShockBps] = useState<number>(-3000);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [publishedClaimId, setPublishedClaimId] = useState<string | null>(null);
  const [publishFailure, setPublishFailure] = useState<string | null>(null);

  // Contract write hook for postClaim
  const {
    data: postTxHash,
    writeContract: writePostClaim,
    isPending: isPostPending,
    error: postWriteError,
    reset: resetPost,
  } = useWriteContract();

  // Settles reverted receipts too (wagmi's receipt hook throws on them and would leave this pending).
  const { outcome: postOutcome, isConfirming: isPostConfirming } = useTxReceipt(postTxHash, ACTIVE_CHAIN_ID);
  const receipt = postOutcome?.receipt;

  useEffect(() => {
    fetchDatasets()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setDatasets(data);
          setSelectedDataset(data[0].datasetId);
        }
      })
      .catch((err) => {
        console.warn("Could not load dynamic datasets:", err);
      });
  }, []);

  // A different account or chain invalidates any half-finished publish attempt.
  useEffect(() => {
    resetPost();
    setPublishFailure(null);
    setPublishedClaimId(null);
  }, [address, currentChainId, resetPost]);

  // When the postClaim receipt confirms, take the claim id from the registry's ClaimPosted event
  useEffect(() => {
    if (!receipt || !result) return;
    try {
      const posted = settlePublishReceipt(receipt, config.registry.address, result.evidenceHash, () => {
        // Refresh claim and vault reads; the settled receipt itself is final.
        queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "stressproof-tx-receipt" });
      });
      if (posted.ok) {
        setPublishedClaimId(posted.claimId.toString());
        setPublishFailure(null);
      } else {
        setPublishedClaimId(null);
        setPublishFailure(postOutcome?.revertReason ? `${posted.reason}: ${postOutcome.revertReason}` : posted.reason);
      }
    } catch (err) {
      console.warn("Could not decode the postClaim receipt:", err);
      setPublishedClaimId(null);
      setPublishFailure("Could not decode the transaction receipt.");
    }
  }, [receipt, postOutcome, config, result, queryClient]);

  const activeDataset = datasets.find((d) => d.datasetId === selectedDataset) || datasets[0];
  const activeDataClass = result?.dataClass || activeDataset?.dataClass || "SYNTHETIC";

  async function handleRun() {
    setLoading(true);
    setError(null);
    setPublishedClaimId(null);
    setPublishFailure(null);
    resetPost();

    try {
      const res = await runStressTest(selectedDataset, shockBps);
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Failed to execute stress test");
    } finally {
      setLoading(false);
    }
  }

  async function handlePublishOnChain() {
    if (!result) return;
    resetPost();
    setPublishedClaimId(null);
    setPublishFailure(null);
    setError(null);

    // 1. Connected account, recorded deployment, wallet on the deployment chain.
    const ready = checkWriteReadiness({
      isConnected,
      address,
      walletChainId: currentChainId,
      targetChainId: ACTIVE_CHAIN_ID,
      contractAddress: config.registry.address,
    });
    if (!ready.ok) {
      setError(ready.message);
      return;
    }
    if (!isConfiguredChainId(ready.chainId) || !publicClient) {
      setError(`Nothing sent: chain ${ready.chainId} is not configured in this build.`);
      return;
    }
    const chainId = ready.chainId;

    // 2. The exact call: registry from the deployment file, the deployment's bond, pinned chain.
    let request;
    try {
      request = buildPostClaimRequest({
        chainId,
        registry: config.registry.address,
        marketId: config.marketId,
        bondWei: config.bondWei,
        residualBadDebtUsd8: String(result.results.residualBadDebtUsd8),
        evidenceHash: String(result.evidenceHash),
        caseFileURI: String(result.caseFileURI),
      });
    } catch (err: unknown) {
      setError(`Nothing sent: ${err instanceof Error ? err.message : "invalid claim data"}.`);
      return;
    }

    // 3. On chain, before the signature request: code at the registry and BOND() == value sent.
    setIsPreparing(true);
    const check = await verifyRegistryBeforeSigning(
      {
        getCode: (args) => publicClient.getCode(args),
        readContract: (args) => publicClient.readContract(args),
      },
      request.address,
      config.registry.abi as Abi,
      request.value
    );
    setIsPreparing(false);
    if (!check.ok) {
      setError(check.reason);
      return;
    }

    // 4. Signature request from the connected wallet; wagmi refuses if its chain differs from chainId.
    writePostClaim({
      chainId,
      address: request.address,
      abi: config.registry.abi,
      functionName: request.functionName,
      args: [request.args[0], request.args[1], request.args[2] as Hex, request.args[3]],
      value: request.value,
    });
  }

  return (
    <div className="max-w-5xl space-y-6 font-mono">
      {/* Required Data-Class Banner (§10.4 & §19.1) */}
      {activeDataClass !== "REAL" && (
        <div className="w-full bg-amber-950/80 border-2 border-amber-500 text-amber-200 px-4 py-2.5 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
            <span>
              <strong className="text-amber-100 uppercase">
                {activeDataClass === "SYNTHETIC" ? "SYNTHETIC_DATASET_BANNER:" : "MIXED_DATASET_BANNER:"}
              </strong>{" "}
              {activeDataClass === "SYNTHETIC"
                ? "Synthetic dataset — does not describe real Aave"
                : "Synthetic accounts included — results do not describe real Aave"}
            </span>
          </div>
          <span className="text-[10px] uppercase font-bold border border-amber-400/40 px-2 py-0.5 bg-amber-900/50">
            MOCK MARKET
          </span>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-border pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground uppercase break-words">
              STRESS_SIMULATION_ENGINE
            </h1>
            <span className="px-2 py-0.5 border border-[#ea580c] bg-orange-950/40 text-[#ea580c] text-[10px] font-bold uppercase tracking-wider shrink-0">
              STATIC_REPLAYER_V1
            </span>
            <span className="px-2 py-0.5 border border-border bg-secondary text-foreground text-[10px] font-bold uppercase tracking-wider shrink-0">
              MOCK MARKET
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
          className="w-full py-3 bg-[#ea580c] text-white text-xs font-bold uppercase tracking-wider hover:bg-foreground hover:text-background transition-all border-2 border-[#ea580c] shadow-[3px_3px_0px_0px_hsl(var(--border))] disabled:opacity-50"
        >
          {loading ? "EXECUTING_DETERMINISTIC_REPLAYER..." : "RUN_STRESS_SIMULATION"}
        </button>
      </div>

      {error && (
        <div className="p-3 border-2 border-rose-500 bg-rose-950/40 text-rose-300 text-xs uppercase">
          ERROR: {error}
        </div>
      )}

      {/* Results Matrix: Exactly the 4 Spec Metrics (Task F9) */}
      {result && (
        <div className="bg-card border-2 border-border p-5 space-y-5">
          <div className="flex items-center justify-between border-b-2 border-border pb-3">
            <span className="text-xs font-bold uppercase tracking-widest text-foreground">
              // REPLAYER_EXECUTION_OUTPUT
            </span>
            <span className="text-[10px] text-emerald-400 font-bold uppercase">
              [DETERMINISTIC_PASS_COMPLETE]
            </span>
          </div>

          {/* 4 Exact Spec Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                liquidatableAccounts
              </span>
              <span className="text-2xl font-bold text-foreground">
                {result.results.liquidatableAccounts}
              </span>
            </div>

            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                debtAtRiskUsd8
              </span>
              <span className="text-2xl font-bold text-foreground">
                {formatUsd8(result.results.debtAtRiskUsd8)}
              </span>
            </div>

            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                liquidationVolumeUsd8
              </span>
              <span className="text-2xl font-bold text-foreground">
                {formatUsd8(result.results.liquidationVolumeUsd8)}
              </span>
            </div>

            <div className="p-3 border border-border bg-background">
              <span className="text-[10px] text-muted-foreground uppercase block">
                residualBadDebtUsd8
              </span>
              <span className="text-2xl font-bold text-[#ea580c]">
                {formatUsd8(result.results.residualBadDebtUsd8)}
              </span>
            </div>
          </div>

          {/* Case File URI and Keccak-256 Hash Display (Task F9 & F16) */}
          <div className="space-y-3 pt-2 border-t border-border">
            <div className="p-3 border border-border bg-background space-y-1">
              <span className="text-[10px] text-muted-foreground uppercase block">
                EVIDENCE_KECCAK256_HASH
              </span>
              <span className="text-xs text-foreground font-mono break-all font-bold">
                {result.evidenceHash}
              </span>
            </div>

            <div className="p-3 border border-border bg-background space-y-1">
              <span className="text-[10px] text-muted-foreground uppercase block">
                CASE_FILE_URI
              </span>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-foreground font-mono break-all">
                  {result.caseFileURI}
                </span>
                <a
                  href={result.caseFileURI}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 border border-border hover:border-foreground text-muted-foreground hover:text-foreground shrink-0"
                  title="Open raw case-file JSON"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </div>
            </div>
          </div>

          {/* On-Chain Publish Claim Button (Task F7) */}
          <div className="pt-2">
            <button
              disabled={isPreparing || isPostPending || isPostConfirming}
              onClick={handlePublishOnChain}
              className="w-full py-3 bg-foreground text-background text-xs font-bold uppercase tracking-wider hover:bg-[#ea580c] hover:text-white transition-all border border-foreground disabled:opacity-50"
            >
              {isPreparing
                ? "CHECKING_REGISTRY_AND_BOND..."
                : isPostPending
                  ? "CONFIRM_IN_WALLET..."
                  : isPostConfirming
                    ? "WAITING_FOR_RECEIPT..."
                    : `PUBLISH_BONDED_CLAIM (STAKE ${formatEther(config.bondWei)} ETH)`}
            </button>
          </div>

          {postTxHash && (
            <div
              className={`p-4 border-2 text-xs space-y-2 ${
                publishFailure
                  ? "border-rose-500 bg-rose-950/40 text-rose-300"
                  : "border-emerald-500 bg-emerald-950/40 text-emerald-300"
              }`}
            >
              <div className="flex items-center gap-2 font-bold uppercase">
                {publishFailure ? (
                  <AlertTriangle className="h-4 w-4 text-rose-400" />
                ) : publishedClaimId ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                )}
                <span>
                  {publishFailure
                    ? "CLAIM_NOT_CONFIRMED"
                    : publishedClaimId
                      ? "CLAIM_POSTED_ON_CHAIN"
                      : "TRANSACTION_CONFIRMING_ON_CHAIN"}
                </span>
              </div>
              {publishFailure && <p className="uppercase">{publishFailure}</p>}
              <p className="break-all font-mono">
                TX_HASH: <code>{postTxHash}</code>
              </p>
              {publishedClaimId && (
                <div className="pt-2 flex items-center justify-between border-t border-emerald-500/30">
                  <span className="font-bold uppercase text-emerald-200">
                    CLAIM_ID: #{publishedClaimId}
                  </span>
                  <Link
                    href={`/claims/${publishedClaimId}`}
                    className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold uppercase text-[10px] tracking-wider"
                  >
                    VIEW_CLAIM_DOSSIER &rarr;
                  </Link>
                </div>
              )}
            </div>
          )}

          {postWriteError && (
            <div className="p-3 border-2 border-rose-500 bg-rose-950/40 text-rose-300 text-xs uppercase">
              ERROR_POSTING_CLAIM: {describeWalletError(postWriteError).message}
            </div>
          )}
        </div>
      )}

      {/* §10.4 Stated Assumptions Panel (Word for Word per Spec) */}
      <div className="border-2 border-border bg-card p-6 space-y-4">
        <div className="flex items-center gap-2 border-b-2 border-border pb-3">
          <Info className="h-4 w-4 text-[#ea580c]" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">
            STATED_ASSUMPTIONS (§10.4 SPECIFICATION)
          </h3>
        </div>

        <ol className="list-decimal list-inside space-y-2 text-xs text-muted-foreground uppercase leading-relaxed">
          <li>
            Each account&apos;s only collateral is WETH, the shocked asset. Debt is the account&apos;s total debt in USD at block N and is not shocked.
          </li>
          <li>
            There is one liquidation pass, and it liquidates fully (close factor 100%) at the shocked oracle price. Aave v3 itself allows only 50% per liquidation in some cases (health factor above 0.95 and position above a dust threshold), so this is a simplification.
          </li>
          <li>
            The model has no slippage or price impact, no limit on liquidator capacity or gas, no delay, no liquidation protocol fee and no interest accrual after block N.
          </li>
          <li>
            It is not a multi-round cascade. It is a &quot;liquidation simulation&quot;.
          </li>
          <li>
            The result is an estimate under these assumptions, not a forecast of real Aave losses. It covers the filtered subset only, not the whole market.
          </li>
          <li>
            &quot;Residual bad debt&quot; here is a model output. It is related to, but not the same thing as, Aave v3.3&apos;s on-chain deficit accounting.
          </li>
        </ol>
      </div>
    </div>
  );
}
