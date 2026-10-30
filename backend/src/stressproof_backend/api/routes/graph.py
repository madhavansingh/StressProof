"""
GET /graph/exposure (WP-5): estimated exposure for one case file, read from TigerGraph.

Read-only. Answers 503 when TigerGraph is not configured or unreachable, and never substitutes local or mock
data for a TigerGraph result. Nothing here affects a claim verdict.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ...dependencies import get_settings, get_store
from ...storage.store import HASH_REGEX
from ...tigergraph.client import TigerGraphClient, TigerGraphConfig, TigerGraphError
from ...tigergraph.exposure import NotLoaded, exposure

router = APIRouter(tags=["Graph"])
logger = logging.getLogger(__name__)
MAX_TOP = 50


def _unavailable(reason: str, status: int = 503) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "unavailable", "source": "tigergraph",
                                                     "detail": reason, "nodes": [], "links": []})


def _client(request: Request, settings) -> Optional[TigerGraphClient]:
    client = getattr(request.app.state, "tigergraph", None)
    if client is None:
        config = TigerGraphConfig.from_settings(settings)
        if config is None:
            return None
        client = TigerGraphClient(config)
        request.app.state.tigergraph = client  # reused so the token is minted once
    return client


@router.get("/graph/exposure")
async def get_graph_exposure(request: Request, evidenceHash: str = "", top: int = Query(10, ge=1, le=MAX_TOP),
                             settings=Depends(get_settings), store=Depends(get_store)):
    if not HASH_REGEX.match(evidenceHash):
        return JSONResponse(status_code=400, content={"detail": "evidenceHash: expected 0x + 64 lowercase hex"})
    try:
        client = _client(request, settings)
    except TigerGraphError as exc:
        logger.warning("TigerGraph misconfigured: %s", exc)
        return _unavailable(f"TigerGraph is misconfigured on this backend: {exc}")
    if client is None:
        return _unavailable("TigerGraph is not configured on this backend (TG_HOST unset)")
    stored = await store.get_case_file(evidenceHash)
    try:
        return await run_in_threadpool(exposure, client, evidenceHash, top, stored)
    except NotLoaded:
        return JSONResponse(status_code=404, content={"status": "notLoaded", "source": "tigergraph",
                                                      "detail": "this case file is not loaded into the graph"})
    except TigerGraphError as exc:
        logger.warning("TigerGraph query failed: %s", exc)
        if exc.status in (401, 403):
            request.app.state.tigergraph = None  # drop a stale token
        return _unavailable(f"TigerGraph query failed: {exc}")
