"""After the watcher's challenge: record how the dispute ended and collect the payout (plan §15.2).

Rejected (challenge upheld) -> WON; Finalized (resolve(false)) -> LOST; Expired -> REFUNDED.
For WON and REFUNDED the watcher withdraws its credit. `withdraw()` pays the whole balance at once,
so a claim whose payout was already collected with another claim's withdrawal is simply marked
WITHDRAWN when the credit is zero.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..common.chain import ChainClient
from ..common.feed import FeedClient
from ..common.state import ClaimRecord, WatcherState
from .processor import ACTOR, read_claim

logger = logging.getLogger(__name__)

STATE_CHALLENGED, STATE_FINALIZED, STATE_REJECTED, STATE_EXPIRED = 2, 3, 4, 5
OUTCOME_BY_STATE = {STATE_REJECTED: "WON", STATE_FINALIZED: "LOST", STATE_EXPIRED: "REFUNDED"}


def settle(client: ChainClient, state: WatcherState, feed: Optional[FeedClient], record: ClaimRecord) -> ClaimRecord:
    """Moves a CHALLENGED/WON/REFUNDED claim forward once the dispute is decided."""
    if record.state == "CHALLENGED":
        on_chain = read_claim(client, record.claim_id).state
        outcome = OUTCOME_BY_STATE.get(on_chain)
        if outcome is None:
            return record  # still Challenged: the resolver has not acted and the window is open
        record = state.transition(record.claim_id, outcome)
        _post(feed, "EXPIRED" if outcome == "REFUNDED" else "RESOLVED", record.claim_id, {"outcome": outcome})
    if record.state in ("WON", "REFUNDED"):
        record = _withdraw(client, state, feed, record)
    return record


def _withdraw(client: ChainClient, state: WatcherState, feed: Optional[FeedClient], record: ClaimRecord) -> ClaimRecord:
    credit = client.call(client.registry.functions.credits(client.address))
    if credit > 0:
        tx = client.transact(client.registry.functions.withdraw())
        _post(feed, "WITHDRAWN", record.claim_id, {"amountWei": str(credit)}, tx.tx_hash)
    else:
        logger.info("claim %s: payout already withdrawn", record.claim_id)
    return state.transition(record.claim_id, "WITHDRAWN")


def _post(feed: Optional[FeedClient], kind: str, claim_id: int, data=None, tx_hash: Optional[str] = None) -> None:
    if feed is not None:
        feed.post(ACTOR, kind, claim_id=claim_id, tx_hash=tx_hash, data=data)
