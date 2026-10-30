"""
Content-addressed raw byte storage.
Matches implementationplan.md §14 & §16.1.

Files are named by the keccak256 of their exact bytes, written atomically, and never
mutated or deleted. Readers always hash what they fetch, so the store is not trusted.
"""

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from stressproof_core.hashing import keccak256_hex

HASH_REGEX = re.compile(r"^0x[0-9a-f]{64}$")

CASE_FILES = "case-files"
REPLAY_REPORTS = "replay-reports"
REPLAY_OUTPUTS = "replay_outputs"


class StoreConflict(Exception):
    """An existing file under a hash does not hold the bytes for that hash (corruption)."""


@dataclass(frozen=True)
class PutResult:
    hash: str
    created: bool


def atomic_write(path: Path, data: bytes) -> None:
    """Unique temp file in the destination directory, fsync, os.replace; temp removed on failure."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


class ContentStore:
    """Filesystem backend (default when DATABASE_URL is unset). Same async interface as PostgresStore."""

    kind = "filesystem"

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self._dirs = {
            CASE_FILES: self.base_dir / CASE_FILES,
            REPLAY_REPORTS: self.base_dir / REPLAY_REPORTS,
            REPLAY_OUTPUTS: self.base_dir / REPLAY_OUTPUTS,
        }
        for d in self._dirs.values():
            d.mkdir(parents=True, exist_ok=True)

    async def open(self) -> None:
        self.check_writable()

    async def close(self) -> None:
        return None

    def check_writable(self) -> None:
        """Fail at startup, not on the first claim, if DATA_DIR cannot be written."""
        for d in self._dirs.values():
            fd, probe = tempfile.mkstemp(dir=d, prefix=".write-probe.")
            os.close(fd)
            os.unlink(probe)

    def _put(self, kind: str, raw: bytes, suffix: str = ".json", name: Optional[str] = None) -> PutResult:
        h = keccak256_hex(raw)
        dest = self._dirs[kind] / f"{name or h}{suffix}"
        if dest.exists():
            if dest.read_bytes() != raw:
                raise StoreConflict(f"{dest} exists with different bytes")
            return PutResult(h, created=False)
        atomic_write(dest, raw)
        return PutResult(h, created=True)

    def _get(self, kind: str, h: str) -> Optional[bytes]:
        if not isinstance(h, str) or not HASH_REGEX.match(h):
            return None
        target = self._dirs[kind] / f"{h}.json"
        try:
            return target.read_bytes()
        except FileNotFoundError:
            return None

    async def put_case_file(self, raw: bytes) -> PutResult:
        return self._put(CASE_FILES, raw)

    async def get_case_file(self, h: str) -> Optional[bytes]:
        return self._get(CASE_FILES, h)

    async def put_replay_report(self, raw: bytes) -> PutResult:
        return self._put(REPLAY_REPORTS, raw)

    async def get_replay_report(self, h: str) -> Optional[bytes]:
        return self._get(REPLAY_REPORTS, h)

    async def put_replay_outputs(self, evidence_hash: str, raw: bytes) -> None:
        """Per-account outcomes (plan §8.5), keyed by the case file's evidenceHash; derived data."""
        if not HASH_REGEX.match(evidence_hash):
            raise ValueError("malformed evidence hash")
        dest = self._dirs[REPLAY_OUTPUTS] / f"{evidence_hash}.jsonl"
        if not dest.exists():
            atomic_write(dest, raw)

    async def get_replay_outputs(self, evidence_hash: str) -> Optional[bytes]:
        """Stored per-account outcomes for an evidenceHash, or None (WP-6 graph; read-only)."""
        if not isinstance(evidence_hash, str) or not HASH_REGEX.match(evidence_hash):
            return None
        try:
            return (self._dirs[REPLAY_OUTPUTS] / f"{evidence_hash}.jsonl").read_bytes()
        except FileNotFoundError:
            return None
