# stressproof-core

The pure Python deterministic calculation engine and evidence validation library for StressProof.
It is the verdict path: the attester, watcher, resolver and backend all import it.

## Rules & Constraints
1. **Zero Network / File I/O:** This package contains no network calls, database queries, file writing, or clock reading.
2. **Integer Arithmetic Discipline:** All financial numbers and liquidation logic operate strictly on integers. Floats are rejected.
3. **Deterministic Replay:** Given an identical case file, `replay(case_file)` produces byte-for-byte identical outcomes on every platform.
4. **Canonical Serialization:** Enforces strict sorting, compact JSON formatting, and canonical string representation for Keccak-256 evidence hashing.

## Public API (`from stressproof_core import ...`)

| Function | Purpose |
|---|---|
| `canonical_bytes(obj) -> bytes` | Canonical JSON. Rejects floats, tuples, sets, bytes and ints with \|v\| >= 2**53 |
| `parse_strict(b) -> obj` | Parse and require the bytes to already be canonical; raises `ValueError` otherwise |
| `keccak256_hex(b) -> "0x…"` | Keccak-256 (never `hashlib.sha3_256`) |
| `market_id(s) -> "0x…"` | bytes32 market id for `postClaim` |
| `validate(raw_bytes, onchain=None) -> list[Violation]` | Rules V-01..V-14. Never raises on hostile input |
| `evaluate(raw_bytes, onchain) -> Evaluation` | Verdict: `MATCH`, `WRONG_RESULT` or `EVIDENCE_INVALID`, plus the challenge counter-value |
| `replay(case_file) -> ReplayResult` | `static-liquidation-v1` (call only on validated files) |
| `build_case_file(snapshot, manifest, scenario, rationale, replayer_commit, market_id_string)` | Assemble a case file with `results` from replay |
| `build_replay_report(evaluation, *, chain_id, registry, claim_id, evidence_hash, fetched_from, watcher, replayer_commit, claimed_onchain_usd8, case_file_copy_uri)` | Replay report per `docs/schemas/replay-report.md` |
| `check_replay_report(obj) -> list[str]` | Shape check for an uploaded report |

`onchain` for `evaluate` is `{"evidenceHash": "0x…", "marketId": "0x…", "claimedResidualBadDebt": int}`.

### Verdict rules
1. Any of V-01..V-13 fails -> `EVIDENCE_INVALID`, counter 0, no replay (V-02 failure means the file is never parsed).
2. The replayed residual differs from the on-chain claim (or V-14 fails and it differs) -> `WRONG_RESULT`, counter = replayed residual.
3. V-14 fails but the replay equals the on-chain claim -> `EVIDENCE_INVALID` (a `WRONG_RESULT` challenge would revert with `CounterEqualsClaim`).
4. Otherwise -> `MATCH`. Differences in the three informational metrics only appear in `info_mismatches`.

Map the verdict to the contract's `Reason` enum: `WRONG_RESULT` = 1, `EVIDENCE_INVALID` = 2.

## Watcher usage

```python
from stressproof_core import build_replay_report, canonical_bytes, evaluate

raw = fetch_raw_bytes(claim.caseFileURI)            # SSRF-safe fetch, never re-serialize
ev = evaluate(raw, {
    "evidenceHash": claim.evidenceHash,
    "marketId": claim.marketId,
    "claimedResidualBadDebt": claim.claimedResidualBadDebt,
})
if ev.verdict != "MATCH":
    report = build_replay_report(
        ev, chain_id=84532, registry=registry_addr, claim_id=claim_id,
        evidence_hash=claim.evidenceHash, fetched_from=claim.caseFileURI,
        watcher=watcher_addr, replayer_commit=git_sha,
        claimed_onchain_usd8=claim.claimedResidualBadDebt,
        case_file_copy_uri=copy_uri if ev.hash_matches else "",
    )
    report_bytes = canonical_bytes(report)          # POST /replay-reports, then challenge()
    # challenge(claim_id, reason, ev.counter_residual_usd8, report_uri, keccak256_hex(report_bytes))
```

## Modules
* `canonical_json.py`: `canonical_bytes()`, `parse_strict()`
* `hashing.py`: `keccak256_hex()`, `market_id()` using `eth_hash`
* `models.py`: Typed data contracts (changes here are `SCHEMA:` changes)
* `constants.py`: Model constraints and bounds
* `validation.py`: Closed set of rules V-01..V-14
* `verdict.py`: `evaluate()`
* `report.py`: case-file and replay-report builders
* `replay.py`: The `static-liquidation-v1` liquidation replay algorithm
