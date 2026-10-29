"""The resolver's own assessment of a challenged claim (implementationplan.md §15.3, C-19).

1. Check the challenger's replay report: fetch it, require keccak256 == replayReportHash, and
   shape-check it with stressproof_core.check_replay_report. It is informational only; its
   caseFileCopyURI is used as an extra evidence source.
2. Try the evidence sources in order (the claim's caseFileURI, the challenger's cached copy, the
   backend's /case-files/<evidenceHash>) and take the first bytes whose keccak256 equals the
   on-chain evidenceHash (C-19: retrievable from any source counts as retrievable).
3. Decide with stressproof_core.evaluate() on those bytes (empty if none matched, which core
   treats as EVIDENCE_INVALID), and build the resolver's own replay report with
   build_replay_report(). upheld = (verdict != MATCH). The challenger's counter never decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from stressproof_core import Evaluation, build_replay_report, check_replay_report, evaluate, keccak256_hex, parse_strict
from stressproof_core.constants import VERDICT_MATCH

from ..common.fetch import EvidenceFetcher, FetchError
from .claim_view import ClaimView


@dataclass(frozen=True)
class SourceAttempt:
    name: str
    uri: str
    outcome: str  # "hash OK", "hash mismatch (0x...)", "fetch failed: ..."


@dataclass(frozen=True)
class ReportCheck:
    available: bool
    hash_ok: bool
    report: Optional[Dict[str, Any]]
    problems: Tuple[str, ...]
    differences: Tuple[str, ...]  # report vs. the resolver's recomputation (informational)


@dataclass(frozen=True)
class Assessment:
    claim: ClaimView
    evaluation: Evaluation
    evidence_source: Optional[SourceAttempt]
    attempts: Tuple[SourceAttempt, ...]
    report_check: ReportCheck
    resolver_report: Dict[str, Any]

    @property
    def upheld(self) -> bool:
        return self.evaluation.verdict != VERDICT_MATCH

    @property
    def decision(self) -> str:
        return "UPHOLD" if self.upheld else "REJECT"


def assess(claim: ClaimView, fetcher: EvidenceFetcher, backend_url: str, resolver_address: str,
           chain_id: int, registry: str, replayer_commit: str) -> Assessment:
    report_check = check_challenger_report(claim, fetcher)
    copy_uri = (report_check.report or {}).get("caseFileCopyURI") if report_check.hash_ok else None
    sources = candidate_sources(claim, copy_uri, backend_url)
    raw, chosen, attempts = gather_evidence(claim, sources, fetcher)
    evaluation = evaluate(raw, claim.onchain_view())
    resolver_report = build_replay_report(
        evaluation, chain_id=chain_id, registry=registry, claim_id=claim.claim_id,
        evidence_hash=claim.evidence_hash, fetched_from=chosen.uri if chosen else claim.case_file_uri,
        watcher=resolver_address, replayer_commit=replayer_commit, claimed_onchain_usd8=claim.claimed_usd8,
        case_file_copy_uri=copy_uri or "",
    )
    differences = _differences(report_check.report, resolver_report, claim) if report_check.hash_ok else ()
    report_check = ReportCheck(report_check.available, report_check.hash_ok, report_check.report,
                               report_check.problems, differences)
    return Assessment(claim, evaluation, chosen, attempts, report_check, resolver_report)


def candidate_sources(claim: ClaimView, copy_uri: Optional[str], backend_url: str) -> List[Tuple[str, str]]:
    sources = [("caseFileURI", claim.case_file_uri)]
    if copy_uri:
        sources.append(("challenger copy", copy_uri))
    sources.append(("backend copy", f"{backend_url.rstrip('/')}/case-files/{claim.evidence_hash}"))
    unique, seen = [], set()
    for name, uri in sources:
        if uri and uri not in seen:
            seen.add(uri)
            unique.append((name, uri))
    return unique


def gather_evidence(claim: ClaimView, sources: List[Tuple[str, str]], fetcher: EvidenceFetcher
                    ) -> Tuple[bytes, Optional[SourceAttempt], Tuple[SourceAttempt, ...]]:
    """First bytes from any source that hash to the on-chain evidenceHash; b"" if none do."""
    attempts: List[SourceAttempt] = []
    for name, uri in sources:
        try:
            content = fetcher.fetch(uri).content
        except FetchError as exc:
            attempts.append(SourceAttempt(name, uri, f"fetch failed: {exc}"))
            continue
        digest = keccak256_hex(content)
        if digest == claim.evidence_hash.lower():
            attempt = SourceAttempt(name, uri, "hash OK")
            attempts.append(attempt)
            return content, attempt, tuple(attempts)
        attempts.append(SourceAttempt(name, uri, f"hash mismatch ({digest})"))
    return b"", None, tuple(attempts)


def check_challenger_report(claim: ClaimView, fetcher: EvidenceFetcher) -> ReportCheck:
    if not claim.replay_report_uri:
        return ReportCheck(False, False, None, ("claim has no replay report URI",), ())
    try:
        content = fetcher.fetch(claim.replay_report_uri).content
    except FetchError as exc:
        return ReportCheck(False, False, None, (f"report fetch failed: {exc}",), ())
    if keccak256_hex(content) != claim.replay_report_hash.lower():
        return ReportCheck(True, False, None, ("report bytes do not match replayReportHash",), ())
    try:
        report = parse_strict(content)
    except Exception as exc:
        return ReportCheck(True, True, None, (f"report is not canonical JSON: {exc}",), ())
    return ReportCheck(True, True, report, tuple(check_replay_report(report)), ())


def _differences(report: Optional[Dict[str, Any]], mine: Dict[str, Any], claim: ClaimView) -> Tuple[str, ...]:
    if report is None:
        return ()
    diffs = []
    for key in ("verdict", "hashMatches", "claimedInFileUsd8", "recomputed", "violations"):
        if report.get(key) != mine.get(key):
            diffs.append(f"{key}: challenger {report.get(key)!r} vs resolver {mine.get(key)!r}")
    mine_counter = (mine.get("recomputed") or {}).get("residualBadDebtUsd8")
    if claim.reason == 1 and mine_counter is not None and str(claim.counter_usd8) != mine_counter:
        diffs.append(f"on-chain counter {claim.counter_usd8} vs resolver recomputed {mine_counter}")
    return tuple(diffs)
