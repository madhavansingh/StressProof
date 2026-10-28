"""Agent feed client for the backend's POST /feed (implementationplan.md §8.6, C-04).

The feed is informational ("agent-reported"); chain events stay authoritative. A feed failure must
never block an agent, so `post` returns False instead of raising, and logs the reason (never the
write token). Entries are checked before sending so programming mistakes show up in the logs.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

import httpx

from .config import Secret

logger = logging.getLogger(__name__)

FEED_KINDS = frozenset({
    "CLAIM_BUILT", "CLAIM_POSTED", "FILE_FETCHED", "FETCH_FAILED", "HASH_OK", "HASH_MISMATCH",
    "VALIDATION_FAILED", "REPLAY_MATCH", "REPLAY_MISMATCH", "INFO_MISMATCH", "REPORT_STORED",
    "CHALLENGE_SENT", "CHALLENGE_FAILED", "RESOLVER_VERDICT", "RESOLVED", "FINALIZED", "EXPIRED",
    "VAULT_APPLIED", "WITHDRAWN", "ERROR",
})
FEED_ACTORS = frozenset({"attester", "malicious_attester", "watcher", "resolver"})
DEFAULT_TIMEOUT_SEC = 3.0


class FeedClient:
    def __init__(self, backend_url: str, token: Optional[Secret], timeout_sec: float = DEFAULT_TIMEOUT_SEC,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._url = backend_url.rstrip("/") + "/feed"
        self._token = token
        self._timeout = timeout_sec
        self._transport = transport

    def post(self, actor: str, kind: str, claim_id: Optional[int] = None, tx_hash: Optional[str] = None,
             data: Optional[Mapping[str, Any]] = None) -> bool:
        """Sends one entry. Returns True if the backend accepted it; never raises."""
        entry = {
            "actor": actor,
            "kind": kind,
            "claimId": None if claim_id is None else str(claim_id),  # uint256 as a decimal string
            "txHash": tx_hash,
            "data": dict(data or {}),
        }
        problem = _invalid(entry)
        if problem:
            logger.error("feed entry dropped (%s): actor=%s kind=%s claim=%s", problem, actor, kind, claim_id)
            return False
        if self._token is None:
            logger.warning("feed entry not sent: API_WRITE_TOKEN is not set (kind=%s claim=%s)", kind, claim_id)
            return False
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                response = client.post(self._url, json=entry,
                                       headers={"Authorization": f"Bearer {self._token.reveal()}"})
        except httpx.HTTPError as exc:
            logger.warning("feed unreachable (%s): kind=%s claim=%s", type(exc).__name__, kind, claim_id)
            return False
        if response.status_code not in (200, 201):
            logger.warning("feed rejected entry (HTTP %s): kind=%s claim=%s", response.status_code, kind, claim_id)
            return False
        return True


def _invalid(entry: Mapping[str, Any]) -> Optional[str]:
    if entry["actor"] not in FEED_ACTORS:
        return f"unknown actor {entry['actor']!r}"
    if entry["kind"] not in FEED_KINDS:
        return f"unknown kind {entry['kind']!r}"
    try:
        json.dumps(entry["data"], allow_nan=False)
    except (TypeError, ValueError) as exc:
        return f"data is not JSON-serializable: {exc}"
    if _has_float(entry["data"]):
        return "data contains a float; send amounts as decimal strings"
    return None


def _has_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_has_float(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_float(v) for v in value)
    return False
