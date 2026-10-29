"""Dry-run claim processing: the same fetch and core verdict as the real watcher, but no report
upload, no challenge and no withdrawal. State goes to a separate SQLite file (watcher-dry-run.sqlite)
so a dry run never affects the real watcher's progress.
"""

from __future__ import annotations

import logging

from stressproof_core import evaluate
from stressproof_core.constants import VERDICT_MATCH, VERDICT_WRONG_RESULT

from ..common.chain import ChainClient
from ..common.fetch import EvidenceFetcher, FetchError
from ..common.state import ClaimRecord, WatcherState
from .processor import PATH_MATCH, REASON_BY_VERDICT, STATE_PENDING, read_claim

logger = logging.getLogger(__name__)


class DryRunProcessor:
    def __init__(self, client: ChainClient, fetcher: EvidenceFetcher, state: WatcherState) -> None:
        self._client = client
        self._fetcher = fetcher
        self._state = state
        self.decisions: dict = {}  # claim_id -> what the real watcher would do (for tests and logs)

    def process(self, claim_id: int) -> ClaimRecord:
        record = self._state.get_required(claim_id)
        if record.is_terminal:
            return record
        claim = read_claim(self._client, claim_id)
        if claim.attester == self._client.address or claim.state != STATE_PENDING:
            return self._finish(claim_id, "would skip: own claim or no longer Pending")
        try:
            raw = self._fetcher.fetch(claim.case_file_uri).content
        except FetchError as exc:
            raw = b""
            logger.info("claim %s: fetch failed (%s)", claim_id, exc)
        evaluation = evaluate(raw, claim.onchain_view())
        if evaluation.verdict == VERDICT_MATCH:
            self.decisions[claim_id] = "MATCH: no challenge"
            for step in PATH_MATCH:
                self._state.transition(claim_id, step)
            return self._state.record(claim_id, verdict=evaluation.verdict)
        reason = REASON_BY_VERDICT[evaluation.verdict]
        counter = evaluation.counter_residual_usd8 if evaluation.verdict == VERDICT_WRONG_RESULT else 0
        self._state.record(claim_id, verdict=evaluation.verdict)
        return self._finish(claim_id, f"would challenge: {evaluation.verdict} (reason {reason}, counter {counter}, "
                                      f"violations {evaluation.violation_codes})")

    def _finish(self, claim_id: int, decision: str) -> ClaimRecord:
        self.decisions[claim_id] = decision
        logger.info("DRY RUN claim %s: %s", claim_id, decision)
        self._state.record(claim_id, error=f"dry run: {decision}")
        return self._state.transition(claim_id, "SKIPPED")
