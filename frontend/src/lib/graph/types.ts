/**
 * Types for the WP-6 exposure graph. The graph is a read-only view of deterministic replay outputs and the
 * hash-verified case file they came from. It informs; it never decides a verdict.
 */

/** One line of data/replay_outputs/<evidenceHash>.jsonl (plan §8.5). USD values are 8-decimal integer strings. */
export interface ReplayOutputRow {
  id: string;
  collateralValueUsd8: string;
  repaidUsd8: string;
  residualUsd8: string;
  liquidatable: boolean;
}

export interface ParseIssue {
  line: number; // 1-based; 0 for whole-input issues
  message: string;
}

export type ParseResult<T> = { ok: true; value: T } | { ok: false; issues: ParseIssue[] };

export interface SnapshotAccount {
  id: string;
  origin: string;
  collateralAmount: string; // collateral asset base units (wei for WETH)
  debtUsd8: string;
}

export interface CollateralAsset {
  symbol: string;
  decimals: number;
  priceUsd8: string;
  ltBps: number;
  bonusBps: number;
}

/** The subset of a case file the graph reads. Everything else in the file is ignored, never inferred. */
export interface GraphCaseFile {
  dataClass: string;
  marketId: string;
  network: string;
  datasetId: string;
  modelId: string;
  scenario: { asset: string; shockBps: number };
  results: {
    liquidatableAccounts: number;
    residualBadDebtUsd8: string;
    liquidationVolumeUsd8: string;
    debtAtRiskUsd8: string;
  };
  collateral: CollateralAsset;
  stablecoins: string[]; // allowlist symbols; per-token debt split is not recorded
  accounts: SnapshotAccount[];
}

/** A claim posted on chain that commits to an evidenceHash. */
export interface GraphClaimRef {
  id: string;
  stateName: string;
  attester: string;
  claimedResidualBadDebtUsd8: string;
}

export type GraphNodeKind = "market" | "collateralAsset" | "debtAsset" | "account" | "evidence" | "claim";
export type GraphEdgeKind = "collateral" | "debt" | "listsAsset" | "evidenceFor" | "attests";
export type AccountOutcome = "safe" | "liquidated" | "badDebt";

/** Where a displayed value comes from. Shown next to every value in the info panel. */
export type DataSource = "replayOutput" | "caseFile" | "onChain";

export interface DetailRow {
  label: string;
  value: string;
  source: DataSource;
}

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  outcome?: AccountOutcome; // accounts only
  synthetic: boolean;
  details: DetailRow[];
}

export interface GraphEdge {
  id: string;
  kind: GraphEdgeKind;
  source: string;
  target: string;
  label: string;
  dataSource: DataSource;
}

export interface ConsistencyCheck {
  name: string;
  fromOutputs: string;
  fromCaseFile: string;
  matches: boolean;
}

export interface ExposureGraph {
  evidenceHash: string;
  dataClass: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  checks: ConsistencyCheck[];
  warnings: string[];
}
