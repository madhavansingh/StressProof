"""
TigerGraph setup and load commands. Credentials come only from the environment (repo .env); nothing secret is
printed.

    uv run python -m stressproof_backend.tigergraph.cli export      # write tigergraph/data/*.csv (no network)
    uv run python -m stressproof_backend.tigergraph.cli check       # token + REST++ echo
    uv run python -m stressproof_backend.tigergraph.cli schema      # apply tigergraph/schema.gsql
    uv run python -m stressproof_backend.tigergraph.cli install     # create + install sp_exposure
    uv run python -m stressproof_backend.tigergraph.cli load        # idempotent upsert of the fixture
    uv run python -m stressproof_backend.tigergraph.cli reconcile   # read back; exit 1 on any mismatch
    uv run python -m stressproof_backend.tigergraph.cli query       # run sp_exposure, print the JSON

Options: --case-file PATH (default: the golden SYNTHETIC fixture data/fixtures/casefile_v1.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from ..config import REPO_ROOT, Settings
from .client import TigerGraphClient, TigerGraphConfig, TigerGraphError
from .graph_data import GraphDataError, build_graph_data, validate_graph_data
from .loader import csvs_match, expected_counts, load, reconcile, write_csvs

GOLDEN = REPO_ROOT / "data" / "fixtures" / "casefile_v1.json"
CSV_DIR = REPO_ROOT / "tigergraph" / "data"
SCHEMA = REPO_ROOT / "tigergraph" / "schema.gsql"
QUERY = REPO_ROOT / "tigergraph" / "queries" / "sp_exposure.gsql"


def _client() -> TigerGraphClient:
    config = TigerGraphConfig.from_settings(Settings())
    if config is None:
        raise TigerGraphError("TG_HOST is not set (repo .env)")
    return TigerGraphClient(config)


def _gsql_ok(output: str) -> bool:
    lowered = output.lower()
    return not any(w in lowered for w in ("error", "failed", "semantic check fails", "exception"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="stressproof-tigergraph")
    parser.add_argument("command", choices=["export", "check", "schema", "install", "load", "reconcile", "query"])
    parser.add_argument("--case-file", type=Path, default=GOLDEN)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        data = build_graph_data(args.case_file.read_bytes())
        problems = validate_graph_data(data)
        if problems:
            print("INVALID graph data:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        if args.command == "export":
            for path in write_csvs(data, CSV_DIR):
                print(f"wrote {path.relative_to(REPO_ROOT)}")
            print(json.dumps({"evidenceHash": data.evidence_hash, "dataClass": data.data_class,
                              **expected_counts(data), "expected": data.expected}, indent=2))
            return 0
        with _client() as client:
            if args.command == "check":
                client.token()
                client.echo()
                print(f"connected: {client.config.public_host} graph={client.config.graph}")
            elif args.command in ("schema", "install"):
                text = (SCHEMA if args.command == "schema" else QUERY).read_text(encoding="utf-8")
                out = client.gsql(text)
                print(out[-4000:])
                if not _gsql_ok(out) and "already exist" not in out.lower():
                    return 1
            elif args.command == "load":
                stale = csvs_match(data, CSV_DIR) if args.case_file == GOLDEN else []
                if stale:
                    print(f"committed CSVs differ from the fixture; run export first: {stale}", file=sys.stderr)
                    return 1
                result = load(client, data)
                print(json.dumps({**result, "expected": expected_counts(data)}, indent=2))
            elif args.command == "reconcile":
                report = reconcile(client, data)
                print(json.dumps(report, indent=2))
                return 0 if report["ok"] else 1
            elif args.command == "query":
                rows = client.run_query("sp_exposure", {"ev": data.evidence_hash, "top_n": str(args.top)})
                print(json.dumps(rows, indent=2))
        return 0
    except (TigerGraphError, GraphDataError, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
