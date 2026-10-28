"""Fakes for attester tests: a backend that follows the real endpoint contract, and a ready context.

The fake backend implements POST /stress/run, POST /case-files and GET /case-files/<hash> the way
backend/src/stressproof_backend/api/routes behave today (stored bytes served unchanged, bearer token
required). Tests can override responses to simulate a broken or hostile backend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
from stressproof_core import keccak256_hex, parse_strict
from web3 import Web3

from stressproof_agents.attester.backend import BackendClient
from stressproof_agents.attester.context import AttesterContext
from stressproof_agents.common.chain import ChainClient, TxPolicy
from stressproof_agents.common.config import AgentSettings, FetchSettings, Secret
from stressproof_agents.common.deployments import Deployment
from stressproof_agents.common.feed import FeedClient
from stressproof_agents.common.fetch import EvidenceFetcher

from conftest import REGISTRY, TEST_KEY, FakeNode

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_BYTES = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.json").read_bytes()
FIXTURE_HASH = keccak256_hex(FIXTURE_BYTES)
FIXTURE_R = int(parse_strict(FIXTURE_BYTES)["results"]["residualBadDebtUsd8"])
TOKEN = "test-write-token"
BASE = "http://127.0.0.1:8000"


class FakeBackend:
    def __init__(self) -> None:
        self.store: Dict[str, bytes] = {FIXTURE_HASH: FIXTURE_BYTES}
        self.requests: List[httpx.Request] = []
        self.feed: List[dict] = []
        self.stress_override: Optional[Callable[[httpx.Request], httpx.Response]] = None
        self.store_override: Optional[Callable[[httpx.Request], httpx.Response]] = None
        self.serve_override: Dict[str, bytes] = {}  # hash -> bytes served instead of the stored ones

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.startswith("/case-files/"):
            h = path.rsplit("/", 1)[-1]
            body = self.serve_override.get(h, self.store.get(h))
            return httpx.Response(200, content=body) if body is not None else httpx.Response(404)
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "Missing or invalid Bearer authorization token"})
        if path == "/stress/run":
            return self.stress_override(request) if self.stress_override else self._stress_run(request)
        if path == "/case-files":
            return self.store_override(request) if self.store_override else self._store(request)
        if path == "/feed":
            self.feed.append(json.loads(request.content))
            return httpx.Response(201, json={"seq": len(self.feed)})
        return httpx.Response(404)

    def _stress_run(self, request: httpx.Request) -> httpx.Response:
        results = parse_strict(FIXTURE_BYTES)["results"]
        return httpx.Response(200, json={
            "evidenceHash": FIXTURE_HASH, "caseFileURI": f"{BASE}/case-files/{FIXTURE_HASH}",
            "caseFileHttpURL": f"{BASE}/case-files/{FIXTURE_HASH}", "results": results,
            "dataClass": "SYNTHETIC", "sizeBytes": len(FIXTURE_BYTES)})

    def _store(self, request: httpx.Request) -> httpx.Response:
        h = keccak256_hex(request.content)
        self.store[h] = request.content
        return httpx.Response(201, json={"evidenceHash": h, "caseFileURI": f"{BASE}/case-files/{h}"})

    def posted(self, path: str) -> List[httpx.Request]:
        return [r for r in self.requests if r.method == "POST" and r.url.path == path]


def local_resolver(host: str, port: int):
    return ["127.0.0.1"] if host in ("127.0.0.1", "localhost") else ["93.184.215.14"]


def make_context(node: FakeNode, deployment: Deployment, backend: FakeBackend) -> AttesterContext:
    transport = httpx.MockTransport(backend)
    settings = AgentSettings(
        deployments_file=Path("unused.json"), backend_url=BASE, data_dir=Path("unused"),
        market_id_string="aave-v3-eth-weth-stable",
        fetch=FetchSettings(max_attempts=1, allow_localhost=True), watcher_poll_sec=2,
        watcher_start_block=None, api_write_token=Secret(TOKEN, "API_WRITE_TOKEN"),
        local_rpc_url="http://127.0.0.1:8546",
    )
    client = ChainClient(Web3(node), deployment, Secret(TEST_KEY, "ATTESTER_PK"),
                         TxPolicy(receipt_timeout_sec=2, receipt_poll_sec=0.01))
    return AttesterContext(
        settings=settings, deployment=deployment, client=client,
        backend=BackendClient(BASE, settings.api_write_token, transport=transport),
        fetcher=EvidenceFetcher(settings.fetch, resolver=local_resolver, transport=transport, sleep=lambda s: None),
        feed=FeedClient(BASE, settings.api_write_token, transport=transport),
    )


def expect_claim(node: FakeNode, claim_id: int, claimed: int, evidence_hash: str, uri: str, attester: str,
                 deadline: int) -> None:
    """Makes the fake chain answer postClaim like the real registry would for this claim."""
    from eth_abi import encode

    from conftest import claim_posted_log, selector

    node.calls[(REGISTRY.lower(), selector("postClaim(bytes32,uint256,bytes32,string)"))] = (
        "0x" + encode(["uint256"], [claim_id]).hex())
    node.logs.clear()
    node.logs.append(claim_posted_log(claim_id, attester, claimed, evidence_hash, uri, deadline))
