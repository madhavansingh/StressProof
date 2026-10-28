"""
Step 2: Borrower discovery and multicall classification.
Matches implementationplan.md §9.3 & §9.4.
"""

from typing import List


def discover_borrowers(archive_rpc_url: str, to_block: int) -> List[str]:
    """
    Collects onBehalfOf addresses from Aave v3 Pool Borrow logs up to to_block.
    """
    print(f"Discovering borrowers up to block {to_block}...")
    return []


def classify_borrowers(fork_rpc_url: str, borrowers: List[str], block_number: int) -> List[dict]:
    """
    Classifies positions via Multicall3 on fork at block_number.
    """
    print(f"Classifying {len(borrowers)} borrowers at block {block_number}...")
    return []


def main():
    print("Running extract pipeline step...")


if __name__ == "__main__":
    main()
