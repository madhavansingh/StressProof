"""Tests for scripts/testnet_preflight.py: local checks of a testnet env file. No network, no signing.

Role keys are generated per test; the only fixed key is Anvil's public account #0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest
from eth_account import Account

SCRIPT = Path(__file__).resolve().parents[1] / "testnet_preflight.py"
_spec = importlib.util.spec_from_file_location("testnet_preflight", SCRIPT)
tp = importlib.util.module_from_spec(_spec)
sys.modules["testnet_preflight"] = tp
_spec.loader.exec_module(tp)

ANVIL_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # public
ROLES = ("DEPLOYER", "ATTESTER", "WATCHER", "RESOLVER", "MALICIOUS")
REFERENCE = {
    "bondWei": "10000000000000000",
    "challengeWindowSec": 120,
    "resolutionWindowSec": 300,
    "pauseThresholdUsd8": "400000000002",
    "ltvThresholdUsd8": "100000000000",
    "reducedLtvBps": 5000,
    "defaultMaxLtvBps": 8000,
    "marketIdString": "aave-v3-eth-weth-stable",
}
SECRET_RPC = "https://base-sepolia.example-rpc.test/v2/SECRETPATHKEY123"


def _fresh_keys() -> Dict[str, str]:
    return {f"{role}_PK": "0x" + Account.create().key.hex().removeprefix("0x") for role in ROLES}


def _env(**overrides: str) -> Dict[str, str]:
    env = {
        **_fresh_keys(),
        "TESTNET_RPC_URL": SECRET_RPC,
        "TESTNET_CHAIN_ID": "84532",
        "DEPLOYMENTS_FILE": "deployments/84532.json",
        "WATCHER_START_BLOCK": "",
        "BOND_WEI": "10000000000000000",
        "CHALLENGE_WINDOW_SEC": "120",
        "RESOLUTION_WINDOW_SEC": "300",
        "TOLERANCE_BPS": "0",
        "MARKET_ID_STRING": "aave-v3-eth-weth-stable",
        "PAUSE_THRESHOLD_USD8": "400000000002",
        "LTV_THRESHOLD_USD8": "100000000000",
        "REDUCED_LTV_BPS": "5000",
        "DEFAULT_MAX_LTV_BPS": "8000",
        "BACKEND_URL": "http://127.0.0.1:8000",
        "BACKEND_PUBLIC_URL": "http://127.0.0.1:8000",
        "FETCH_ALLOW_LOCALHOST": "true",
        "API_WRITE_TOKEN": "a-local-token",
    }
    env.update(overrides)
    return env


def _run(env: Dict[str, str], chain_id: Optional[int] = 84532, ignored: bool = True, keys_only: bool = False):
    calls = []

    def rpc(url: str) -> int:
        calls.append(url)
        if chain_id is None:
            raise tp.PreflightError("connection refused")
        return chain_id

    checks = tp.run_checks(
        env,
        env_file=Path(".env.testnet"),
        reference=REFERENCE,
        rpc_chain_id=None if keys_only else rpc,
        is_ignored=lambda _path: ignored,
        keys_only=keys_only,
    )
    return checks, calls


def _status(checks, name: str) -> str:
    matches = [c for c in checks if c.name == name]
    assert matches, f"no check named {name}: {[c.name for c in checks]}"
    return matches[0].status


def _text(checks) -> str:
    return "\n".join(f"{c.status} {c.name} {c.detail}" for c in checks)


def test_valid_testnet_env_passes_every_check():
    checks, calls = _run(_env())
    assert not tp.failed(checks), _text(checks)
    assert _status(checks, "role keys") == "PASS"
    assert _status(checks, "rpc chain id") == "PASS"
    assert calls == [SECRET_RPC]


def test_public_anvil_key_is_rejected_and_never_printed():
    checks, _ = _run(_env(ATTESTER_PK=ANVIL_KEY_0))
    assert tp.failed(checks)
    text = _text(checks)
    assert "ATTESTER_PK" in text and "public development account" in text
    assert ANVIL_KEY_0 not in text and ANVIL_KEY_0[2:] not in text


def test_later_hardhat_dev_account_is_rejected():
    Account.enable_unaudited_hdwallet_features()
    key19 = Account.from_mnemonic(tp.PUBLIC_DEV_MNEMONIC, account_path="m/44'/60'/0'/0/19").key.hex()
    checks, _ = _run(_env(WATCHER_PK="0x" + key19.removeprefix("0x")))
    assert "WATCHER_PK" in _text(checks) and tp.failed(checks)


def test_duplicate_role_keys_are_rejected():
    env = _env()
    env["RESOLVER_PK"] = env["WATCHER_PK"]
    checks, _ = _run(env)
    assert tp.failed(checks)
    assert "WATCHER_PK" in _text(checks) and "RESOLVER_PK" in _text(checks)


@pytest.mark.parametrize("bad", ["", "0x1234", "not-a-key", "0x" + "00" * 32, "0x" + "ff" * 32])
def test_missing_or_invalid_key_is_rejected_without_echo(bad):
    checks, _ = _run(_env(MALICIOUS_PK=bad))
    assert tp.failed(checks)
    text = _text(checks)
    assert "MALICIOUS_PK" in text
    if len(bad) > 6:
        assert bad not in text


def test_role_address_must_match_its_key():
    env = _env(ATTESTER_ADDRESS=Account.create().address)
    checks, _ = _run(env)
    assert "ATTESTER_ADDRESS" in _text(checks) and tp.failed(checks)


def test_missing_rpc_url_is_a_blocker_and_no_request_is_made():
    checks, calls = _run(_env(TESTNET_RPC_URL=""))
    assert _status(checks, "rpc url") == "FAIL"
    assert calls == []


def test_rpc_url_is_shown_as_host_only():
    checks, _ = _run(_env())
    text = _text(checks)
    assert "base-sepolia.example-rpc.test" in text
    assert "SECRETPATHKEY123" not in text and "/v2/" not in text


def test_wrong_chain_from_rpc_fails():
    checks, _ = _run(_env(), chain_id=8453)
    assert _status(checks, "rpc chain id") == "FAIL"
    assert "8453" in _text(checks)


def test_unreachable_rpc_fails():
    checks, _ = _run(_env(), chain_id=None)
    assert _status(checks, "rpc chain id") == "FAIL"


def test_watcher_start_block_zero_is_rejected():
    checks, _ = _run(_env(WATCHER_START_BLOCK="0"))
    assert _status(checks, "watcher start block") == "FAIL"


def test_local_deployments_file_is_rejected():
    checks, _ = _run(_env(DEPLOYMENTS_FILE="deployments/31337.json"))
    assert _status(checks, "deployments file") == "FAIL"


@pytest.mark.parametrize(
    "name,value",
    [("BOND_WEI", "20000000000000000"), ("CHALLENGE_WINDOW_SEC", "60"), ("RESOLUTION_WINDOW_SEC", "30"),
     ("TOLERANCE_BPS", "5"), ("REDUCED_LTV_BPS", "6000"), ("DEFAULT_MAX_LTV_BPS", "9000"),
     ("PAUSE_THRESHOLD_USD8", "1"), ("LTV_THRESHOLD_USD8", ""), ("MARKET_ID_STRING", "other")],
)
def test_deploy_parameters_must_match_the_validated_local_configuration(name, value):
    checks, _ = _run(_env(**{name: value}))
    assert _status(checks, "deploy parameters") == "FAIL"
    assert name in _text(checks)


def test_localhost_case_files_are_a_warning_and_need_localhost_fetching():
    checks, _ = _run(_env())
    assert _status(checks, "case-file hosting") == "WARN"
    checks, _ = _run(_env(FETCH_ALLOW_LOCALHOST="false"))
    assert _status(checks, "case-file hosting") == "FAIL"


def test_public_https_case_files_pass():
    checks, _ = _run(_env(BACKEND_PUBLIC_URL="https://case-files.example.test", FETCH_ALLOW_LOCALHOST="false"))
    assert _status(checks, "case-file hosting") == "PASS"


def test_env_file_must_be_git_ignored():
    checks, _ = _run(_env(), ignored=False)
    assert _status(checks, "env file ignored") == "FAIL"


def test_keys_only_mode_checks_keys_and_parameters_without_network():
    checks, calls = _run(_env(), keys_only=True)
    assert calls == []
    names = {c.name for c in checks}
    assert {"role keys", "deploy parameters", "rpc url"} <= names
    assert "rpc chain id" not in names and "case-file hosting" not in names
    assert not tp.failed(checks)


def test_backend_token_must_be_set_and_is_never_printed():
    checks, _ = _run(_env(API_WRITE_TOKEN=""))
    assert _status(checks, "backend token") == "FAIL"
    checks, _ = _run(_env(API_WRITE_TOKEN="very-secret-token-value"))
    assert _status(checks, "backend token") == "PASS"
    assert "very-secret-token-value" not in _text(checks)


# ---------------------------------------------------------------- http_chain_id (mocked HTTP)

import io  # noqa: E402
import json  # noqa: E402
import urllib.error  # noqa: E402


class _Reply:
    def __init__(self, body: bytes):
        self._body = io.BytesIO(body)

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(SECRET_RPC, code, "error", {"server": "cloudflare"}, io.BytesIO(body))


def _ok(result: str = "0x14a34", **fields) -> _Reply:
    return _Reply(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result, **fields}).encode())


def _mock_urlopen(monkeypatch, outcomes):
    """Each call takes the next outcome: a _Reply is returned, an exception is raised."""
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(tp.urllib.request, "urlopen", fake_urlopen)
    return calls


def _no_sleep(_seconds: float) -> None:
    return None


def test_http_chain_id_sends_a_json_rpc_post_with_an_explicit_user_agent(monkeypatch):
    calls = _mock_urlopen(monkeypatch, [_ok()])
    assert tp.http_chain_id(SECRET_RPC, sleep=_no_sleep) == 84532
    request = calls[0]
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("User-agent", "").startswith("stressproof-preflight/")
    assert json.loads(request.data) == {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}


def test_http_chain_id_reports_another_chain_for_the_check_to_reject(monkeypatch):
    _mock_urlopen(monkeypatch, [_ok("0x2105")])  # 8453, Base mainnet
    assert tp.http_chain_id(SECRET_RPC, sleep=_no_sleep) == 8453
    assert tp.check_rpc_chain(SECRET_RPC, lambda _u: 8453).status == "FAIL"


@pytest.mark.parametrize(
    "body,expected",
    [
        (b"<html>not json</html>", "not valid JSON"),
        (json.dumps({"id": 1, "result": "0x14a34"}).encode(), "JSON-RPC 2.0"),
        (json.dumps({"jsonrpc": "2.0", "id": 7, "result": "0x14a34"}).encode(), "JSON-RPC 2.0"),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": "84532"}).encode(), "hex"),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "method not found"}}).encode(),
         "-32601"),
    ],
)
def test_http_chain_id_rejects_invalid_replies_without_retrying(monkeypatch, body, expected):
    calls = _mock_urlopen(monkeypatch, [_Reply(body)])
    with pytest.raises(tp.PreflightError, match=expected):
        tp.http_chain_id(SECRET_RPC, sleep=_no_sleep)
    assert len(calls) == 1


def test_http_403_is_reported_with_status_and_excerpt_and_not_retried(monkeypatch):
    calls = _mock_urlopen(monkeypatch, [_http_error(403, b"error code: 1010\n")])
    with pytest.raises(tp.PreflightError) as info:
        tp.http_chain_id(SECRET_RPC, sleep=_no_sleep)
    message = str(info.value)
    assert "HTTP 403" in message and "error code: 1010" in message
    assert len(calls) == 1


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_http_errors_are_retried_then_succeed(monkeypatch, code):
    calls = _mock_urlopen(monkeypatch, [_http_error(code, b"slow down"), _ok()])
    assert tp.http_chain_id(SECRET_RPC, sleep=_no_sleep) == 84532
    assert len(calls) == 2


def test_transient_errors_stop_after_a_bounded_number_of_attempts(monkeypatch):
    calls = _mock_urlopen(monkeypatch, [_http_error(503, b"unavailable")] * 5)
    with pytest.raises(tp.PreflightError, match="HTTP 503"):
        tp.http_chain_id(SECRET_RPC, attempts=3, sleep=_no_sleep)
    assert len(calls) == 3


def test_timeouts_are_retried_and_reported(monkeypatch):
    calls = _mock_urlopen(monkeypatch, [TimeoutError("timed out")] * 3)
    with pytest.raises(tp.PreflightError, match="timed out"):
        tp.http_chain_id(SECRET_RPC, attempts=3, sleep=_no_sleep)
    assert len(calls) == 3
    calls = _mock_urlopen(monkeypatch, [urllib.error.URLError(TimeoutError("timed out")), _ok()])
    assert tp.http_chain_id(SECRET_RPC, sleep=_no_sleep) == 84532


def test_error_messages_never_contain_the_url_path_or_secrets(monkeypatch):
    echo = f"bad request for {SECRET_RPC} apikey=0123456789abcdef0123456789abcdef".encode()
    _mock_urlopen(monkeypatch, [_http_error(400, echo)])
    with pytest.raises(tp.PreflightError) as info:
        tp.http_chain_id(SECRET_RPC, sleep=_no_sleep)
    message = str(info.value)
    assert "HTTP 400" in message
    assert "SECRETPATHKEY123" not in message and "/v2/" not in message
    assert "0123456789abcdef0123456789abcdef" not in message
