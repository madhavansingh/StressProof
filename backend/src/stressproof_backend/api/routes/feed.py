"""
Routes for the append-only agent feed.
Matches implementationplan.md §8.6 & §14. Entries are agent-reported; chain events stay authoritative.
"""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from ...config import Settings
from ...dependencies import get_feed, get_settings, verify_write_token
from ...storage.feed import FEED_ACTORS, FEED_KINDS

router = APIRouter(tags=["Feed"])


class FeedEntryInput(BaseModel):
    """Same body shape agents/src/stressproof_agents/common/feed.py sends."""
    model_config = ConfigDict(extra="forbid")
    actor: StrictStr
    kind: StrictStr
    claimId: Optional[StrictStr] = None
    txHash: Optional[StrictStr] = None
    data: Optional[Dict[str, Any]] = None

    @field_validator("actor")
    @classmethod
    def known_actor(cls, v: str) -> str:
        if v not in FEED_ACTORS:
            raise ValueError(f"unknown actor; expected one of {sorted(FEED_ACTORS)}")
        return v

    @field_validator("kind")
    @classmethod
    def known_kind(cls, v: str) -> str:
        if v not in FEED_KINDS:
            raise ValueError(f"unknown kind; expected one of {sorted(FEED_KINDS)}")
        return v

    @field_validator("claimId")
    @classmethod
    def decimal_claim_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.isdigit() and (v == "0" or not v.startswith("0"))):
            raise ValueError("claimId must be a decimal string")
        return v


@router.post("/feed", status_code=status.HTTP_201_CREATED)
async def post_feed_entry(
    entry: FeedEntryInput,
    _token: str = Depends(verify_write_token),
    settings: Settings = Depends(get_settings),
    feed=Depends(get_feed),
):
    data = entry.data or {}
    try:
        size = len(json.dumps(data, allow_nan=False))
    except ValueError:
        raise HTTPException(status_code=422, detail="data must be finite JSON")
    if size > settings.MAX_FEED_ENTRY_BYTES:
        raise HTTPException(status_code=413, detail="feed entry too large")
    seq = await feed.append(entry.actor, entry.kind, entry.claimId, entry.txHash, data)
    return {"seq": seq}


@router.get("/feed")
async def get_feed_entries(
    since: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    feed=Depends(get_feed),
):
    entries = await feed.read(since, limit)
    return {"entries": entries, "nextSince": entries[-1]["seq"] if entries else since}
