"""SQLite-backed watcher state (implementationplan.md §15.2), so the watcher resumes after a restart.

Records are returned as frozen dataclasses. Every change goes through an explicit method:
`add_claim` (insert once), `transition` (state changes, checked against the §15.2 state machine)
and `record` (named columns only). The log cursor is stored alongside.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, Optional, Tuple

# Allowed transitions. Repeating the current state is allowed, so steps can be retried after a restart.
TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "SEEN": frozenset({"FETCHING", "SKIPPED"}),
    "FETCHING": frozenset({"FETCHED", "FETCH_FAILED", "SKIPPED"}),
    "FETCH_FAILED": frozenset({"INVALID", "SKIPPED"}),
    "FETCHED": frozenset({"HASH_OK", "INVALID", "SKIPPED"}),
    "HASH_OK": frozenset({"VALID", "INVALID", "SKIPPED"}),
    "VALID": frozenset({"MATCH", "MISMATCH", "SKIPPED"}),
    "INVALID": frozenset({"REPORT_BUILT", "SKIPPED"}),
    "MISMATCH": frozenset({"REPORT_BUILT", "SKIPPED"}),
    "REPORT_BUILT": frozenset({"REPORT_STORED", "SKIPPED"}),
    "REPORT_STORED": frozenset({"CHALLENGE_SENDING", "SKIPPED"}),
    "CHALLENGE_SENDING": frozenset({"CHALLENGED", "CHALLENGE_FAILED", "SKIPPED"}),
    "CHALLENGED": frozenset({"WON", "LOST", "REFUNDED"}),
    "WON": frozenset({"WITHDRAWN"}),
    "REFUNDED": frozenset({"WITHDRAWN"}),
    "MATCH": frozenset(),
    "LOST": frozenset(),
    "WITHDRAWN": frozenset(),
    "CHALLENGE_FAILED": frozenset(),
    "SKIPPED": frozenset(),  # someone else challenged, the claim is ours, or the window closed
}
TERMINAL_STATES = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)
RECORD_COLUMNS = ("verdict", "recomputed_usd8", "report_hash", "report_uri", "challenge_tx", "error")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id        TEXT PRIMARY KEY,
    state           TEXT NOT NULL,
    attester        TEXT NOT NULL,
    evidence_hash   TEXT NOT NULL,
    case_file_uri   TEXT NOT NULL,
    claimed_usd8    TEXT NOT NULL,
    verdict         TEXT,
    recomputed_usd8 TEXT,
    report_hash     TEXT,
    report_uri      TEXT,
    challenge_tx    TEXT,
    error           TEXT,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class StateError(RuntimeError):
    """An unknown claim, a disallowed transition or an unknown column."""


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: int
    state: str
    attester: str
    evidence_hash: str
    case_file_uri: str
    claimed_usd8: int
    verdict: Optional[str]
    recomputed_usd8: Optional[int]
    report_hash: Optional[str]
    report_uri: Optional[str]
    challenge_tx: Optional[str]
    error: Optional[str]
    updated_at: float

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class WatcherState:
    def __init__(self, db_path: Path, clock=time.time) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    # ----------------------------------------------------------------- claims

    def add_claim(self, claim_id: int, attester: str, evidence_hash: str, case_file_uri: str,
                  claimed_usd8: int) -> ClaimRecord:
        """Inserts a claim in SEEN. If it already exists (e.g. re-read logs after a restart), keeps it."""
        with self._tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO claims (claim_id, state, attester, evidence_hash, case_file_uri,"
                " claimed_usd8, updated_at) VALUES (?, 'SEEN', ?, ?, ?, ?, ?)",
                (str(claim_id), attester, evidence_hash, case_file_uri, str(claimed_usd8), self._clock()),
            )
        return self.get_required(claim_id)

    def get(self, claim_id: int) -> Optional[ClaimRecord]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM claims WHERE claim_id = ?", (str(claim_id),)).fetchone()
        return _to_record(row) if row else None

    def get_required(self, claim_id: int) -> ClaimRecord:
        record = self.get(claim_id)
        if record is None:
            raise StateError(f"claim {claim_id} is not tracked")
        return record

    def transition(self, claim_id: int, new_state: str) -> ClaimRecord:
        """Moves a claim to `new_state` if the §15.2 state machine allows it."""
        if new_state not in TRANSITIONS:
            raise StateError(f"unknown state {new_state!r}")
        with self._tx() as conn:
            row = conn.execute("SELECT state FROM claims WHERE claim_id = ?", (str(claim_id),)).fetchone()
            if row is None:
                raise StateError(f"claim {claim_id} is not tracked")
            current = row["state"]
            if new_state != current and new_state not in TRANSITIONS[current]:
                raise StateError(f"claim {claim_id}: {current} -> {new_state} is not allowed")
            conn.execute("UPDATE claims SET state = ?, updated_at = ? WHERE claim_id = ?",
                         (new_state, self._clock(), str(claim_id)))
        return self.get_required(claim_id)

    def record(self, claim_id: int, **fields: object) -> ClaimRecord:
        """Sets named result columns (verdict, recomputed_usd8, report_hash, ...) without changing state."""
        unknown = set(fields) - set(RECORD_COLUMNS)
        if unknown or not fields:
            raise StateError(f"cannot set {sorted(unknown) or 'nothing'}; allowed: {RECORD_COLUMNS}")
        values = {k: (None if v is None else str(v)) for k, v in fields.items()}
        assignments = ", ".join(f"{k} = ?" for k in values)  # names come from RECORD_COLUMNS only
        with self._tx() as conn:
            cursor = conn.execute(f"UPDATE claims SET {assignments}, updated_at = ? WHERE claim_id = ?",
                                  (*values.values(), self._clock(), str(claim_id)))
            if cursor.rowcount == 0:
                raise StateError(f"claim {claim_id} is not tracked")
        return self.get_required(claim_id)

    def unfinished(self) -> Tuple[ClaimRecord, ...]:
        """Claims not in a terminal state, oldest id first: what to re-check after a restart."""
        placeholders = ", ".join("?" for _ in TERMINAL_STATES)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM claims WHERE state NOT IN ({placeholders}) ORDER BY CAST(claim_id AS INTEGER)",
                tuple(TERMINAL_STATES),
            ).fetchall()
        return tuple(_to_record(r) for r in rows)

    # ------------------------------------------------------------------ cursor

    def cursor(self) -> Optional[int]:
        """The last block whose logs were fully processed, or None before the first poll."""
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = 'cursor'").fetchone()
        return int(row["value"]) if row else None

    def set_cursor(self, block: int) -> None:
        if block < 0:
            raise StateError("cursor must be non-negative")
        current = self.cursor()
        if current is not None and block < current:
            raise StateError(f"cursor cannot move backwards ({current} -> {block})")
        with self._tx() as conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('cursor', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(block),))


def _to_record(row: sqlite3.Row) -> ClaimRecord:
    def opt_int(v):
        return None if v is None else int(v)

    return ClaimRecord(
        claim_id=int(row["claim_id"]), state=row["state"], attester=row["attester"],
        evidence_hash=row["evidence_hash"], case_file_uri=row["case_file_uri"],
        claimed_usd8=int(row["claimed_usd8"]), verdict=row["verdict"],
        recomputed_usd8=opt_int(row["recomputed_usd8"]), report_hash=row["report_hash"],
        report_uri=row["report_uri"], challenge_tx=row["challenge_tx"], error=row["error"],
        updated_at=float(row["updated_at"]),
    )
