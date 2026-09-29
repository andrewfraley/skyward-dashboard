"""The payload for e-paper displays: GET /api/display (see DISPLAY.md).

A battery display wakes, fetches this once, draws it and sleeps, so everything
it needs is worked out here: the current grading period, first names, course
titles, due labels, and how long to sleep. The firmware only places text.

The grade helpers are ports of frontend/src/grades.js, so the display and the
web UI agree; tests/test_display.py repeats grades.test.js's cases.

Version 1 of this shape is a contract with firmware that doesn't update
itself: fields may be added, never renamed or removed. A breaking change is a
new version, served beside this one.
"""

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.db import Database

VERSION = 1

# Sleep until the next scheduled sync has had time to finish.
SYNC_GRACE = timedelta(minutes=10)
MIN_SLEEP = timedelta(minutes=15)
MAX_SLEEP = timedelta(hours=12)

# A cached sync older than this is flagged, so an old screen says it's old.
STALE_AFTER = timedelta(hours=24)

# List caps keep the payload small however far behind a student is.
MAX_MISSING = 12
MAX_UPCOMING = 10
MAX_TEXT = 80


# -- helpers ported from frontend/src/grades.js -------------------------------


def _is_grading_period(term: str) -> bool:
    return re.fullmatch(r"GP\d+", term or "") is not None


def current_term(grades: list[dict], today: str) -> dict | None:
    """The GP whose dates contain today, else the latest GP that has a grade."""
    graded = [g for g in grades or [] if g.get("grade") and _is_grading_period(g["term"])]
    for g in graded:
        if g.get("start_date") and g.get("end_date") and g["start_date"] <= today <= g["end_date"]:
            return g
    return graded[-1] if graded else None


def grading_period(courses: list[dict], today: str) -> dict | None:
    """The school's current GP: the one containing today, else the latest one started."""
    periods = [
        g
        for c in courses or []
        for g in c.get("grades") or []
        if _is_grading_period(g["term"]) and g.get("start_date") and g.get("end_date")
    ]
    for g in periods:
        if g["start_date"] <= today <= g["end_date"]:
            return g
    started = sorted(
        (g for g in periods if g["start_date"] <= today), key=lambda g: g["start_date"]
    )
    return started[-1] if started else None


def in_period(assignment: dict, period: dict | None) -> bool:
    due = assignment.get("due_date")
    return not period or not due or period["start_date"] <= due <= period["end_date"]


def grade_band(grade: str | None) -> str | None:
    letter = (grade or "").strip()[:1].upper()
    return letter if letter and letter in "ABCDF" else None


def is_struggling(grade: str | None) -> bool:
    """C- or below."""
    return grade_band(grade) in ("D", "F") or (grade or "").strip().upper() == "C-"


def format_percent(percent: float | None) -> str:
    # Half up from the float's exact value, as JavaScript's toFixed(1) does;
    # Python's format() would round 70.25 to even.
    if percent is None:
        return ""
    return f"{Decimal(percent).quantize(Decimal('0.1'), ROUND_HALF_UP)}%"


def days_until(iso_date: str | None, today: str) -> int | None:
    if not iso_date:
        return None
    return (date.fromisoformat(iso_date) - date.fromisoformat(today)).days


def short_date(iso_date: str | None) -> str:
    """'Tue Sep 29'."""
    if not iso_date:
        return ""
    d = date.fromisoformat(iso_date)
    return f"{d:%a %b} {d.day}"


def clock(when: datetime) -> str:
    """'9:02 AM'."""
    hour = when.hour % 12 or 12
    return f"{hour}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"


def due_label(iso_date: str | None, today: str) -> str:
    days = days_until(iso_date, today)
    if days is None:
        return "No due date"
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    if days == -1:
        return "Yesterday"
    if 1 < days < 7:
        return f"In {days} days"
    if -7 < days < -1:
        return f"{-days} days ago"
    return short_date(iso_date)


def first_name(full_name: str | None) -> str:
    """'STUDENT, DEMO' -> 'Demo'."""
    full_name = full_name or ""
    parts = full_name.split(",")
    first = (parts[1].split() or [""])[0] if len(parts) > 1 else ""
    first = first or full_name
    return first[:1].upper() + first[1:].lower()


_SMALL_WORDS = {"and", "or", "for", "of", "the", "a", "an", "in", "to", "&"}
_KEEP_UPPER = {"AP", "IB", "PE", "ELL", "ESL", "STEM"}


def course_title(name: str | None) -> str:
    """'ENGLISH 8 AP-I' -> 'English 8 AP-I': Skyward shouts; keep codes and numerals."""

    def word(w: str, i: int) -> str:
        lower = w.lower()
        if len(w) == 1:  # a label ("TEACHER A"), not the article "a"
            return w
        if i > 0 and lower in _SMALL_WORDS:
            return lower
        if w in _KEEP_UPPER or re.search(r"\d", w) or re.fullmatch(r"[IVX]+", w) or len(w) <= 2:
            return w
        return w[0] + lower[1:]

    return " ".join(
        "-".join(word(part, i + j) for j, part in enumerate(token.split("-")))
        for i, token in enumerate((name or "").split())
    )


# -- text the firmware's fonts can draw ----------------------------------------

# Fonts on a display carry a fixed glyph set to save flash; DISPLAY.md
# documents it as printable ASCII. Anything else would draw as a box.
_REPLACEMENTS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        " ": " ",
        "×": "x",
    }
)


def fold(text: str | None, limit: int = MAX_TEXT) -> str:
    """Text reduced to printable ASCII: accents dropped, quotes and dashes straightened."""
    text = unicodedata.normalize("NFKD", (text or "").translate(_REPLACEMENTS))
    text = "".join(ch for ch in text if " " <= ch <= "~")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


# -- the payload ---------------------------------------------------------------


def sleep_seconds(next_run: datetime | None, now: datetime) -> int:
    """How long a display should sleep: until just after the next sync, within bounds."""
    wait = MAX_SLEEP if next_run is None else next_run + SYNC_GRACE - now
    return int(min(max(wait, MIN_SLEEP), MAX_SLEEP).total_seconds())


def _sync_state(database: Database, now: datetime, paused: bool) -> dict:
    last_run = next(iter(database.last_runs(1)), None)
    success = database.last_success()
    finished = (
        datetime.fromisoformat(success["finished_at"])
        if success and success["finished_at"]
        else None
    )
    # When the data last changed, not when it was last checked: it moves only
    # when the content does, so the hash stays put between unchanged syncs.
    change = database.last_change()
    changed = (
        datetime.fromisoformat(change["finished_at"]).astimezone(now.tzinfo)
        if change and change["finished_at"]
        else None
    )
    error = None
    if paused:
        error = "Skyward sign-in rejected"
    elif last_run and last_run["status"] == "error":
        error = "Last update failed"
    return {
        "updated": (
            short_date(finished.astimezone(now.tzinfo).date().isoformat()) if finished else ""
        ),
        "changed": (
            f"{short_date(changed.date().isoformat())}, {clock(changed)}" if changed else ""
        ),
        "stale": finished is None or now - finished > STALE_AFTER,
        "sync_error": error,
    }


def _student(database: Database, student: dict, today: str) -> dict:
    courses = database.courses(student["id"])
    assignments = database.assignments(student["id"])
    period = grading_period(courses, today)

    missing = [a for a in assignments if a["status"] == "missing" and in_period(a, period)]
    upcoming = sorted(
        (a for a in assignments if a["status"] == "upcoming"),
        key=lambda a: (a["due_date"] is None, a["due_date"] or "", a["name"]),
    )

    grades = []
    for c in courses:
        term = current_term(c["grades"], today)
        if term:
            grades.append(
                {
                    "course": fold(course_title(c["name"]), 40),
                    "letter": fold(term["grade"], 4),
                    "percent": format_percent(term["percent"]),
                    "struggling": is_struggling(term["grade"]),
                    "missing": sum(a["course"] == c["name"] for a in missing),
                }
            )

    def item(a: dict) -> dict:
        return {
            "course": fold(course_title(a["course"]), 40),
            "title": fold(a["name"]),
            "due": due_label(a["due_date"], today),
            "date": short_date(a["due_date"]),
        }

    days = [days_until(a["due_date"], today) for a in upcoming]
    due_this_week = [d for d in days if d is not None and 0 <= d < 7]  # today and the next six
    # When the period closes, and so does the chance to hand in what's missing.
    # Blank between periods, when the latest one has already ended.
    days_left = days_until(period["end_date"], today) if period else None
    if days_left is not None and days_left < 0:
        days_left = None
    return {
        "name": fold(first_name(student["name"]), 20),
        "grading_period": period["term"] if period else "",
        "period_ends": short_date(period["end_date"]) if days_left is not None else "",
        "period_days_left": days_left,
        "grades": grades,
        "missing": {
            "count": len(missing),
            "items": [item(a) for a in missing[:MAX_MISSING]],
            "more": max(0, len(missing) - MAX_MISSING),
        },
        "upcoming": {
            "count": len(upcoming),
            "due_this_week": len(due_this_week),
            "items": [item(a) for a in upcoming[:MAX_UPCOMING]],
            "more": max(0, len(upcoming) - MAX_UPCOMING),
        },
    }


def build(
    database: Database, now: datetime, next_run: datetime | None, paused: bool = False
) -> dict:
    """The v1 payload. `now` must be timezone-aware, in the app's local zone."""
    today = now.date().isoformat()
    content = {
        **_sync_state(database, now, paused),
        "students": [_student(database, s, today) for s in database.students()],
    }
    # The hash covers only what's drawn, so a display skips redrawing when a
    # sync changed nothing. It must never include a time of day; the date does
    # enter it (period_days_left, due labels), so a display redraws once a day.
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "v": VERSION,
        "hash": digest,
        "sleep_seconds": sleep_seconds(next_run, now),
        **content,
    }
