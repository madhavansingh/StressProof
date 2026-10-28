"""
Regression tests for the Part 5 audit fixes:

1. Startup refuses an empty write token, and the public development token when DATABASE_URL is set.
2. The PostgreSQL feed never lets a poller skip an entry when inserts would commit out of order.

Postgres tests need TEST_DATABASE_URL (see backend_harness.py); the config tests need no database.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from backend_harness import AUTH, TEST_DATABASE_URL
from stressproof_backend.config import DEV_WRITE_TOKEN, ConfigError, Settings
from stressproof_backend.main import create_app

needs_postgres = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")
FAKE_DB_URL = "postgresql://user:not-a-real-password@127.0.0.1:1/none"


def settings(tmp_path, **values):
    return Settings(_env_file=None, DATA_DIR=str(tmp_path / "data"), GIT_COMMIT="0" * 40, **values)


# --- Fix 1: write token at startup ------------------------------------------------------------

@pytest.mark.parametrize("token", [DEV_WRITE_TOKEN, "", "   "])
def test_postgres_mode_refuses_dev_or_empty_token(tmp_path, token):
    s = settings(tmp_path, DATABASE_URL=FAKE_DB_URL, API_WRITE_TOKEN=token)
    with pytest.raises(ConfigError) as exc:
        with TestClient(create_app(s)):
            pass
    message = str(exc.value)
    assert "API_WRITE_TOKEN" in message
    assert DEV_WRITE_TOKEN not in message and "not-a-real-password" not in message
    assert not (tmp_path / "data").exists()          # refused before any storage was opened


def test_file_mode_refuses_empty_token(tmp_path):
    with pytest.raises(ConfigError, match="empty"):
        with TestClient(create_app(settings(tmp_path, API_WRITE_TOKEN=""))):
            pass


def test_file_mode_keeps_dev_token_for_local_development(tmp_path):
    with TestClient(create_app(settings(tmp_path, API_WRITE_TOKEN=DEV_WRITE_TOKEN))) as c:
        assert c.get("/health").json()["storage"] == "filesystem"
        ok = c.post("/feed", json={"actor": "watcher", "kind": "HASH_OK"},
                    headers={"Authorization": f"Bearer {DEV_WRITE_TOKEN}"})
        assert ok.status_code == 201


def test_bare_bearer_header_never_authorizes(tmp_path):
    with TestClient(create_app(settings(tmp_path, API_WRITE_TOKEN="real-secret-123"))) as c:
        res = c.post("/feed", json={"actor": "watcher", "kind": "HASH_OK"}, headers={"Authorization": "Bearer "})
        assert res.status_code in (401, 403)


@needs_postgres
def test_postgres_mode_starts_with_a_real_token(tmp_path):
    schema = f"test_{uuid.uuid4().hex[:12]}"
    s = settings(tmp_path, DATABASE_URL=TEST_DATABASE_URL, DATABASE_SCHEMA=schema, API_WRITE_TOKEN="test-write-token")
    try:
        with TestClient(create_app(s)) as c:
            assert c.get("/health").json()["storage"] == "postgres"
            assert c.post("/feed", json={"actor": "watcher", "kind": "HASH_OK"}, headers=AUTH).status_code == 201
    finally:
        _drop_schema(schema)


# --- Fix 2: Postgres feed ordering -----------------------------------------------------------

def _drop_schema(schema):
    import psycopg
    from psycopg import sql
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def pg_schema():
    schema = f"test_{uuid.uuid4().hex[:12]}"
    yield schema
    _drop_schema(schema)


async def _open_db(schema):
    from stressproof_backend.storage.postgres import PostgresDatabase
    db = PostgresDatabase(TEST_DATABASE_URL, schema, max_size=8)
    await db.open()
    return db


@needs_postgres
def test_feed_never_commits_a_lower_seq_after_a_higher_one(pg_schema):
    """
    Reproduces the audit race: append A has inserted (seq allocated) but not committed when
    append B runs on a different pool (as another process would). Before the fix B committed
    seq A+1 first and a reader saw [A+1], so `since` skipped A forever.
    """
    from stressproof_backend.storage.postgres import PostgresFeed

    async def scenario():
        db_a, db_b = await _open_db(pg_schema), await _open_db(pg_schema)
        try:
            feed_a, feed_b, reader = PostgresFeed(db_a), PostgresFeed(db_b), PostgresFeed(db_b)
            inserted, release = asyncio.Event(), asyncio.Event()

            async def hold_before_commit():
                inserted.set()
                await release.wait()
            feed_a._before_commit = hold_before_commit

            task_a = asyncio.create_task(feed_a.append("attester", "CLAIM_POSTED", "1", None, {}))
            await asyncio.wait_for(inserted.wait(), 10)
            task_b = asyncio.create_task(feed_b.append("watcher", "HASH_OK", "1", None, {}))
            await asyncio.sleep(0.5)

            b_finished_early = task_b.done()
            visible_while_a_open = [e["seq"] for e in await reader.read(0, 10)]

            release.set()
            seq_a, seq_b = await asyncio.wait_for(asyncio.gather(task_a, task_b), 10)
            final = [e["seq"] for e in await reader.read(0, 10)]
            return b_finished_early, visible_while_a_open, seq_a, seq_b, final
        finally:
            await db_a.close()
            await db_b.close()

    b_finished_early, visible, seq_a, seq_b, final = asyncio.run(scenario())
    assert not b_finished_early, "B committed while A held an earlier seq open"
    assert visible == [], f"reader saw {visible} while seq {seq_a} was uncommitted"
    assert seq_a < seq_b
    assert final == [seq_a, seq_b]


@needs_postgres
def test_concurrent_appends_with_polling_reader_skip_nothing(pg_schema):
    """80 concurrent appends over a pool of 8 connections while a reader polls with `since`."""
    from stressproof_backend.storage.postgres import PostgresFeed

    async def scenario():
        db = await _open_db(pg_schema)
        try:
            feed = PostgresFeed(db)
            appends = [asyncio.create_task(feed.append("watcher", "HASH_OK", str(i), None, {"i": i}))
                       for i in range(80)]
            seen, since = [], 0
            while True:
                batch = await feed.read(since, 200)
                seen.extend(e["seq"] for e in batch)
                if batch:
                    since = batch[-1]["seq"]
                if all(t.done() for t in appends) and not batch:
                    break
                await asyncio.sleep(0)
            return [t.result() for t in appends], seen
        finally:
            await db.close()

    appended, seen = asyncio.run(scenario())
    assert len(set(appended)) == 80
    assert sorted(seen) == sorted(appended), f"poller missed {sorted(set(appended) - set(seen))}"
    assert seen == sorted(seen)
