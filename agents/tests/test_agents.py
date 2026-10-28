"""
Tests for agent utilities and SSRF safety.
"""

from stressproof_agents.common.fetch import is_safe_url


def test_ssrf_safety_allowed_schemes():
    assert is_safe_url("https://example.com/case-file.json") is True
    assert is_safe_url("ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi") is True
    assert is_safe_url("ftp://example.com/file") is False
    assert is_safe_url("file:///etc/passwd") is False


def test_ssrf_safety_blocks_metadata():
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
