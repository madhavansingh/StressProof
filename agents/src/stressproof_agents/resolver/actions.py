"""Eligibility checks and the two transactions the resolver CLI can send.

The checks mirror StressRegistry.resolve / expireUnresolved (contracts/src/StressRegistry.sol) so
the CLI refuses with a clear reason instead of sending a transaction that would revert. The contract
stays the authority: if state changes between the check and the send, the decoded revert is shown.
Each send re-reads the claim and the chain time immediately before transacting and verifies the
emitted event afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..common.chain import ChainClient, ChainError
from ..common.feed import FeedClient
from .claim_view import CHALLENGED, NONE, PENDING, TERMINAL_STATES, ClaimView, read_claim_view

ACTOR = "resolver"


class Refused(RuntimeError):
    """The action is not allowed for this signer or this claim right now. Nothing was sent."""


class NothingToDo(RuntimeError):
    """The claim is already in a terminal state; repeating the action would only revert."""


@dataclass(frozen=True)
class Sent:
    tx_hash: str
    block_number: int
    detail: str


def _not_challenged(claim: ClaimView) -> None:
    if claim.state in TERMINAL_STATES:
        raise NothingToDo(f"claim {claim.claim_id} is already {claim.state_name}; nothing to do")
    if claim.state == NONE:
        raise Refused(f"claim {claim.claim_id} does not exist")
    if claim.state == PENDING:
        raise Refused(f"claim {claim.claim_id} is Pending (not challenged); there is no dispute to settle")
    if claim.state != CHALLENGED:
        raise Refused(f"claim {claim.claim_id} is in an unexpected state {claim.state_name}")


def check_resolve_allowed(client: ChainClient, claim: ClaimView, now: int) -> None:
    """StressRegistry.resolve order: NotResolver, InvalidState, ResolutionWindowClosed, ResolverIsParty."""
    signer = client.address
    if signer is None:
        raise Refused("RESOLVER_PK is needed to resolve")
    designated = client.call(client.registry.functions.resolver())
    if signer != designated:
        raise Refused(f"signer {signer} is not the designated resolver {designated} (NotResolver)")
    _not_challenged(claim)
    if now >= claim.resolution_deadline:
        raise Refused(f"resolution window closed at {claim.resolution_deadline} (chain time {now}); "
                      "only expire is possible now")
    if signer in (claim.attester, claim.challenger):
        raise Refused(f"the resolver {signer} is a party to claim {claim.claim_id} (ResolverIsParty); "
                      "it cannot resolve it; expire it after the resolution deadline")


def check_expire_allowed(claim: ClaimView, now: int) -> None:
    """StressRegistry.expireUnresolved: anyone; Challenged; now >= resolutionDeadline."""
    _not_challenged(claim)
    if now < claim.resolution_deadline:
        raise Refused(f"resolution window is still open for {claim.resolution_deadline - now}s "
                      f"(until {claim.resolution_deadline}); the resolver should resolve instead")


def send_resolve(client: ChainClient, claim_id: int, upheld: bool, feed: Optional[FeedClient]) -> Sent:
    fresh = read_claim_view(client, claim_id)  # re-read immediately before sending
    check_resolve_allowed(client, fresh, client.latest_block_timestamp())
    result = client.transact(client.registry.functions.resolve(claim_id, upheld))
    events = client.parse_events(result.receipt, "StressRegistry", "ClaimResolved")
    if len(events) != 1 or events[0].args.claimId != claim_id or events[0].args.challengeUpheld != upheld:
        raise ChainError(f"transaction {result.tx_hash} did not emit the expected ClaimResolved event")
    args = events[0].args
    detail = f"winner {args.winner} credited {args.amountCredited} wei"
    _post(feed, "RESOLVED", claim_id, result.tx_hash, {"upheld": upheld, "winner": args.winner,
                                                       "amountWei": str(args.amountCredited)})
    return Sent(result.tx_hash, result.block_number, detail)


def send_expire(client: ChainClient, claim_id: int, feed: Optional[FeedClient]) -> Sent:
    if client.address is None:
        raise Refused("a signing key is needed to send expireUnresolved")
    fresh = read_claim_view(client, claim_id)
    check_expire_allowed(fresh, client.latest_block_timestamp())
    result = client.transact(client.registry.functions.expireUnresolved(claim_id))
    events = client.parse_events(result.receipt, "StressRegistry", "ClaimExpired")
    if len(events) != 1 or events[0].args.claimId != claim_id:
        raise ChainError(f"transaction {result.tx_hash} did not emit the expected ClaimExpired event")
    _post(feed, "EXPIRED", claim_id, result.tx_hash, {"attester": fresh.attester, "challenger": fresh.challenger})
    return Sent(result.tx_hash, result.block_number, "both bonds refunded to attester and challenger")


def _post(feed: Optional[FeedClient], kind: str, claim_id: int, tx_hash: Optional[str], data) -> None:
    if feed is not None:
        feed.post(ACTOR, kind, claim_id=claim_id, tx_hash=tx_hash, data=data)
