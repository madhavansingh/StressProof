"""
Routes for case-files and replay-reports.
Matches implementationplan.md §14.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from ...config import settings
from ...dependencies import verify_write_token
from ...storage.store import ContentStore, HASH_REGEX

router = APIRouter(tags=["Files"])
store = ContentStore(settings.DATA_DIR)


@router.get("/case-files/{evidence_hash}")
async def get_case_file(evidence_hash: str):
    if not HASH_REGEX.match(evidence_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed hash format")
    data = store.get_case_file(evidence_hash)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case file not found")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Keccak256": evidence_hash,
        },
    )


@router.post("/case-files", status_code=status.HTTP_201_CREATED)
async def post_case_file(request: Request, _token: str = Depends(verify_write_token)):
    body = await request.body()
    if len(body) > settings.FETCH_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds maximum size")
    h = store.put_case_file(body)
    return {
        "evidenceHash": h,
        "caseFileURI": f"{settings.BACKEND_PUBLIC_URL}/case-files/{h}",
    }


@router.get("/replay-reports/{report_hash}")
async def get_replay_report(report_hash: str):
    if not HASH_REGEX.match(report_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed hash format")
    data = store.get_replay_report(report_hash)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay report not found")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Keccak256": report_hash,
        },
    )


@router.post("/replay-reports", status_code=status.HTTP_201_CREATED)
async def post_replay_report(request: Request, _token: str = Depends(verify_write_token)):
    body = await request.body()
    if len(body) > settings.FETCH_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds maximum size")
    h = store.put_replay_report(body)
    return {
        "reportHash": h,
        "reportURI": f"{settings.BACKEND_PUBLIC_URL}/replay-reports/{h}",
    }
