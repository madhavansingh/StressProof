"""Read-only view of one claim, decoded from StressRegistry.claim(id) (contracts/src/IStressRegistry.sol)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..common.chain import ChainClient

# IStressRegistry.State and IStressRegistry.Reason, in declaration order.
STATE_NAMES = ("None", "Pending", "Challenged", "Finalized", "Rejected", "Expired")
REASON_NAMES = ("NONE", "WRONG_RESULT", "EVIDENCE_INVALID")
NONE, PENDING, CHALLENGED, FINALIZED, REJECTED, EXPIRED = range(6)
TERMINAL_STATES = (FINALIZED, REJECTED, EXPIRED)


@dataclass(frozen=True)
class ClaimView:
    claim_id: int
    attester: str
    challenge_deadline: int
    state: int
    reason: int
    challenger: str
    resolution_deadline: int
    market_id: str
    evidence_hash: str
    replay_report_hash: str
    claimed_usd8: int
    counter_usd8: int
    case_file_uri: str
    replay_report_uri: str

    @property
    def state_name(self) -> str:
        return STATE_NAMES[self.state] if self.state < len(STATE_NAMES) else f"Unknown({self.state})"

    @property
    def reason_name(self) -> str:
        return REASON_NAMES[self.reason] if self.reason < len(REASON_NAMES) else f"Unknown({self.reason})"

    def onchain_view(self) -> Dict[str, Any]:
        """The dict stressproof_core.evaluate() expects."""
        return {"evidenceHash": self.evidence_hash, "marketId": self.market_id,
                "claimedResidualBadDebt": self.claimed_usd8}


def read_claim_view(client: ChainClient, claim_id: int) -> ClaimView:
    c = client.call(client.registry.functions.claim(claim_id))
    return ClaimView(
        claim_id=claim_id, attester=c[0], challenge_deadline=c[1], state=c[2], reason=c[3], challenger=c[4],
        resolution_deadline=c[5], market_id="0x" + bytes(c[6]).hex(), evidence_hash="0x" + bytes(c[7]).hex(),
        replay_report_hash="0x" + bytes(c[8]).hex(), claimed_usd8=c[9], counter_usd8=c[10],
        case_file_uri=c[11], replay_report_uri=c[12],
    )
