"""SSRF-safe evidence fetcher (plan §16.3; tests T-P-40..45 and more). No network: DNS and HTTP are faked."""

import re
from typing import Dict, List

import httpx
import pytest

from stressproof_agents.common.config import FetchSettings
from stressproof_agents.common.fetch import EvidenceFetcher, FetchError, is_safe_url, rewrite_ipfs

PUBLIC_IP = "93.184.215.14"
BODY = b'{"schemaVersion":1}'


def resolver_for(table: Dict[str, List[str]]):
    def resolve(host, port):
        if host not in table:
            raise FetchError(f"DNS lookup failed for {host}", retryable=True)
        return table[host]
    return resolve


class Recorder:
    """An httpx transport that records requests and replays scripted responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def make(settings=None, table=None, *responses, sleeps=None):
    recorder = Recorder(*(responses or (httpx.Response(200, content=BODY),)))
    fetcher = EvidenceFetcher(
        settings or FetchSettings(ipfs_gateway_url="https://gateway.example"),
        resolver=resolver_for(table or {"files.example": [PUBLIC_IP], "gateway.example": [PUBLIC_IP]}),
        transport=httpx.MockTransport(recorder),
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
    )
    return fetcher, recorder


# --------------------------------------------------------------- happy path


def test_fetches_raw_bytes_and_pins_the_checked_ip():
    fetcher, rec = make()
    result = fetcher.fetch("https://files.example/case-files/0xabc?x=1")
    assert result.content == BODY and result.status == 200
    req = rec.requests[0]
    assert req.url.host == PUBLIC_IP and req.url.path == "/case-files/0xabc" and req.url.query == b"x=1"
    assert req.headers["host"] == "files.example"  # original name kept for virtual hosting
    assert req.extensions["sni_hostname"] == "files.example"  # TLS certificate checked against the name
    assert req.headers["accept-encoding"] == "identity"


def test_ipfs_uri_is_rewritten_to_the_https_gateway():
    fetcher, rec = make()
    result = fetcher.fetch("ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi/file.json")
    assert result.url == "https://gateway.example/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi/file.json"
    assert rec.requests[0].headers["host"] == "gateway.example"


def test_ipfs_without_gateway_or_with_bad_cid_is_refused():
    with pytest.raises(FetchError, match="IPFS_GATEWAY_URL is not configured"):
        rewrite_ipfs("ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi", None)
    with pytest.raises(FetchError, match="invalid IPFS CID"):
        rewrite_ipfs("ipfs://../../etc", "https://gateway.example")


def test_localhost_http_only_when_allowed():
    allowed = FetchSettings(allow_localhost=True)
    fetcher, rec = make(allowed, {"localhost": ["127.0.0.1"]})
    assert fetcher.fetch("http://localhost:8000/case-files/0x1").content == BODY
    assert rec.requests[0].url.host == "127.0.0.1" and rec.requests[0].headers["host"] == "localhost:8000"
    fetcher, rec = make(FetchSettings(allow_localhost=False), {"localhost": ["127.0.0.1"]})
    with pytest.raises(FetchError, match="http:// is only allowed for localhost"):
        fetcher.fetch("http://localhost:8000/x")
    assert rec.requests == []


# ------------------------------------------------------------ refused URLs


@pytest.mark.parametrize("url, message", [
    ("file:///etc/passwd", "scheme 'file' is not allowed"),
    ("ftp://files.example/x", "scheme 'ftp' is not allowed"),
    ("gopher://files.example/x", "scheme 'gopher' is not allowed"),
    ("data:text/plain,hi", "scheme 'data' is not allowed"),
    ("//files.example/x", "scheme '(none)' is not allowed"),
    ("http://files.example/x", "http:// is only allowed for localhost"),
    ("http://169.254.169.254/latest/meta-data/", "http:// is only allowed for localhost"),
    ("https://user:pass@files.example/x", "credentials are not allowed"),
    ("https://files.example:99999/x", "invalid port"),
])
def test_disallowed_urls_are_refused_before_any_request(url, message):
    fetcher, rec = make()
    with pytest.raises(FetchError, match=re.escape(message)):
        fetcher.fetch(url)
    assert rec.requests == []


@pytest.mark.parametrize("address", [
    "10.0.0.1", "172.16.5.4", "192.168.1.1",  # RFC 1918
    "127.0.0.1",  # loopback (not allowed by default)
    "169.254.169.254",  # link-local / cloud metadata
    "100.64.0.1",  # carrier-grade NAT
    "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",  # unspecified, multicast, reserved, broadcast
    "::1", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1",  # IPv6 loopback, link-local, ULA, multicast
    "::ffff:10.0.0.1", "::ffff:169.254.169.254",  # IPv4-mapped forms
])
def test_hostnames_resolving_to_non_public_addresses_are_refused(address):
    fetcher, rec = make(None, {"evil.example": [address]})
    with pytest.raises(FetchError, match="non-public address"):
        fetcher.fetch("https://evil.example/case-file")
    assert rec.requests == []


def test_any_non_public_address_in_a_mixed_answer_refuses_the_host():
    fetcher, rec = make(None, {"rebind.example": [PUBLIC_IP, "10.0.0.1"]})
    with pytest.raises(FetchError, match="non-public"):
        fetcher.fetch("https://rebind.example/x")
    assert rec.requests == []


@pytest.mark.parametrize("literal", ["https://10.0.0.1/x", "https://[::1]/x", "https://169.254.169.254/x"])
def test_ip_literals_are_checked_too(literal):
    host = literal.split("//")[1].split("/")[0].strip("[]")
    fetcher, rec = make(None, {host: [host]})
    with pytest.raises(FetchError, match="non-public"):
        fetcher.fetch(literal)


# ------------------------------------------------------ redirects and size


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_are_never_followed(status):
    fetcher, rec = make(None, None, httpx.Response(status, headers={"location": "http://169.254.169.254/"}))
    with pytest.raises(FetchError, match="redirect"):
        fetcher.fetch("https://files.example/x")
    assert len(rec.requests) == 1


def test_declared_oversize_is_refused():
    fetcher, _ = make(FetchSettings(max_bytes=10), None,
                      httpx.Response(200, headers={"content-length": "11"}, content=b"x" * 11))
    with pytest.raises(FetchError, match="declared size 11 exceeds 10"):
        fetcher.fetch("https://files.example/x")


def test_streamed_oversize_without_length_header_is_aborted():
    def chunks():
        for _ in range(100):
            yield b"x" * 4096

    fetcher, _ = make(FetchSettings(max_bytes=10_000), None, httpx.Response(200, content=chunks()))
    with pytest.raises(FetchError, match="exceeds 10000 bytes"):
        fetcher.fetch("https://files.example/x")


def test_exactly_max_bytes_is_accepted():
    fetcher, _ = make(FetchSettings(max_bytes=len(BODY)), None, httpx.Response(200, content=BODY))
    assert fetcher.fetch("https://files.example/x").content == BODY


def test_slow_body_hits_the_deadline():
    """A server that trickles data stays under the per-read timeout; the total deadline stops it."""
    ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])  # deadline set at t=0, first chunk at t=0, second at t=99
    chunk = b"x" * 65_536  # one read per chunk
    fetcher = EvidenceFetcher(
        FetchSettings(timeout_sec=10, max_attempts=1), resolver=resolver_for({"files.example": [PUBLIC_IP]}),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=iter([chunk, chunk, chunk]))),
        clock=lambda: next(ticks),
    )
    with pytest.raises(FetchError, match="timed out"):
        fetcher.fetch("https://files.example/x")


# ------------------------------------------------------------------- retries


def test_retries_network_errors_and_5xx_then_succeeds():
    sleeps: List[float] = []
    fetcher, rec = make(FetchSettings(max_attempts=3), None,
                        httpx.ConnectError("boom"), httpx.Response(503), httpx.Response(200, content=BODY),
                        sleeps=sleeps)
    assert fetcher.fetch("https://files.example/x").content == BODY
    assert len(rec.requests) == 3 and sleeps == [0.5, 1.0]


def test_gives_up_after_max_attempts():
    fetcher, rec = make(FetchSettings(max_attempts=3), None, httpx.ReadTimeout("slow"))
    with pytest.raises(FetchError, match="giving up after 3 attempts"):
        fetcher.fetch("https://files.example/x")
    assert len(rec.requests) == 3


@pytest.mark.parametrize("status", [400, 403, 404, 410])
def test_client_errors_are_not_retried(status):
    fetcher, rec = make(FetchSettings(max_attempts=3), None, httpx.Response(status))
    with pytest.raises(FetchError, match=f"unexpected status {status}"):
        fetcher.fetch("https://files.example/x")
    assert len(rec.requests) == 1


def test_dns_failure_is_retried():
    calls = []

    def flaky(host, port):
        calls.append(host)
        if len(calls) < 2:
            raise FetchError("DNS lookup failed", retryable=True)
        return [PUBLIC_IP]

    fetcher = EvidenceFetcher(FetchSettings(max_attempts=2), resolver=flaky,
                              transport=httpx.MockTransport(lambda r: httpx.Response(200, content=BODY)),
                              sleep=lambda s: None)
    assert fetcher.fetch("https://files.example/x").content == BODY and len(calls) == 2


# --------------------------------------------------------- compat helper


def test_is_safe_url_compat_helper():
    assert is_safe_url("https://example.com/case-file.json") is True
    assert is_safe_url("https://ipfs.io") is True
    assert is_safe_url("ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi") is True
    assert is_safe_url("ftp://example.com/file") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_url("https://10.0.0.1/x") is False
