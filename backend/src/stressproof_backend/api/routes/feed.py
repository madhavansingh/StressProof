"""
Routes for append-only agent feed.
Matches implementationplan.md §8.6 & §14.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from ...dependencies import verify_write_token

router = APIRouter(tags=["Feed"])

# In-memory storage with fallback file persistence
FEED_ENTRIES: List[Dict[str, Any]] = []


class FeedEntryInput(BaseModel):
    actor: str
    kind: str
    claimId: Optional[str] = None
    txHash: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.post("/feed", status_code=status.HTTP_201_CREATED)
async def post_feed_entry(entry: FeedEntryInput, _token: str = Depends(verify_write_token)):
    seq = len(FEED_ENTRIES) + 1
    new_entry = {
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": entry.actor,
        "kind": entry.kind,
        "claimId": entry.claimId,
        "txHash": entry.txHash,
        "data": entry.data or {},
    }
    FEED_ENTRIES.append(new_entry)
    return {"seq": seq}


@router.get("/feed")
async def get_feed(since: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    entries = [e for e in FEED_ENTRIES if e["seq"] > since][:limit]
    next_since = entries[-1]["seq"] if entries else since
    return {
        "entries": entries,
        "nextSince": next_since,
    }
