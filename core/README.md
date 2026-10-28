# stressproof-core

The pure Python deterministic calculation engine and evidence validation library for StressProof.

## Rules & Constraints
1. **Zero Network / File I/O:** This package contains no network calls, database queries, file writing, or clock reading.
2. **Integer Arithmetic Discipline:** All financial numbers and liquidation logic operate strictly on integers. Floats are rejected.
3. **Deterministic Replay:** Given an identical case file, `replay(case_file)` produces byte-for-byte identical outcomes on every platform.
4. **Canonical Serialization:** Enforces strict sorting, compact JSON formatting, and canonical string representation for Keccak-256 evidence hashing.

## Modules
* `canonical_json.py`: `canonical_bytes()`, `parse_strict()`
* `hashing.py`: `keccak256_hex()`, `market_id()` using `eth_hash`
* `models.py`: Typed data contracts
* `constants.py`: Model constraints and bounds
* `validation.py`: Closed set of rules V-01..V-14
* `replay.py`: The `static-liquidation-v1` liquidation replay algorithm
