"""Client for the backend endpoints the attesters use (implementationplan.md §14).

`POST /stress/run` builds and stores a case file; `POST /case-files` stores raw bytes.
The backend URL comes from configuration (BACKEND_URL), not from chain data, so it is called
directly. Every case-file URI it returns is still fetched through the SSRF-safe fetcher before use.
Responses are checked strictly: a malformed answer stops the attester before anything is signed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx

from ..common.config import Secret

_HASH_RE = re.compile(r"^0x[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_RESULT_KEYS = frozenset({"debtAtRiskUsd8", "liquidatableAccounts", "liquidationVolumeUsd8", "residualBadDebtUsd8"})
DEFAULT_TIMEOUT_SEC = 30.0


class BackendError(RuntimeError):
    """The backend refused the request or answered with something unexpected."""


@dataclass(frozen=True)
class StoredCaseFile:
    evidence_hash: str
    case_file_uri: str


@dataclass(frozen=True)
class StressRun:
    evidence_hash: str
    case_file_uri: str
    residual_bad_debt_usd8: int
    results: Mapping[str, Any]  # the four metrics as returned (informational)
    data_class: str


class BackendClient:
    def __init__(self, base_url: str, token: Optional[Secret], timeout_sec: float = DEFAULT_TIMEOUT_SEC,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        if token is None:
            raise BackendError("API_WRITE_TOKEN is not set; the backend's write endpoints need it")
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_sec
        self._transport = transport

    def stress_run(self, dataset_id: str, shock_bps: int, rationale: str) -> StressRun:
        body = {"datasetId": dataset_id, "scenario": {"asset": "WETH", "shockBps": shock_bps},
                "agentRationale": rationale}
        data = self._post_json("/stress/run", json=body, ok=(200,))
        evidence_hash = _hash(data.get("evidenceHash"), "evidenceHash")
        results = data.get("results")
        if not isinstance(results, dict) or set(results) != _RESULT_KEYS:
            raise BackendError(f"/stress/run returned unexpected results: {results!r}")
        residual = results["residualBadDebtUsd8"]
        if not isinstance(residual, str) or not _DECIMAL_RE.match(residual):
            raise BackendError(f"/stress/run returned a non-decimal residualBadDebtUsd8: {residual!r}")
        return StressRun(
            evidence_hash=evidence_hash,
            case_file_uri=_uri(data.get("caseFileURI")),
            residual_bad_debt_usd8=int(residual),
            results=dict(results),
            data_class=str(data.get("dataClass", "")),
        )

    def store_case_file(self, raw: bytes) -> StoredCaseFile:
        data = self._post_json("/case-files", content=raw, ok=(200, 201),
                               headers={"Content-Type": "application/json"})
        return StoredCaseFile(_hash(data.get("evidenceHash"), "evidenceHash"), _uri(data.get("caseFileURI")))

    def store_replay_report(self, raw: bytes) -> StoredCaseFile:
        """POST /replay-reports (C-03). Returns (reportHash, reportURI) in the same shape as a case file."""
        data = self._post_json("/replay-reports", content=raw, ok=(200, 201),
                               headers={"Content-Type": "application/json"})
        return StoredCaseFile(_hash(data.get("reportHash"), "reportHash"), _uri(data.get("reportURI")))

    def _post_json(self, path: str, ok, headers: Optional[Mapping[str, str]] = None, **kwargs) -> dict:
        all_headers = {"Authorization": f"Bearer {self._token.reveal()}", **(headers or {})}
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                response = client.post(self._base + path, headers=all_headers, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendError(f"backend {path} unreachable: {type(exc).__name__}") from None
        if response.status_code not in ok:
            raise BackendError(f"backend {path} returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except ValueError:
            raise BackendError(f"backend {path} returned invalid JSON") from None
        if not isinstance(data, dict):
            raise BackendError(f"backend {path} returned {type(data).__name__}, expected an object")
        return data


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.match(value):
        raise BackendError(f"backend returned an invalid {name}: {value!r}")
    return value


def _uri(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:  # MAX_URI_LENGTH on-chain
        raise BackendError(f"backend returned an invalid caseFileURI: {value!r}")
    return value
