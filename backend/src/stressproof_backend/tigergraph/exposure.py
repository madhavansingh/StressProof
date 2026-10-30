"""
Exposure read path for GET /graph/exposure (WP-5). Runs the installed read-only query sp_exposure and
re-checks its totals against the stored case file with Python big integers. Informational only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from stressproof_core.canonical_json import parse_strict

from .client import TigerGraphClient

QUERY = "sp_exposure"
TOTAL_KEYS = ("liquidatable_accounts", "residual_bad_debt_usd8", "liquidation_volume_usd8", "debt_at_risk_usd8")
RESULT_KEYS = {"liquidatable_accounts": "liquidatableAccounts", "residual_bad_debt_usd8": "residualBadDebtUsd8",
               "liquidation_volume_usd8": "liquidationVolumeUsd8", "debt_at_risk_usd8": "debtAtRiskUsd8"}
EXPOSURE_FIELDS = ("account_id", "origin", "data_class", "liquidatable", "debt_usd8", "collateral_usd8",
                   "collateral_value_usd8", "repaid_usd8", "residual_usd8")


class NotLoaded(LookupError):
    """The case file is not in the graph."""


def _flatten(results: List[Mapping[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for part in results:
        if isinstance(part, Mapping):
            merged.update(part)
    return merged


def _case_file_attrs(merged: Mapping[str, Any]) -> Dict[str, Any]:
    rows = merged.get("case_file") or []
    if not rows or not isinstance(rows[0], Mapping):
        return {}
    return dict(rows[0].get("attributes") or {})


def _reconcile(totals: Mapping[str, str], stored: Optional[bytes]) -> Dict[str, Any]:
    if stored is None:
        return {"status": "notChecked", "reason": "case file not stored on this backend", "checks": []}
    results = parse_strict(stored).get("results") or {}
    checks = []
    for key in TOTAL_KEYS:
        committed = str(results.get(RESULT_KEYS[key], ""))
        checks.append({"name": key, "tigergraph": totals[key], "caseFile": committed,
                       "matches": totals[key] == committed})
    return {"status": "matched" if all(c["matches"] for c in checks) else "mismatch", "checks": checks}


def exposure(client: TigerGraphClient, evidence_hash: str, top_n: int, stored_case_file: Optional[bytes]) -> Dict[str, Any]:
    merged = _flatten(client.run_query(QUERY, {"ev": evidence_hash, "top_n": str(top_n)}))
    case_file = _case_file_attrs(merged)
    if not case_file or int(merged.get("accounts") or 0) == 0:
        raise NotLoaded(evidence_hash)
    totals = {"accounts": str(int(merged["accounts"])), **{k: str(int(merged.get(k) or 0)) for k in TOTAL_KEYS}}
    top = [{f: row.get(f) for f in EXPOSURE_FIELDS} for row in merged.get("top_exposures") or []
           if isinstance(row, Mapping)]
    data_classes = sorted(str(c) for c in merged.get("data_classes") or [])
    return {
        "status": "ok",
        "source": "tigergraph",
        "label": "estimated exposure",
        "informationalOnly": True,
        "host": client.config.public_host,
        "graph": client.config.graph,
        "query": QUERY,
        "evidenceHash": evidence_hash,
        "dataClass": case_file.get("data_class"),
        "dataClasses": data_classes,
        "caseFile": {k: case_file.get(k) for k in ("dataset_id", "market_id", "shock_bps", "model_id")},
        "totals": totals,
        "topExposures": top,
        "reconciliation": _reconcile(totals, stored_case_file),
    }
