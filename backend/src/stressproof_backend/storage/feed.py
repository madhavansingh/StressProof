"""
Append-only agent feed (implementationplan.md §8.6, C-04), stored as DATA_DIR/feed.jsonl.

seq is assigned under an asyncio.Lock and an OS file lock (flock). The plan runs one backend
process; the file lock keeps seq unique even if a second worker is started by mistake.
On startup and before every read or append the store catches up with lines other processes
wrote. A torn last line (crash mid-write) is skipped with a log message, never fatal.
"""

import asyncio
import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FEED_KINDS = frozenset({
    "CLAIM_BUILT", "CLAIM_POSTED", "FILE_FETCHED", "FETCH_FAILED", "HASH_OK", "HASH_MISMATCH",
    "VALIDATION_FAILED", "REPLAY_MATCH", "REPLAY_MISMATCH", "INFO_MISMATCH", "REPORT_STORED",
    "CHALLENGE_SENT", "CHALLENGE_FAILED", "RESOLVER_VERDICT", "RESOLVED", "FINALIZED", "EXPIRED",
    "VAULT_APPLIED", "WITHDRAWN", "ERROR",
})
# Union of the Part 5 list, Dev 3's agents client (malicious_attester) and the frontend type (user).
FEED_ACTORS = frozenset({
    "attester", "malicious_attester", "malicious", "watcher", "resolver", "backend", "ui", "user",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FeedStore:
    """Filesystem feed (default when DATABASE_URL is unset). Same async interface as PostgresFeed."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._entries: List[Dict[str, Any]] = []
        self._offset = 0
        self._lock = asyncio.Lock()
        self._catch_up()

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @property
    def last_seq(self) -> int:
        return self._entries[-1]["seq"] if self._entries else 0

    def _catch_up(self) -> None:
        """Load complete lines written since our last read (by us or another process)."""
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            chunk = f.read()
        if not chunk:
            return
        end = chunk.rfind(b"\n") + 1   # only consume complete lines; a torn tail is retried later
        for line in chunk[:end].splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                seq = entry["seq"]
            except (ValueError, KeyError, TypeError):
                logger.error("feed: skipping unreadable line in %s", self.path)
                continue
            if isinstance(seq, int) and seq > self.last_seq:
                self._entries.append(entry)
        self._offset += end

    async def append(self, actor: str, kind: str, claim_id: Optional[str], tx_hash: Optional[str],
                     data: Dict[str, Any]) -> int:
        async with self._lock:
            with open(self.path, "ab") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    self._repair_torn_tail(f)
                    self._catch_up()
                    entry = {
                        "actor": actor,
                        "claimId": claim_id,
                        "data": data,
                        "kind": kind,
                        "seq": self.last_seq + 1,
                        "ts": utc_now(),
                        "txHash": tx_hash,
                    }
                    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            self._catch_up()
            return entry["seq"]

    def _repair_torn_tail(self, f) -> None:
        """If the file does not end in a newline (crash mid-write), end the torn line so the next one is intact."""
        size = os.fstat(f.fileno()).st_size
        if size == 0:
            return
        with open(self.path, "rb") as r:
            r.seek(size - 1)
            if r.read(1) != b"\n":
                f.write(b"\n")
                f.flush()

    async def read(self, since: int, limit: int) -> List[Dict[str, Any]]:
        async with self._lock:
            self._catch_up()
            return [e for e in self._entries if e["seq"] > since][:limit]
