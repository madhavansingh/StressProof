"""
Cryptographic hashing functions using eth-hash Keccak-256.
Matches Section 7.3 of implementationplan.md.
"""

from eth_hash.auto import keccak


def keccak256_hex(b: bytes) -> str:
    """
    Computes Keccak-256 hash of raw bytes and returns lowercase 0x-prefixed 66-character string.
    """
    if not isinstance(b, (bytes, bytearray)):
        raise TypeError(f"Expected bytes, got {type(b)}")
    return "0x" + keccak(b).hex()


def market_id(s: str) -> str:
    """
    Computes bytes32 marketId representation from string for StressRegistry.postClaim.
    """
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s)}")
    return keccak256_hex(s.encode("utf-8"))
