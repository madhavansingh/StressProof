"""Watcher poll loop (implementationplan.md §15.2): read new ClaimPosted logs from a persistent
cursor, then advance every unfinished claim. Polling, not websockets, by plan decision.

The cursor is only moved forward after the logs for that range are stored, so a crash in between
re-reads the same logs (add_claim ignores duplicates). Claims are processed in parallel so one
slow evidence host cannot hold up the others. A failure on one claim is logged and reported to
the feed; it never stops the loop.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from ..common.chain import ChainClient
from ..common.feed import FeedClient
from ..common.state import WatcherState
from .outcomes import settle
from .processor import ACTOR, ClaimProcessor

logger = logging.getLogger(__name__)

LOG_RANGE = 2_000  # blocks per eth_getLogs request
SETTLE_STATES = ("CHALLENGED", "WON", "REFUNDED")


@dataclass(frozen=True)
class PollResult:
    new_claims: Tuple[int, ...]
    processed: Tuple[int, ...]
    errors: Tuple[Tuple[int, str], ...]
    cursor: int


class Watcher:
    def __init__(self, client: ChainClient, state: WatcherState, processor: ClaimProcessor,
                 feed: Optional[FeedClient], start_block: int, workers: int = 4) -> None:
        self._client = client
        self._state = state
        self._processor = processor
        self._feed = feed
        self._start_block = start_block
        self._workers = workers

    @property
    def client(self) -> ChainClient:
        return self._client

    def poll_once(self) -> PollResult:
        new_claims, cursor = self._ingest_logs()
        work = self._state.unfinished()
        errors = []
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            outcomes = list(pool.map(self._advance, work))
        for record, error in zip(work, outcomes):
            if error:
                errors.append((record.claim_id, error))
        return PollResult(tuple(new_claims), tuple(r.claim_id for r in work), tuple(errors), cursor)

    def run_forever(self, poll_sec: float, sleep: Callable[[float], None] = time.sleep,
                    stop: Callable[[], bool] = lambda: False) -> None:
        while not stop():
            try:
                result = self.poll_once()
                if result.new_claims or result.errors:
                    logger.info("poll: new=%s errors=%s cursor=%s", result.new_claims, result.errors, result.cursor)
            except Exception as exc:  # RPC outage etc.: keep watching
                logger.error("poll failed: %s: %s", type(exc).__name__, exc)
            sleep(poll_sec)

    # -------------------------------------------------------------- steps

    def _ingest_logs(self) -> Tuple[list, int]:
        cursor = self._state.cursor()
        next_block = self._start_block if cursor is None else cursor + 1
        latest = self._client.w3.eth.block_number
        new_claims = []
        while next_block <= latest:
            to_block = min(next_block + LOG_RANGE - 1, latest)
            for event in self._client.get_events("ClaimPosted", from_block=next_block, to_block=to_block):
                a = event.args
                self._state.add_claim(a.claimId, a.attester, "0x" + bytes(a.evidenceHash).hex(), a.caseFileURI,
                                      a.claimedResidualBadDebt)
                new_claims.append(a.claimId)
            self._state.set_cursor(to_block)
            next_block = to_block + 1
        current = self._state.cursor()
        return new_claims, (self._start_block - 1 if current is None else current)

    def _advance(self, record) -> Optional[str]:
        try:
            if record.state in SETTLE_STATES:
                settle(self._client, self._state, self._feed, record)
            else:
                self._processor.process(record.claim_id)
            return None
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            logger.warning("claim %s: %s", record.claim_id, message)
            self._state.record(record.claim_id, error=message[:500])
            if self._feed is not None:
                self._feed.post(ACTOR, "ERROR", claim_id=record.claim_id, data={"error": message[:500]})
            return message
