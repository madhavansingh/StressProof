/**
 * Core type definitions for StressProof frontend.
 * Matches backend schemas and on-chain structs.
 */

export type ClaimState = "None" | "Pending" | "Challenged" | "Finalized" | "Rejected" | "Expired";
export type ChallengeReason = "NONE" | "WRONG_RESULT" | "EVIDENCE_INVALID";

export interface OnChainClaim {
  id: bigint;
  attester: string;
  challengeDeadline: bigint;
  state: ClaimState;
  reason: ChallengeReason;
  challenger: string;
  resolutionDeadline: bigint;
  marketId: string;
  evidenceHash: string;
  replayReportHash: string;
  claimedResidualBadDebt: bigint;
  counterResidualBadDebt: bigint;
  caseFileURI: string;
  replayReportURI: string;
}

export interface ReplayMetrics {
  liquidatableAccounts: number;
  debtAtRiskUsd8: string;
  liquidationVolumeUsd8: string;
  residualBadDebtUsd8: string;
}

export interface CaseFile {
  schemaVersion: number;
  marketId: string;
  dataClass: "REAL" | "MIXED" | "SYNTHETIC";
  dataset: {
    datasetId: string;
    forkBlock: number;
    network: string;
    snapshotHash: string;
    counts: { real: number; synthetic: number };
  };
  scenario: {
    asset: string;
    shockBps: number;
  };
  agentRationale: string;
  model: {
    id: string;
    replayerCommit: string;
  };
  results: ReplayMetrics;
}

export type FeedActor =
  | "attester"
  | "malicious_attester"
  | "malicious"
  | "watcher"
  | "resolver"
  | "backend"
  | "ui"
  | "user"
  | string;

export interface FeedEntry {
  seq: number;
  ts: string;
  actor: FeedActor;
  kind: string;
  claimId?: string | null;
  txHash?: string | null;
  data?: Record<string, unknown>;
  source?: "on-chain" | "agent-reported";
}

export interface FeedResponse {
  entries: FeedEntry[];
  nextSince: number;
}
