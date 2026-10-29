"""
Configuration management using pydantic-settings.

Paths resolve against the repository root, never the current working directory, so the
server finds the same data no matter where it is started from.
"""

import subprocess
from functools import cached_property
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_WRITE_TOKEN = "stressproof_dev_token_secret"


def _resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def read_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    API_WRITE_TOKEN: str = DEV_WRITE_TOKEN
    BACKEND_PUBLIC_URL: str = "http://127.0.0.1:8000"
    DATA_DIR: str = "./data"
    # Extra dataset roots, comma-separated. Default: <DATA_DIR>/datasets, then data/fixtures/datasets.
    DATASETS_DIR: str = ""
    # Comma-separated. Default: both local dev addresses of the Next.js frontend; deployments set their own.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    MARKET_ID_STRING: str = "aave-v3-eth-weth-stable"
    MAX_BODY_BYTES: int = 26214400
    MAX_FEED_ENTRY_BYTES: int = 16384
    # Empty means: read `git rev-parse HEAD` at startup ("unknown" if git is unavailable).
    GIT_COMMIT: str = ""
    # Set on hosts without persistent disk (free tiers): stores blobs and the feed in Postgres.
    # Unset: filesystem storage under DATA_DIR (local development, tests). Never logged.
    DATABASE_URL: str = ""
    DATABASE_SCHEMA: str = "public"
    DATABASE_POOL_MAX: int = 5

    @cached_property
    def data_dir(self) -> Path:
        return _resolve(self.DATA_DIR)

    @cached_property
    def datasets_dirs(self) -> List[Path]:
        if self.DATASETS_DIR.strip():
            return [_resolve(p.strip()) for p in self.DATASETS_DIR.split(",") if p.strip()]
        return [self.data_dir / "datasets", REPO_ROOT / "data" / "fixtures" / "datasets"]

    @cached_property
    def git_commit(self) -> str:
        return self.GIT_COMMIT.strip() or read_git_commit()

    @cached_property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def storage_backend(self) -> str:
        return "postgres" if self.DATABASE_URL.strip() else "filesystem"

    @property
    def public_url(self) -> str:
        return self.BACKEND_PUBLIC_URL.rstrip("/")


class ConfigError(RuntimeError):
    """The configuration is unsafe to serve with; startup is refused. Messages never contain secrets."""


def check_startup_config(settings: Settings) -> None:
    """
    Refuse unsafe write-token configurations before any storage is opened.

    - An empty token is refused in every mode: it would let `Authorization: Bearer ` through.
    - With DATABASE_URL set (a deployment), the public development default is refused too.
      File mode keeps the development default so local runs, tests and agents work unchanged.
    """
    token = settings.API_WRITE_TOKEN.strip()
    if not token:
        raise ConfigError("API_WRITE_TOKEN is empty; set it to a random secret")
    if settings.storage_backend == "postgres" and token == DEV_WRITE_TOKEN:
        raise ConfigError(
            "API_WRITE_TOKEN is the public development default while DATABASE_URL is set; "
            "set API_WRITE_TOKEN to a random secret before deploying"
        )


def get_settings() -> Settings:
    return Settings()
