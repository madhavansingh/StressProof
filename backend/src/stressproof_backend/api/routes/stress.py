"""
Stress test execution route.
Matches implementationplan.md §14.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.replay import replay
from stressproof_core.validation import validate
from ...config import settings
from ...dependencies import verify_write_token
from ...storage.store import ContentStore

router = APIRouter(tags=["Stress"])
store = ContentStore(settings.DATA_DIR)


class ScenarioModel(BaseModel):
    asset: str = "WETH"
    shockBps: int = Field(..., ge=-9000, le=-1)


class StressRunRequest(BaseModel):
    datasetId: str
    scenario: ScenarioModel
    agentRationale: Optional[str] = "Phase 1 fixed scenario."


@router.post("/stress/run")
async def run_stress_test(req: StressRunRequest, _token: str = Depends(verify_write_token)):
    # In a full implementation, this loads dataset from data/datasets/<datasetId>/
    # Here we provide the standard execution flow using the fixture snapshot
    import json
    from pathlib import Path

    fixture_path = Path("data/fixtures/casefile_v1.json")
    if not fixture_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    with open(fixture_path, "rb") as f:
        case_file = json.loads(f.read().decode("utf-8"))

    case_file["scenario"]["shockBps"] = req.scenario.shockBps
    case_file["agentRationale"] = req.agentRationale

    # Run deterministic replay
    replay_res = replay(case_file)
    case_file["results"] = replay_res.to_results_dict()

    raw_bytes = canonical_bytes(case_file)

    # Self-validation
    violations = validate(raw_bytes)
    # Filter out placeholder hash violations in skeleton mode
    structural_violations = [v for v in violations if v.code in ("V-03", "V-04", "V-06", "V-07", "V-08", "V-09")]
    if structural_violations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[v.message for v in structural_violations],
        )

    evidence_hash = store.put_case_file(raw_bytes)
    case_file_uri = f"{settings.BACKEND_PUBLIC_URL}/case-files/{evidence_hash}"

    return {
        "evidenceHash": evidence_hash,
        "caseFileURI": case_file_uri,
        "caseFileHttpURL": case_file_uri,
        "results": case_file["results"],
        "dataClass": case_file["dataClass"],
        "sizeBytes": len(raw_bytes),
    }
