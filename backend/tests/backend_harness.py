"""
Backend test harness (shared by conftest.py and the test modules). The name is unique across
the repo's test folders so `pytest` from the root never imports another package's helpers.

Every behaviour test runs against both storage backends:

- filesystem: always, in a temporary DATA_DIR;
- postgres: only when TEST_DATABASE_URL is set; each test gets its own throwaway schema.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stressproof_backend.config import Settings
from stressproof_backend.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DATASETS = REPO_ROOT / "data" / "fixtures" / "datasets"
TOKEN = "test-write-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

BACKENDS = [
    "filesystem",
    pytest.param("postgres", marks=pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")),
]


class Harness:
    def __init__(self, tmp_path: Path, backend: str, schema: str):
        self.tmp_path = tmp_path
        self.backend = backend
        self.schema = schema
        self.data_dir = tmp_path / "data"
        self.extra_datasets = tmp_path / "datasets"
        self.extra_datasets.mkdir()

    def settings(self, **overrides) -> Settings:
        values = {
            "API_WRITE_TOKEN": TOKEN,
            "BACKEND_PUBLIC_URL": "http://testserver",
            "DATA_DIR": str(self.data_dir),
            "DATASETS_DIR": f"{self.extra_datasets},{FIXTURE_DATASETS}",
            "CORS_ORIGINS": "http://localhost:3000",
            "GIT_COMMIT": "0" * 40,
            "DATABASE_URL": TEST_DATABASE_URL if self.backend == "postgres" else "",
            "DATABASE_SCHEMA": self.schema,
            "TG_HOST": "",  # tests never reach a real TigerGraph, even if the shell exports TG_HOST
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    @contextmanager
    def client(self, **overrides):
        with TestClient(create_app(self.settings(**overrides))) as client:
            yield client
