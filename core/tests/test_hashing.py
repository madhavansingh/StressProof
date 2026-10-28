"""
Tests for Keccak-256 hashing.
"""

from stressproof_core.hashing import keccak256_hex, market_id


def test_keccak_empty_bytes():
    # Pinned test vector from implementationplan.md §7.3
    h = keccak256_hex(b"")
    assert h == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_market_id_hashing():
    m_id = market_id("aave-v3-eth-weth-stable")
    assert m_id.startswith("0x")
    assert len(m_id) == 66
