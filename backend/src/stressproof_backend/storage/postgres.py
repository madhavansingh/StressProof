"""
PostgreSQL backends, used when DATABASE_URL is set (e.g. a free Neon or Supabase database).

Free hosting platforms wipe local disk on restart or redeploy, so everything the backend
writes (case files, replay reports, per-account outputs, the feed) lives in Postgres there.
Behaviour matches the filesystem backends exactly:

- blobs are content-addressed by keccak256 of their exact bytes, stored as bytea and returned
  unchanged; a write never mutates an existing row (INSERT ... ON CONFLICT DO NOTHING);
- feed seq is a database identity column, so it is unique and increasing across any number of
  backend processes and survives restarts. Inserts are serialized by a transaction-level advisory
  lock (see PostgresFeed), so a seq is never committed after a higher one and pollers using
  `since` never skip an entry.

The schema is created idempotently at startup (CREATE ... IF NOT EXISTS).
"""

import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from stressproof_core.hashing import keccak256_hex

from .feed import utc_now
from .store import CASE_FILES, HASH_REGEX, REPLAY_OUTPUTS, REPLAY_REPORTS, PutResult, StoreConflict

logger = logging.getLogger(__name__)

_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

_DDL = [
    """CREATE TABLE IF NOT EXISTS blobs (
        kind        text        NOT NULL,
        hash        text        NOT NULL,
        data        bytea       NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (kind, hash)
    )""",
    """CREATE TABLE IF NOT EXISTS feed (
        seq       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        ts        text   NOT NULL,
        actor     text   NOT NULL,
        kind      text   NOT NULL,
        claim_id  text,
        tx_hash   text,
        data      jsonb  NOT NULL
    )""",
]


class PostgresDatabase:
    """One connection pool shared by the blob store and the feed."""

    def __init__(self, url: str, schema: str = "public", max_size: int = 5):
        if not _SCHEMA_NAME.match(schema):
            raise ValueError(f"invalid DATABASE_SCHEMA {schema!r}")
        self.schema = schema
        self.pool = AsyncConnectionPool(
            url,
            min_size=1,
            max_size=max_size,
            open=False,
            # Free databases (Neon) suspend when idle and drop connections: check before use.
            check=AsyncConnectionPool.check_connection,
            configure=self._configure,
            kwargs={"autocommit": True},
        )

    async def _configure(self, conn) -> None:
        await conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))

    async def open(self) -> None:
        await self.pool.open(wait=True, timeout=30)
        async with self.pool.connection() as conn:
            await conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            for statement in _DDL:
                await conn.execute(statement)
        logger.info("postgres storage ready (schema %s)", self.schema)

    async def close(self) -> None:
        await self.pool.close()


class PostgresStore:
    """Content-addressed blob store with the same interface as the filesystem ContentStore."""

    kind = "postgres"

    def __init__(self, db: PostgresDatabase):
        self.db = db

    async def open(self) -> None:
        return None   # the shared PostgresDatabase is opened by the app lifespan

    async def close(self) -> None:
        return None

    async def _put(self, kind: str, raw: bytes, key: Optional[str] = None) -> PutResult:
        h = keccak256_hex(raw)
        async with self.db.pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO blobs (kind, hash, data) VALUES (%s, %s, %s) ON CONFLICT (kind, hash) DO NOTHING RETURNING hash",
                (kind, key or h, raw),
            )
            if await cur.fetchone() is not None:
                return PutResult(h, created=True)
            cur = await conn.execute("SELECT data FROM blobs WHERE kind = %s AND hash = %s", (kind, key or h))
            row = await cur.fetchone()
        if row is None or bytes(row[0]) != raw:
            raise StoreConflict(f"{kind}/{key or h} exists with different bytes")
        return PutResult(h, created=False)

    async def _get(self, kind: str, h: str) -> Optional[bytes]:
        if not isinstance(h, str) or not HASH_REGEX.match(h):
            return None
        async with self.db.pool.connection() as conn:
            cur = await conn.execute("SELECT data FROM blobs WHERE kind = %s AND hash = %s", (kind, h))
            row = await cur.fetchone()
        return bytes(row[0]) if row is not None else None

    async def put_case_file(self, raw: bytes) -> PutResult:
        return await self._put(CASE_FILES, raw)

    async def get_case_file(self, h: str) -> Optional[bytes]:
        return await self._get(CASE_FILES, h)

    async def put_replay_report(self, raw: bytes) -> PutResult:
        return await self._put(REPLAY_REPORTS, raw)

    async def get_replay_report(self, h: str) -> Optional[bytes]:
        return await self._get(REPLAY_REPORTS, h)

    async def put_replay_outputs(self, evidence_hash: str, raw: bytes) -> None:
        if not HASH_REGEX.match(evidence_hash):
            raise ValueError("malformed evidence hash")
        async with self.db.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO blobs (kind, hash, data) VALUES (%s, %s, %s) ON CONFLICT (kind, hash) DO NOTHING",
                (REPLAY_OUTPUTS, evidence_hash, raw),
            )


class PostgresFeed:
    """
    Append-only feed with the same interface as the filesystem FeedStore.

    Ordering: an identity value is allocated when an INSERT runs, but concurrent transactions can
    commit in a different order. A reader could then see seq N+1 before N commits, advance `since`
    past N and never return for it. Each append therefore runs in its own transaction that first
    takes a transaction-scoped advisory lock (one per schema) and holds it until COMMIT, so seqs are
    allocated and committed strictly one at a time, across all connections and processes. Readers
    take no lock and always see a gap-free committed prefix. A rolled-back insert can leave a gap
    in the numbers; that gap is never filled later, so it cannot be skipped over.
    """

    LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext(current_schema() || '.stressproof_feed'))"

    def __init__(self, db: PostgresDatabase):
        self.db = db
        self._before_commit: Optional[Callable[[], Awaitable[None]]] = None   # test seam only

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def append(self, actor: str, kind: str, claim_id: Optional[str], tx_hash: Optional[str],
                     data: Dict[str, Any]) -> int:
        json.dumps(data, allow_nan=False)  # same finiteness rule as the file feed
        async with self.db.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(self.LOCK_SQL)
                cur = await conn.execute(
                    "INSERT INTO feed (ts, actor, kind, claim_id, tx_hash, data) VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                    (utc_now(), actor, kind, claim_id, tx_hash, Jsonb(data)),
                )
                row = await cur.fetchone()
                if self._before_commit is not None:
                    await self._before_commit()
        return int(row[0])

    async def read(self, since: int, limit: int) -> List[Dict[str, Any]]:
        async with self.db.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT seq, ts, actor, kind, claim_id, tx_hash, data FROM feed WHERE seq > %s ORDER BY seq LIMIT %s",
                (since, limit),
            )
            rows = await cur.fetchall()
        return [
            {"actor": actor, "claimId": claim_id, "data": data, "kind": kind, "seq": int(seq), "ts": ts, "txHash": tx_hash}
            for seq, ts, actor, kind, claim_id, tx_hash, data in rows
        ]
