"""
Routes for Phase 2 TigerGraph exposure graph visualization.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Graph"])


@router.get("/graph/exposure")
async def get_graph_exposure(datasetId: str = "weth-stable-fixture-v1"):
    return {
        "nodes": [
            {"id": "WETH", "type": "Asset", "symbol": "WETH"},
            {"id": "synth-0001", "type": "Account", "origin": "synthetic"},
        ],
        "links": [
            {"source": "synth-0001", "target": "WETH", "label": "COLLATERAL_IN"}
        ],
        "label": "estimated exposure",
    }
