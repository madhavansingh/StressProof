"""
Shared file helpers for pipeline steps: canonical JSON and JSONL I/O, atomic writes,
structure checks for accounts, assets, manifests and snapshots, and the guard that keeps
RPC URLs and keys out of outputs.

Every check raises PipelineError with the file and field at fault, so CLIs exit non-zero
with a clear message instead of a traceback.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from stressproof_core.canonical_json import canonical_bytes, parse_strict
from stressproof_core.constants import (
    ACCOUNT_ID_REAL_REGEX,
    ACCOUNT_ID_SYNTH_REGEX,
    DATA_CLASSES,
    DECIMAL_REGEX,
    EXPECTED_DECIMALS,
    HASH_REGEX,
    MAX_BONUS_BPS,
    MAX_LT_BONUS_PRODUCT,
    MAX_LT_BPS,
    MIN_BONUS_BPS,
    MIN_LT_BPS,
    ORIGIN_REAL,
    ORIGIN_SYNTHETIC,
)
from stressproof_core.models import DatasetManifest

from .paths import REPO_ROOT

ACCOUNT_KEYS = frozenset({"collateralAmount", "debtUsd8", "id", "origin"})
ASSET_KEYS = frozenset({"bonusBps", "decimals", "ltBps", "priceUsd8"})
MANIFEST_KEYS = frozenset(DatasetManifest.__annotations__)
EXCLUDED_KEYS = frozenset({"eMode", "noDebt", "nonStableDebt", "nonWethCollateral", "other", "wethNotCollateral"})
COUNT_KEYS = frozenset({"real", "synthetic"})

_DEC = re.compile(DECIMAL_REGEX)
_HASH = re.compile(HASH_REGEX)
_ID_BY_ORIGIN = {ORIGIN_REAL: re.compile(ACCOUNT_ID_REAL_REGEX), ORIGIN_SYNTHETIC: re.compile(ACCOUNT_ID_SYNTH_REGEX)}

# Env variables whose values must never appear in a written file.
_SECRET_ENV = re.compile(r"(_PK|_RPC_URL|_KEY|_SECRET|_PASSWORD|_JWT|_TOKEN)$")


class PipelineError(Exception):
    """A pipeline step cannot continue; the CLI prints it and exits non-zero."""


# --- writing --------------------------------------------------------------------

def atomic_write(path: Path, data: bytes) -> None:
    """
    Write via a uniquely named temporary file in the destination directory, fsync, then
    os.replace. On any failure the temporary file is removed and an existing destination
    is left untouched; concurrent writers never share a temporary file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def assert_no_secrets(data: bytes, what: str) -> None:
    """Refuse to write bytes containing a URL or the value of any secret-looking env variable."""
    if b"://" in data:
        raise PipelineError(f"{what}: refusing to write a URL into an output file")
    for name, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_ENV.search(name) and value.encode() in data:
            raise PipelineError(f"{what}: refusing to write the value of ${name}")


def encode_canonical(obj: Any, what: str) -> bytes:
    data = canonical_bytes(obj)
    assert_no_secrets(data, what)
    return data


def encode_jsonl(records: Iterable[Dict], what: str) -> bytes:
    data = b"".join(canonical_bytes(r) + b"\n" for r in records)
    assert_no_secrets(data, what)
    return data


def write_canonical(path: Path, obj: Any) -> bytes:
    data = encode_canonical(obj, path.name)
    atomic_write(path, data)
    return data


def write_jsonl(path: Path, records: Iterable[Dict]) -> bytes:
    data = encode_jsonl(records, path.name)
    atomic_write(path, data)
    return data


# --- reading --------------------------------------------------------------------

def read_canonical(path: Path) -> Any:
    try:
        return parse_strict(path.read_bytes())
    except FileNotFoundError:
        raise PipelineError(f"missing file {path}") from None
    except ValueError as e:
        raise PipelineError(f"{path}: {e}") from None


def read_jsonl(path: Path) -> List[Dict]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise PipelineError(f"missing file {path}") from None
    records = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(parse_strict(line))
        except ValueError as e:
            raise PipelineError(f"{path.name}:{lineno}: {e}") from None
    return records


# --- structure checks -------------------------------------------------------------

def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _require_int(v: Any, where: str, lo: Optional[int] = None, hi: Optional[int] = None) -> int:
    if not _is_int(v):
        raise PipelineError(f"{where}: expected integer, got {type(v).__name__}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise PipelineError(f"{where}: {v} outside [{lo}, {hi}]")
    return v


def _require_str(v: Any, where: str) -> str:
    if not isinstance(v, str):
        raise PipelineError(f"{where}: expected string, got {type(v).__name__}")
    return v


def _require_keys(obj: Any, keys: frozenset, where: str) -> Dict:
    if not isinstance(obj, dict):
        raise PipelineError(f"{where}: expected object, got {type(obj).__name__}")
    if set(obj) != keys:
        raise PipelineError(f"{where}: missing keys {sorted(keys - set(obj))}, unknown keys {sorted(set(obj) - keys)}")
    return obj


def check_account(record: Any, expected_origin: str, where: str) -> Dict:
    """Validate one account record; raise PipelineError with the location on any problem."""
    if expected_origin not in _ID_BY_ORIGIN:
        raise PipelineError(f"{where}: unsupported origin {expected_origin!r}")
    _require_keys(record, ACCOUNT_KEYS, where)
    if record["origin"] != expected_origin:
        raise PipelineError(f"{where}: origin {record['origin']!r} != {expected_origin!r}")
    if not isinstance(record["id"], str) or not _ID_BY_ORIGIN[expected_origin].match(record["id"]):
        raise PipelineError(f"{where}: malformed {expected_origin} id {record['id']!r}")
    for key in ("collateralAmount", "debtUsd8"):
        if not isinstance(record[key], str) or not _DEC.match(record[key]):
            raise PipelineError(f"{where}: {key} {record[key]!r} is not a canonical decimal string")
    return record


def check_weth_params(price_usd8: Any, lt_bps: Any, bonus_bps: Any, where: str) -> None:
    """The WETH parameters the replay engine consumes (plan §10.3 domain)."""
    _require_int(price_usd8, f"{where}.priceUsd8", lo=1)
    _require_int(lt_bps, f"{where}.ltBps", MIN_LT_BPS, MAX_LT_BPS)
    _require_int(bonus_bps, f"{where}.bonusBps", MIN_BONUS_BPS, MAX_BONUS_BPS)
    if lt_bps * bonus_bps > MAX_LT_BONUS_PRODUCT:
        raise PipelineError(f"{where}: ltBps * bonusBps = {lt_bps * bonus_bps} exceeds {MAX_LT_BONUS_PRODUCT} (= 100%)")


def check_assets(assets: Any, where: str = "assets") -> Dict:
    """assets must be exactly {"WETH": {bonusBps, decimals, ltBps, priceUsd8}} within the replay domain."""
    _require_keys(assets, frozenset({"WETH"}), where)
    weth = _require_keys(assets["WETH"], ASSET_KEYS, f"{where}.WETH")
    price = weth["priceUsd8"]
    if not isinstance(price, str) or not _DEC.match(price):
        raise PipelineError(f"{where}.WETH.priceUsd8: {price!r} is not a canonical decimal string")
    _require_int(weth["decimals"], f"{where}.WETH.decimals", EXPECTED_DECIMALS, EXPECTED_DECIMALS)
    check_weth_params(int(price), weth["ltBps"], weth["bonusBps"], f"{where}.WETH")
    return assets


_MANIFEST_STR_FIELDS = ("dataProviderAddress", "datasetId", "extractedAt", "extractionScriptCommit", "filter",
                        "forkBlockHash", "network", "oracleAddress", "poolAddress", "poolAddressesProvider",
                        "rpcProvider", "snapshotHash", "wethAddress")


def check_manifest(manifest: Any, where: str, *, final: bool) -> Dict:
    """
    Check every plan §8.1 manifest field and nested type. Drafts may leave extractedAt,
    extractionScriptCommit and snapshotHash empty; a final manifest must have them set.
    """
    _require_keys(manifest, MANIFEST_KEYS, where)
    for key in _MANIFEST_STR_FIELDS:
        _require_str(manifest[key], f"{where}.{key}")
    if manifest["dataClass"] not in DATA_CLASSES:
        raise PipelineError(f"{where}.dataClass: {manifest['dataClass']!r} not in {list(DATA_CLASSES)}")
    _require_int(manifest["forkBlock"], f"{where}.forkBlock", lo=0)
    _require_int(manifest["forkBlockTimestamp"], f"{where}.forkBlockTimestamp", lo=0)
    if manifest["syntheticSeed"] is not None:
        _require_int(manifest["syntheticSeed"], f"{where}.syntheticSeed", lo=0)
    counts = _require_keys(manifest["counts"], COUNT_KEYS, f"{where}.counts")
    for key in COUNT_KEYS:
        _require_int(counts[key], f"{where}.counts.{key}", lo=0)
    excluded = _require_keys(manifest["excludedCounts"], EXCLUDED_KEYS, f"{where}.excludedCounts")
    for key in EXCLUDED_KEYS:
        _require_int(excluded[key], f"{where}.excludedCounts.{key}", lo=0)
    allowlist = manifest["stablecoinAllowlist"]
    if not isinstance(allowlist, list):
        raise PipelineError(f"{where}.stablecoinAllowlist: expected array")
    for i, entry in enumerate(allowlist):
        _require_keys(entry, frozenset({"address", "symbol"}), f"{where}.stablecoinAllowlist[{i}]")
        _require_str(entry["address"], f"{where}.stablecoinAllowlist[{i}].address")
        _require_str(entry["symbol"], f"{where}.stablecoinAllowlist[{i}].symbol")
    if final:
        if not _HASH.match(manifest["snapshotHash"]):
            raise PipelineError(f"{where}.snapshotHash: not a 0x-prefixed 32-byte hex hash")
        for key in ("extractedAt", "extractionScriptCommit"):
            if not manifest[key]:
                raise PipelineError(f"{where}.{key}: must be set in a final manifest")
    return manifest


def check_snapshot(snapshot: Any, where: str = "snapshot") -> Dict:
    _require_keys(snapshot, frozenset({"accounts", "assets"}), where)
    check_assets(snapshot["assets"], f"{where}.assets")
    accounts = snapshot["accounts"]
    if not isinstance(accounts, list) or not accounts:
        raise PipelineError(f"{where}.accounts: expected a non-empty array")
    for i, acc in enumerate(accounts):
        origin = acc.get("origin") if isinstance(acc, dict) else None
        check_account(acc, origin if origin in _ID_BY_ORIGIN else ORIGIN_SYNTHETIC, f"{where}.accounts[{i}]")
    return snapshot


# --- provenance -------------------------------------------------------------------

def git_commit(allow_dirty: bool) -> str:
    """HEAD commit of the repo. Refuses a dirty tree unless allow_dirty, which marks the commit '-dirty'."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        if allow_dirty:
            return "unknown"
        raise PipelineError(f"cannot read git commit ({e}); pass --allow-dirty to continue") from None
    if dirty:
        if not allow_dirty:
            raise PipelineError("working tree is dirty; commit first or pass --allow-dirty (the commit is then marked -dirty)")
        return sha + "-dirty"
    return sha


def optional_file(path: Path) -> Optional[Path]:
    return path if path.exists() else None
