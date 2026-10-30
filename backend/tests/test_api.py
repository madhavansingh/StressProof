"""
Backend API tests (Part 5): datasets, /stress/run, validated uploads, raw-byte reads,
auth, durable feed, CORS and the Phase 2 graph stub. See conftest.py for the harness.
"""

import json
import shutil

import pytest

from backend_harness import AUTH, FIXTURE_DATASETS, REPO_ROOT
from stressproof_core import build_replay_report, canonical_bytes, evaluate, keccak256_hex, market_id

FIXTURE_ID = "weth-stable-fixture-v1"
GOLDEN_HASH = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.keccak").read_text().strip()
GOLDEN_BYTES = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.json").read_bytes()
SNAPSHOT_HASH = "0x9df1899fbcae4e418753920e0d1bee59eed4cb3d0445d982cbc06807838e199d"
RUN = {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": -3000}}


# --- health and datasets -------------------------------------------------------------

def test_health(client, harness):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["service"] == "stressproof-backend"
    assert body["gitCommit"] == "0" * 40
    assert FIXTURE_ID in body["datasets"]
    assert body["storage"] == harness.backend


def test_datasets_lists_fixture(client):
    datasets = client.get("/datasets").json()
    fixture = next(d for d in datasets if d["datasetId"] == FIXTURE_ID)
    assert fixture == {"counts": {"real": 0, "synthetic": 6}, "dataClass": "SYNTHETIC", "datasetId": FIXTURE_ID,
                       "forkBlock": 19000000, "snapshotHash": SNAPSHOT_HASH}


def test_manifest_is_raw_bytes(client):
    res = client.get(f"/datasets/{FIXTURE_ID}/manifest")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/json"
    assert res.content == (FIXTURE_DATASETS / FIXTURE_ID / "dataset_manifest.json").read_bytes()


@pytest.mark.parametrize("dataset_id,code", [("UPPER", 400), ("bad_id", 400), ("does-not-exist", 404)])
def test_manifest_errors(client, dataset_id, code):
    assert client.get(f"/datasets/{dataset_id}/manifest").status_code == code


def test_registry_skips_bad_datasets_and_first_root_wins(harness):
    src = FIXTURE_DATASETS / FIXTURE_ID
    good = harness.extra_datasets / "copy-v1"
    shutil.copytree(src, good)
    manifest = json.loads((good / "dataset_manifest.json").read_bytes())
    manifest["datasetId"] = "copy-v1"
    (good / "dataset_manifest.json").write_bytes(canonical_bytes(manifest))

    tampered = harness.extra_datasets / "tampered-v1"
    shutil.copytree(good, tampered)
    m2 = dict(manifest, datasetId="tampered-v1")
    (tampered / "dataset_manifest.json").write_bytes(canonical_bytes(m2))
    (tampered / "snapshot.json").write_bytes((tampered / "snapshot.json").read_bytes().replace(b"synth-0001", b"synth-0000"))

    shadow = harness.extra_datasets / FIXTURE_ID      # same id as the committed fixture, earlier root
    shutil.copytree(good, shadow)
    (shadow / "dataset_manifest.json").write_bytes(canonical_bytes(dict(manifest, datasetId=FIXTURE_ID, forkBlock=7)))

    with harness.client() as c:
        ids = c.get("/health").json()["datasets"]
        assert "copy-v1" in ids and "tampered-v1" not in ids
        assert next(d for d in c.get("/datasets").json() if d["datasetId"] == FIXTURE_ID)["forkBlock"] == 7


# --- /stress/run -----------------------------------------------------------------------

def test_stress_run_reproduces_golden_fixture(client):
    res = client.post("/stress/run", json=RUN, headers=AUTH)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["results"]["residualBadDebtUsd8"] == "200000000001"
    assert body["dataClass"] == "SYNTHETIC"
    # Same snapshot, scenario, rationale default, marketId and replayerCommit as the golden fixture.
    assert body["evidenceHash"] == GOLDEN_HASH
    assert body["sizeBytes"] == len(GOLDEN_BYTES)
    assert body["caseFileURI"] == body["caseFileHttpURL"] == f"http://testserver/case-files/{GOLDEN_HASH}"

    fetched = client.get(body["caseFileURI"].removeprefix("http://testserver"))   # T-P-20
    assert fetched.status_code == 200
    assert keccak256_hex(fetched.content) == body["evidenceHash"]
    assert fetched.content == GOLDEN_BYTES
    assert fetched.headers["x-content-keccak256"] == GOLDEN_HASH
    assert "immutable" in fetched.headers["cache-control"]


def test_stress_run_writes_outputs_and_feed(client, harness):
    body = client.post("/stress/run", json={**RUN, "agentRationale": "custom"}, headers=AUTH).json()
    assert body["evidenceHash"] != GOLDEN_HASH                      # rationale is committed by the hash
    if harness.backend == "filesystem":
        outputs = (harness.data_dir / "replay_outputs" / f"{body['evidenceHash']}.jsonl").read_bytes().splitlines()
        assert len(outputs) == 6 and json.loads(outputs[1])["residualUsd8"] == "200000000000"
    entries = client.get("/feed").json()["entries"]
    built = [e for e in entries if e["kind"] == "CLAIM_BUILT"]
    assert built[-1]["actor"] == "backend" and built[-1]["data"]["evidenceHash"] == body["evidenceHash"]


def test_stress_run_is_repeatable(client):
    a = client.post("/stress/run", json=RUN, headers=AUTH).json()
    b = client.post("/stress/run", json=RUN, headers=AUTH).json()
    assert a["evidenceHash"] == b["evidenceHash"]


@pytest.mark.parametrize("body", [
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": 0}},
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": -9001}},
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": "-3000"}},
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": -3000.0}},
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WBTC", "shockBps": -3000}},
    {"datasetId": FIXTURE_ID, "scenario": {"asset": "WETH", "shockBps": -3000, "x": 1}},
    {"datasetId": FIXTURE_ID},
])
def test_stress_run_bad_scenario_422(client, body):
    assert client.post("/stress/run", json=body, headers=AUTH).status_code == 422


@pytest.mark.parametrize("dataset_id", ["does-not-exist", "../etc", "UPPER"])
def test_stress_run_unknown_dataset_404(client, dataset_id):
    assert client.post("/stress/run", json={**RUN, "datasetId": dataset_id}, headers=AUTH).status_code == 404


# --- uploads and raw reads -----------------------------------------------------------------

def test_case_file_upload_is_idempotent(client):
    first = client.post("/case-files", content=GOLDEN_BYTES, headers=AUTH)
    assert first.status_code == 201
    assert first.json() == {"evidenceHash": GOLDEN_HASH, "caseFileURI": f"http://testserver/case-files/{GOLDEN_HASH}"}
    again = client.post("/case-files", content=GOLDEN_BYTES, headers=AUTH)
    assert again.status_code == 200 and again.json() == first.json()
    assert client.get(f"/case-files/{GOLDEN_HASH}").content == GOLDEN_BYTES


def test_case_file_upload_rejects_non_canonical_and_invalid(client):
    spaced = GOLDEN_BYTES.replace(b'"schemaVersion":1', b'"schemaVersion": 1')
    res = client.post("/case-files", content=spaced, headers=AUTH)
    assert res.status_code == 422 and res.json()["detail"]["violations"] == ["V-03"]

    cf = json.loads(GOLDEN_BYTES)
    cf["snapshot"]["accounts"].reverse()
    res = client.post("/case-files", content=canonical_bytes(cf), headers=AUTH)
    assert res.status_code == 422 and "V-10" in res.json()["detail"]["violations"]


def test_malicious_style_upload_is_accepted(client):
    """Spec §11: an inflated but well-formed case file is stored; only the replay catches it."""
    cf = json.loads(GOLDEN_BYTES)
    cf["results"]["residualBadDebtUsd8"] = str(3 * 200000000001)
    res = client.post("/case-files", content=canonical_bytes(cf), headers=AUTH)
    assert res.status_code == 201


def test_body_size_cap_413(harness):
    with harness.client(MAX_BODY_BYTES=100) as c:
        assert c.post("/case-files", content=GOLDEN_BYTES, headers=AUTH).status_code == 413
        assert c.post("/replay-reports", content=b"x" * 101, headers=AUTH).status_code == 413


def _report_bytes():
    ev = evaluate(GOLDEN_BYTES, {"evidenceHash": GOLDEN_HASH, "marketId": market_id("aave-v3-eth-weth-stable"),
                                 "claimedResidualBadDebt": 3 * 200000000001})
    report = build_replay_report(ev, chain_id=31337, registry="0x" + "11" * 20, claim_id=1, evidence_hash=GOLDEN_HASH,
                                 fetched_from="http://testserver/case-files/x", watcher="0x" + "22" * 20,
                                 replayer_commit="0" * 40, claimed_onchain_usd8=3 * 200000000001)
    return canonical_bytes(report)


def test_replay_report_upload_and_read(client):
    raw = _report_bytes()
    first = client.post("/replay-reports", content=raw, headers=AUTH)
    assert first.status_code == 201
    h = keccak256_hex(raw)
    assert first.json() == {"reportHash": h, "reportURI": f"http://testserver/replay-reports/{h}"}
    assert client.post("/replay-reports", content=raw, headers=AUTH).status_code == 200
    got = client.get(f"/replay-reports/{h}")
    assert got.content == raw and got.headers["x-content-keccak256"] == h


@pytest.mark.parametrize("raw", [b'{"a": 1}', b"not json", canonical_bytes({"verdict": "MATCH"})])
def test_replay_report_rejects_bad_bodies(client, raw):
    assert client.post("/replay-reports", content=raw, headers=AUTH).status_code == 422


@pytest.mark.parametrize("path", ["/case-files/0x123", f"/case-files/{GOLDEN_HASH.upper()}",
                                  f"/case-files/{GOLDEN_HASH[2:]}", "/case-files/%2e%2e",
                                  "/replay-reports/0xZZ", f"/replay-reports/0X{GOLDEN_HASH[2:]}"])
def test_bad_hash_400(client, path):   # T-P-21
    assert client.get(path).status_code == 400


@pytest.mark.parametrize("path", ["/case-files/..%2fsecret", "/case-files/..%2f..%2fetc%2fpasswd", "/replay-reports/a%2fb"])
def test_traversal_paths_never_reach_the_store(client, path):
    """A decoded '/' no longer matches the {hash} route, so these never reach a file lookup."""
    res = client.get(path)
    assert res.status_code in (400, 404) and not res.content.startswith(b"{\"agentRationale\"")


# --- replay outputs read route (WP-6) ------------------------------------------------------

def test_replay_outputs_are_served_as_stored_bytes(client, harness):
    body = client.post("/stress/run", json=RUN, headers=AUTH).json()
    res = client.get(f"/replay-outputs/{body['evidenceHash']}")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    assert res.headers["x-evidence-hash"] == body["evidenceHash"]
    assert "x-content-keccak256" not in res.headers          # the bytes are not hashed to the evidenceHash
    lines = res.content.splitlines()
    assert len(lines) == 6
    assert all(line == canonical_bytes(json.loads(line)) for line in lines)
    if harness.backend == "filesystem":
        assert res.content == (harness.data_dir / "replay_outputs" / f"{body['evidenceHash']}.jsonl").read_bytes()


@pytest.mark.parametrize("path", ["/replay-outputs/0x123", f"/replay-outputs/{GOLDEN_HASH.upper()}",
                                  f"/replay-outputs/{GOLDEN_HASH[2:]}", "/replay-outputs/%2e%2e"])
def test_replay_outputs_bad_hash_400(client, path):
    assert client.get(path).status_code == 400


def test_replay_outputs_missing_404(client):
    res = client.get("/replay-outputs/0x" + "ab" * 32)
    assert res.status_code == 404 and res.json()["detail"] == "Replay outputs not found"


def test_replay_outputs_route_is_read_only(client):
    assert client.post("/replay-outputs/0x" + "ab" * 32, content=b"{}", headers=AUTH).status_code == 405


def test_missing_file_404(client):
    assert client.get("/case-files/0x" + "ab" * 32).status_code == 404
    assert client.get("/replay-reports/0x" + "ab" * 32).status_code == 404


# --- auth (T-P-22) ------------------------------------------------------------------------------

WRITE_CALLS = [
    ("/case-files", {"content": GOLDEN_BYTES}),
    ("/replay-reports", {"content": b"{}"}),
    ("/stress/run", {"json": RUN}),
    ("/feed", {"json": {"actor": "watcher", "kind": "HASH_OK"}}),
]


@pytest.mark.parametrize("path,kwargs", WRITE_CALLS)
def test_write_routes_need_token(client, path, kwargs):
    assert client.post(path, **kwargs).status_code == 401
    assert client.post(path, headers={"Authorization": "Token abc"}, **kwargs).status_code == 401
    assert client.post(path, headers={"Authorization": "Bearer wrong"}, **kwargs).status_code == 403


# --- feed -----------------------------------------------------------------------------------------

def test_feed_seq_monotonic_and_paginated(client):
    seqs = [client.post("/feed", json={"actor": "watcher", "kind": "HASH_OK", "claimId": str(i)}, headers=AUTH).json()["seq"]
            for i in range(5)]
    assert seqs == sorted(seqs) and len(set(seqs)) == 5
    page = client.get("/feed", params={"since": seqs[1], "limit": 2}).json()
    assert [e["seq"] for e in page["entries"]] == seqs[2:4]
    assert page["nextSince"] == seqs[3]
    assert client.get("/feed", params={"since": seqs[-1]}).json() == {"entries": [], "nextSince": seqs[-1]}


def test_feed_entry_shape_matches_agent_client(client):
    entry = {"actor": "malicious_attester", "kind": "CLAIM_POSTED", "claimId": "7", "txHash": "0x" + "ab" * 32,
             "data": {"recomputedUsd8": "200000000001"}}
    assert client.post("/feed", json=entry, headers=AUTH).status_code == 201
    got = client.get("/feed").json()["entries"][-1]
    assert set(got) == {"actor", "claimId", "data", "kind", "seq", "ts", "txHash"}
    assert {k: got[k] for k in entry} == entry
    assert got["ts"].endswith("Z")


@pytest.mark.parametrize("entry", [
    {"actor": "stranger", "kind": "HASH_OK"},
    {"actor": "watcher", "kind": "NOT_A_KIND"},
    {"actor": "watcher", "kind": "HASH_OK", "claimId": 7},
    {"actor": "watcher", "kind": "HASH_OK", "claimId": "07"},
    {"actor": "watcher", "kind": "HASH_OK", "extra": 1},
])
def test_feed_rejects_invalid_entries(client, entry):
    assert client.post("/feed", json=entry, headers=AUTH).status_code == 422


def test_feed_survives_restart(harness):
    with harness.client() as c:
        first = [c.post("/feed", json={"actor": "attester", "kind": "CLAIM_POSTED"}, headers=AUTH).json()["seq"] for _ in range(3)]
    with harness.client() as c:
        after = c.post("/feed", json={"actor": "attester", "kind": "FINALIZED"}, headers=AUTH).json()["seq"]
        assert after > first[-1]
        assert [e["seq"] for e in c.get("/feed").json()["entries"]] == first + [after]


def test_file_feed_tolerates_torn_last_line(harness):
    if harness.backend != "filesystem":
        pytest.skip("file feed only")
    with harness.client() as c:
        c.post("/feed", json={"actor": "attester", "kind": "CLAIM_POSTED"}, headers=AUTH)
    with open(harness.data_dir / "feed.jsonl", "ab") as f:
        f.write(b'{"seq":2,"kind":"HALF')                         # crash mid-write
    with harness.client() as c:
        seq = c.post("/feed", json={"actor": "attester", "kind": "FINALIZED"}, headers=AUTH).json()["seq"]
        assert seq == 2
        assert [e["seq"] for e in c.get("/feed").json()["entries"]] == [1, 2]


# --- CORS and graph -------------------------------------------------------------------------------

def test_cors_only_configured_origins(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    assert ok.headers.get("access-control-allow-credentials") is None


def test_graph_exposure_without_tigergraph_is_503_not_mock_data(client):
    res = client.get(f"/graph/exposure?evidenceHash={GOLDEN_HASH}")
    body = res.json()
    assert res.status_code == 503 and body["status"] == "unavailable" and body["nodes"] == []
    assert "not configured" in body["detail"]


@pytest.mark.parametrize("query", ["", "?evidenceHash=0x123", f"?evidenceHash={GOLDEN_HASH.upper()}",
                                   f"?evidenceHash={GOLDEN_HASH}&top=0", f"?evidenceHash={GOLDEN_HASH}&top=51"])
def test_graph_exposure_validates_inputs(client, query):
    assert client.get(f"/graph/exposure{query}").status_code in (400, 422)


def test_import_has_no_filesystem_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib
    import stressproof_backend.main as main
    importlib.reload(main)
    assert list(tmp_path.iterdir()) == []
