"""
Phase 2 TigerGraph exposure graph. Not built yet: answers 503 rather than inventing nodes.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Graph"])


@router.get("/graph/exposure")
async def get_graph_exposure(datasetId: str = "", evidenceHash: str = ""):
    return JSONResponse(
        status_code=503,
        content={"detail": "exposure graph is not available (Phase 2)", "label": "estimated exposure",
                 "nodes": [], "links": []},
    )
