"""
Stress test execution route.
Matches implementationplan.md §14: builds and stores a case file; never touches the chain.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from stressproof_core.canonical_json import canonical_bytes
from stressproof_core.constants import MAX_SHOCK_BPS, MIN_SHOCK_BPS
from stressproof_core.replay import replay
from stressproof_core.report import build_case_file
from stressproof_core.validation import validate

from ...config import Settings
from ...dependencies import get_feed, get_registry, get_settings, get_store, verify_write_token
from ...registry import DATASET_ID_REGEX, DatasetRegistry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Stress"])


class ScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Literal["WETH"] = "WETH"
    shockBps: StrictInt = Field(..., ge=MIN_SHOCK_BPS, le=MAX_SHOCK_BPS)


class StressRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datasetId: StrictStr
    scenario: ScenarioModel
    agentRationale: Optional[StrictStr] = None


@router.post("/stress/run")
async def run_stress_test(
    req: StressRunRequest,
    _token: str = Depends(verify_write_token),
    settings: Settings = Depends(get_settings),
    registry: DatasetRegistry = Depends(get_registry),
    store=Depends(get_store),
    feed=Depends(get_feed),
):
    if not DATASET_ID_REGEX.match(req.datasetId):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    dataset = registry.get(req.datasetId)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    shock = req.scenario.shockBps
    rationale = req.agentRationale if req.agentRationale is not None else f"Phase 1 fixed scenario: {shock} bps WETH shock."
    case_file = build_case_file(
        snapshot=dataset.snapshot,
        manifest=dataset.manifest,
        scenario={"asset": req.scenario.asset, "shockBps": shock},
        rationale=rationale,
        replayer_commit=settings.git_commit,
        market_id_string=settings.MARKET_ID_STRING,
    )
    raw = canonical_bytes(case_file)

    # Self-check: a case file this backend builds must be valid. Anything else is our bug (500).
    violations = validate(raw, None)
    if violations:
        logger.error("built an invalid case file for %s: %s", req.datasetId, [v.code for v in violations])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "backend built an invalid case file", "violations": [v.code for v in violations]},
        )

    result = await store.put_case_file(raw)
    outcomes = replay(case_file).outcomes
    await store.put_replay_outputs(result.hash, b"".join(canonical_bytes(o.to_dict()) + b"\n" for o in outcomes))

    uri = f"{settings.public_url}/case-files/{result.hash}"
    await feed.append("backend", "CLAIM_BUILT", None, None, {
        "datasetId": req.datasetId,
        "evidenceHash": result.hash,
        "residualBadDebtUsd8": case_file["results"]["residualBadDebtUsd8"],
        "shockBps": shock,
    })
    return {
        "evidenceHash": result.hash,
        "caseFileURI": uri,
        "caseFileHttpURL": uri,
        "results": case_file["results"],
        "dataClass": case_file["dataClass"],
        "sizeBytes": len(raw),
    }
