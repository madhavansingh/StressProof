"""
Fixtures for the backend tests; the harness itself lives in backend_harness.py.
"""

import uuid

import pytest

from backend_harness import BACKENDS, TEST_DATABASE_URL, Harness


@pytest.fixture(params=BACKENDS)
def harness(request, tmp_path):
    schema = f"test_{uuid.uuid4().hex[:12]}"
    h = Harness(tmp_path, request.param, schema)
    yield h
    if request.param == "postgres":
        import psycopg
        from psycopg import sql
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def client(harness):
    with harness.client() as c:
        yield c
