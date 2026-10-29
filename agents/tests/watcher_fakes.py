"""A fake StressRegistry on top of FakeNode for watcher tests.

It answers claim(id), status(id), BOND() and credits(addr) per claim, emits ClaimPosted logs at
chosen blocks, and applies the watcher's challenge()/withdraw() transactions to its own state, so
tests can check exactly what was sent and how a restart sees it.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from eth_abi import decode, encode
from web3 import Web3

from conftest import CORE_MARKET_ID, REGISTRY, FakeNode, claim_posted_log, selector

ZERO = "0x" + "00" * 20
CLAIM_TUPLE = "(address,uint64,uint8,uint8,address,uint64,bytes32,bytes32,bytes32,uint256,uint256,string,string)"
ATTESTER = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"


class FakeRegistry:
    def __init__(self, node: FakeNode) -> None:
        self.node = node
        self.claims: Dict[int, dict] = {}
        self.credit = 0
        self.challenges: List[dict] = []
        self.withdrawals = 0
        self.flip_after_reads: Dict[int, int] = {}  # claim id -> reads before it becomes Challenged by someone else
        self.resolutions: List[dict] = []
        self.expiries: List[int] = []
        self.bond = 10**16
        self._reads: Dict[int, int] = {}
        reg = REGISTRY.lower()
        node.call_handlers[(reg, selector("claim(uint256)"))] = self._claim
        node.call_handlers[(reg, selector("status(uint256)"))] = self._status
        node.call_handlers[(reg, selector("credits(address)"))] = lambda data: "0x" + encode(["uint256"], [self.credit]).hex()
        node.on_send.append(self._on_send)

    def add(self, claim_id: int, claimed: int, evidence_hash: str, uri: str, deadline: int,
            block: int = 5, attester: str = ATTESTER) -> None:
        self.claims[claim_id] = {
            "attester": attester, "challengeDeadline": deadline, "state": 1, "reason": 0, "challenger": ZERO,
            "resolutionDeadline": 0, "evidenceHash": evidence_hash, "claimed": claimed, "counter": 0,
            "uri": uri, "reportHash": "0x" + "00" * 32, "reportURI": "",
        }
        log = claim_posted_log(claim_id, attester, claimed, evidence_hash, uri, deadline)
        log["blockNumber"] = hex(block)
        self.node.logs.append(log)

    def set_state(self, claim_id: int, state: int, challenger: Optional[str] = None) -> None:
        self.claims[claim_id]["state"] = state
        if challenger:
            self.claims[claim_id]["challenger"] = challenger

    # ----------------------------------------------------------- handlers

    def _claim(self, data: str) -> str:
        claim_id = int(data[10:], 16)
        self._reads[claim_id] = self._reads.get(claim_id, 0) + 1
        limit = self.flip_after_reads.get(claim_id)
        if limit is not None and self._reads[claim_id] > limit:
            self.set_state(claim_id, 2, "0x" + "99" * 20)  # someone else challenged meanwhile
        c = self.claims.get(claim_id)
        if c is None:
            values = (ZERO, 0, 0, 0, ZERO, 0, b"\0" * 32, b"\0" * 32, b"\0" * 32, 0, 0, "", "")
        else:
            values = (c["attester"], c["challengeDeadline"], c["state"], c["reason"], c["challenger"],
                      c["resolutionDeadline"], bytes.fromhex(CORE_MARKET_ID[2:]), bytes.fromhex(c["evidenceHash"][2:]),
                      bytes.fromhex(c["reportHash"][2:]), c["claimed"], c["counter"], c["uri"], c["reportURI"])
        return "0x" + encode([CLAIM_TUPLE], [values]).hex()

    def _status(self, data: str) -> str:
        c = self.claims.get(int(data[10:], 16))
        return "0x" + encode(["uint8"], [c["state"] if c else 0]).hex()

    def _on_send(self, tx: dict) -> None:
        data = bytes(tx["data"])
        if data[:4].hex() == selector("challenge(uint256,uint8,uint256,string,bytes32)")[2:]:
            claim_id, reason, counter, uri, report_hash = decode(["uint256", "uint8", "uint256", "string", "bytes32"], data[4:])
            self.challenges.append({"claimId": claim_id, "reason": reason, "counter": counter, "uri": uri,
                                    "reportHash": "0x" + report_hash.hex(), "value": tx["value"]})
            c = self.claims[claim_id]
            c.update(state=2, reason=reason, counter=counter, reportURI=uri, reportHash="0x" + report_hash.hex(),
                     challenger=Web3.to_checksum_address(tx["from"]))
        elif data[:4].hex() == selector("withdraw()")[2:]:
            self.withdrawals += 1
            self.credit = 0
        elif data[:4].hex() == selector("resolve(uint256,bool)")[2:]:
            claim_id, upheld = decode(["uint256", "bool"], data[4:])
            c = self.claims[claim_id]
            winner = c["challenger"] if upheld else c["attester"]
            c["state"] = 4 if upheld else 3  # Rejected / Finalized, as StressRegistry.resolve
            self.resolutions.append({"claimId": claim_id, "upheld": upheld, "from": tx["from"]})
            return [_log("ClaimResolved(uint256,bool,address,uint256)", [claim_id, winner],
                         ["bool", "uint256"], [upheld, 2 * self.bond])]
        elif data[:4].hex() == selector("expireUnresolved(uint256)")[2:]:
            (claim_id,) = decode(["uint256"], data[4:])
            self.claims[claim_id]["state"] = 5  # Expired
            self.expiries.append(claim_id)
            return [_log("ClaimExpired(uint256)", [claim_id], [], [])]
        return None

    def challenged(self, claim_id: int, challenger: str, reason: int, counter: int, report_uri: str,
                   report_hash: str, resolution_deadline: int) -> None:
        """Puts an existing claim into the Challenged state, as challenge() would."""
        self.claims[claim_id].update(state=2, challenger=challenger, reason=reason, counter=counter,
                                     reportURI=report_uri, reportHash=report_hash,
                                     resolutionDeadline=resolution_deadline)


def _log(signature: str, indexed: list, types: list, values: list) -> dict:
    """A registry event log; `indexed` holds the claim id first, then any indexed address."""
    topics = ["0x" + Web3.keccak(text=signature).hex()]
    for value in indexed:
        kind = "address" if isinstance(value, str) else "uint256"
        topics.append("0x" + encode([kind], [value]).hex())
    return {"address": REGISTRY, "topics": topics, "data": "0x" + encode(types, values).hex(),
            "blockHash": "0x" + "ee" * 32, "transactionIndex": "0x0", "logIndex": "0x1", "removed": False}
