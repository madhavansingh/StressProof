"""
SQLite-backed per-claim watcher state store.
Matches implementationplan.md §15.2.
"""

import sqlite3
from pathlib import Path


class WatcherState:
    def __init__(self, db_path: str = "data/watcher.sqlite"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watched_claims (
                    claim_id INTEGER PRIMARY KEY,
                    state TEXT NOT NULL,
                    evidence_hash TEXT,
                    claimed_usd8 TEXT,
                    recomputed_usd8 TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def set_claim_state(self, claim_id: int, state: str, **kwargs):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO watched_claims (claim_id, state) VALUES (?, ?)",
                (claim_id, state),
            )
            conn.commit()
