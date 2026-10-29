"""
Routes for case-files and replay-reports.
Matches implementationplan.md §14, C-03 and C-11: GET returns the stored bytes unchanged.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from stressproof_core.canonical_json import parse_strict
from stressproof_core.report import check_replay_report
from stressproof_core.validation import validate

from ...config import Settings
from ...dependencies import get_settings, get_store, verify_write_token
from ...storage.store import HASH_REGEX

router = APIRouter(tags=["Files"])

IMMUTABLE = "public, max-age=31536000, immutable"


def raw_json(data: bytes, content_hash: str) -> Response:
    return Response(
        content=data,
        media_type="application/json",
        headers={"Cache-Control": IMMUTABLE, "X-Content-Keccak256": content_hash},
    )


def check_hash(value: str) -> None:
    if not HASH_REGEX.match(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed hash: expected 0x + 64 lowercase hex")


async def read_body(request: Request, settings: Settings) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body exceeds maximum size")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Body exceeds maximum size")
        chunks.append(chunk)
    return b"".join(chunks)


def stored(response: Response, created: bool, body: dict) -> dict:
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return body


@router.get("/case-files/{evidence_hash}")
async def get_case_file(evidence_hash: str, store=Depends(get_store)):
    check_hash(evidence_hash)
    data = await store.get_case_file(evidence_hash)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case file not found")
    return raw_json(data, evidence_hash)


@router.post("/case-files", status_code=status.HTTP_201_CREATED)
async def post_case_file(
    request: Request,
    response: Response,
    _token: str = Depends(verify_write_token),
    settings: Settings = Depends(get_settings),
    store=Depends(get_store),
):
    body = await read_body(request, settings)
    violations = validate(body, None)
    if violations:
        raise HTTPException(
            status_code=422,
            detail={
                "violations": list(dict.fromkeys(v.code for v in violations)),
                "messages": [f"{v.code}: {v.message}" for v in violations[:20]],
            },
        )
    result = await store.put_case_file(body)
    return stored(response, result.created, {
        "evidenceHash": result.hash,
        "caseFileURI": f"{settings.public_url}/case-files/{result.hash}",
    })


@router.get("/replay-reports/{report_hash}")
async def get_replay_report(report_hash: str, store=Depends(get_store)):
    check_hash(report_hash)
    data = await store.get_replay_report(report_hash)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay report not found")
    return raw_json(data, report_hash)


@router.post("/replay-reports", status_code=status.HTTP_201_CREATED)
async def post_replay_report(
    request: Request,
    response: Response,
    _token: str = Depends(verify_write_token),
    settings: Settings = Depends(get_settings),
    store=Depends(get_store),
):
    body = await read_body(request, settings)
    try:
        report = parse_strict(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Not canonical JSON: {e}")
    errors = check_replay_report(report)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    result = await store.put_replay_report(body)
    return stored(response, result.created, {
        "reportHash": result.hash,
        "reportURI": f"{settings.public_url}/replay-reports/{result.hash}",
    })
