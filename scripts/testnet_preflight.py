#!/usr/bin/env python3
"""Local preflight for a Base Sepolia (84532) session. Sends no transaction and signs nothing.

Checks the testnet env file (default .env.testnet):
- the file is git-ignored;
- five role keys are present, valid and distinct, none is a public development account (the
  Anvil/Hardhat "test ... junk" mnemonic), and any <ROLE>_ADDRESS matches its key;
- deploy parameters equal the validated local deployment (deployments/31337.json);
- TESTNET_RPC_URL is set (shown as scheme and host only) and, unless --no-network, answers a
  read-only eth_chainId with 84532;
- agents use deployments/84532.json and do not scan from block 0;
- case-file URLs can be fetched by the watcher and resolver, and API_WRITE_TOKEN is set.

Never prints a private key, a token or the RPC URL's path or query.

Usage:
    uv run --no-sync python scripts/testnet_preflight.py [--env-file .env.testnet] [--keys-only] [--no-network]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_SEPOLIA_CHAIN_ID = 84532
ROLES = ("DEPLOYER", "ATTESTER", "WATCHER", "RESOLVER", "MALICIOUS")
PUBLIC_DEV_MNEMONIC = "test test test test test test test test test test test junk"
PUBLIC_DEV_ACCOUNTS = 20  # Anvil creates 10 default accounts, Hardhat 20, from the mnemonic above
TESTNET_DEPLOYMENTS_FILE = "deployments/84532.json"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
_KEY_RE = re.compile(r"0x[0-9a-fA-F]{64}")
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_TRUE = {"1", "true", "yes", "on"}

# env name -> key in deployments/31337.json (the configuration the local gate validated)
PARAMETERS = {
    "BOND_WEI": "bondWei",
    "CHALLENGE_WINDOW_SEC": "challengeWindowSec",
    "RESOLUTION_WINDOW_SEC": "resolutionWindowSec",
    "PAUSE_THRESHOLD_USD8": "pauseThresholdUsd8",
    "LTV_THRESHOLD_USD8": "ltvThresholdUsd8",
    "REDUCED_LTV_BPS": "reducedLtvBps",
    "DEFAULT_MAX_LTV_BPS": "defaultMaxLtvBps",
    "MARKET_ID_STRING": "marketIdString",
}


class PreflightError(Exception):
    """A check could not run (its message never contains secrets)."""


@dataclass(frozen=True)
class Check:
    status: str  # PASS, WARN or FAIL
    name: str
    detail: str


def failed(checks: List[Check]) -> bool:
    return any(c.status == "FAIL" for c in checks)


_dev_addresses: Optional[FrozenSet[str]] = None


def public_dev_addresses() -> FrozenSet[str]:
    """Lowercase addresses of the public development accounts, derived offline once."""
    global _dev_addresses
    if _dev_addresses is None:
        from eth_account import Account

        Account.enable_unaudited_hdwallet_features()
        _dev_addresses = frozenset(
            Account.from_mnemonic(PUBLIC_DEV_MNEMONIC, account_path=f"m/44'/60'/0'/0/{i}").address.lower()
            for i in range(PUBLIC_DEV_ACCOUNTS)
        )
    return _dev_addresses


def _short(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}"


def _value(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _derive(name: str, raw: str) -> Tuple[Optional[str], Optional[str]]:
    """(address, problem) for one key; the key itself never appears in a problem."""
    if not raw:
        return None, f"{name} is not set"
    if not _KEY_RE.fullmatch(raw) or not 0 < int(raw, 16) < _SECP256K1_ORDER:
        return None, f"{name} is not a valid private key (0x and 64 hex characters, in the secp256k1 range)"
    from eth_account import Account

    return Account.from_key(raw).address, None


def check_role_keys(env: Mapping[str, str]) -> Check:
    problems: List[str] = []
    owners: Dict[str, List[str]] = {}
    summary: List[str] = []
    for role in ROLES:
        name = f"{role}_PK"
        address, problem = _derive(name, _value(env, name))
        if problem:
            problems.append(problem)
            continue
        if address.lower() in public_dev_addresses():
            problems.append(f"{name} is a public development account ({_short(address)}); create a dedicated testnet key")
        explicit = _value(env, f"{role}_ADDRESS")
        if explicit and explicit.lower() != address.lower():
            problems.append(f"{role}_ADDRESS does not match {name}")
        owners.setdefault(address.lower(), []).append(name)
        summary.append(f"{role.lower()} {_short(address)}")
    for names in owners.values():
        if len(names) > 1:
            problems.append(f"{' and '.join(names)} use the same account; every role needs its own key")
    if problems:
        return Check("FAIL", "role keys", "; ".join(problems))
    return Check("PASS", "role keys", "five distinct dedicated keys: " + ", ".join(summary))


def check_testnet_chain_setting(env: Mapping[str, str]) -> Check:
    value = _value(env, "TESTNET_CHAIN_ID")
    if value and value != str(BASE_SEPOLIA_CHAIN_ID):
        return Check("FAIL", "testnet chain id", f"TESTNET_CHAIN_ID is {value}, expected {BASE_SEPOLIA_CHAIN_ID}")
    return Check("PASS", "testnet chain id", f"{BASE_SEPOLIA_CHAIN_ID} (Base Sepolia)")


def check_deploy_parameters(env: Mapping[str, str], reference: Mapping[str, object]) -> Check:
    problems = [
        f"{name} is {_value(env, name) or 'empty'}, expected {reference[key]}"
        for name, key in PARAMETERS.items()
        if _value(env, name) != str(reference[key])
    ]
    if _value(env, "TOLERANCE_BPS") != "0":
        problems.append(f"TOLERANCE_BPS is {_value(env, 'TOLERANCE_BPS') or 'empty'}, expected 0")
    if problems:
        return Check("FAIL", "deploy parameters", "; ".join(problems))
    return Check(
        "PASS",
        "deploy parameters",
        f"bond {reference['bondWei']} wei, windows {reference['challengeWindowSec']}/{reference['resolutionWindowSec']} s, "
        f"pause {reference['pauseThresholdUsd8']}, ltv {reference['ltvThresholdUsd8']} (USD8), "
        f"reduced/default LTV {reference['reducedLtvBps']}/{reference['defaultMaxLtvBps']} bps, tolerance 0",
    )


def check_rpc_url(env: Mapping[str, str]) -> Tuple[Check, Optional[str]]:
    url = _value(env, "TESTNET_RPC_URL")
    if not url:
        return Check("FAIL", "rpc url", "TESTNET_RPC_URL is empty; add a Base Sepolia RPC URL to the env file"), None
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        return Check("FAIL", "rpc url", "TESTNET_RPC_URL is not an http(s) URL"), None
    if parsed.scheme == "http" and host not in LOCAL_HOSTS:
        return Check("FAIL", "rpc url", f"use https for a remote RPC (got http://{host})"), None
    return Check("PASS", "rpc url", f"{parsed.scheme}://{host} (path and query hidden)"), url


def check_rpc_chain(url: str, rpc_chain_id: Callable[[str], int]) -> Check:
    try:
        chain_id = rpc_chain_id(url)
    except PreflightError as exc:
        return Check("FAIL", "rpc chain id", str(exc))
    if chain_id != BASE_SEPOLIA_CHAIN_ID:
        return Check("FAIL", "rpc chain id", f"the RPC reports chain {chain_id}, expected {BASE_SEPOLIA_CHAIN_ID}")
    return Check("PASS", "rpc chain id", f"{chain_id} (read-only eth_chainId)")


def check_deployments_file(env: Mapping[str, str]) -> Check:
    value = _value(env, "DEPLOYMENTS_FILE")
    if value != TESTNET_DEPLOYMENTS_FILE:
        return Check("FAIL", "deployments file", f"DEPLOYMENTS_FILE is {value or 'empty'}, expected {TESTNET_DEPLOYMENTS_FILE}")
    return Check("PASS", "deployments file", TESTNET_DEPLOYMENTS_FILE)


def check_watcher_start_block(env: Mapping[str, str]) -> Check:
    value = _value(env, "WATCHER_START_BLOCK")
    if not value:
        return Check("PASS", "watcher start block", "empty: the watcher starts at the registry's deploy block")
    if not value.isdigit() or int(value) == 0:
        return Check("FAIL", "watcher start block", f"WATCHER_START_BLOCK={value} would scan from the wrong block; leave it empty")
    return Check("PASS", "watcher start block", f"starts at block {value}")


def check_case_file_hosting(env: Mapping[str, str]) -> Check:
    public_url = _value(env, "BACKEND_PUBLIC_URL") or "http://127.0.0.1:8000"
    parsed = urlparse(public_url)
    host = parsed.hostname or ""
    if host in LOCAL_HOSTS:
        if _value(env, "FETCH_ALLOW_LOCALHOST").lower() not in _TRUE:
            return Check("FAIL", "case-file hosting",
                         f"claims would point at {parsed.scheme}://{host}, but FETCH_ALLOW_LOCALHOST is off, so the watcher and resolver would refuse it")
        return Check("WARN", "case-file hosting",
                     f"claims will point at {parsed.scheme}://{host}: only agents on this machine can fetch the evidence (a same-machine gate run). "
                     "Independent verifiers need a hosted HTTPS case-file URL.")
    if parsed.scheme != "https":
        return Check("WARN", "case-file hosting", f"{parsed.scheme}://{host} is not https")
    return Check("PASS", "case-file hosting", f"https://{host}")


def check_backend_token(env: Mapping[str, str]) -> Check:
    """The agents write case files and feed events with this token; its value is never shown."""
    if not _value(env, "API_WRITE_TOKEN"):
        return Check("FAIL", "backend token",
                     "API_WRITE_TOKEN is empty; set it to the token of the backend you will run (the local backend reads it from the root .env)")
    return Check("PASS", "backend token", "API_WRITE_TOKEN is set (value hidden)")


def check_env_ignored(env_file: Path, is_ignored: Callable[[Path], bool]) -> Check:
    if not is_ignored(env_file):
        return Check("FAIL", "env file ignored", f"{env_file.name} is not git-ignored; it would be committable")
    return Check("PASS", "env file ignored", f"{env_file.name} is git-ignored")


def run_checks(
    env: Mapping[str, str],
    *,
    env_file: Path,
    reference: Mapping[str, object],
    rpc_chain_id: Optional[Callable[[str], int]],
    is_ignored: Callable[[Path], bool],
    keys_only: bool = False,
) -> List[Check]:
    rpc_check, url = check_rpc_url(env)
    checks = [
        check_env_ignored(env_file, is_ignored),
        check_role_keys(env),
        check_testnet_chain_setting(env),
        check_deploy_parameters(env, reference),
        rpc_check,
    ]
    if keys_only:
        return checks
    if url and rpc_chain_id is not None:
        checks.append(check_rpc_chain(url, rpc_chain_id))
    checks += [
        check_deployments_file(env),
        check_watcher_start_block(env),
        check_case_file_hosting(env),
        check_backend_token(env),
    ]
    return checks


# ------------------------------------------------------------------ IO


# Cloudflare (in front of https://sepolia.base.org) rejects Python's default "Python-urllib/x.y"
# User-Agent with HTTP 403 / error 1010, so the request names itself explicitly.
USER_AGENT = "stressproof-preflight/1.0 (read-only eth_chainId)"
RPC_ATTEMPTS = 3
RPC_RETRY_BASE_SEC = 0.5
RPC_MAX_REPLY_BYTES = 64 * 1024
TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
_HEX_QUANTITY = re.compile(r"0x[0-9a-fA-F]+")
_LONG_SECRET = re.compile(r"[A-Za-z0-9_\-]{24,}")


def _excerpt(body: bytes, url: str) -> str:
    """A short, single-line slice of a reply with the URL and anything token-like removed."""
    text = body[:400].decode("utf-8", "replace")
    parsed = urlparse(url)
    for secret in filter(None, (url, parsed.path, parsed.query)):
        if secret not in ("/", ""):
            text = text.replace(secret, "[redacted]")
    text = _LONG_SECRET.sub("[redacted]", " ".join(text.split()))
    return text[:120]


def parse_chain_id_reply(raw: bytes, request_id: int = 1) -> int:
    """Accepts only a JSON-RPC 2.0 reply for this request whose result is a hex quantity."""
    try:
        reply = json.loads(raw)
    except ValueError:
        raise PreflightError("eth_chainId reply is not valid JSON") from None
    if not isinstance(reply, dict) or reply.get("jsonrpc") != "2.0" or reply.get("id") != request_id:
        raise PreflightError("eth_chainId reply is not a JSON-RPC 2.0 response to this request")
    if "error" in reply:
        error = reply["error"] if isinstance(reply["error"], dict) else {}
        message = " ".join(str(error.get("message", "")).split())[:80]
        raise PreflightError(f"eth_chainId returned RPC error {error.get('code')}: {message}")
    result = reply.get("result")
    if not isinstance(result, str) or not _HEX_QUANTITY.fullmatch(result):
        raise PreflightError("eth_chainId result is not a hex quantity")
    return int(result, 16)


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)


def http_chain_id(
    url: str,
    timeout_sec: float = 10.0,
    attempts: int = RPC_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Read-only eth_chainId. Retries 429, 5xx and timeouts a bounded number of times; never
    reports the URL's path or query (they may hold an API key)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        retry = attempt < attempts
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310 (http(s) checked)
                return parse_chain_id_reply(response.read(RPC_MAX_REPLY_BYTES))
        except urllib.error.HTTPError as exc:
            detail = f"HTTP {exc.code}"
            excerpt = _excerpt(exc.read(RPC_MAX_REPLY_BYTES) if exc.fp else b"", url)
            if excerpt:
                detail += f" ({excerpt})"
            if exc.code in TRANSIENT_HTTP_STATUS and retry:
                sleep(RPC_RETRY_BASE_SEC * attempt)
                continue
            raise PreflightError(f"eth_chainId request failed: {detail} after {attempt} attempt(s)") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            kind = "timed out" if _is_timeout(exc) else f"connection error ({type(exc).__name__})"
            if retry:
                sleep(RPC_RETRY_BASE_SEC * attempt)
                continue
            raise PreflightError(f"eth_chainId request failed: {kind} after {attempt} attempt(s)") from None
    raise PreflightError("eth_chainId request failed: no attempts were made")


def git_ignored(path: Path) -> bool:
    git = os.environ.get("GIT", "git")
    result = subprocess.run([git, "check-ignore", "-q", str(path)], cwd=REPO_ROOT, capture_output=True)
    return result.returncode == 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Local Base Sepolia preflight (no transactions)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env.testnet")
    parser.add_argument("--keys-only", action="store_true", help="keys, parameters and RPC URL only (used by deploy.sh)")
    parser.add_argument("--no-network", action="store_true", help="skip the read-only eth_chainId request")
    args = parser.parse_args(argv)

    if not args.env_file.is_file():
        print(f"[FAIL] env file: {args.env_file} not found (cp .env.example {args.env_file.name}, then fill it in)")
        return 1
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(args.env_file).items() if v is not None}
    reference = json.loads((REPO_ROOT / "deployments" / "31337.json").read_text())
    checks = run_checks(
        env,
        env_file=args.env_file,
        reference=reference,
        rpc_chain_id=None if args.no_network else http_chain_id,
        is_ignored=git_ignored,
        keys_only=args.keys_only,
    )
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    if failed(checks):
        print("Preflight FAILED: nothing may be deployed or sent until every FAIL is fixed.")
        return 1
    print("Preflight passed (this is not a deployment and not GATE-24).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
