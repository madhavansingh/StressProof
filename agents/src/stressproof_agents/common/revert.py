"""Decode revert data into readable errors: the contracts' custom errors, Error(string) and Panic(uint256)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from eth_abi import decode as abi_decode
from web3 import Web3

ERROR_STRING_SELECTOR = "0x08c379a0"  # Error(string)
PANIC_SELECTOR = "0x4e487b71"  # Panic(uint256)


@dataclass(frozen=True)
class DecodedError:
    name: str
    args: Tuple[Any, ...]

    def __str__(self) -> str:
        return f"{self.name}({', '.join(str(a) for a in self.args)})"


@dataclass(frozen=True)
class _ErrorSpec:
    name: str
    types: Tuple[str, ...]


def _canonical_type(param: Dict[str, Any]) -> str:
    # Enums are uint8 in the ABI's internal form; tuples are not used by these contracts' errors.
    return param["type"]


class ErrorDecoder:
    """Maps 4-byte selectors to the custom errors declared in the given ABIs."""

    def __init__(self, abis: Iterable[Iterable[Dict[str, Any]]]) -> None:
        specs: Dict[str, _ErrorSpec] = {}
        for abi in abis:
            for entry in abi:
                if entry.get("type") != "error":
                    continue
                types = tuple(_canonical_type(p) for p in entry.get("inputs", []))
                signature = f"{entry['name']}({','.join(types)})"
                selector = "0x" + Web3.keccak(text=signature)[:4].hex()
                specs[selector] = _ErrorSpec(entry["name"], types)
        self._specs = specs

    @property
    def known_errors(self) -> Tuple[str, ...]:
        return tuple(sorted(s.name for s in self._specs.values()))

    def decode(self, data: Any) -> Optional[DecodedError]:
        """Revert data (hex string or bytes) to a DecodedError, or None if it is not recognised."""
        raw = _to_bytes(data)
        if raw is None or len(raw) < 4:
            return None
        selector, payload = "0x" + raw[:4].hex(), raw[4:]
        try:
            if selector == ERROR_STRING_SELECTOR:
                return DecodedError("Error", tuple(abi_decode(["string"], payload)))
            if selector == PANIC_SELECTOR:
                return DecodedError("Panic", tuple(abi_decode(["uint256"], payload)))
            spec = self._specs.get(selector)
            if spec is None:
                return None
            return DecodedError(spec.name, tuple(abi_decode(list(spec.types), payload)))
        except Exception:  # malformed payload for a known selector
            return DecodedError(f"Unparseable<{selector}>", ())


def revert_data_from(exc: BaseException) -> Optional[str]:
    """Pulls revert data out of a web3 exception (ContractCustomError, ContractLogicError, RPC errors)."""
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        data = data.get("data")
    if isinstance(data, str) and data.startswith("0x"):
        return data
    if isinstance(data, (bytes, bytearray)):
        return "0x" + bytes(data).hex()
    return None


def _to_bytes(data: Any) -> Optional[bytes]:
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str) and data.startswith("0x"):
        try:
            return bytes.fromhex(data[2:])
        except ValueError:
            return None
    return None
