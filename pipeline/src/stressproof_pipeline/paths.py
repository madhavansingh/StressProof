"""
Filesystem layout for pipeline outputs.

DATA_DIR (env) overrides the data root; a relative value resolves against the repo root,
never the current directory. Datasets live in <DATA_DIR>/datasets/<datasetId>/.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

DATASET_ID_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")

# File names inside a dataset directory (implementationplan.md §4 data/ layout).
REAL_ACCOUNTS = "real_accounts.jsonl"
SYNTHETIC_ACCOUNTS = "synthetic_accounts.jsonl"
ASSETS = "assets.json"
DRAFT_MANIFEST = "dataset_manifest.draft.json"
MANIFEST = "dataset_manifest.json"
SNAPSHOT = "snapshot.json"
SWEEP = "sweep.json"


def load_env() -> None:
    """Load <repo>/.env without overriding variables already set in the environment."""
    load_dotenv(REPO_ROOT / ".env", override=False)


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR")
    if not raw:
        return REPO_ROOT / "data"
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def datasets_dir() -> Path:
    return data_dir() / "datasets"


def dataset_dir(dataset_id: str) -> Path:
    if not isinstance(dataset_id, str) or not DATASET_ID_REGEX.match(dataset_id):
        raise ValueError(f"invalid datasetId {dataset_id!r}: lowercase letters, digits and '-' only, max 80 chars")
    return datasets_dir() / dataset_id
