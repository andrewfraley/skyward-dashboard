"""SQLite storage: the latest snapshot, grade history, and a feed of changes.

The dashboard and API only ever read from here; app/sync.py is the only
writer. Each sync replaces the latest state wholesale inside one transaction,
after diffing it against what was there to record what changed.
"""

import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.skyward.models import Assignment, Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,            -- running | ok | error
    error TEXT,
    changes INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    school TEXT,
    school_year TEXT
);
CREATE TABLE IF NOT EXISTS courses (
    student_section_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    course_code TEXT,
    period TEXT,
    teacher TEXT,
    missing_count INTEGER DEFAULT 0,
    position INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS term_grades (
    student_section_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    position INTEGER NOT NULL,
    grade TEXT,
    percent REAL,
    start_date TEXT,
    end_date TEXT,
    categories TEXT,                 -- JSON list of Category
    assignment_ids TEXT,             -- JSON list of ints
    PRIMARY KEY (student_section_id, term)
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    course TEXT NOT NULL,
    section_code TEXT,
    teacher TEXT,
    category TEXT,
    due_date TEXT,
    grade TEXT,
    score REAL,
    max_score REAL,
    weight REAL,
    class_average REAL,
    status TEXT NOT NULL,
    first_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assignments_by_student ON assignments (student_id, status, due_date);
CREATE TABLE IF NOT EXISTS grade_history (
    student_section_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    grade TEXT,
    percent REAL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS grade_history_by_course ON grade_history (student_section_id, term, recorded_at);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY,
    sync_id INTEGER NOT NULL,
    at TEXT NOT NULL,
    student_id INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- see Change kinds in diff_snapshot()
    course TEXT,
    subject TEXT,
    old TEXT,
    new TEXT
);
CREATE INDEX IF NOT EXISTS changes_by_time ON changes (at DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)
        # A child's grades: owner only, like the cookie file. SQLite gives
        # its journal files the database's permissions.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # not ours to change (a read-only copy, say); it still works

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # commits, or rolls back on error
                yield conn
        finally:
            conn.close()

    # -- sync bookkeeping ---------------------------------------------------

    def start_run(self) -> int:
        with self.connect() as db:
            return db.execute(
                "INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (now(),)
            ).lastrowid

    def finish_run(self, run_id: int, error: str | None = None, changes: int = 0) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE sync_runs SET finished_at = ?, status = ?, error = ?, changes = ? WHERE id = ?",
                (now(), "error" if error else "ok", error, changes, run_id),
            )

    def fail_stale_runs(self) -> None:
        """Runs left 'running' by a crash or restart can never finish."""
        with self.connect() as db:
            db.execute(
                "UPDATE sync_runs SET status = 'error', error = 'interrupted', finished_at = ? "
                "WHERE status = 'running'",
                (now(),),
            )

    def last_runs(self, limit: int = 1) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in rows]

    def last_success(self) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sync_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def last_change(self) -> dict | None:
        """The last good sync that changed something, or the first good one if none has."""
        with self.connect() as db:
            row = (
                db.execute(
                    "SELECT * FROM sync_runs WHERE status = 'ok' AND changes > 0 ORDER BY id DESC LIMIT 1"
                ).fetchone()
                or db.execute(
                    "SELECT * FROM sync_runs WHERE status = 'ok' ORDER BY id LIMIT 1"
                ).fetchone()
            )
            return dict(row) if row else None

    def counts(self) -> dict[str, Counter]:
        """Courses and assignments cached per student id."""
        with self.connect() as db:
            return {
                table: Counter(
                    {
                        r[0]: r[1]
                        for r in db.execute(
                            f"SELECT student_id, COUNT(*) FROM {table} GROUP BY student_id"
                        )
                    }
                )
                for table in ("courses", "assignments")
            }

    # -- writing a snapshot -------------------------------------------------

    def save_snapshot(self, run_id: int, snap: Snapshot) -> int:
        """Replace the latest state with `snap`; return how many changes were logged."""
        stamp = now()
        with self.connect() as db:
            first_sync = db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0
            old_courses = {
                r["student_section_id"]: dict(r) for r in db.execute("SELECT * FROM courses")
            }
            old_grades = {
                (r["student_section_id"], r["term"]): dict(r)
                for r in db.execute("SELECT * FROM term_grades")
            }
            old_assignments = {r["id"]: dict(r) for r in db.execute("SELECT * FROM assignments")}

            changes = (
                [] if first_sync else diff_snapshot(snap, old_courses, old_grades, old_assignments)
            )
            db.executemany(
                "INSERT INTO changes (sync_id, at, student_id, kind, course, subject, old, new) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(run_id, stamp, *c) for c in changes],
            )

            db.execute("DELETE FROM students")
            db.executemany(
                "INSERT INTO students (id, name, school, school_year) VALUES (?, ?, ?, ?)",
                [(s.id, s.name, s.school, s.school_year) for s in snap.students],
            )

            db.execute("DELETE FROM courses")
            db.execute("DELETE FROM term_grades")
            for pos, c in enumerate(snap.courses):
                db.execute(
                    "INSERT INTO courses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (c.student_section_id, c.student_id, c.name, c.course_code, c.period, c.teacher,
                     c.missing_count, pos),
                )  # fmt: skip
                for tpos, g in enumerate(c.grades):
                    db.execute(
                        "INSERT INTO term_grades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (c.student_section_id, g.term, tpos, g.grade, g.percent,
                         _iso(g.start_date), _iso(g.end_date),
                         json.dumps([cat.model_dump() for cat in g.categories]),
                         json.dumps(g.assignment_ids)),
                    )  # fmt: skip
                    old = old_grades.get((c.student_section_id, g.term))
                    if g.grade and (
                        not old or (old["grade"], old["percent"]) != (g.grade, g.percent)
                    ):
                        db.execute(
                            "INSERT INTO grade_history VALUES (?, ?, ?, ?, ?)",
                            (c.student_section_id, g.term, g.grade, g.percent, stamp),
                        )

            db.execute("DELETE FROM assignments")
            db.executemany(
                "INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (a.id, a.student_id, a.name, a.course, a.section_code, a.teacher, a.category,
                     _iso(a.due_date), a.grade, a.score, a.max_score, a.weight, a.class_average,
                     a.status, old_assignments.get(a.id, {}).get("first_seen", stamp))
                    for a in snap.assignments
                ],
            )  # fmt: skip
            return len(changes)

    # -- reading ------------------------------------------------------------

    def students(self) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM students ORDER BY name")]

    def courses(self, student_id: int) -> list[dict]:
        with self.connect() as db:
            courses = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM courses WHERE student_id = ? ORDER BY position", (student_id,)
                )
            ]
            for c in courses:
                c["grades"] = self._grades(db, c["student_section_id"])
            return courses

    def course(self, student_section_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM courses WHERE student_section_id = ?", (student_section_id,)
            ).fetchone()
            if not row:
                return None
            course = dict(row)
            course["grades"] = self._grades(db, student_section_id)
            course["history"] = [
                dict(r)
                for r in db.execute(
                    "SELECT term, grade, percent, recorded_at FROM grade_history "
                    "WHERE student_section_id = ? ORDER BY recorded_at",
                    (student_section_id,),
                )
            ]
            return course

    @staticmethod
    def _grades(db, student_section_id: int) -> list[dict]:
        grades = []
        for r in db.execute(
            "SELECT * FROM term_grades WHERE student_section_id = ? ORDER BY position",
            (student_section_id,),
        ):
            g = dict(r)
            g["categories"] = json.loads(g["categories"] or "[]")
            g["assignment_ids"] = json.loads(g["assignment_ids"] or "[]")
            del g["student_section_id"], g["position"]
            grades.append(g)
        return grades

    def assignments(
        self, student_id: int, status: str | None = None, course: str | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM assignments WHERE student_id = ?"
        args: list = [student_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        if course:
            sql += " AND course = ?"
            args.append(course)
        # Upcoming soonest first; everything else most recent first. Undated
        # ones last either way (SQLite would put them first when ascending).
        sql += (
            " ORDER BY due_date IS NULL, due_date "
            + ("ASC" if status == "upcoming" else "DESC")
            + ", name"
        )
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def changes(self, student_id: int | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM changes"
        args: list = []
        if student_id is not None:
            sql += " WHERE student_id = ?"
            args.append(student_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _fmt_grade(grade: str | None, percent: float | None) -> str | None:
    if grade is None:
        return None
    return f"{grade} ({percent:.2f}%)" if percent is not None else grade


def diff_snapshot(
    snap: Snapshot,
    old_courses: dict[int, dict],
    old_grades: dict[tuple[int, str], dict],
    old_assignments: dict[int, dict],
) -> list[tuple]:
    """What changed since the last sync, as (student_id, kind, course, subject, old, new).

    Change kinds:
      grade_changed    a term grade's letter or percent moved
      now_missing      an assignment became missing
      no_longer_missing  a missing assignment was turned in or excused
      scored           an assignment got (or changed) a score
      new_assignment   an assignment appeared for the first time
    """
    out: list[tuple] = []
    for c in snap.courses:
        for g in c.grades:
            old = old_grades.get((c.student_section_id, g.term))
            if not g.grade or not old:
                continue
            if (old["grade"], old["percent"]) != (g.grade, g.percent):
                out.append(
                    (c.student_id, "grade_changed", c.name, g.term,
                     _fmt_grade(old["grade"], old["percent"]), _fmt_grade(g.grade, g.percent))
                )  # fmt: skip

    for a in snap.assignments:
        old = old_assignments.get(a.id)
        if old is None:
            kind = "now_missing" if a.status == "missing" else "new_assignment"
            out.append((a.student_id, kind, a.course, a.name, None, _score(a)))
            continue
        if a.status == "missing" and old["status"] != "missing":
            out.append((a.student_id, "now_missing", a.course, a.name, None, _score(a)))
        elif old["status"] == "missing" and a.status != "missing":
            out.append(
                (a.student_id, "no_longer_missing", a.course, a.name, _score(old), _score(a))
            )
        elif (old["score"], old["grade"]) != (a.score, a.grade) and a.score is not None:
            out.append((a.student_id, "scored", a.course, a.name, _score(old), _score(a)))
    return out


def _score(a: Assignment | dict) -> str | None:
    """'12.5/25 F' style summary of an assignment (model or stored row)."""
    get = a.get if isinstance(a, dict) else lambda k: getattr(a, k)
    score, max_score, grade = get("score"), get("max_score"), get("grade")
    if score is None:
        return None
    text = f"{score:g}/{max_score:g}" if max_score is not None else f"{score:g}"
    return f"{text} {grade}" if grade else text
