"""Snapshot storage and change detection."""

from datetime import date

import pytest

from app.db import Database
from app.skyward.models import Assignment, Category, Course, Snapshot, Student, TermGrade


def snapshot(gp2="B", gp2_pct=85.0, hw_status="missing", hw_score=0.0, extra=()):
    course = Course(
        student_section_id=10,
        student_id=1,
        name="MATH",
        period="Period 1",
        teacher="TEACHER A",
        missing_count=1 if hw_status == "missing" else 0,
        grades=[
            TermGrade(
                term="GP1",
                grade="A",
                percent=95.0,
                categories=[Category(name="Quiz", percent=95.0)],
            ),
            TermGrade(term="GP2", grade=gp2, percent=gp2_pct),
            TermGrade(term="S1"),
        ],
    )
    assignments = [
        Assignment(id=1, student_id=1, name="Homework 1", course="MATH", due_date=date(2026, 9, 1),
                   score=hw_score, max_score=10, grade="F" if hw_score == 0 else "A", status=hw_status),
        Assignment(id=2, student_id=1, name="Quiz 1", course="MATH", due_date=date(2026, 10, 1),
                   status="upcoming"),
        *extra,
    ]  # fmt: skip
    return Snapshot(
        students=[Student(id=1, name="STUDENT, DEMO")], courses=[course], assignments=assignments
    )


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def save(db, snap):
    run = db.start_run()
    n = db.save_snapshot(run, snap)
    db.finish_run(run, changes=n)
    return n


def test_first_sync_logs_no_changes_but_records_history(db):
    assert save(db, snapshot()) == 0
    course = db.course(10)
    assert [g["term"] for g in course["grades"]] == ["GP1", "GP2", "S1"]
    assert course["grades"][0]["categories"][0]["name"] == "Quiz"
    assert {(h["term"], h["grade"]) for h in course["history"]} == {("GP1", "A"), ("GP2", "B")}


def test_unchanged_sync_logs_nothing(db):
    save(db, snapshot())
    assert save(db, snapshot()) == 0
    assert len(db.course(10)["history"]) == 2


def test_changes_are_detected(db):
    save(db, snapshot())
    new = Assignment(id=3, student_id=1, name="Essay", course="MATH", status="missing")
    save(db, snapshot(gp2="B+", gp2_pct=88.5, hw_status="past", hw_score=9, extra=[new]))
    kinds = {(c["kind"], c["subject"]): (c["old"], c["new"]) for c in db.changes()}
    assert kinds[("grade_changed", "GP2")] == ("B (85.00%)", "B+ (88.50%)")
    assert kinds[("no_longer_missing", "Homework 1")] == ("0/10 F", "9/10 A")
    assert ("now_missing", "Essay") in kinds
    assert len(db.course(10)["history"]) == 3


def test_first_seen_survives_resync(db):
    save(db, snapshot())
    first = db.assignments(1, status="upcoming")[0]["first_seen"]
    save(db, snapshot())
    assert db.assignments(1, status="upcoming")[0]["first_seen"] == first


def test_assignment_filters_and_order(db):
    save(db, snapshot())
    assert [a["name"] for a in db.assignments(1, status="missing")] == ["Homework 1"]
    assert [a["name"] for a in db.assignments(1)] == ["Quiz 1", "Homework 1"]  # newest due first
    assert db.assignments(1, course="SCIENCE") == []


def test_stale_runs_are_failed(db):
    db.start_run()
    db.fail_stale_runs()
    assert db.last_runs(1)[0]["status"] == "error"
