"""
Build TigerGraph rows from a case file and its deterministic replay (plan §17, C-05).

Every row comes from the case-file bytes or from stressproof_core.replay over them. Nothing is inferred:
there are no account-to-account edges and no claims unless claims are passed in from the chain.
Amounts stay as decimal strings (64-bit GSQL integers overflow for wei amounts, §17.1).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from stressproof_core.canonical_json import parse_strict
from stressproof_core.hashing import keccak256_hex
from stressproof_core.replay import replay

UINT = re.compile(r"^(0|[1-9][0-9]{0,77})$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
HASH = re.compile(r"^0x[0-9a-f]{64}$")

# Column order of every CSV file and of the upsert payloads. Keep in sync with tigergraph/schema.gsql.
VERTEX_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "Dataset": ("dataset_id", "data_class", "snapshot_hash", "fork_block", "network"),
    "Market": ("market_id", "dataset_id", "data_class"),
    "Asset": ("vid", "symbol", "role", "price_usd8", "lt_bps", "bonus_bps", "decimals", "dataset_id", "data_class"),
    "Account": ("vid", "account_id", "origin", "debt_usd8", "collateral_amount", "collateral_usd8", "dataset_id", "data_class"),
    "CaseFile": ("evidence_hash", "dataset_id", "market_id", "shock_bps", "model_id", "liquidatable_accounts",
                 "residual_bad_debt_usd8", "liquidation_volume_usd8", "debt_at_risk_usd8", "data_class"),
}
# (edge type, from vertex type, to vertex type, attribute columns)
EDGE_TYPES: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {
    "INCLUDED_IN": ("Account", "Dataset", ()),
    "COLLATERAL_IN": ("Account", "Asset", ("amount",)),
    "BORROWS": ("Account", "Asset", ("debt_usd8",)),
    "LISTS": ("Market", "Asset", ()),
    "REPLAYS": ("CaseFile", "Market", ()),
    "OUTCOME": ("CaseFile", "Account", ("collateral_value_usd8", "liquidatable", "repaid_usd8", "residual_usd8")),
}
INT_ATTRIBUTES = {"fork_block", "lt_bps", "bonus_bps", "decimals", "shock_bps", "liquidatable_accounts"}
BOOL_ATTRIBUTES = {"liquidatable"}


class GraphDataError(ValueError):
    """The source data cannot be turned into graph rows without guessing."""


@dataclass(frozen=True)
class GraphData:
    evidence_hash: str
    dataset_id: str
    data_class: str
    vertices: Dict[str, List[Dict[str, str]]]
    edges: Dict[str, List[Dict[str, str]]]  # rows carry "from" and "to" keys plus attributes
    expected: Dict[str, str] = field(default_factory=dict)  # totals the graph must reproduce


def _uint(value: Any, where: str) -> str:
    if not isinstance(value, str) or not UINT.match(value):
        raise GraphDataError(f"{where}: expected a non-negative integer string")
    return value


def _safe(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.match(value):
        raise GraphDataError(f"{where}: expected 1-128 characters of [A-Za-z0-9._:-]")
    return value


def _dataset_rows(cf: Mapping[str, Any]) -> Tuple[str, str, Dict[str, str]]:
    ds = cf["dataset"]
    dataset_id = _safe(ds["datasetId"], "dataset.datasetId")
    data_class = cf["dataClass"]
    if data_class not in ("SYNTHETIC", "REAL", "MIXED") or ds.get("dataClass") != data_class:
        raise GraphDataError("dataClass missing or inconsistent between case file and dataset")
    row = {"dataset_id": dataset_id, "data_class": data_class, "snapshot_hash": ds["snapshotHash"],
           "fork_block": str(int(ds["forkBlock"])), "network": _safe(ds["network"], "dataset.network")}
    return dataset_id, data_class, row


def _asset_rows(cf: Mapping[str, Any], dataset_id: str, data_class: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    symbol = _safe(cf["scenario"]["asset"], "scenario.asset")
    a = cf["snapshot"]["assets"][symbol]
    collateral = {"vid": f"{dataset_id}:{symbol}", "symbol": symbol, "role": "collateral",
                  "price_usd8": _uint(a["priceUsd8"], "asset.priceUsd8"), "lt_bps": str(int(a["ltBps"])),
                  "bonus_bps": str(int(a["bonusBps"])), "decimals": str(int(a["decimals"])),
                  "dataset_id": dataset_id, "data_class": data_class}
    symbols = [_safe(s["symbol"], "stablecoinAllowlist.symbol") for s in cf["dataset"]["stablecoinAllowlist"]]
    if not symbols:
        raise GraphDataError("dataset.stablecoinAllowlist is empty")
    # Debt is one USD total per account; the per-token split is not recorded, so one aggregate debt vertex.
    debt = {"vid": f"{dataset_id}:STABLE_DEBT", "symbol": "+".join(symbols), "role": "debt", "price_usd8": "",
            "lt_bps": "0", "bonus_bps": "0", "decimals": "0", "dataset_id": dataset_id, "data_class": data_class}
    return collateral, debt


def build_graph_data(raw_case_file: bytes) -> GraphData:
    """Rows for one case file. The evidence hash is keccak256 of the exact bytes given."""
    evidence_hash = keccak256_hex(raw_case_file)
    cf = parse_strict(raw_case_file)
    try:
        return _build(cf, evidence_hash)
    except (KeyError, TypeError) as exc:
        raise GraphDataError(f"case file is missing a field the graph needs: {exc}") from exc


def _build(cf: Mapping[str, Any], evidence_hash: str) -> GraphData:
    dataset_id, data_class, dataset = _dataset_rows(cf)
    market_id = _safe(cf["marketId"], "marketId")
    collateral, debt = _asset_rows(cf, dataset_id, data_class)
    result = replay(dict(cf))
    if result.to_results_dict() != cf["results"]:
        raise GraphDataError("replay of the case file does not reproduce its committed results")

    price, decimals = int(collateral["price_usd8"]), int(collateral["decimals"])
    accounts, edges = [], {name: [] for name in EDGE_TYPES}
    outcomes = {o.id: o for o in result.outcomes}
    seen = set()
    for i, acc in enumerate(cf["snapshot"]["accounts"]):
        account_id = _safe(acc["id"], f"snapshot.accounts[{i}].id")
        if account_id in seen:
            raise GraphDataError(f"duplicate account id {account_id}")
        seen.add(account_id)
        vid = f"{dataset_id}:{account_id}"
        amount = _uint(acc["collateralAmount"], f"{account_id}.collateralAmount")
        debt_usd8 = _uint(acc["debtUsd8"], f"{account_id}.debtUsd8")
        accounts.append({"vid": vid, "account_id": account_id, "origin": _safe(acc["origin"], f"{account_id}.origin"),
                         "debt_usd8": debt_usd8, "collateral_amount": amount,
                         "collateral_usd8": str(int(amount) * price // 10 ** decimals),  # unshocked, §17.2
                         "dataset_id": dataset_id, "data_class": data_class})
        edges["INCLUDED_IN"].append({"from": vid, "to": dataset_id})
        if int(amount) > 0:
            edges["COLLATERAL_IN"].append({"from": vid, "to": collateral["vid"], "amount": amount})
        if int(debt_usd8) > 0:
            edges["BORROWS"].append({"from": vid, "to": debt["vid"], "debt_usd8": debt_usd8})
        o = outcomes[account_id]
        edges["OUTCOME"].append({"from": evidence_hash, "to": vid, "collateral_value_usd8": str(o.collateral_value_usd8),
                                 "liquidatable": "true" if o.liquidatable else "false",
                                 "repaid_usd8": str(o.repaid_usd8), "residual_usd8": str(o.residual_usd8)})

    edges["LISTS"] = [{"from": market_id, "to": collateral["vid"]}, {"from": market_id, "to": debt["vid"]}]
    edges["REPLAYS"] = [{"from": evidence_hash, "to": market_id}]
    results = cf["results"]
    case_file = {"evidence_hash": evidence_hash, "dataset_id": dataset_id, "market_id": market_id,
                 "shock_bps": str(int(cf["scenario"]["shockBps"])), "model_id": _safe(cf["model"]["id"], "model.id"),
                 "liquidatable_accounts": str(int(results["liquidatableAccounts"])),
                 "residual_bad_debt_usd8": _uint(results["residualBadDebtUsd8"], "results.residualBadDebtUsd8"),
                 "liquidation_volume_usd8": _uint(results["liquidationVolumeUsd8"], "results.liquidationVolumeUsd8"),
                 "debt_at_risk_usd8": _uint(results["debtAtRiskUsd8"], "results.debtAtRiskUsd8"),
                 "data_class": data_class}
    expected = {"accounts": str(len(accounts)),
                "debt_usd8": str(sum(int(a["debt_usd8"]) for a in accounts)),
                "collateral_amount": str(sum(int(a["collateral_amount"]) for a in accounts)),
                **{k: case_file[k] for k in ("liquidatable_accounts", "residual_bad_debt_usd8",
                                             "liquidation_volume_usd8", "debt_at_risk_usd8")}}
    return GraphData(
        evidence_hash=evidence_hash, dataset_id=dataset_id, data_class=data_class,
        vertices={"Dataset": [dataset], "Market": [{"market_id": market_id, "dataset_id": dataset_id, "data_class": data_class}],
                  "Asset": [collateral, debt], "Account": accounts, "CaseFile": [case_file]},
        edges=edges, expected=expected,
    )


def validate_graph_data(data: GraphData) -> List[str]:
    """Referential and total checks on generated rows. Returns problems; an empty list means valid."""
    problems: List[str] = []
    ids = {vtype: [r[cols[0]] for r in data.vertices.get(vtype, [])] for vtype, cols in VERTEX_COLUMNS.items()}
    for vtype, values in ids.items():
        if len(values) != len(set(values)):
            problems.append(f"duplicate {vtype} primary ids")
    for name, (src, dst, _) in EDGE_TYPES.items():
        for row in data.edges.get(name, []):
            if row["from"] not in ids[src] or row["to"] not in ids[dst]:
                problems.append(f"{name} {row['from']} -> {row['to']} points at a missing vertex")
    outcome = data.edges.get("OUTCOME", [])
    sums = {
        "accounts": str(len(ids["Account"])),
        "liquidatable_accounts": str(sum(r["liquidatable"] == "true" for r in outcome)),
        "residual_bad_debt_usd8": str(sum(int(r["residual_usd8"]) for r in outcome)),
        "liquidation_volume_usd8": str(sum(int(r["repaid_usd8"]) for r in outcome)),
    }
    for key, value in sums.items():
        if value != data.expected.get(key):
            problems.append(f"{key}: rows give {value}, case file says {data.expected.get(key)}")
    if any(r.get("data_class") != data.data_class for rows in data.vertices.values() for r in rows):
        problems.append("a vertex lost its data_class label")
    return problems


def to_csv(rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(columns), lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row[c] for c in columns})
    return out.getvalue()


def csv_files(data: GraphData) -> Dict[str, str]:
    """File name -> CSV text for every vertex and edge type (deterministic order)."""
    files = {f"vertex_{vtype}.csv": to_csv(data.vertices[vtype], cols) for vtype, cols in VERTEX_COLUMNS.items()}
    for name, (_, _, attrs) in EDGE_TYPES.items():
        files[f"edge_{name}.csv"] = to_csv(data.edges[name], ("from", "to", *attrs))
    return files

