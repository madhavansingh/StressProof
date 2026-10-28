"""SSRF-safe fetcher for untrusted evidence URIs (implementationplan.md §16.3, threats S-06/S-07).

Case-file and replay-report URIs come from chain data, so they are attacker-chosen. The fetcher:

1. allows only https://, ipfs:// (rewritten to the configured https gateway) and, when
   FETCH_ALLOW_LOCALHOST is on, http:// to localhost; URLs with credentials are refused;
2. resolves DNS itself and refuses the request if ANY resolved address is not a public unicast
   address (private, loopback unless allowed, link-local incl. 169.254.169.254, multicast,
   reserved, unspecified, IPv6 ULA/link-local, IPv4-mapped forms of these);
3. connects to the address it checked (Host header and TLS SNI keep the original name, so TLS
   certificates are still verified), which closes the DNS-rebinding gap between check and connect;
4. never follows redirects; streams the body and aborts past the size cap; enforces a per-attempt
   deadline; retries only network errors and 5xx responses, with backoff;
5. returns the raw bytes, never decoded or re-serialized (C-11).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

import httpx

from .config import FetchSettings

LOCALHOST_NAMES = ("localhost", "127.0.0.1", "::1")
_CID_RE = re.compile(r"^[A-Za-z0-9]{10,128}$")
_BACKOFF_SEC = (0.5, 1.0, 2.0)
_CHUNK = 64 * 1024

Resolver = Callable[[str, int], Sequence[str]]


class FetchError(RuntimeError):
    """The URI was refused or could not be fetched within the limits. `retryable` marks transient failures."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    url: str  # the URL actually fetched (gateway URL for ipfs://)
    status: int


def system_resolver(host: str, port: int) -> Sequence[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"DNS lookup failed for {host}: {exc}", retryable=True) from None
    return tuple(dict.fromkeys(info[4][0] for info in infos))


# ------------------------------------------------------------------- policy


def is_safe_url(url: str, allow_localhost: bool = True) -> bool:
    """Quick scheme and literal-host check, kept for scripts/e2e_local.sh. `EvidenceFetcher` also
    checks every resolved address; this function does not resolve DNS."""
    if url.startswith("ipfs://"):
        cid = url[len("ipfs://"):].partition("/")[0]
        return bool(_CID_RE.match(cid))  # the gateway itself is checked at fetch time
    try:
        target = _parse_target(url, allow_localhost=allow_localhost)
    except FetchError:
        return False
    try:
        ip = ipaddress.ip_address(target.host)
    except ValueError:
        return True  # a hostname: DNS is checked at fetch time
    return _ip_allowed(ip, allow_localhost)


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    path_and_query: str


def rewrite_ipfs(uri: str, gateway_url: Optional[str]) -> str:
    """ipfs://<CID>[/path] -> <gateway>/ipfs/<CID>[/path]. The gateway must be https."""
    if gateway_url is None:
        raise FetchError("ipfs:// URI but IPFS_GATEWAY_URL is not configured")
    rest = uri[len("ipfs://"):]
    cid, _, path = rest.partition("/")
    if not _CID_RE.match(cid):
        raise FetchError(f"invalid IPFS CID in {uri!r}")
    return f"{gateway_url.rstrip('/')}/ipfs/{cid}" + (f"/{path}" if path else "")


def _parse_target(url: str, allow_localhost: bool) -> _Target:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http"):
        raise FetchError(f"scheme {scheme or '(none)'!r} is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise FetchError("URLs with credentials are not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise FetchError("URL has no host")
    if scheme == "http" and not (allow_localhost and host in LOCALHOST_NAMES):
        raise FetchError("http:// is only allowed for localhost with FETCH_ALLOW_LOCALHOST=true")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise FetchError("URL has an invalid port") from None
    path_and_query = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    return _Target(scheme, host, port, path_and_query)


def _ip_allowed(ip: ipaddress._BaseAddress, allow_localhost: bool) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _ip_allowed(mapped, allow_localhost)
    if ip.is_loopback:
        return allow_localhost
    return ip.is_global and not ip.is_multicast


def _checked_addresses(target: _Target, resolver: Resolver, allow_localhost: bool) -> List[str]:
    addresses = list(resolver(target.host, target.port))
    if not addresses:
        raise FetchError(f"{target.host} did not resolve", retryable=True)
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            raise FetchError(f"{target.host} resolved to an invalid address {address!r}") from None
        if not _ip_allowed(ip, allow_localhost):
            raise FetchError(f"{target.host} resolves to a non-public address ({ip}); refused")
    return addresses


# ------------------------------------------------------------------ fetcher


class EvidenceFetcher:
    def __init__(self, settings: FetchSettings, resolver: Resolver = system_resolver,
                 transport: Optional[httpx.BaseTransport] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self._settings = settings
        self._resolver = resolver
        self._transport = transport
        self._sleep = sleep
        self._clock = clock

    def fetch(self, uri: str) -> FetchResult:
        url = rewrite_ipfs(uri, self._settings.ipfs_gateway_url) if uri.startswith("ipfs://") else uri
        target = _parse_target(url, self._settings.allow_localhost)
        last_error: Optional[FetchError] = None
        for attempt in range(self._settings.max_attempts):
            if attempt:
                self._sleep(_BACKOFF_SEC[min(attempt - 1, len(_BACKOFF_SEC) - 1)])
            try:
                return self._attempt(url, target)
            except FetchError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
        raise FetchError(f"giving up after {self._settings.max_attempts} attempts: {last_error}")

    def _attempt(self, url: str, target: _Target) -> FetchResult:
        address = _checked_addresses(target, self._resolver, self._settings.allow_localhost)[0]
        host_literal = f"[{address}]" if ":" in address else address
        pinned = f"{target.scheme}://{host_literal}:{target.port}{target.path_and_query}"
        default_port = 443 if target.scheme == "https" else 80
        host_header = target.host if target.port == default_port else f"{target.host}:{target.port}"
        deadline = self._clock() + self._settings.timeout_sec
        timeout = httpx.Timeout(self._settings.timeout_sec)
        try:
            with httpx.Client(transport=self._transport, follow_redirects=False, timeout=timeout,
                              trust_env=False) as client:
                request = client.build_request(
                    # identity: the bytes hashed must be exactly the bytes served
                    "GET", pinned, headers={"Host": host_header, "Accept": "*/*", "Accept-Encoding": "identity"},
                    extensions={"sni_hostname": target.host} if target.scheme == "https" else {},
                )
                response = client.send(request, stream=True)
                try:
                    return FetchResult(self._read(response, deadline), url, response.status_code)
                finally:
                    response.close()
        except httpx.TimeoutException:
            raise FetchError(f"timed out after {self._settings.timeout_sec}s", retryable=True) from None
        except httpx.TransportError as exc:
            raise FetchError(f"network error: {type(exc).__name__}", retryable=True) from None

    def _read(self, response: httpx.Response, deadline: float) -> bytes:
        status = response.status_code
        if 300 <= status < 400:
            raise FetchError(f"redirect ({status}) refused; redirects are never followed")
        if status >= 500:
            raise FetchError(f"server error {status}", retryable=True)
        if status != 200:
            raise FetchError(f"unexpected status {status}")
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._settings.max_bytes:
            raise FetchError(f"declared size {declared} exceeds {self._settings.max_bytes} bytes")
        chunks: List[bytes] = []
        total = 0
        # iter_bytes decodes any content-encoding, so the cap also limits decompression bombs.
        for chunk in response.iter_bytes(_CHUNK):
            total += len(chunk)
            if total > self._settings.max_bytes:
                raise FetchError(f"body exceeds {self._settings.max_bytes} bytes; aborted")
            if self._clock() > deadline:
                raise FetchError(f"timed out after {self._settings.timeout_sec}s", retryable=True)
            chunks.append(chunk)
        return b"".join(chunks)
