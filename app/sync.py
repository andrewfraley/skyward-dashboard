"""Fetch from Skyward and store the result. The only code that talks to Skyward.

uv run python -m app.sync            # one sync, then exit
"""

import logging
import threading

from app.config import Settings, load_settings
from app.db import Database
from app.skyward.client import fetch_snapshot
from app.skyward.session import SkywardSession

log = logging.getLogger(__name__)


class SyncAlreadyRunning(Exception):
    pass


class Syncer:
    """Runs one sync at a time, whether started by the schedule or the API."""

    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self._lock = threading.Lock()

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
            with SkywardSession(s.base_url, s.username, s.password) as session:
                snap = fetch_snapshot(session)
            changes = self.db.save_snapshot(run_id, snap)
        except Exception as e:
            log.exception("Sync %d failed", run_id)
            # Never let the password reach the log or the database.
            message = f"{type(e).__name__}: {e}".replace(self.settings.password, "***")
            self.db.finish_run(run_id, error=message)
            return self.db.last_runs(1)[0]
        self.db.finish_run(run_id, changes=changes)
        log.info(
            "Sync %d ok: %d courses, %d assignments, %d changes",
            run_id, len(snap.courses), len(snap.assignments), changes,
        )  # fmt: skip
        return self.db.last_runs(1)[0]


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
