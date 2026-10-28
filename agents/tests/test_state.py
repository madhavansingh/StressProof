"""SQLite watcher state: persistence across restarts, immutable records, explicit transitions."""

import sqlite3
import threading

import pytest

from stressproof_agents.common.state import (
    RECORD_COLUMNS, TERMINAL_STATES, TRANSITIONS, StateError, WatcherState,
)

ATTESTER = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
EVIDENCE = "0x" + "aa" * 32
BIG = 2**200  # uint256-sized values survive the round trip


@pytest.fixture
def db(tmp_path):
    state = WatcherState(tmp_path / "watcher.sqlite", clock=lambda: 1000.0)
    yield state
    state.close()


def _add(db, claim_id=1, claimed=600_000_000_003):
    return db.add_claim(claim_id, ATTESTER, EVIDENCE, "http://127.0.0.1:8000/case-files/0x1", claimed)


def test_add_claim_returns_an_immutable_record(db):
    record = _add(db)
    assert record.claim_id == 1 and record.state == "SEEN" and record.claimed_usd8 == 600_000_000_003
    with pytest.raises(AttributeError):
        record.state = "MATCH"
    assert db.get(1).state == "SEEN"  # the database is unaffected


def test_add_claim_is_idempotent_and_keeps_progress(db):
    _add(db)
    db.transition(1, "FETCHING")
    again = _add(db, claimed=1)  # the same ClaimPosted log read again after a restart
    assert again.state == "FETCHING" and again.claimed_usd8 == 600_000_000_003


def test_full_challenge_path_transitions(db):
    _add(db)
    for state in ("FETCHING", "FETCHED", "HASH_OK", "VALID", "MISMATCH", "REPORT_BUILT", "REPORT_STORED",
                  "CHALLENGE_SENDING", "CHALLENGED", "WON", "WITHDRAWN"):
        assert db.transition(1, state).state == state
    assert db.get(1).is_terminal


def test_disallowed_transitions_are_rejected(db):
    _add(db)
    with pytest.raises(StateError, match="SEEN -> CHALLENGED is not allowed"):
        db.transition(1, "CHALLENGED")
    for state in ("FETCHING", "FETCHED", "HASH_OK", "VALID", "MATCH"):
        db.transition(1, state)
    with pytest.raises(StateError, match="MATCH -> MISMATCH is not allowed"):
        db.transition(1, "MISMATCH")  # terminal states never change
    with pytest.raises(StateError, match="unknown state"):
        db.transition(1, "DONE")
    with pytest.raises(StateError, match="not tracked"):
        db.transition(99, "FETCHING")


def test_repeating_the_current_state_is_allowed_for_retries(db):
    _add(db)
    db.transition(1, "FETCHING")
    assert db.transition(1, "FETCHING").state == "FETCHING"


def test_state_machine_is_consistent():
    assert all(target in TRANSITIONS for targets in TRANSITIONS.values() for target in targets)
    assert {"MATCH", "LOST", "WITHDRAWN", "SKIPPED", "CHALLENGE_FAILED"} == set(TERMINAL_STATES)


def test_record_sets_only_named_columns(db):
    _add(db)
    record = db.record(1, verdict="WRONG_RESULT", recomputed_usd8=BIG, report_hash="0x" + "bb" * 32)
    assert record.verdict == "WRONG_RESULT" and record.recomputed_usd8 == BIG and record.state == "SEEN"
    with pytest.raises(StateError, match="cannot set"):
        db.record(1, state="MATCH")  # state only changes through transition()
    with pytest.raises(StateError, match="cannot set"):
        db.record(1, **{"verdict = 'x'; DROP TABLE claims; --": "x"})
    with pytest.raises(StateError, match="cannot set nothing"):
        db.record(1)
    with pytest.raises(StateError, match="not tracked"):
        db.record(42, verdict="MATCH")
    assert set(RECORD_COLUMNS) >= {"verdict", "challenge_tx"}


def test_state_survives_a_restart(tmp_path):
    path = tmp_path / "watcher.sqlite"
    first = WatcherState(path)
    _add(first, claim_id=1)
    _add(first, claim_id=2)
    first.transition(1, "FETCHING")
    for state in ("FETCHING", "FETCHED", "HASH_OK", "VALID", "MATCH"):
        first.transition(2, state)
    first.record(1, error="gateway timeout")
    first.set_cursor(41)
    first.close()

    second = WatcherState(path)
    assert second.get(1).state == "FETCHING" and second.get(1).error == "gateway timeout"
    assert [r.claim_id for r in second.unfinished()] == [1]  # claim 2 is terminal
    assert second.cursor() == 41
    second.close()


def test_cursor_only_moves_forward(db):
    assert db.cursor() is None
    db.set_cursor(10)
    db.set_cursor(10)
    db.set_cursor(12)
    with pytest.raises(StateError, match="cannot move backwards"):
        db.set_cursor(11)
    with pytest.raises(StateError, match="non-negative"):
        db.set_cursor(-1)
    assert db.cursor() == 12


def test_unfinished_orders_by_numeric_claim_id(db):
    for claim_id in (10, 2, 33):
        _add(db, claim_id=claim_id)
    assert [r.claim_id for r in db.unfinished()] == [2, 10, 33]


def test_concurrent_writers_do_not_corrupt_state(db):
    for claim_id in range(1, 21):
        _add(db, claim_id=claim_id)

    def worker(claim_id):
        db.transition(claim_id, "FETCHING")
        db.record(claim_id, verdict="MATCH")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 21)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(db.get(i).state == "FETCHING" and db.get(i).verdict == "MATCH" for i in range(1, 21))


def test_database_file_has_the_expected_schema(tmp_path):
    WatcherState(tmp_path / "w.sqlite").close()
    with sqlite3.connect(tmp_path / "w.sqlite") as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"claims", "meta"} <= tables
