"""
Feed reporter helper sending agent events to backend POST /feed.
"""

from typing import Any, Dict, Optional
import httpx


async def report_feed(
    backend_url: str,
    token: str,
    actor: str,
    kind: str,
    claim_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "actor": actor,
        "kind": kind,
        "claimId": claim_id,
        "txHash": tx_hash,
        "data": data or {},
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{backend_url}/feed", json=payload, headers=headers)
    except Exception as e:
        print(f"Warning: Failed to report to feed: {e}")
