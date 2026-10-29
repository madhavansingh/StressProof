export const STATE_NAMES = [
  "None",
  "Pending",
  "Challenged",
  "Finalized",
  "Rejected",
  "Expired",
] as const;

export type ClaimStateName = (typeof STATE_NAMES)[number];

export function mapClaimState(stateInt: number): ClaimStateName {
  if (stateInt >= 0 && stateInt < STATE_NAMES.length) {
    return STATE_NAMES[stateInt];
  }
  return "None";
}

export const REASON_NAMES = ["NONE", "WRONG_RESULT", "EVIDENCE_INVALID"] as const;
export type ClaimReasonName = (typeof REASON_NAMES)[number];

export function mapClaimReason(reasonInt: number): ClaimReasonName {
  if (reasonInt >= 0 && reasonInt < REASON_NAMES.length) {
    return REASON_NAMES[reasonInt];
  }
  return "NONE";
}

export interface OnChainClaim {
  id: bigint;
  attester: `0x${string}`;
  challengeDeadline: bigint;
  state: number;
  stateName: ClaimStateName;
  reason: number;
  reasonName: ClaimReasonName;
  challenger: `0x${string}`;
  resolutionDeadline: bigint;
  marketId: `0x${string}`;
  evidenceHash: `0x${string}`;
  replayReportHash: `0x${string}`;
  claimedResidualBadDebt: bigint;
  counterResidualBadDebt: bigint;
  caseFileURI: string;
  replayReportURI: string;
}

export function parseClaimStruct(id: bigint, raw: any): OnChainClaim {
  const isObj = raw && typeof raw === "object" && !Array.isArray(raw);
  const attester = (isObj ? raw.attester : raw[0]) as `0x${string}`;
  const challengeDeadline = BigInt(isObj ? raw.challengeDeadline : raw[1]);
  const stateNum = Number(isObj ? raw.state : raw[2]);
  const reasonNum = Number(isObj ? raw.reason : raw[3]);
  const challenger = (isObj ? raw.challenger : raw[4]) as `0x${string}`;
  const resolutionDeadline = BigInt(isObj ? raw.resolutionDeadline : raw[5]);
  const marketId = (isObj ? raw.marketId : raw[6]) as `0x${string}`;
  const evidenceHash = (isObj ? raw.evidenceHash : raw[7]) as `0x${string}`;
  const replayReportHash = (isObj ? raw.replayReportHash : raw[8]) as `0x${string}`;
  const claimedResidualBadDebt = BigInt(isObj ? raw.claimedResidualBadDebt : raw[9]);
  const counterResidualBadDebt = BigInt(isObj ? raw.counterResidualBadDebt : raw[10]);
  const caseFileURI = String(isObj ? raw.caseFileURI : raw[11] || "");
  const replayReportURI = String(isObj ? raw.replayReportURI : raw[12] || "");

  return {
    id,
    attester,
    challengeDeadline,
    state: stateNum,
    stateName: mapClaimState(stateNum),
    reason: reasonNum,
    reasonName: mapClaimReason(reasonNum),
    challenger,
    resolutionDeadline,
    marketId,
    evidenceHash,
    replayReportHash,
    claimedResidualBadDebt,
    counterResidualBadDebt,
    caseFileURI,
    replayReportURI,
  };
}

export function calculateBlockTimeCountdown(
  deadlineSec: number | bigint,
  blockTimestampSec: number | bigint,
  localElapsedSec: number = 0
): { text: string; isExpired: boolean; remainingSec: number } {
  const deadline = Number(deadlineSec);
  const blockTime = Number(blockTimestampSec);
  if (deadline === 0) {
    return { text: "—", isExpired: true, remainingSec: 0 };
  }
  const effectiveNow = blockTime + localElapsedSec;
  const remaining = deadline - effectiveNow;
  if (remaining <= 0) {
    return { text: "Expired", isExpired: true, remainingSec: 0 };
  }
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  return {
    text: m > 0 ? `${m}m ${s}s` : `${s}s`,
    isExpired: false,
    remainingSec: remaining,
  };
}
