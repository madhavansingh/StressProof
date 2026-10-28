"""web3.py client for the StressProof contracts: connection, contract handles, reads, transactions,
receipts, events and custom-error decoding.

Pinned to web3.py v7 (agents/pyproject.toml: >=7.16,<8). The code uses only APIs that v8 also has.
Transactions are EIP-1559, signed locally with the one key this process owns, and use a local nonce
manager (plan §15.1: one process per key). Every revert is decoded into the contracts' custom errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.exceptions import ContractCustomError, ContractLogicError, TimeExhausted, Web3RPCError
from web3.logs import DISCARD

from .abi import load_abi
from .config import ALLOWED_CHAIN_IDS, Secret
from .deployments import Deployment, verify_on_chain
from .nonce import NonceManager
from .revert import DecodedError, ErrorDecoder, revert_data_from

BPS = 10_000
_NONCE_TOO_LOW = ("nonce too low", "nonce is too low")


class ChainError(RuntimeError):
    """A chain interaction failed (connection, wrong chain, send failure, receipt timeout)."""


class TransactionReverted(ChainError):
    """A call or transaction reverted. `error` holds the decoded custom error when known."""

    def __init__(self, action: str, error: Optional[DecodedError], tx_hash: Optional[str] = None) -> None:
        self.action = action
        self.error = error
        self.tx_hash = tx_hash
        reason = str(error) if error else "unknown reason"
        where = f" (tx {tx_hash})" if tx_hash else ""
        super().__init__(f"{action} reverted: {reason}{where}")


@dataclass(frozen=True)
class TxPolicy:
    gas_multiplier_bps: int = 12_000  # +20% over the estimate (plan §15.1)
    base_fee_multiplier: int = 2  # maxFeePerGas = 2 x base fee + tip
    receipt_timeout_sec: float = 120
    receipt_poll_sec: float = 0.5


@dataclass(frozen=True)
class TxResult:
    tx_hash: str
    block_number: int
    gas_used: int
    receipt: Any  # web3 AttributeDict (read-only)


class ChainClient:
    def __init__(self, w3: Web3, deployment: Deployment, signer: Optional[Secret] = None,
                 policy: TxPolicy = TxPolicy()) -> None:
        chain_id = w3.eth.chain_id
        if chain_id not in ALLOWED_CHAIN_IDS:
            raise ChainError(f"refusing to use chain {chain_id} (only {ALLOWED_CHAIN_IDS})")
        if chain_id != deployment.chain_id:
            raise ChainError(f"connected to chain {chain_id}, deployments file is for {deployment.chain_id}")
        self._w3 = w3
        self._policy = policy
        self.deployment = deployment
        self.registry = w3.eth.contract(address=deployment.registry, abi=list(load_abi("StressRegistry")))
        self.vault = w3.eth.contract(address=deployment.vault, abi=list(load_abi("DemoVault")))
        self.market = w3.eth.contract(address=deployment.market, abi=list(load_abi("MockLendingMarket")))
        self._contracts = {"StressRegistry": self.registry, "DemoVault": self.vault, "MockLendingMarket": self.market}
        self.errors = ErrorDecoder([load_abi("StressRegistry"), load_abi("DemoVault"), load_abi("MockLendingMarket")])
        self._account = Account.from_key(signer.reveal()) if signer is not None else None
        self._nonces = (
            NonceManager(lambda: w3.eth.get_transaction_count(self._account.address, "pending"))
            if self._account is not None else None
        )

    @classmethod
    def connect(cls, rpc_url: str, deployment: Deployment, signer: Optional[Secret] = None,
                timeout_sec: float = 10, policy: TxPolicy = TxPolicy()) -> "ChainClient":
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": timeout_sec}))
        try:
            return cls(w3, deployment, signer, policy)
        except (OSError, Web3RPCError) as exc:
            raise ChainError(f"cannot reach the RPC endpoint: {type(exc).__name__}") from None

    # ---------------------------------------------------------------- reads

    @property
    def w3(self) -> Web3:
        return self._w3

    @property
    def address(self) -> Optional[str]:
        return self._account.address if self._account is not None else None

    def __repr__(self) -> str:
        return f"ChainClient(chain={self.deployment.chain_id}, signer={self.address})"

    def verify_deployment(self) -> None:
        """Checks chain id, code and on-chain constants against the deployments file."""
        verify_on_chain(self.deployment, self._w3, self.registry, self.vault, self.market)

    def latest_block_timestamp(self) -> int:
        return int(self._w3.eth.get_block("latest")["timestamp"])

    def call(self, fn: Any, block: Any = "latest") -> Any:
        """A read-only contract call; reverts are raised as TransactionReverted with the decoded error."""
        try:
            return fn.call({"from": self.address} if self.address else {}, block_identifier=block)
        except (ContractCustomError, ContractLogicError) as exc:
            raise TransactionReverted(_fn_name(fn), self.errors.decode(revert_data_from(exc))) from None

    def get_events(self, event_name: str, from_block: int, to_block: Any = "latest") -> Tuple[Any, ...]:
        """Registry events in a block range, decoded (e.g. ClaimPosted for the watcher)."""
        event = getattr(self.registry.events, event_name)()
        return tuple(event.get_logs(from_block=from_block, to_block=to_block))

    def parse_events(self, receipt: Any, contract: str, event_name: str) -> Tuple[Any, ...]:
        """Decoded events of one kind from a receipt; logs of other events are skipped."""
        event = getattr(self._contracts[contract].events, event_name)()
        return tuple(event.process_receipt(receipt, errors=DISCARD))

    # --------------------------------------------------------- transactions

    def transact(self, fn: Any, value: int = 0) -> TxResult:
        """Estimates, signs, sends and waits for one transaction. Raises on revert or failure."""
        if self._account is None:
            raise ChainError("this client has no signing key")
        tx = self._build(fn, value)
        tx_hash = self._send(tx)
        receipt = self._wait(tx_hash)
        if receipt["status"] != 1:
            raise TransactionReverted(_fn_name(fn), self._replay_revert(fn, value, receipt), tx_hash)
        return TxResult(tx_hash=tx_hash, block_number=receipt["blockNumber"],
                        gas_used=receipt["gasUsed"], receipt=receipt)

    def _build(self, fn: Any, value: int) -> Dict[str, Any]:
        base = {"from": self._account.address, "value": value, "chainId": self.deployment.chain_id}
        try:
            gas = fn.estimate_gas(base)  # reverts surface here, before any nonce is used
        except (ContractCustomError, ContractLogicError) as exc:
            raise TransactionReverted(_fn_name(fn), self.errors.decode(revert_data_from(exc))) from None
        priority = self._w3.eth.max_priority_fee
        base_fee = self._w3.eth.get_block("latest").get("baseFeePerGas")
        if base_fee is None:
            raise ChainError("latest block has no baseFeePerGas; EIP-1559 is required")
        fees = {
            "gas": gas * self._policy.gas_multiplier_bps // BPS,
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base_fee * self._policy.base_fee_multiplier + priority,
            "nonce": 0,  # placeholder; the real nonce is set when signing
            "type": 2,
        }
        return fn.build_transaction({**base, **fees})

    def _send(self, tx: Dict[str, Any]) -> str:
        for attempt in range(2):
            nonce = self._nonces.reserve()
            signed = self._account.sign_transaction({**tx, "nonce": nonce})
            try:
                return "0x" + bytes(self._w3.eth.send_raw_transaction(signed.raw_transaction)).hex()
            except Web3RPCError as exc:
                if attempt == 0 and _is_nonce_too_low(exc):
                    self._nonces.resync()  # another sender used this key, or the node restarted
                    continue
                self._nonces.release(nonce)
                raise ChainError(f"sending the transaction failed: {exc}") from None
        raise ChainError("sending the transaction failed: nonce still too low after resync")

    def _wait(self, tx_hash: str) -> Any:
        try:
            return self._w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self._policy.receipt_timeout_sec, poll_latency=self._policy.receipt_poll_sec
            )
        except TimeExhausted:
            raise ChainError(f"no receipt for {tx_hash} after {self._policy.receipt_timeout_sec}s") from None

    def _replay_revert(self, fn: Any, value: int, receipt: Any) -> Optional[DecodedError]:
        """Best effort: re-run the call at the parent block to recover the revert reason."""
        try:
            fn.call({"from": self._account.address, "value": value}, block_identifier=receipt["blockNumber"] - 1)
        except (ContractCustomError, ContractLogicError) as exc:
            return self.errors.decode(revert_data_from(exc))
        except Exception:
            return None
        return None


def _fn_name(fn: Any) -> str:
    return getattr(fn, "fn_name", None) or getattr(fn, "abi_element_identifier", None) or "call"


def _is_nonce_too_low(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _NONCE_TOO_LOW)
