"""
SSRF-safe raw byte fetcher.
Matches implementationplan.md §16.3 and threat S-06.
"""

from urllib.parse import urlparse
import httpx


def is_safe_url(url: str, allow_localhost: bool = True) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "ipfs", "http"):
        return False
    if parsed.scheme == "http":
        if not allow_localhost or parsed.hostname not in ("localhost", "127.0.0.1"):
            return False
    # Link-local / AWS metadata endpoint
    if parsed.hostname == "169.254.169.254":
        return False
    return True


async def fetch_evidence_bytes(url: str, max_bytes: int = 26214400, timeout_sec: int = 10) -> bytes:
    """
    Fetches raw bytes without JSON decoding.
    Rejects SSRF targets, blocks redirects, and enforces size limit.
    """
    if not is_safe_url(url):
        raise ValueError(f"Target URL {url} is not permitted by SSRF policy")

    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout_sec) as client:
        res = await client.get(url)
        res.raise_for_status()
        content = res.content
        if len(content) > max_bytes:
            raise ValueError(f"Content length {len(content)} exceeds {max_bytes} limit")
        return content
