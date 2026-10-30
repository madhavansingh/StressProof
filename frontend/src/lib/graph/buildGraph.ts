import { formatUnits } from "viem";
import { formatBps, formatUsd8 } from "@/lib/format";
import type {
  AccountOutcome,
  ConsistencyCheck,
  DetailRow,
  ExposureGraph,
  GraphCaseFile,
  GraphClaimRef,
  GraphEdge,
  GraphNode,
  ReplayOutputRow,
  SnapshotAccount,
} from "./types";

export interface BuildGraphInput {
  evidenceHash: string;
  outputs: ReplayOutputRow[];
  caseFile: GraphCaseFile;
  claims?: GraphClaimRef[]; // claims already known to commit to this evidenceHash
}

export const nodeIds = {
  market: (marketId: string) => `market:${marketId}`,
  collateral: (symbol: string) => `asset:collateral:${symbol}`,
  debt: () => "asset:debt:stablecoins",
  account: (id: string) => `account:${id}`,
  evidence: (hash: string) => `evidence:${hash}`,
  claim: (id: string) => `claim:${id}`,
};

export function accountOutcome(row: ReplayOutputRow): AccountOutcome {
  if (BigInt(row.residualUsd8) > BigInt(0)) return "badDebt";
  return row.liquidatable ? "liquidated" : "safe";
}

const OUTCOME_LABEL: Record<AccountOutcome, string> = {
  safe: "Not liquidatable",
  liquidated: "Liquidatable, debt covered",
  badDebt: "Liquidatable, residual bad debt",
};

export function outcomeLabel(outcome: AccountOutcome): string {
  return OUTCOME_LABEL[outcome];
}

function sum(values: string[]): bigint {
  return values.reduce((acc, v) => acc + BigInt(v), BigInt(0));
}

function contextNodes(hash: string, cf: GraphCaseFile, accountCount: number): GraphNode[] {
  const synthetic = cf.dataClass === "SYNTHETIC";
  const c = cf.collateral;
  return [
    {
      id: nodeIds.evidence(hash),
      kind: "evidence",
      label: `Case file ${hash.slice(0, 10)}…`,
      synthetic,
      details: [
        { label: "Evidence hash", value: hash, source: "caseFile" },
        { label: "Data class", value: cf.dataClass, source: "caseFile" },
        { label: "Dataset", value: cf.datasetId, source: "caseFile" },
        { label: "Network", value: cf.network, source: "caseFile" },
        { label: "Model", value: cf.modelId, source: "caseFile" },
        { label: "Scenario", value: `${cf.scenario.asset} ${formatBps(cf.scenario.shockBps)}`, source: "caseFile" },
      ],
    },
    {
      id: nodeIds.market(cf.marketId),
      kind: "market",
      label: cf.marketId,
      synthetic,
      details: [
        { label: "Market id", value: cf.marketId, source: "caseFile" },
        { label: "Accounts in snapshot", value: String(accountCount), source: "caseFile" },
        { label: "Liquidatable accounts", value: String(cf.results.liquidatableAccounts), source: "caseFile" },
        { label: "Residual bad debt", value: formatUsd8(cf.results.residualBadDebtUsd8), source: "caseFile" },
        { label: "Liquidation volume", value: formatUsd8(cf.results.liquidationVolumeUsd8), source: "caseFile" },
        { label: "Debt at risk", value: formatUsd8(cf.results.debtAtRiskUsd8), source: "caseFile" },
      ],
    },
    {
      id: nodeIds.collateral(c.symbol),
      kind: "collateralAsset",
      label: `${c.symbol} collateral`,
      synthetic,
      details: [
        { label: "Asset", value: c.symbol, source: "caseFile" },
        { label: "Pre-shock price", value: formatUsd8(c.priceUsd8), source: "caseFile" },
        { label: "Shock", value: formatBps(cf.scenario.shockBps), source: "caseFile" },
        { label: "Liquidation threshold", value: formatBps(c.ltBps), source: "caseFile" },
        { label: "Liquidation bonus", value: formatBps(c.bonusBps), source: "caseFile" },
      ],
    },
    {
      id: nodeIds.debt(),
      kind: "debtAsset",
      label: `Stablecoin debt (${cf.stablecoins.join(", ")})`,
      synthetic,
      details: [
        { label: "Allowlist", value: cf.stablecoins.join(", "), source: "caseFile" },
        { label: "Per-token split", value: "Not recorded: debt is one USD total per account", source: "caseFile" },
      ],
    },
  ];
}

function accountDetails(row: ReplayOutputRow, snap: SnapshotAccount | undefined, cf: GraphCaseFile): DetailRow[] {
  const position: DetailRow[] = snap
    ? [
        { label: "Origin", value: snap.origin, source: "caseFile" },
        {
          label: "Collateral",
          value: `${formatUnits(BigInt(snap.collateralAmount), cf.collateral.decimals)} ${cf.collateral.symbol}`,
          source: "caseFile",
        },
        { label: "Debt", value: formatUsd8(snap.debtUsd8), source: "caseFile" },
      ]
    : [{ label: "Snapshot position", value: "Missing from the case file", source: "caseFile" }];
  return [
    { label: "Account id", value: row.id, source: "replayOutput" },
    ...position,
    { label: "Outcome", value: outcomeLabel(accountOutcome(row)), source: "replayOutput" },
    { label: "Collateral value after shock", value: formatUsd8(row.collateralValueUsd8), source: "replayOutput" },
    { label: "Liquidatable", value: row.liquidatable ? "Yes" : "No", source: "replayOutput" },
    { label: "Repaid by liquidation", value: formatUsd8(row.repaidUsd8), source: "replayOutput" },
    { label: "Residual bad debt", value: formatUsd8(row.residualUsd8), source: "replayOutput" },
  ];
}

function accountParts(input: BuildGraphInput, snapshots: Map<string, SnapshotAccount>) {
  const { caseFile: cf } = input;
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  for (const row of input.outputs) {
    const snap = snapshots.get(row.id);
    const id = nodeIds.account(row.id);
    nodes.push({
      id,
      kind: "account",
      label: row.id,
      outcome: accountOutcome(row),
      synthetic: snap ? snap.origin === "synthetic" : cf.dataClass === "SYNTHETIC",
      details: accountDetails(row, snap, cf),
    });
    if (!snap) continue; // no position data: draw no exposure edges rather than invent them
    if (BigInt(snap.collateralAmount) > BigInt(0)) {
      edges.push({
        id: `${id}->collateral`,
        kind: "collateral",
        source: id,
        target: nodeIds.collateral(cf.collateral.symbol),
        label: `${formatUnits(BigInt(snap.collateralAmount), cf.collateral.decimals)} ${cf.collateral.symbol}`,
        dataSource: "caseFile",
      });
    }
    if (BigInt(snap.debtUsd8) > BigInt(0)) {
      edges.push({
        id: `${id}->debt`,
        kind: "debt",
        source: id,
        target: nodeIds.debt(),
        label: formatUsd8(snap.debtUsd8),
        dataSource: "caseFile",
      });
    }
  }
  return { nodes, edges };
}

function claimParts(input: BuildGraphInput) {
  const hash = input.evidenceHash.toLowerCase();
  const seen = new Set<string>();
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  for (const claim of input.claims ?? []) {
    if (seen.has(claim.id)) continue;
    seen.add(claim.id);
    const id = nodeIds.claim(claim.id);
    nodes.push({
      id,
      kind: "claim",
      label: `Claim #${claim.id}`,
      synthetic: false,
      details: [
        { label: "Claim id", value: claim.id, source: "onChain" },
        { label: "State", value: claim.stateName, source: "onChain" },
        { label: "Attester", value: claim.attester, source: "onChain" },
        { label: "Claimed residual bad debt", value: formatUsd8(claim.claimedResidualBadDebtUsd8), source: "onChain" },
      ],
    });
    edges.push({
      id: `${id}->evidence`,
      kind: "attests",
      source: id,
      target: nodeIds.evidence(hash),
      label: "commits to evidenceHash",
      dataSource: "onChain",
    });
  }
  return { nodes, edges };
}

/** Compare per-account replay outputs with the totals the case file commits to. */
export function consistencyChecks(outputs: ReplayOutputRow[], cf: GraphCaseFile): ConsistencyCheck[] {
  const debtById = new Map(cf.accounts.map((a) => [a.id, a.debtUsd8]));
  const liquidatable = outputs.filter((o) => o.liquidatable);
  const rows: Array<[string, bigint, string, (v: bigint) => string]> = [
    ["Liquidatable accounts", BigInt(liquidatable.length), String(cf.results.liquidatableAccounts), String],
    ["Residual bad debt", sum(outputs.map((o) => o.residualUsd8)), cf.results.residualBadDebtUsd8, formatUsd8],
    ["Liquidation volume", sum(outputs.map((o) => o.repaidUsd8)), cf.results.liquidationVolumeUsd8, formatUsd8],
    ["Debt at risk", sum(liquidatable.map((o) => debtById.get(o.id) ?? "0")), cf.results.debtAtRiskUsd8, formatUsd8],
  ];
  return rows.map(([name, computed, committed, fmt]) => ({
    name,
    fromOutputs: fmt(computed),
    fromCaseFile: fmt(BigInt(committed)),
    matches: computed === BigInt(committed),
  }));
}

function idWarnings(outputs: ReplayOutputRow[], cf: GraphCaseFile): string[] {
  const outputIds = new Set(outputs.map((o) => o.id));
  const snapshotIds = new Set(cf.accounts.map((a) => a.id));
  const warnings: string[] = [];
  const noSnapshot = outputs.filter((o) => !snapshotIds.has(o.id)).map((o) => o.id);
  const noOutput = cf.accounts.filter((a) => !outputIds.has(a.id)).map((a) => a.id);
  if (noSnapshot.length > 0) {
    warnings.push(`${noSnapshot.length} replay output account(s) have no case-file position: ${noSnapshot.slice(0, 5).join(", ")}`);
  }
  if (noOutput.length > 0) {
    warnings.push(`${noOutput.length} case-file account(s) have no replay output: ${noOutput.slice(0, 5).join(", ")}`);
  }
  if (snapshotIds.size !== cf.accounts.length) warnings.push("The case file lists an account id more than once");
  return warnings;
}

/**
 * Build the exposure graph. Every node and edge comes from the replay outputs, the case file or an on-chain
 * claim; nothing is inferred. There are no account-to-account edges because the data records none.
 */
export function buildExposureGraph(input: BuildGraphInput): ExposureGraph {
  const { caseFile: cf } = input;
  const hash = input.evidenceHash.toLowerCase();
  const snapshots = new Map(cf.accounts.map((a) => [a.id, a]));
  const accounts = accountParts(input, snapshots);
  const claims = claimParts(input);
  const marketId = nodeIds.market(cf.marketId);

  const edges: GraphEdge[] = [
    ...claims.edges,
    { id: "evidence->market", kind: "evidenceFor", source: nodeIds.evidence(hash), target: marketId, label: "replayed market", dataSource: "caseFile" },
    { id: "market->collateral", kind: "listsAsset", source: marketId, target: nodeIds.collateral(cf.collateral.symbol), label: "collateral asset", dataSource: "caseFile" },
    { id: "market->debt", kind: "listsAsset", source: marketId, target: nodeIds.debt(), label: "debt assets", dataSource: "caseFile" },
    ...accounts.edges,
  ];

  return {
    evidenceHash: hash,
    dataClass: cf.dataClass,
    nodes: [...claims.nodes, ...contextNodes(hash, cf, cf.accounts.length), ...accounts.nodes],
    edges,
    checks: consistencyChecks(input.outputs, cf),
    warnings: idWarnings(input.outputs, cf),
  };
}
