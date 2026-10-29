/**
 * Phases of a contract write as the UI must describe them. A passing simulation is not a
 * transaction, a submitted hash is not a mined transaction, and a mined transaction can revert.
 */
export type TxPhase =
  | "idle"
  | "simulation-passed"
  | "awaiting-signature"
  | "submitted"
  | "mined-success"
  | "mined-reverted";

export interface TxPhaseInput {
  simulationPassed: boolean;
  awaitingSignature: boolean;
  hash?: string;
  receiptStatus?: "success" | "reverted";
}

export function txPhase({ simulationPassed, awaitingSignature, hash, receiptStatus }: TxPhaseInput): TxPhase {
  if (hash) {
    if (receiptStatus === "success") return "mined-success";
    if (receiptStatus === "reverted") return "mined-reverted";
    return "submitted";
  }
  if (awaitingSignature) return "awaiting-signature";
  if (simulationPassed) return "simulation-passed";
  return "idle";
}

const LABELS: Record<TxPhase, string> = {
  idle: "",
  "simulation-passed": "SIMULATION_PASSED (NOTHING SENT YET)",
  "awaiting-signature": "SIMULATION_PASSED — CONFIRM IN WALLET",
  submitted: "SUBMITTED — WAITING FOR RECEIPT",
  "mined-success": "MINED: SUCCESS",
  "mined-reverted": "MINED: REVERTED",
};

export function txPhaseLabel(phase: TxPhase): string {
  return LABELS[phase];
}
