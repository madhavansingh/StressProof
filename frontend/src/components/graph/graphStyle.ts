import type { AccountOutcome, DataSource, GraphEdgeKind, GraphNode, GraphNodeKind } from "@/lib/graph/types";

/** Colours and labels shared by the canvas, legend and info panel. */

export const OUTCOME_COLOR: Record<AccountOutcome, string> = {
  safe: "#34d399",
  liquidated: "#fbbf24",
  badDebt: "#ef4444",
};

export const KIND_COLOR: Record<Exclude<GraphNodeKind, "account">, string> = {
  market: "#ea580c",
  collateralAsset: "#e7e5e4",
  debtAsset: "#a8a29e",
  evidence: "#38bdf8",
  claim: "#a78bfa",
};

export const KIND_LABEL: Record<GraphNodeKind, string> = {
  market: "Market",
  collateralAsset: "Collateral asset",
  debtAsset: "Debt asset",
  account: "Account",
  evidence: "Case file (evidence)",
  claim: "On-chain claim",
};

export const EDGE_STYLE: Record<GraphEdgeKind, { label: string; dash?: string; color: string }> = {
  collateral: { label: "Supplies collateral", color: "#e7e5e4" },
  debt: { label: "Owes stablecoin debt", dash: "6 4", color: "#a8a29e" },
  listsAsset: { label: "Market asset", dash: "2 3", color: "#ea580c" },
  evidenceFor: { label: "Case file replays market", dash: "2 3", color: "#38bdf8" },
  attests: { label: "Claim commits to case file", dash: "1 3", color: "#a78bfa" },
};

export const SOURCE_LABEL: Record<DataSource, string> = {
  replayOutput: "REPLAY OUTPUT",
  caseFile: "CASE FILE",
  onChain: "ON CHAIN",
};

export function nodeColor(node: GraphNode): string {
  if (node.kind === "account") return OUTCOME_COLOR[node.outcome ?? "safe"];
  return KIND_COLOR[node.kind];
}
