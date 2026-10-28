"""Local nonce manager for one signing key (plan §15.1: one process per key)."""

from __future__ import annotations

import threading
from typing import Callable, Optional


class NonceManager:
    """Hands out sequential nonces without asking the node each time.

    `fetch` returns the account's pending transaction count from the node. It is called on first use
    and whenever `resync()` is called, e.g. after a "nonce too low" error. A nonce that was handed out
    but never sent can be returned with `release()` only if it is still the latest one.
    """

    def __init__(self, fetch: Callable[[], int]) -> None:
        self._fetch = fetch
        self._lock = threading.Lock()
        self._next: Optional[int] = None

    def reserve(self) -> int:
        with self._lock:
            if self._next is None:
                self._next = self._fetch()
            nonce = self._next
            self._next += 1
            return nonce

    def release(self, nonce: int) -> None:
        """Gives back an unsent nonce if nothing was reserved after it; otherwise forces a resync."""
        with self._lock:
            if self._next is not None and nonce == self._next - 1:
                self._next = nonce
            else:
                self._next = None

    def resync(self) -> int:
        with self._lock:
            self._next = self._fetch()
            return self._next
