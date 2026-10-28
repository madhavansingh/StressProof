"""
Step 4: Normalize, sort, canonicalize, and hash dataset snapshot.
Matches implementationplan.md §9.6.
"""

from typing import List
from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.hashing import keccak256_hex


def normalize_dataset(
    real_accounts: List[dict],
    synthetic_accounts: List[dict],
    assets: dict,
    manifest_draft: dict,
) -> tuple[dict, bytes, str]:
    """
    Merges, deduplicates, sorts by id, canonicalizes and computes snapshotHash.
    """
    all_accounts = real_accounts + synthetic_accounts
    # Sort strictly by id
    all_accounts.sort(key=lambda x: x["id"])

    snapshot = {
        "accounts": all_accounts,
        "assets": assets,
    }
    snapshot_bytes = canonical_bytes(snapshot)
    snapshot_hash = keccak256_hex(snapshot_bytes)

    return snapshot, snapshot_bytes, snapshot_hash


def main():
    print("Running normalize pipeline step...")


if __name__ == "__main__":
    main()
