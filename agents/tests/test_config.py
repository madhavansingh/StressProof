"""Settings, secrets and private-key loading."""

import pickle
from pathlib import Path

import pytest

from stressproof_agents.common.config import (
    AgentSettings, ConfigError, Secret, load_env_file, load_private_key,
)

KEY = "0x" + "4c" * 32


def test_defaults_from_an_empty_environment(tmp_path):
    s = AgentSettings.from_env({}, base_dir=tmp_path)
    assert s.deployments_file == tmp_path / "deployments/31337.json"
    assert s.backend_url == "http://127.0.0.1:8000"
    assert s.market_id_string == "aave-v3-eth-weth-stable"
    assert s.fetch.max_bytes == 26_214_400 and s.fetch.timeout_sec == 10 and s.fetch.max_attempts == 3
    assert s.fetch.allow_localhost is False  # safe default
    assert s.api_write_token is None and s.watcher_start_block is None


def test_values_are_parsed_and_settings_are_immutable(tmp_path):
    s = AgentSettings.from_env({
        "FETCH_MAX_BYTES": "1024", "FETCH_ALLOW_LOCALHOST": "true", "WATCHER_START_BLOCK": "7",
        "IPFS_GATEWAY_URL": "https://gateway.example/", "LOCAL_RPC_URL": "http://127.0.0.1:8546",
        "DEPLOYMENTS_FILE": "/abs/deploy.json",
    }, base_dir=tmp_path)
    assert s.fetch.max_bytes == 1024 and s.fetch.allow_localhost is True and s.watcher_start_block == 7
    assert s.fetch.ipfs_gateway_url == "https://gateway.example"
    assert s.deployments_file == Path("/abs/deploy.json")
    with pytest.raises(AttributeError):
        s.backend_url = "http://evil"  # frozen dataclass


@pytest.mark.parametrize("env, message", [
    ({"FETCH_MAX_BYTES": "lots"}, "FETCH_MAX_BYTES must be a whole number"),
    ({"FETCH_MAX_BYTES": "0"}, "FETCH_MAX_BYTES must be at least 1"),
    ({"FETCH_RETRIES": "-1"}, "FETCH_RETRIES must be a whole number"),
    ({"FETCH_ALLOW_LOCALHOST": "maybe"}, "FETCH_ALLOW_LOCALHOST must be true or false"),
    ({"BACKEND_URL": "ftp://x"}, "BACKEND_URL must be an http/https URL"),
    ({"IPFS_GATEWAY_URL": "http://gateway.example"}, "IPFS_GATEWAY_URL must be an https URL"),
    ({"LOCAL_RPC_URL": "not a url"}, "LOCAL_RPC_URL must be"),
    ({"WATCHER_START_BLOCK": "1.5"}, "WATCHER_START_BLOCK must be a whole number"),
])
def test_malformed_settings_name_the_variable(env, message, tmp_path):
    with pytest.raises(ConfigError, match=message):
        AgentSettings.from_env(env, base_dir=tmp_path)


def test_rpc_url_errors_do_not_leak_the_url(tmp_path):
    with pytest.raises(ConfigError) as exc:
        AgentSettings.from_env({"TESTNET_RPC_URL": "wss://eth.example/v2/SECRET-API-KEY"}, base_dir=tmp_path)
    assert "SECRET-API-KEY" not in str(exc.value)


def test_rpc_url_for_chain(tmp_path):
    s = AgentSettings.from_env({"LOCAL_RPC_URL": "http://127.0.0.1:8546"}, base_dir=tmp_path)
    assert s.rpc_url_for(31337) == "http://127.0.0.1:8546"
    with pytest.raises(ConfigError, match="TESTNET_RPC_URL is not set"):
        s.rpc_url_for(84532)
    with pytest.raises(ConfigError, match="chain 1 is not allowed"):
        s.rpc_url_for(1)


def test_rpc_urls_and_token_are_not_in_repr(tmp_path):
    s = AgentSettings.from_env({"TESTNET_RPC_URL": "https://eth.example/v2/SECRET-API-KEY",
                                "API_WRITE_TOKEN": "super-secret-token"}, base_dir=tmp_path)
    assert "SECRET-API-KEY" not in repr(s) and "super-secret-token" not in repr(s)
    assert s.api_write_token.reveal() == "super-secret-token"


def test_private_key_loading():
    key = load_private_key("WATCHER", {"WATCHER_PK": KEY})
    assert key.reveal() == KEY
    assert KEY not in repr(key) and KEY not in str(key) and KEY[2:] not in f"{key}"


@pytest.mark.parametrize("env, message", [
    ({}, "WATCHER_PK is not set"),
    ({"WATCHER_PK": "   "}, "WATCHER_PK is not set"),
    ({"WATCHER_PK": "4c" * 32}, "must be 0x followed by 64 hex"),
    ({"WATCHER_PK": "0x" + "4c" * 31}, "must be 0x followed by 64 hex"),
    ({"WATCHER_PK": "0x" + "zz" * 32}, "must be 0x followed by 64 hex"),
    ({"WATCHER_PK": "0x" + "00" * 32}, "not a valid secp256k1 private key"),
    ({"WATCHER_PK": "0x" + "ff" * 32}, "not a valid secp256k1 private key"),
])
def test_bad_private_keys_are_rejected_without_echoing_them(env, message):
    with pytest.raises(ConfigError, match=message) as exc:
        load_private_key("WATCHER", env)
    raw = env.get("WATCHER_PK", "").strip()
    if len(raw) > 8:
        assert raw not in str(exc.value)


def test_unknown_role_is_rejected():
    with pytest.raises(ConfigError, match="unknown role"):
        load_private_key("ADMIN", {"ADMIN_PK": KEY})


def test_secret_cannot_be_changed_or_pickled():
    secret = Secret("value", "LABEL")
    with pytest.raises(AttributeError):
        secret._value = "other"
    with pytest.raises(TypeError):
        pickle.dumps(secret)


def test_env_file_is_parsed_without_touching_os_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("STRESSPROOF_TEST_VAR", raising=False)
    path = tmp_path / ".env"
    path.write_text("STRESSPROOF_TEST_VAR=hello   # comment\nEMPTY=\n")
    values = load_env_file(path)
    assert values["STRESSPROOF_TEST_VAR"] == "hello"
    import os
    assert "STRESSPROOF_TEST_VAR" not in os.environ
    with pytest.raises(ConfigError, match="env file not found"):
        load_env_file(tmp_path / "missing.env")
