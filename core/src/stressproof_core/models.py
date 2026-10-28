"""
Data structures, TypedDicts, and dataclasses for stressproof_core.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict


class AssetData(TypedDict):
    bonusBps: int
    decimals: int
    ltBps: int
    priceUsd8: str


class AccountData(TypedDict):
    collateralAmount: str
    debtUsd8: str
    id: str
    origin: Literal["real_aave_v3_fork", "synthetic"]


class Snapshot(TypedDict):
    accounts: List[AccountData]
    assets: Dict[str, AssetData]


class Counts(TypedDict):
    real: int
    synthetic: int


class ExcludedCounts(TypedDict):
    eMode: int
    noDebt: int
    nonStableDebt: int
    nonWethCollateral: int
    other: int
    wethNotCollateral: int


class StablecoinEntry(TypedDict):
    address: str
    symbol: str


class DatasetManifest(TypedDict):
    counts: Counts
    dataClass: Literal["REAL", "MIXED", "SYNTHETIC"]
    datasetId: str
    dataProviderAddress: str
    excludedCounts: ExcludedCounts
    extractedAt: str
    extractionScriptCommit: str
    filter: str
    forkBlock: int
    forkBlockHash: str
    forkBlockTimestamp: int
    network: str
    oracleAddress: str
    poolAddress: str
    poolAddressesProvider: str
    rpcProvider: str
    snapshotHash: str
    stablecoinAllowlist: List[StablecoinEntry]
    syntheticSeed: Optional[int]
    wethAddress: str


class Scenario(TypedDict):
    asset: str
    shockBps: int


class ModelInfo(TypedDict):
    id: str
    replayerCommit: str


class Results(TypedDict):
    debtAtRiskUsd8: str
    liquidatableAccounts: int
    liquidationVolumeUsd8: str
    residualBadDebtUsd8: str


class CaseFile(TypedDict):
    agentRationale: str
    dataClass: Literal["REAL", "MIXED", "SYNTHETIC"]
    dataset: DatasetManifest
    marketId: str
    model: ModelInfo
    results: Results
    scenario: Scenario
    schemaVersion: int
    snapshot: Snapshot


@dataclass(frozen=True)
class AccountOutcome:
    id: str
    liquidatable: bool
    repaid_usd8: int
    residual_usd8: int
    collateral_value_usd8: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "liquidatable": self.liquidatable,
            "repaidUsd8": str(self.repaid_usd8),
            "residualUsd8": str(self.residual_usd8),
            "collateralValueUsd8": str(self.collateral_value_usd8),
        }


@dataclass(frozen=True)
class ReplayResult:
    liquidatable_accounts: int
    debt_at_risk_usd8: int
    liquidation_volume_usd8: int
    residual_bad_debt_usd8: int
    outcomes: List[AccountOutcome]

    def to_results_dict(self) -> Results:
        return {
            "liquidatableAccounts": self.liquidatable_accounts,
            "debtAtRiskUsd8": str(self.debt_at_risk_usd8),
            "liquidationVolumeUsd8": str(self.liquidation_volume_usd8),
            "residualBadDebtUsd8": str(self.residual_bad_debt_usd8),
        }


@dataclass(frozen=True)
class Violation:
    code: str
    message: str


class ReplayReport(TypedDict):
    caseFileCopyURI: str
    chainId: int
    claimId: str
    claimedInFileUsd8: str
    claimedOnChainUsd8: str
    evidenceHash: str
    fetchedFrom: str
    hashMatches: bool
    infoMismatches: List[str]
    modelId: str
    recomputed: Results
    registry: str
    replayerCommit: str
    schemaVersion: int
    verdict: Literal["MATCH", "WRONG_RESULT", "EVIDENCE_INVALID"]
    violations: List[str]
    watcher: str
