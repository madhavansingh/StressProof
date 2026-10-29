"""Watcher decision for one claim (implementationplan.md §15.2, §11).

The verdict comes only from stressproof_core.evaluate() on bytes that hash to the on-chain
evidenceHash; the replay report only from build_replay_report(). This module adds the
operational rules around them: self-skip, deadline guard, fetch retry until 30 s before the
deadline, report storage, a re-read of on-chain state right before challenging, and idempotent
resumption from the SQLite state after a restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from stressproof_core import Evaluation, build_replay_report, canonical_bytes, evaluate, keccak256_hex
from stressproof_core.constants import VERDICT_EVIDENCE_INVALID, VERDICT_MATCH, VERDICT_WRONG_RESULT

from ..attester.backend import BackendClient, BackendError
from ..common.chain import ChainClient, ChainError, TransactionReverted
from ..common.feed import FeedClient
from ..common.fetch import EvidenceFetcher, FetchError
from ..common.state import ClaimRecord, StateError, WatcherState

logger = logging.getLogger(__name__)

ACTOR = "watcher"
STATE_PENDING = 1
# Contract enum IStressRegistry.Reason: NONE = 0, WRONG_RESULT = 1, EVIDENCE_INVALID = 2.
REASON_BY_VERDICT = {VERDICT_WRONG_RESULT: 1, VERDICT_EVIDENCE_INVALID: 2}
FETCH_GIVE_UP_BEFORE_DEADLINE_SEC = 30  # plan §15.2 rule 5

# Linear state paths (common/state.py TRANSITIONS); resumption skips the steps already recorded.
PATH_MATCH = ("FETCHING", "FETCHED", "HASH_OK", "VALID", "MATCH")
PATH_MISMATCH = ("FETCHING", "FETCHED", "HASH_OK", "VALID", "MISMATCH", "REPORT_BUILT", "REPORT_STORED")
PATH_INVALID_CONTENT = ("FETCHING", "FETCHED", "HASH_OK", "INVALID", "REPORT_BUILT", "REPORT_STORED")
PATH_HASH_MISMATCH = ("FETCHING", "FETCHED", "INVALID", "REPORT_BUILT", "REPORT_STORED")
PATH_UNRETRIEVABLE = ("FETCHING", "FETCH_FAILED", "INVALID", "REPORT_BUILT", "REPORT_STORED")


@dataclass(frozen=True)
class OnChainClaim:
    claim_id: int
    attester: str
    state: int
    challenge_deadline: int
    challenger: str
    evidence_hash: str
    market_id: str
    claimed_usd8: int
    case_file_uri: str

    def onchain_view(self) -> Dict[str, Any]:
        """The dict stressproof_core.evaluate() expects."""
        return {"evidenceHash": self.evidence_hash, "marketId": self.market_id,
                "claimedResidualBadDebt": self.claimed_usd8}


@dataclass(frozen=True)
class Fetched:
    raw: bytes  # b"" when the evidence could not be retrieved
    fetched_from: str
    error: Optional[str]


def read_claim(client: ChainClient, claim_id: int) -> OnChainClaim:
    c = client.call(client.registry.functions.claim(claim_id))
    return OnChainClaim(
        claim_id=claim_id, attester=c[0], challenge_deadline=c[1], state=c[2], challenger=c[4],
        market_id="0x" + bytes(c[6]).hex(), evidence_hash="0x" + bytes(c[7]).hex(),
        claimed_usd8=c[9], case_file_uri=c[11],
    )


class ClaimProcessor:
    def __init__(self, client: ChainClient, fetcher: EvidenceFetcher, backend: BackendClient,
                 state: WatcherState, feed: Optional[FeedClient], replayer_commit: str, bond_wei: int) -> None:
        self._client = client
        self._fetcher = fetcher
        self._backend = backend
        self._state = state
        self._feed = feed
        self._replayer_commit = replayer_commit
        self._bond = bond_wei

    # ------------------------------------------------------------- entry

    def process(self, claim_id: int) -> ClaimRecord:
        """Advances one claim as far as it can go now. Safe to call again at any time."""
        record = self._state.get_required(claim_id)
        if record.is_terminal or record.state in ("CHALLENGED", "WON", "REFUNDED"):
            return record  # settled by outcomes.py
        claim = read_claim(self._client, claim_id)
        if record.state in ("REPORT_STORED", "CHALLENGE_SENDING"):
            return self._challenge(claim, record)  # re-reads the chain; recognises a challenge that landed
        skip = self._skip_reason(claim)
        if skip:
            return self._skip(claim_id, skip)

        fetched = self._fetch(claim)
        if fetched is None:  # failed, but there is still time to retry on a later poll
            return self._state.get_required(claim_id)
        evaluation = evaluate(fetched.raw, claim.onchain_view())
        if evaluation.verdict == VERDICT_MATCH:
            return self._record_match(claim, evaluation)
        record = self._record_report(claim, fetched, evaluation)
        return self._challenge(claim, record)

    # ------------------------------------------------------------ checks

    def _skip_reason(self, claim: OnChainClaim) -> Optional[str]:
        if claim.attester == self._client.address:
            return "own claim"
        if claim.state != STATE_PENDING:
            return f"claim is in state {claim.state}, no longer Pending"
        if self._client.latest_block_timestamp() >= claim.challenge_deadline:
            return "challenge window closed"
        return None

    def _skip(self, claim_id: int, reason: str) -> ClaimRecord:
        logger.info("claim %s skipped: %s", claim_id, reason)
        self._state.record(claim_id, error=f"skipped: {reason}")
        return self._state.transition(claim_id, "SKIPPED")

    # ----------------------------------------------------------- fetching

    def _fetch(self, claim: OnChainClaim) -> Optional[Fetched]:
        if self._state.get_required(claim.claim_id).state == "SEEN":
            self._state.transition(claim.claim_id, "FETCHING")
        try:
            result = self._fetcher.fetch(claim.case_file_uri)
            self._post("FILE_FETCHED", claim.claim_id, {"bytes": len(result.content)})
            return Fetched(result.content, result.url, None)
        except FetchError as exc:
            seconds_left = claim.challenge_deadline - self._client.latest_block_timestamp()
            self._state.record(claim.claim_id, error=f"fetch failed: {exc}")
            self._post("FETCH_FAILED", claim.claim_id, {"error": str(exc), "secondsLeft": str(seconds_left)})
            if seconds_left > FETCH_GIVE_UP_BEFORE_DEADLINE_SEC:
                return None
            return Fetched(b"", claim.case_file_uri, str(exc))  # unretrievable: EVIDENCE_INVALID

    # ------------------------------------------------------------ results

    def _record_match(self, claim: OnChainClaim, evaluation: Evaluation) -> ClaimRecord:
        self._walk(claim.claim_id, PATH_MATCH)
        self._post("HASH_OK", claim.claim_id)
        self._post_info_mismatches(claim.claim_id, evaluation)
        recomputed = evaluation.recomputed.residual_bad_debt_usd8
        self._post("REPLAY_MATCH", claim.claim_id, {"recomputedUsd8": str(recomputed)})
        return self._state.record(claim.claim_id, verdict=evaluation.verdict, recomputed_usd8=recomputed)

    def _record_report(self, claim: OnChainClaim, fetched: Fetched, evaluation: Evaluation) -> ClaimRecord:
        """Builds and stores the replay report; for hash-matching evidence also stores a copy (C-19)."""
        copy_uri = ""
        if evaluation.hash_matches:
            copy_uri = self._backend.store_case_file(fetched.raw).case_file_uri
        report = build_replay_report(
            evaluation, chain_id=self._client.deployment.chain_id, registry=self._client.deployment.registry,
            claim_id=claim.claim_id, evidence_hash=claim.evidence_hash, fetched_from=fetched.fetched_from,
            watcher=self._client.address, replayer_commit=self._replayer_commit,
            claimed_onchain_usd8=claim.claimed_usd8, case_file_copy_uri=copy_uri,
        )
        raw_report = canonical_bytes(report)
        stored = self._backend.store_replay_report(raw_report)
        if stored.evidence_hash != keccak256_hex(raw_report):
            raise BackendError(f"backend stored the report as {stored.evidence_hash}, expected {keccak256_hex(raw_report)}")

        self._walk(claim.claim_id, _path_for(fetched, evaluation))
        self._post_verdict(claim.claim_id, fetched, evaluation)
        self._post("REPORT_STORED", claim.claim_id, {"reportHash": stored.evidence_hash})
        recomputed = evaluation.recomputed.residual_bad_debt_usd8 if evaluation.recomputed else None
        return self._state.record(claim.claim_id, verdict=evaluation.verdict, recomputed_usd8=recomputed,
                                  report_hash=stored.evidence_hash, report_uri=stored.case_file_uri)

    # ---------------------------------------------------------- challenge

    def _challenge(self, claim: OnChainClaim, record: ClaimRecord) -> ClaimRecord:
        fresh = read_claim(self._client, claim.claim_id)  # re-read right before acting
        if fresh.challenger == self._client.address:
            self._walk(claim.claim_id, ("REPORT_STORED", "CHALLENGE_SENDING", "CHALLENGED"))  # landed before a restart
            return self._state.get_required(claim.claim_id)
        skip = self._skip_reason(fresh)
        if skip:
            return self._skip(claim.claim_id, skip)
        reason = REASON_BY_VERDICT[record.verdict]
        counter = record.recomputed_usd8 if record.verdict == VERDICT_WRONG_RESULT else 0
        if record.verdict == VERDICT_WRONG_RESULT and counter == fresh.claimed_usd8:
            raise ChainError(f"claim {claim.claim_id}: counter equals the claim; refusing to challenge")

        self._walk(claim.claim_id, ("REPORT_STORED", "CHALLENGE_SENDING"))
        fn = self._client.registry.functions.challenge(
            claim.claim_id, reason, counter, record.report_uri, bytes.fromhex(record.report_hash[2:]))
        try:
            tx = self._client.transact(fn, value=self._bond)
        except TransactionReverted as exc:
            self._state.record(claim.claim_id, error=str(exc))
            self._post("CHALLENGE_FAILED", claim.claim_id, {"error": str(exc)})
            return self._state.transition(claim.claim_id, "CHALLENGE_FAILED")
        # Other ChainErrors (RPC down, receipt timeout) propagate: the row stays CHALLENGE_SENDING and
        # the next poll re-reads the chain, so a challenge that did land is recognised, not resent.
        self._post("CHALLENGE_SENT", claim.claim_id, {"reason": str(reason), "counterUsd8": str(counter)},
                   tx_hash=tx.tx_hash)
        self._state.record(claim.claim_id, challenge_tx=tx.tx_hash)
        return self._state.transition(claim.claim_id, "CHALLENGED")

    # -------------------------------------------------------------- utils

    def _walk(self, claim_id: int, path: Sequence[str]) -> None:
        """Applies the transitions in `path` that come after the claim's current state, so a pass
        that is repeated after a restart only records the steps that were not recorded yet."""
        current = self._state.get_required(claim_id).state
        if current in path:
            start = path.index(current) + 1
        elif current == "SEEN":
            start = 0
        else:
            raise StateError(f"claim {claim_id}: cannot resume from {current} along {path}")
        for step in path[start:]:
            self._state.transition(claim_id, step)

    def _post_verdict(self, claim_id: int, fetched: Fetched, evaluation: Evaluation) -> None:
        if fetched.error is None and not evaluation.hash_matches:
            self._post("HASH_MISMATCH", claim_id)
        elif evaluation.verdict == VERDICT_EVIDENCE_INVALID:
            self._post("VALIDATION_FAILED", claim_id, {"violations": evaluation.violation_codes})
        else:
            self._post("HASH_OK", claim_id)
            self._post_info_mismatches(claim_id, evaluation)
            self._post("REPLAY_MISMATCH", claim_id, {"recomputedUsd8": str(evaluation.counter_residual_usd8)})

    def _post_info_mismatches(self, claim_id: int, evaluation: Evaluation) -> None:
        if evaluation.info_mismatches:
            self._post("INFO_MISMATCH", claim_id, {"metrics": list(evaluation.info_mismatches)})

    def _post(self, kind: str, claim_id: int, data: Optional[Dict[str, Any]] = None,
              tx_hash: Optional[str] = None) -> None:
        if self._feed is not None:
            self._feed.post(ACTOR, kind, claim_id=claim_id, tx_hash=tx_hash, data=data)


def _path_for(fetched: Fetched, evaluation: Evaluation) -> Tuple[str, ...]:
    if fetched.error is not None:
        return PATH_UNRETRIEVABLE
    if not evaluation.hash_matches:
        return PATH_HASH_MISMATCH
    if evaluation.verdict == VERDICT_EVIDENCE_INVALID:
        return PATH_INVALID_CONTENT
    return PATH_MISMATCH
