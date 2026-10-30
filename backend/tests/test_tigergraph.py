"""
TigerGraph integration tests (WP-2..5) against a fake TigerGraph built on httpx.MockTransport: they check the
exact REST calls and payloads, not a live database. The live check is the CLI (see tigergraph/README.md).
"""

import json

import httpx
import pytest

from backend_harness import AUTH, REPO_ROOT
from stressproof_backend.tigergraph.client import TigerGraphClient, TigerGraphConfig, TigerGraphError
from stressproof_backend.tigergraph.exposure import NotLoaded, exposure
from stressproof_backend.tigergraph.graph_data import (GraphDataError, build_graph_data, csv_files,
                                                         validate_graph_data)
from stressproof_backend.tigergraph.loader import csvs_match, edge_payload, load, reconcile, vertex_payload

GOLDEN_BYTES = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.json").read_bytes()
GOLDEN_HASH = (REPO_ROOT / "data" / "fixtures" / "casefile_v1.keccak").read_text().strip()
HOST = "https://ws-test.i.tgcloud.io"
SECRET = "test-secret-value-not-real"
TOKEN = "tok_test_0123456789"


def config(**kw):
    return TigerGraphConfig(**{"host": HOST, "graph": "StressProof", "secret": SECRET, **kw})


class FakeTigerGraph:
    """Holds upserted vertices and answers the REST calls the client makes."""

    def __init__(self, token_route="/gsql/v1/tokens"):
        self.token_route = token_route
        self.calls = []
        self.vertices = {}
        self.edges = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.calls.append((req.method, path))
        if path in ("/gsql/v1/tokens", "/restpp/requesttoken"):
            if path != self.token_route:
                return httpx.Response(404, json={"error": True, "message": "Route not found"})
            if json.loads(req.content)["secret"] != SECRET:
                return httpx.Response(401, json={"error": True, "message": "bad secret"})
            return httpx.Response(200, json={"error": False, "token": TOKEN})
        if req.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"error": True, "message": "unauthorized"})
        if path == "/restpp/echo":
            return httpx.Response(200, json={"error": False, "message": "Hello GSQL"})
        if path == "/restpp/graph/StressProof" and req.method == "POST":
            body = json.loads(req.content)
            nv = 0
            for vtype, rows in body.get("vertices", {}).items():
                for vid, attrs in rows.items():
                    self.vertices.setdefault(vtype, {})[vid] = {k: v["value"] for k, v in attrs.items()}
                    nv += 1
            ne = 0
            for stype, srcs in body.get("edges", {}).items():
                for sid, etypes in srcs.items():
                    for etype, ttypes in etypes.items():
                        for ttype, tgts in ttypes.items():
                            for tid, attrs in tgts.items():
                                assert tid in self.vertices[ttype] and sid in self.vertices[stype]
                                key = (stype, sid, etype, ttype, tid)
                                self.edges = [e for e in self.edges if e[0] != key] + [(key, attrs)]
                                ne += 1
            return httpx.Response(200, json={"error": False, "results": [{"accepted_vertices": nv, "accepted_edges": ne}]})
        if path.startswith("/restpp/graph/StressProof/vertices/"):
            vtype = path.rsplit("/", 1)[1]
            key, value = req.url.params["filter"].split("=", 1)
            value = value.strip('"')
            rows = [{"v_id": vid, "attributes": a} for vid, a in self.vertices.get(vtype, {}).items() if a.get(key, vid) == value or vid == value]
            return httpx.Response(200, json={"error": False, "results": rows})
        if path == "/restpp/query/StressProof/sp_exposure":
            return httpx.Response(200, json={"error": False, "results": self.run_exposure(req.url.params["ev"], int(req.url.params["top_n"]))})
        return httpx.Response(404, json={"error": True, "message": f"no route {path}"})

    def run_exposure(self, ev, top_n):
        """What the GSQL query computes, over the stored rows (mirrors tigergraph/queries/sp_exposure.gsql)."""
        cf = self.vertices.get("SP_CaseFile", {}).get(ev)
        outs = [(k[4], a) for k, a in self.edges if k[1] == ev and k[2] == "SP_OUTCOME"]
        accts = self.vertices.get("SP_Account", {})
        top = sorted(outs, key=lambda o: (-int(o[1]["residual_usd8"]["value"]), -int(accts[o[0]]["debt_usd8"])))[:top_n]
        return [
            {"case_file": [{"v_id": ev, "attributes": cf}] if cf else []},
            {"accounts": len(outs),
             "liquidatable_accounts": sum(a["liquidatable"]["value"] for _, a in outs),
             "residual_bad_debt_usd8": sum(int(a["residual_usd8"]["value"]) for _, a in outs),
             "liquidation_volume_usd8": sum(int(a["repaid_usd8"]["value"]) for _, a in outs),
             "debt_at_risk_usd8": sum(int(accts[v]["debt_usd8"]) for v, a in outs if a["liquidatable"]["value"]),
             "data_classes": sorted({accts[v]["data_class"] for v, _ in outs}),
             "top_exposures": [{"account_id": accts[v]["account_id"], "origin": accts[v]["origin"],
                                "data_class": accts[v]["data_class"], "liquidatable": a["liquidatable"]["value"],
                                "debt_usd8": accts[v]["debt_usd8"], "collateral_usd8": accts[v]["collateral_usd8"],
                                "collateral_value_usd8": a["collateral_value_usd8"]["value"],
                                "repaid_usd8": a["repaid_usd8"]["value"], "residual_usd8": a["residual_usd8"]["value"],
                                "residual_sort": 0, "debt_sort": 0} for v, a in top]},
        ]


def client_for(fake, **kw):
    return TigerGraphClient(config(**kw), transport=httpx.MockTransport(fake))


# --- graph data and CSVs ----------------------------------------------------------------------

def test_graph_data_from_golden_fixture_is_valid_and_synthetic():
    data = build_graph_data(GOLDEN_BYTES)
    assert data.evidence_hash == GOLDEN_HASH and data.data_class == "SYNTHETIC"
    assert validate_graph_data(data) == []
    assert {k: len(v) for k, v in data.vertices.items()} == {"Dataset": 1, "Market": 1, "Asset": 2, "Account": 6, "CaseFile": 1}
    assert {k: len(v) for k, v in data.edges.items()} == {"INCLUDED_IN": 6, "COLLATERAL_IN": 6, "BORROWS": 6,
                                                         "LISTS": 2, "REPLAYS": 1, "OUTCOME": 6}
    assert all(r["data_class"] == "SYNTHETIC" for rows in data.vertices.values() for r in rows)
    assert data.expected == {"accounts": "6", "debt_usd8": "4548600000002", "collateral_amount": "27000000000000000001",
                             "liquidatable_accounts": "4", "residual_bad_debt_usd8": "200000000001",
                             "liquidation_volume_usd8": "3174300000001", "debt_at_risk_usd8": "3374300000002"}


def test_committed_csvs_match_the_fixture():
    assert csvs_match(build_graph_data(GOLDEN_BYTES), REPO_ROOT / "tigergraph" / "data") == []


def test_tampered_results_are_rejected():
    raw = json.loads(GOLDEN_BYTES)
    raw["results"]["residualBadDebtUsd8"] = "1"
    from stressproof_core.canonical_json import canonical_bytes
    with pytest.raises(GraphDataError, match="does not reproduce"):
        build_graph_data(canonical_bytes(raw))


def test_bad_account_id_is_rejected():
    raw = json.loads(GOLDEN_BYTES)
    raw["snapshot"]["accounts"][0]["id"] = 'x" OR 1=1'
    from stressproof_core.canonical_json import canonical_bytes
    with pytest.raises(GraphDataError):
        build_graph_data(canonical_bytes(raw))


def test_validation_catches_dangling_edges_and_total_drift():
    data = build_graph_data(GOLDEN_BYTES)
    data.edges["OUTCOME"].append({"from": GOLDEN_HASH, "to": "missing", "collateral_value_usd8": "0",
                                  "liquidatable": "false", "repaid_usd8": "0", "residual_usd8": "5"})
    problems = validate_graph_data(data)
    assert any("missing vertex" in p for p in problems) and any("residual_bad_debt_usd8" in p for p in problems)


def test_csv_files_cover_every_type():
    files = csv_files(build_graph_data(GOLDEN_BYTES))
    assert len(files) == 11 and files["vertex_Account.csv"].splitlines()[0].startswith("vid,account_id")


def test_schema_declares_every_type_used():
    schema = (REPO_ROOT / "tigergraph" / "schema.gsql").read_text()
    payload = {**vertex_payload(build_graph_data(GOLDEN_BYTES)), **edge_payload(build_graph_data(GOLDEN_BYTES))}
    used = set(payload["vertices"]) | {e for src in payload["edges"].values() for es in src.values() for e in es}
    for name in used:
        assert f" {name} (" in schema, name
    query = "\n".join(l for l in (REPO_ROOT / "tigergraph" / "queries" / "sp_exposure.gsql").read_text().splitlines()
                      if not l.lstrip().startswith("//"))
    for forbidden in ("INSERT", "DELETE", "UPDATE", "POST-ACCUM"):
        assert forbidden not in query  # the read query writes nothing


# --- client ---------------------------------------------------------------------------------------

def test_config_requires_https_origin_and_credentials():
    for bad in ({"host": "http://ws.i.tgcloud.io"}, {"host": "https://ws.i.tgcloud.io/restpp"},
                {"graph": "Stress Proof"}, {"secret": "", "token": ""}):
        with pytest.raises(TigerGraphError):
            TigerGraphClient(config(**bad))


@pytest.mark.parametrize("route", ["/gsql/v1/tokens", "/restpp/requesttoken"])
def test_token_from_secret_on_either_route(route):
    fake = FakeTigerGraph(token_route=route)
    with client_for(fake) as c:
        assert c.token() == TOKEN and c.echo()["message"] == "Hello GSQL"


def test_bad_secret_fails_without_leaking_it():
    with client_for(FakeTigerGraph(), secret="wrong-secret") as c, pytest.raises(TigerGraphError) as exc:
        c.token()
    assert "wrong-secret" not in str(exc.value) and SECRET not in str(exc.value)


def test_unreachable_host_is_a_clean_error():
    def boom(req):
        raise httpx.ConnectError("refused")
    with TigerGraphClient(config(), transport=httpx.MockTransport(boom)) as c, pytest.raises(TigerGraphError, match="cannot reach"):
        c.token()


# --- load, reconcile, query --------------------------------------------------------------------------

def test_load_is_idempotent_and_reconciles():
    fake, data = FakeTigerGraph(), build_graph_data(GOLDEN_BYTES)
    with client_for(fake) as c:
        first = load(c, data)
        second = load(c, data)
        report = reconcile(c, data)
    assert first == second == {"accepted_vertices": 11, "accepted_edges": 27}
    assert len(fake.edges) == 27 and sum(len(v) for v in fake.vertices.values()) == 11
    assert report["ok"] is True and report["diffs"] == {}


def test_reconcile_fails_loudly_on_drift():
    fake, data = FakeTigerGraph(), build_graph_data(GOLDEN_BYTES)
    with client_for(fake) as c:
        load(c, data)
        fake.vertices["SP_Account"]["weth-stable-fixture-v1:synth-0001"]["debt_usd8"] = "1"
        fake.vertices["SP_Account"]["weth-stable-fixture-v1:synth-0002"]["data_class"] = "REAL"
        report = reconcile(c, data)
    assert report["ok"] is False and set(report["diffs"]) == {"debt_usd8", "data_class"}


def test_exposure_returns_query_results_and_reconciles_with_the_case_file():
    fake, data = FakeTigerGraph(), build_graph_data(GOLDEN_BYTES)
    with client_for(fake) as c:
        load(c, data)
        out = exposure(c, GOLDEN_HASH, 3, GOLDEN_BYTES)
    assert out["source"] == "tigergraph" and out["dataClass"] == "SYNTHETIC" and out["informationalOnly"] is True
    assert out["totals"] == {"accounts": "6", "liquidatable_accounts": "4", "residual_bad_debt_usd8": "200000000001",
                             "liquidation_volume_usd8": "3174300000001", "debt_at_risk_usd8": "3374300000002"}
    assert [r["account_id"] for r in out["topExposures"]] == ["synth-0002", "synth-0006", "synth-0001"]
    assert out["reconciliation"]["status"] == "matched"
    assert ("GET", "/restpp/query/StressProof/sp_exposure") in fake.calls


def test_exposure_for_an_unloaded_case_file_is_not_loaded():
    with client_for(FakeTigerGraph()) as c, pytest.raises(NotLoaded):
        exposure(c, "0x" + "ab" * 32, 5, None)


# --- route with a fake TigerGraph -------------------------------------------------------------------

def _route_client(harness, fake, monkeypatch):
    real = TigerGraphClient.__init__

    def init(self, cfg, transport=None):
        real(self, cfg, transport=httpx.MockTransport(fake))
    monkeypatch.setattr(TigerGraphClient, "__init__", init)
    return harness.client(TG_HOST=HOST, TG_SECRET=SECRET)


def test_route_serves_live_query_results(harness, monkeypatch):
    fake = FakeTigerGraph()
    with client_for(fake) as c:
        load(c, build_graph_data(GOLDEN_BYTES))
    with _route_client(harness, fake, monkeypatch) as client:
        assert client.post("/case-files", content=GOLDEN_BYTES, headers=AUTH).status_code in (200, 201)
        res = client.get(f"/graph/exposure?evidenceHash={GOLDEN_HASH}&top=2")
        missing = client.get(f"/graph/exposure?evidenceHash=0x{'cd' * 32}")
    body = res.json()
    assert res.status_code == 200 and body["source"] == "tigergraph" and body["host"] == "ws-test.i.tgcloud.io"
    assert body["reconciliation"]["status"] == "matched"
    assert len(body["topExposures"]) == 2 and SECRET not in res.text and TOKEN not in res.text
    assert missing.status_code == 404 and missing.json()["status"] == "notLoaded"


def test_route_reports_tigergraph_failure_as_unavailable(harness, monkeypatch):
    def down(req):
        return httpx.Response(503, json={"error": True, "message": "workspace is paused"})
    with _route_client(harness, down, monkeypatch) as client:
        res = client.get(f"/graph/exposure?evidenceHash={GOLDEN_HASH}")
    assert res.status_code == 503 and res.json()["status"] == "unavailable" and SECRET not in res.text
