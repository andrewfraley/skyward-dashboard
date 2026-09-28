"""The sync runner: what it saves, what it refuses, and what it logs."""

import logging
import threading
from collections import Counter
from urllib.parse import quote_plus

import pytest

import app.sync as sync
from app.config import Settings
from app.db import Database
from app.skyward.models import Snapshot, Student
from app.sync import IncompleteSnapshot, SyncAlreadyRunning, Syncer, check_complete
from tests.test_db import save, snapshot

PASSWORD = "pa ss&word"


@pytest.fixture
def syncer(tmp_path):
    settings = Settings(
        base_url="https://skyward.example.org",
        username="parent",
        password=PASSWORD,
        data_dir=tmp_path,
        sync_cron="0 6 * * *",
        timezone=None,
    )
    return Syncer(settings, Database(settings.db_path))


def fetches(monkeypatch, result):
    """Make the sync's fetch return `result`, or raise it if it's an exception."""

    def fake(session):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(sync, "fetch_snapshot", fake)


def test_a_good_sync_is_saved(syncer, monkeypatch):
    fetches(monkeypatch, snapshot())
    run = syncer.run()
    assert run["status"] == "ok"
    assert syncer.db.courses(1)


def test_the_password_never_reaches_the_log_or_database(syncer, monkeypatch, caplog):
    fetches(monkeypatch, RuntimeError(f"bad {PASSWORD} and {quote_plus(PASSWORD)}"))
    with caplog.at_level(logging.DEBUG):
        run = syncer.run()
    assert run["status"] == "error"
    assert PASSWORD not in run["error"] and quote_plus(PASSWORD) not in run["error"]
    assert "***" in run["error"]
    # Records at INFO and above carry the message; tracebacks go to DEBUG only.
    for record in caplog.records:
        if record.levelno >= logging.INFO:
            assert PASSWORD not in record.getMessage()
            assert record.exc_info is None


def test_an_empty_fetch_keeps_the_cache(syncer, monkeypatch):
    save(syncer.db, snapshot())
    empty = Snapshot(students=[Student(id=1, name="STUDENT, DEMO")], courses=[], assignments=[])
    fetches(monkeypatch, empty)
    run = syncer.run()
    assert run["status"] == "error" and "no courses" in run["error"]
    assert syncer.db.courses(1) and syncer.db.assignments(1)


def counts(courses=None, assignments=None):
    return {"courses": Counter(courses or {}), "assignments": Counter(assignments or {})}


def test_complete_snapshots_pass():
    snap = snapshot()
    check_complete(snap, counts())  # first sync: nothing cached yet
    check_complete(snap, counts({1: 5}, {1: 50}))  # fewer than before is fine


def test_no_students_is_refused():
    with pytest.raises(IncompleteSnapshot, match="no students"):
        check_complete(Snapshot(students=[], courses=[], assignments=[]), counts())


def test_a_student_losing_every_assignment_is_refused():
    snap = snapshot()
    snap.assignments = []
    with pytest.raises(IncompleteSnapshot, match="no assignments"):
        check_complete(snap, counts({1: 1}, {1: 2}))


def test_a_student_no_longer_listed_is_let_go():
    # Student 2 left the account: their cached rows don't block the sync.
    check_complete(snapshot(), counts({1: 1, 2: 3}, {1: 2, 2: 9}))


def test_one_sync_at_a_time(syncer, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(session):
        started.set()
        release.wait(5)
        return snapshot()

    monkeypatch.setattr(sync, "fetch_snapshot", slow)
    t = threading.Thread(target=syncer.run)
    t.start()
    started.wait(5)
    assert syncer.running
    with pytest.raises(SyncAlreadyRunning):
        syncer.run()
    release.set()
    t.join(5)
    assert not syncer.running


def test_one_sync_at_a_time_across_processes(syncer, monkeypatch):
    # A second Syncer on the same data dir stands in for `python -m app.sync`
    # run next to the server: its lock file is separate from the thread lock.
    other = Syncer(syncer.settings, syncer.db)
    started, release = threading.Event(), threading.Event()

    def slow(session):
        started.set()
        release.wait(5)
        return snapshot()

    monkeypatch.setattr(sync, "fetch_snapshot", slow)
    t = threading.Thread(target=syncer.run)
    t.start()
    started.wait(5)
    try:
        assert other.running
        with pytest.raises(SyncAlreadyRunning):
            other.run()
        # Its run is live, not stale: another process starting up leaves it alone.
        other.fail_stale_runs()
        assert syncer.db.last_runs(1)[0]["status"] == "running"
    finally:
        release.set()
        t.join(5)
    assert not other.running
    assert syncer.db.last_runs(1)[0]["status"] == "ok"


def test_stale_runs_are_failed_when_nothing_is_syncing(syncer):
    syncer.db.start_run()  # left 'running' by a crash
    syncer.fail_stale_runs()
    assert syncer.db.last_runs(1)[0]["status"] == "error"
