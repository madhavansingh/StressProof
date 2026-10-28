"""
Routes for dataset catalog and manifests.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Datasets"])


@router.get("/datasets")
async def list_datasets():
    return [
        {
            "datasetId": "weth-stable-fixture-v1",
            "dataClass": "SYNTHETIC",
            "forkBlock": 19000000,
            "counts": {"real": 0, "synthetic": 6},
            "snapshotHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        }
    ]
