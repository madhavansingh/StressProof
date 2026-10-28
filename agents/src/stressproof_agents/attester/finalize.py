"""Optional honest-attester follow-up (`--auto-finalize`, plan §15.1 step 6).

After the challenge window: finalize the claim if it is still Pending, apply it to the vault
(BelowThreshold or AlreadyApplied are expected outcomes and only noted), then withdraw any credit.
Timing follows the chain's latest block timestamp, never the local clock (plan §19.1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from ..common.chain import ChainClient, ChainError, TransactionReverted
from ..common.feed import FeedClient
from .workflow import PostedClaim

STATE_PENDING = 1
STATE_FINALIZED = 3
EXPECTED_VAULT_REVERTS = ("BelowThreshold", "AlreadyApplied")
STALLED_POLLS = 10  # the chain timestamp did not move for this many polls: no blocks are being mined


@dataclass(frozen=True)
class FinalizeOutcome:
    finalized: bool
    applied: bool
    withdrawn_wei: int
    notes: Tuple[str, ...] = field(default_factory=tuple)


def wait_for_deadline(client: ChainClient, deadline: int, max_wait_sec: float, poll_sec: float,
                      sleep: Callable[[float], None] = time.sleep) -> int:
    """Polls until the latest block timestamp reaches `deadline`. Returns that timestamp."""
    waited, last_ts, stalled = 0.0, None, 0
    while True:
        now = client.latest_block_timestamp()
        if now >= deadline:
            return now
        stalled = stalled + 1 if now == last_ts else 0
        if stalled >= STALLED_POLLS:
            raise ChainError("the chain is not producing blocks, so its time does not advance; "
                             "for local Anvil start it with --block-time 1")
        if waited >= max_wait_sec:
            raise ChainError(f"challenge window still open after waiting {max_wait_sec:.0f}s")
        last_ts = now
        sleep(poll_sec)
        waited += poll_sec


def finalize_apply_withdraw(client: ChainClient, claim: PostedClaim, feed: Optional[FeedClient],
                            actor: str = "attester") -> FinalizeOutcome:
    notes: List[str] = []
    state = client.call(client.registry.functions.status(claim.claim_id))
    finalized = state == STATE_FINALIZED
    if state == STATE_PENDING:
        tx = client.transact(client.registry.functions.finalize(claim.claim_id))
        finalized = True
        _feed(feed, actor, "FINALIZED", claim.claim_id, tx.tx_hash)
    elif not finalized:
        notes.append(f"claim is in state {state}, not Pending or Finalized; not applying it")

    applied = False
    if finalized:
        try:
            tx = client.transact(client.vault.functions.applyClaim(claim.claim_id))
            applied = True
            _feed(feed, actor, "VAULT_APPLIED", claim.claim_id, tx.tx_hash)
        except TransactionReverted as exc:
            if exc.error is None or exc.error.name not in EXPECTED_VAULT_REVERTS:
                raise
            notes.append(f"vault did not apply the claim: {exc.error}")

    withdrawn = _withdraw_if_credited(client, claim, feed, actor)
    return FinalizeOutcome(finalized=finalized, applied=applied, withdrawn_wei=withdrawn, notes=tuple(notes))


def _withdraw_if_credited(client: ChainClient, claim: PostedClaim, feed: Optional[FeedClient], actor: str) -> int:
    credit = client.call(client.registry.functions.credits(client.address))
    if credit == 0:
        return 0
    tx = client.transact(client.registry.functions.withdraw())
    _feed(feed, actor, "WITHDRAWN", claim.claim_id, tx.tx_hash, {"amountWei": str(credit)})
    return credit


def _feed(feed: Optional[FeedClient], actor: str, kind: str, claim_id: int, tx_hash: str, data=None) -> None:
    if feed is not None:
        feed.post(actor, kind, claim_id=claim_id, tx_hash=tx_hash, data=data)
