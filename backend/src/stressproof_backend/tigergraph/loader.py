"""
Idempotent load (WP-3, plan §17.2) and reconciliation (§17.3).

Loading upserts by primary id, so re-running overwrites the same vertices and edges. Reconciliation reads the
graph back and compares counts and big-integer totals with the case file and its deterministic replay; any
difference is a failure (the plan's "fail loudly").
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .client import TigerGraphClient
from .graph_data import BOOL_ATTRIBUTES, EDGE_TYPES, INT_ATTRIBUTES, VERTEX_COLUMNS, GraphData, csv_files

PREFIX = "SP_"


def tg_type(name: str) -> str:
    return f"{PREFIX}{name}"


def _value(column: str, raw: str) -> Any:
    if column in INT_ATTRIBUTES:
        return int(raw)
    if column in BOOL_ATTRIBUTES:
        return raw == "true"
    return raw


def vertex_payload(data: GraphData) -> Dict[str, Any]:
    vertices: Dict[str, Dict[str, Any]] = {}
    for vtype, cols in VERTEX_COLUMNS.items():
        key, attrs = cols[0], cols[1:]
        vertices[tg_type(vtype)] = {
            row[key]: {c: {"value": _value(c, row[c])} for c in attrs} for row in data.vertices[vtype]
        }
    return {"vertices": vertices}


def edge_payload(data: GraphData) -> Dict[str, Any]:
    edges: Dict[str, Dict[str, Any]] = {}
    for name, (src, dst, attrs) in EDGE_TYPES.items():
        for row in data.edges[name]:
            target = (edges.setdefault(tg_type(src), {}).setdefault(row["from"], {})
                      .setdefault(tg_type(name), {}).setdefault(tg_type(dst), {}))
            target[row["to"]] = {c: {"value": _value(c, row[c])} for c in attrs}
    return {"edges": edges}


def expected_counts(data: GraphData) -> Dict[str, int]:
    return {"vertices": sum(len(v) for v in data.vertices.values()),
            "edges": sum(len(e) for e in data.edges.values())}


def write_csvs(data: GraphData, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in csv_files(data).items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def csvs_match(data: GraphData, csv_dir: Path) -> List[str]:
    """Names of committed CSV files that differ from the rows generated from the case file."""
    return [name for name, text in csv_files(data).items()
            if not (csv_dir / name).is_file() or (csv_dir / name).read_text(encoding="utf-8") != text]


def load(client: TigerGraphClient, data: GraphData) -> Dict[str, int]:
    """Upsert vertices, then edges (edges require their vertices to exist)."""
    v = client.upsert(vertex_payload(data))
    e = client.upsert(edge_payload(data))
    return {"accepted_vertices": v["accepted_vertices"], "accepted_edges": e["accepted_edges"]}


def _attrs(rows: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [r.get("attributes") or {} for r in rows]


def reconcile(client: TigerGraphClient, data: GraphData) -> Dict[str, Any]:
    """Read the graph back and compare it with the case file and replay. Returns a report; ok=False on any diff."""
    ds = data.dataset_id
    accounts = _attrs(client.vertices(tg_type("Account"), {"dataset_id": ds}))
    case_files = _attrs(client.vertices(tg_type("CaseFile"), {"evidence_hash": data.evidence_hash}))
    graph = {
        "accounts": str(len(accounts)),
        "debt_usd8": str(sum(int(a.get("debt_usd8", "0")) for a in accounts)),
        "collateral_amount": str(sum(int(a.get("collateral_amount", "0")) for a in accounts)),
    }
    if case_files:
        cf = case_files[0]
        for key in ("residual_bad_debt_usd8", "liquidation_volume_usd8", "debt_at_risk_usd8"):
            graph[key] = str(cf.get(key, ""))
        graph["liquidatable_accounts"] = str(cf.get("liquidatable_accounts", ""))
    labels = sorted({str(a.get("data_class")) for a in accounts})
    diffs = {k: {"graph": graph.get(k), "expected": v} for k, v in data.expected.items() if graph.get(k) != v}
    if labels != [data.data_class]:
        diffs["data_class"] = {"graph": ",".join(labels), "expected": data.data_class}
    return {"ok": not diffs, "evidenceHash": data.evidence_hash, "datasetId": ds, "graph": graph,
            "expected": data.expected, "diffs": diffs}


def read_csv(text: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))
