"""FastAPI app: the /api routes over cached data, the sync schedule, and the built UI on /.

Nothing here calls Skyward. Routes read the SQLite cache; the scheduler (and
POST /api/sync) run app.sync.Syncer, which is what refreshes it.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, load_settings
from app.db import Database
from app.sync import SyncAlreadyRunning, Syncer

logging.basicConfig(
    level=os.environ.get("SKYWARD_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("skyward_dashboard")

SYNC_JOB = "sync"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    db = Database(settings.db_path)
    db.fail_stale_runs()
    syncer = Syncer(settings, db)
    scheduler = BackgroundScheduler(timezone=settings.timezone or None)
    app.state.db, app.state.syncer, app.state.scheduler = db, syncer, scheduler

    if settings.has_credentials:
        trigger = CronTrigger.from_crontab(settings.sync_cron, timezone=settings.timezone or None)
        scheduler.add_job(_scheduled_sync, trigger, args=[syncer], id=SYNC_JOB, max_instances=1)
        if db.last_success() is None:
            # Nothing cached yet: fetch now rather than waiting for the schedule.
            scheduler.add_job(_scheduled_sync, args=[syncer], id="initial-sync")
        log.info("Syncing on schedule %r", settings.sync_cron)
    else:
        log.warning(
            "SKYWARD_BASE_URL / SKYWARD_USER / SKYWARD_PASS not set; serving cached data only"
        )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def _scheduled_sync(syncer: Syncer) -> None:
    try:
        syncer.run()
    except SyncAlreadyRunning:
        log.info("Skipping scheduled sync: one is already running")


app = FastAPI(title="Skyward Dashboard", lifespan=lifespan)


def db(request: Request) -> Database:
    return request.app.state.db


@app.get("/api/ping")
def ping() -> dict:
    return {"ok": True}


@app.get("/api/status")
def status(request: Request) -> dict:
    job = request.app.state.scheduler.get_job(SYNC_JOB)
    return {
        "syncing": request.app.state.syncer.running,
        "last_run": next(iter(db(request).last_runs(1)), None),
        "last_success": db(request).last_success(),
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "schedule": request.app.state.syncer.settings.sync_cron if job else None,
    }


@app.post("/api/sync", status_code=202)
def start_sync(request: Request) -> dict:
    syncer: Syncer = request.app.state.syncer
    if not syncer.settings.has_credentials:
        raise HTTPException(
            400, "SKYWARD_BASE_URL, SKYWARD_USER and SKYWARD_PASS are not configured"
        )
    if syncer.running:
        raise HTTPException(409, "A sync is already running")
    request.app.state.scheduler.add_job(_scheduled_sync, args=[syncer])
    return {"started": True}


@app.get("/api/students")
def students(request: Request) -> list[dict]:
    return db(request).students()


@app.get("/api/students/{student_id}/courses")
def courses(request: Request, student_id: int) -> list[dict]:
    return db(request).courses(student_id)


@app.get("/api/students/{student_id}/assignments")
def assignments(
    request: Request,
    student_id: int,
    status: Literal["missing", "upcoming", "past"] | None = None,
    course: str | None = None,
) -> list[dict]:
    return db(request).assignments(student_id, status=status, course=course)


@app.get("/api/courses/{student_section_id}")
def course(request: Request, student_section_id: int) -> dict:
    found = db(request).course(student_section_id)
    if not found:
        raise HTTPException(404, "No such course")
    found["assignments"] = db(request).assignments(found["student_id"], course=found["name"])
    return found


@app.get("/api/changes")
def changes(request: Request, student_id: int | None = None, limit: int = 100) -> list[dict]:
    return db(request).changes(student_id=student_id, limit=min(limit, 500))


@app.exception_handler(404)
async def not_found(request: Request, exc) -> JSONResponse | HTMLResponse:
    """Unknown /api paths get JSON; anything else is a client-side route, so serve the UI."""
    index = _static_dir / "index.html" if _static_dir else None
    if not request.url.path.startswith("/api/") and index and index.exists():
        return HTMLResponse(index.read_text())
    detail = getattr(exc, "detail", "Not found")
    return JSONResponse({"detail": detail}, status_code=404)


def resolve_static_dir() -> Path | None:
    """Where the built UI lives: ./static in the image, frontend/dist in dev."""
    for path in (ROOT / "static", ROOT / "frontend" / "dist"):
        if (path / "index.html").exists():
            return path
    return None


_static_dir = resolve_static_dir()
if _static_dir:
    log.info("Serving UI from %s", _static_dir)
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="ui")
else:

    @app.get("/", response_class=HTMLResponse)
    def missing_ui() -> HTMLResponse:
        return HTMLResponse(
            "<h1>Skyward Dashboard</h1><p>No built UI found. Run <code>npm --prefix frontend "
            "install &amp;&amp; npm --prefix frontend run build</code>, or use the Docker image. "
            "The API is up at <a href='docs'>/docs</a>.</p>"
        )
