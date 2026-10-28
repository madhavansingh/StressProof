"""Immutable agent settings read from environment variables (names as in .env.example).

Settings are built from a plain mapping, so tests and agents never mutate os.environ.
Secrets (private keys, the backend write token) are wrapped in `Secret`, which never shows its
value in repr, str, logs, tracebacks or pickles. Error messages name the variable, never its value.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

ROLES = ("DEPLOYER", "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER")
LOCAL_CHAIN_ID = 31337
BASE_SEPOLIA_CHAIN_ID = 84532
ALLOWED_CHAIN_IDS = (LOCAL_CHAIN_ID, BASE_SEPOLIA_CHAIN_ID)
RPC_ENV_BY_CHAIN = {LOCAL_CHAIN_ID: "LOCAL_RPC_URL", BASE_SEPOLIA_CHAIN_ID: "TESTNET_RPC_URL"}

DEFAULT_FETCH_MAX_BYTES = 26_214_400  # 25 MB, plan §16.3
DEFAULT_FETCH_TIMEOUT_SEC = 10
DEFAULT_FETCH_RETRIES = 3
DEFAULT_WATCHER_POLL_SEC = 2

_PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_TRUE = {"1", "true", "yes"}
_FALSE = {"0", "false", "no"}


class ConfigError(ValueError):
    """A setting is missing or invalid. The message names the variable, never a secret value."""


class Secret:
    """A secret string that is hidden everywhere except through `reveal()`."""

    __slots__ = ("_value", "label")

    def __init__(self, value: str, label: str) -> None:
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "label", label)

    def reveal(self) -> str:
        """The raw value. Call only where it is used (signing, an Authorization header)."""
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Secret is immutable")

    def __repr__(self) -> str:
        return f"Secret({self.label}=<redacted>)"

    __str__ = __repr__

    def __reduce__(self):  # refuse pickling, which would write the value out
        raise TypeError("Secret values cannot be serialized")


@dataclass(frozen=True)
class FetchSettings:
    """Limits for fetching untrusted evidence URIs (plan §16.3)."""

    max_bytes: int = DEFAULT_FETCH_MAX_BYTES
    timeout_sec: float = DEFAULT_FETCH_TIMEOUT_SEC
    max_attempts: int = DEFAULT_FETCH_RETRIES
    allow_localhost: bool = False
    ipfs_gateway_url: Optional[str] = None


@dataclass(frozen=True)
class AgentSettings:
    deployments_file: Path
    backend_url: str
    data_dir: Path
    market_id_string: str
    fetch: FetchSettings
    watcher_poll_sec: float
    watcher_start_block: Optional[int]
    api_write_token: Optional[Secret] = field(repr=False)
    # Provider URLs often embed API keys, so they are kept out of repr.
    local_rpc_url: Optional[str] = field(repr=False, default=None)
    testnet_rpc_url: Optional[str] = field(repr=False, default=None)

    def rpc_url_for(self, chain_id: int) -> str:
        """The RPC URL for a deployment's chain. Mainnet and unknown chains are refused."""
        name = RPC_ENV_BY_CHAIN.get(chain_id)
        if name is None:
            raise ConfigError(f"chain {chain_id} is not allowed (only {ALLOWED_CHAIN_IDS})")
        url = self.local_rpc_url if chain_id == LOCAL_CHAIN_ID else self.testnet_rpc_url
        if not url:
            raise ConfigError(f"{name} is not set")
        return url

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, base_dir: Optional[Path] = None) -> "AgentSettings":
        env = dict(os.environ if env is None else env)
        base = Path.cwd() if base_dir is None else base_dir
        token = _optional(env, "API_WRITE_TOKEN")
        return cls(
            deployments_file=_path(env, "DEPLOYMENTS_FILE", base, default="deployments/31337.json"),
            backend_url=_url(env, "BACKEND_URL", default="http://127.0.0.1:8000"),
            data_dir=_path(env, "DATA_DIR", base, default="data"),
            market_id_string=_optional(env, "MARKET_ID_STRING") or "aave-v3-eth-weth-stable",
            fetch=FetchSettings(
                max_bytes=_int(env, "FETCH_MAX_BYTES", DEFAULT_FETCH_MAX_BYTES, minimum=1),
                timeout_sec=_int(env, "FETCH_TIMEOUT_SEC", DEFAULT_FETCH_TIMEOUT_SEC, minimum=1),
                max_attempts=_int(env, "FETCH_RETRIES", DEFAULT_FETCH_RETRIES, minimum=1),
                allow_localhost=_bool(env, "FETCH_ALLOW_LOCALHOST", default=False),
                ipfs_gateway_url=_url(env, "IPFS_GATEWAY_URL", default=None, schemes=("https",)),
            ),
            watcher_poll_sec=_int(env, "WATCHER_POLL_SEC", DEFAULT_WATCHER_POLL_SEC, minimum=1),
            watcher_start_block=_optional_int(env, "WATCHER_START_BLOCK"),
            api_write_token=Secret(token, "API_WRITE_TOKEN") if token else None,
            local_rpc_url=_url(env, "LOCAL_RPC_URL", default=None),
            testnet_rpc_url=_url(env, "TESTNET_RPC_URL", default=None),
        )


def load_private_key(role: str, env: Optional[Mapping[str, str]] = None) -> Secret:
    """Reads <ROLE>_PK for one role. Each agent process loads only the key it signs with."""
    if role not in ROLES:
        raise ConfigError(f"unknown role {role!r} (expected one of {ROLES})")
    name = f"{role}_PK"
    raw = _optional(dict(os.environ if env is None else env), name)
    if raw is None:
        raise ConfigError(f"{name} is not set")
    if not _PRIVATE_KEY_RE.match(raw):
        raise ConfigError(f"{name} must be 0x followed by 64 hex characters")
    if not 0 < int(raw, 16) < _SECP256K1_ORDER:
        raise ConfigError(f"{name} is not a valid secp256k1 private key")
    return Secret(raw, name)


def load_env_file(path: Path) -> dict:
    """Parses a .env file into a dict without touching os.environ."""
    from dotenv import dotenv_values

    if not path.is_file():
        raise ConfigError(f"env file not found: {path}")
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


# ------------------------------------------------------------------ parsers


def _optional(env: Mapping[str, str], name: str) -> Optional[str]:
    value = env.get(name, "").strip()
    return value or None


def _int(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw = _optional(env, name)
    if raw is None:
        return default
    if not re.fullmatch(r"[0-9]+", raw):
        raise ConfigError(f"{name} must be a whole number, got {raw!r}")
    value = int(raw)
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}")
    return value


def _optional_int(env: Mapping[str, str], name: str) -> Optional[int]:
    return None if _optional(env, name) is None else _int(env, name, 0, minimum=0)


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _optional(env, name)
    if raw is None:
        return default
    if raw.lower() in _TRUE:
        return True
    if raw.lower() in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _url(env: Mapping[str, str], name: str, default: Optional[str], schemes=("http", "https")) -> Optional[str]:
    raw = _optional(env, name) or default
    if raw is None:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise ConfigError(f"{name} must be an {'/'.join(schemes)} URL")  # value may hold an API key
    return raw.rstrip("/")


def _path(env: Mapping[str, str], name: str, base: Path, default: str) -> Path:
    raw = Path(_optional(env, name) or default)
    return raw if raw.is_absolute() else (base / raw)
