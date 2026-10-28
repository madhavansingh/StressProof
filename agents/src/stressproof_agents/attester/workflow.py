"""Claim steps shared by the honest and malicious attesters (implementationplan.md §15.1, §15.4).

1. `fetch_verified`: fetch the case file through the SSRF-safe fetcher and check its keccak256
   against the evidence hash.
2. `self_check`: run stressproof_core.evaluate() exactly as the watcher will, against the on-chain
   values the claim is about to use, and require the expected verdict. No validation, replay or
   verdict logic lives here; it all comes from the core library.
3. `plan_claim` / `simulate_post` / `send_post`: read BOND from the chain (it must match the
   deployments file), simulate postClaim with eth_call, and only when asked, send it and parse
   the ClaimPosted event, checking every field against what was intended.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from stressproof_core import Evaluation, evaluate, keccak256_hex, market_id
from web3.exceptions import ContractCustomError, ContractLogicError

from ..common.chain import ChainClient, ChainError, TransactionReverted
from ..common.fetch import EvidenceFetcher
from ..common.revert import revert_data_from


class AttesterError(RuntimeError):
    """A pre-flight check failed. Nothing has been signed or sent."""


@dataclass(frozen=True)
class VerifiedEvidence:
    raw: bytes
    evidence_hash: str
    case_file_uri: str
    fetched_from: str


@dataclass(frozen=True)
class ClaimPlan:
    market_id: str  # bytes32 hex = keccak256(MARKET_ID_STRING)
    claimed_usd8: int
    evidence_hash: str
    case_file_uri: str
    bond_wei: int


@dataclass(frozen=True)
class PostedClaim:
    claim_id: int
    tx_hash: str
    block_number: int
    attester: str
    challenge_deadline: int


def fetch_verified(fetcher: EvidenceFetcher, case_file_uri: str, evidence_hash: str) -> VerifiedEvidence:
    """Fetches raw bytes and refuses them unless keccak256(bytes) equals the evidence hash."""
    result = fetcher.fetch(case_file_uri)
    actual = keccak256_hex(result.content)
    if actual != evidence_hash.lower():
        raise AttesterError(f"fetched case file hashes to {actual}, expected {evidence_hash}")
    return VerifiedEvidence(raw=result.content, evidence_hash=actual, case_file_uri=case_file_uri,
                            fetched_from=result.url)


def onchain_view(evidence_hash: str, market_id_string: str, claimed_usd8: int) -> Dict[str, Any]:
    """The claim as the watcher will read it from chain, in the form core.evaluate() expects."""
    return {"evidenceHash": evidence_hash, "marketId": market_id(market_id_string),
            "claimedResidualBadDebt": claimed_usd8}


def self_check(evidence: VerifiedEvidence, market_id_string: str, claimed_usd8: int,
               expected_verdict: str) -> Evaluation:
    """Evaluates the evidence the way the watcher will, and requires `expected_verdict`."""
    evaluation = evaluate(evidence.raw, onchain_view(evidence.evidence_hash, market_id_string, claimed_usd8))
    if evaluation.verdict != expected_verdict:
        codes = evaluation.violation_codes or "none"
        raise AttesterError(f"self-check verdict is {evaluation.verdict} (violations: {codes}), "
                            f"expected {expected_verdict}; refusing to post")
    if not evaluation.hash_matches:
        raise AttesterError("self-check: evidence hash does not match the bytes")
    return evaluation


def plan_claim(client: ChainClient, evidence: VerifiedEvidence, market_id_string: str,
               claimed_usd8: int) -> ClaimPlan:
    """Builds the postClaim arguments. BOND is read from the chain, not from configuration."""
    bond = client.call(client.registry.functions.BOND())
    if bond != client.deployment.bond_wei:
        raise AttesterError(f"on-chain BOND {bond} differs from the deployments file ({client.deployment.bond_wei})")
    expected_market = market_id(market_id_string)
    if expected_market != client.deployment.market_id:
        raise AttesterError(f"MARKET_ID_STRING gives {expected_market}, deployment uses {client.deployment.market_id}")
    return ClaimPlan(market_id=expected_market, claimed_usd8=claimed_usd8, evidence_hash=evidence.evidence_hash,
                     case_file_uri=evidence.case_file_uri, bond_wei=bond)


def _post_fn(client: ChainClient, plan: ClaimPlan) -> Any:
    return client.registry.functions.postClaim(
        bytes.fromhex(plan.market_id[2:]), plan.claimed_usd8, bytes.fromhex(plan.evidence_hash[2:]),
        plan.case_file_uri,
    )


def simulate_post(client: ChainClient, plan: ClaimPlan) -> int:
    """eth_call of postClaim from the signer with the bond attached. Returns the id it would get."""
    if client.address is None:
        raise ChainError("a signing key is needed to simulate postClaim from the attester's address")
    try:
        return _post_fn(client, plan).call({"from": client.address, "value": plan.bond_wei})
    except (ContractCustomError, ContractLogicError) as exc:
        raise TransactionReverted("postClaim (simulated)", client.errors.decode(revert_data_from(exc))) from None


def send_post(client: ChainClient, plan: ClaimPlan) -> PostedClaim:
    """Sends postClaim and returns the claim parsed from its ClaimPosted event."""
    result = client.transact(_post_fn(client, plan), value=plan.bond_wei)
    events = client.parse_events(result.receipt, "StressRegistry", "ClaimPosted")
    if len(events) != 1:
        raise ChainError(f"expected one ClaimPosted event in {result.tx_hash}, found {len(events)}")
    args = events[0].args
    _expect_event(args, plan, client.address)
    return PostedClaim(claim_id=args.claimId, tx_hash=result.tx_hash, block_number=result.block_number,
                       attester=args.attester, challenge_deadline=args.challengeDeadline)


def _expect_event(args: Any, plan: ClaimPlan, attester: Optional[str]) -> None:
    checks = [
        ("attester", args.attester, attester),
        ("marketId", "0x" + bytes(args.marketId).hex(), plan.market_id),
        ("claimedResidualBadDebt", args.claimedResidualBadDebt, plan.claimed_usd8),
        ("evidenceHash", "0x" + bytes(args.evidenceHash).hex(), plan.evidence_hash),
        ("caseFileURI", args.caseFileURI, plan.case_file_uri),
    ]
    for name, got, want in checks:
        if got != want:
            raise ChainError(f"ClaimPosted.{name} is {got}, expected {want}")
