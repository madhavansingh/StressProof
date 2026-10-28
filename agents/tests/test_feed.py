"""Feed client: entries are well formed, and no failure ever raises."""

import json
import logging

import httpx
import pytest

from stressproof_agents.common.config import Secret
from stressproof_agents.common.feed import FeedClient

TOKEN = Secret("feed-write-token-123", "API_WRITE_TOKEN")


def client_with(handler):
    seen = []

    def transport(request):
        seen.append(request)
        return handler(request)

    return FeedClient("http://127.0.0.1:8000/", TOKEN, transport=httpx.MockTransport(transport)), seen


def test_posts_entry_matching_backend_contract():
    client, seen = client_with(lambda r: httpx.Response(201, json={"seq": 1}))
    assert client.post("watcher", "REPLAY_MATCH", claim_id=3, data={"recomputedUsd8": "200000000001"}) is True
    req = seen[0]
    assert str(req.url) == "http://127.0.0.1:8000/feed"
    assert req.headers["authorization"] == "Bearer feed-write-token-123"
    assert json.loads(req.content) == {"actor": "watcher", "kind": "REPLAY_MATCH", "claimId": "3",
                                       "txHash": None, "data": {"recomputedUsd8": "200000000001"}}


@pytest.mark.parametrize("handler", [
    lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")),
    lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    lambda r: httpx.Response(401),
    lambda r: httpx.Response(500),
])
def test_backend_failures_return_false_and_never_raise(handler, caplog):
    client, _ = client_with(handler)
    with caplog.at_level(logging.WARNING):
        assert client.post("watcher", "HASH_OK", claim_id=1) is False
    assert "feed-write-token-123" not in caplog.text  # the token is never logged


@pytest.mark.parametrize("actor, kind, data, reason", [
    ("watcher", "NOT_A_KIND", {}, "unknown kind"),
    ("admin", "HASH_OK", {}, "unknown actor"),
    ("watcher", "HASH_OK", {"amount": 1.5}, "contains a float"),
    ("watcher", "HASH_OK", {"bad": object()}, "not JSON-serializable"),
])
def test_invalid_entries_are_dropped_and_logged(actor, kind, data, reason, caplog):
    client, seen = client_with(lambda r: httpx.Response(201))
    with caplog.at_level(logging.ERROR):
        assert client.post(actor, kind, data=data) is False
    assert seen == [] and reason in caplog.text


def test_missing_token_does_not_send(caplog):
    client = FeedClient("http://127.0.0.1:8000", None,
                        transport=httpx.MockTransport(lambda r: pytest.fail("must not send")))
    with caplog.at_level(logging.WARNING):
        assert client.post("watcher", "HASH_OK") is False
    assert "API_WRITE_TOKEN is not set" in caplog.text
