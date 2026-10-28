"""
Routes for dataset catalog and manifests.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...dependencies import get_registry
from ...registry import DATASET_ID_REGEX, DatasetRegistry

router = APIRouter(tags=["Datasets"])


@router.get("/datasets")
async def list_datasets(registry: DatasetRegistry = Depends(get_registry)):
    return [d.summary() for d in registry.all()]


@router.get("/datasets/{dataset_id}/manifest")
async def get_manifest(dataset_id: str, registry: DatasetRegistry = Depends(get_registry)):
    if not DATASET_ID_REGEX.match(dataset_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed datasetId")
    dataset = registry.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return Response(content=dataset.manifest_bytes, media_type="application/json")
