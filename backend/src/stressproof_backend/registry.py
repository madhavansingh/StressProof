"""
Dataset registry: loads <root>/<datasetId>/{dataset_manifest.json, snapshot.json} from each
dataset root, in order, and caches them.

A dataset is loaded only if both files are canonical JSON, the manifest has the plan §8.1 key
set and names its own directory, and keccak256(snapshot.json) equals manifest.snapshotHash.
Anything else is skipped and logged. When two roots hold the same id, the first root wins.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from stressproof_core.canonical_json import parse_strict
from stressproof_core.hashing import keccak256_hex
from stressproof_core.models import DatasetManifest

logger = logging.getLogger(__name__)

DATASET_ID_REGEX = re.compile(r"^[a-z0-9-]{1,80}$")
MANIFEST_KEYS = frozenset(DatasetManifest.__annotations__)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    manifest: dict
    manifest_bytes: bytes
    snapshot: dict
    root: Path

    def summary(self) -> dict:
        m = self.manifest
        return {
            "counts": m["counts"],
            "dataClass": m["dataClass"],
            "datasetId": self.dataset_id,
            "forkBlock": m["forkBlock"],
            "snapshotHash": m["snapshotHash"],
        }


def _load_one(directory: Path) -> Dataset:
    manifest_bytes = (directory / "dataset_manifest.json").read_bytes()
    snapshot_bytes = (directory / "snapshot.json").read_bytes()
    manifest = parse_strict(manifest_bytes)
    snapshot = parse_strict(snapshot_bytes)
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("manifest does not have the plan §8.1 key set")
    if manifest["datasetId"] != directory.name:
        raise ValueError(f"manifest datasetId {manifest['datasetId']!r} != directory name")
    if keccak256_hex(snapshot_bytes) != manifest["snapshotHash"]:
        raise ValueError("keccak256(snapshot.json) != manifest.snapshotHash")
    if not isinstance(snapshot, dict) or set(snapshot) != {"accounts", "assets"}:
        raise ValueError("snapshot must have exactly accounts and assets")
    return Dataset(directory.name, manifest, manifest_bytes, snapshot, directory.parent)


class DatasetRegistry:
    def __init__(self, roots: List[Path]):
        self.roots = [Path(r) for r in roots]
        self._datasets: Dict[str, Dataset] = {}
        self.load()

    def load(self) -> None:
        found: Dict[str, Dataset] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for directory in sorted(p for p in root.iterdir() if p.is_dir()):
                if not DATASET_ID_REGEX.match(directory.name):
                    continue
                if not (directory / "dataset_manifest.json").exists() or not (directory / "snapshot.json").exists():
                    continue
                if directory.name in found:
                    logger.warning("dataset %s in %s ignored: already loaded from %s",
                                   directory.name, root, found[directory.name].root)
                    continue
                try:
                    found[directory.name] = _load_one(directory)
                except (OSError, ValueError, KeyError, TypeError) as e:
                    logger.error("dataset %s in %s skipped: %s", directory.name, root, e)
        self._datasets = found
        logger.info("loaded %d dataset(s): %s", len(found), ", ".join(sorted(found)) or "none")

    def ids(self) -> List[str]:
        return sorted(self._datasets)

    def all(self) -> List[Dataset]:
        return [self._datasets[i] for i in self.ids()]

    def get(self, dataset_id: str) -> Optional[Dataset]:
        return self._datasets.get(dataset_id)
