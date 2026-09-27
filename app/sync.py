"""Fetch from Skyward and store the result. The only code that talks to Skyward.

uv run python -m app.sync            # one sync, then exit
"""

import logging
import threading
from collections import Counter
from urllib.parse import quote, quote_plus

from app.config import Settings, load_settings
from app.db import Database
from app.skyward.client import fetch_snapshot
from app.skyward.models import Snapshot
from app.skyward.session import LoginError, SkywardError, SkywardSession

log = logging.getLogger(__name__)


class SyncAlreadyRunning(Exception):
    pass


class IncompleteSnapshot(SkywardError):
    """What was fetched is missing things the last sync had; the cache is kept."""


class Syncer:
    """Runs one sync at a time, whether started by the schedule or the API."""

    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self._lock = threading.Lock()
        # Set when Skyward rejects the sign-in. Automatic syncs stop until a
        # sync succeeds or the app restarts (as it does when .env changes):
        # retrying a wrong password every few hours can lock the account.
        self.login_failed: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def run(self) -> dict:
        if not self._lock.acquire(blocking=False):
            raise SyncAlreadyRunning()
        try:
            return self._run()
        finally:
            self._lock.release()

    def _run(self) -> dict:
        run_id = self.db.start_run()
        log.info("Sync %d started", run_id)
        try:
            s = self.settings
            with SkywardSession(
                s.base_url, s.username, s.password, cookie_file=s.cookie_path
            ) as session:
                snap = fetch_snapshot(session)
                signed_in = session.sign_ins
            check_complete(snap, self.db.counts())
            changes = self.db.save_snapshot(run_id, snap)
        except Exception as e:
            # Never let the password reach the log or the database. The
            # traceback is only logged at debug level, since it repeats the
            # unredacted message.
            message = self._redact(f"{type(e).__name__}: {e}")
            log.error("Sync %d failed: %s", run_id, message)
            log.debug("Sync %d traceback", run_id, exc_info=True)
            if isinstance(e, LoginError):
                self.login_failed = message
            self.db.finish_run(run_id, error=message)
            return self.db.last_runs(1)[0]
        self.login_failed = None
        self.db.finish_run(run_id, changes=changes)
        log.info(
            "Sync %d ok: %d courses, %d assignments, %d changes (%s)",
            run_id, len(snap.courses), len(snap.assignments), changes,
            "signed in" if signed_in else "reused the saved session",
        )  # fmt: skip
        return self.db.last_runs(1)[0]

    def _redact(self, text: str) -> str:
        pw = self.settings.password
        for form in {pw, quote(pw, safe=""), quote_plus(pw)}:
            text = text.replace(form, "***")
        return text


def check_complete(snap: Snapshot, before: dict[str, Counter]) -> None:
    """Refuse a snapshot that lost everything of a kind the cache has.

    Saving replaces the cache wholesale, so a parse that quietly found nothing
    (Skyward changed its pages, say) would empty the dashboard and still look
    like a good sync, and the next good one would log every assignment as new.
    Fewer rows is fine (a dropped class); none at all, for a student Skyward
    still lists, is not. A student no longer listed at all is let go.
    """
    if not snap.students:
        raise IncompleteSnapshot("Skyward listed no students")
    listed = {s.id for s in snap.students}
    now = {
        "courses": Counter(c.student_id for c in snap.courses),
        "assignments": Counter(a.student_id for a in snap.assignments),
    }
    for kind, counts in now.items():
        for student_id, had in before[kind].items():
            if student_id in listed and had and not counts[student_id]:
                raise IncompleteSnapshot(
                    f"Found no {kind} for student {student_id}, who had {had}; "
                    "keeping the last sync's data"
                )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings()
    if not settings.has_credentials:
        raise SystemExit(
            "Set SKYWARD_BASE_URL, SKYWARD_USER and SKYWARD_PASS (in .env or the environment)"
        )
    db = Database(settings.db_path)
    db.fail_stale_runs()
    result = Syncer(settings, db).run()
    print(result)
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
