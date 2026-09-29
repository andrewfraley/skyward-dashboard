"""The e-paper display payload, and its ports of frontend/src/grades.js.

The helper cases repeat grades.test.js so the display and the web UI agree.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app import display
from app.db import Database
from app.skyward.models import Assignment, Course, Snapshot, Student, TermGrade
from tests.test_db import save

TODAY = "2026-09-27"

GRADES = [
    {"term": "GP1", "grade": "D+", "percent": 69.4, "start_date": "2026-08-05",
     "end_date": "2026-09-18"},
    {"term": "GP2", "grade": "B+", "percent": 86.7, "start_date": "2026-09-21",
     "end_date": "2026-10-30"},
    {"term": "GP3", "grade": None},
    {"term": "S1", "grade": "C-", "percent": 71.6},
]  # fmt: skip


def test_current_term():
    assert display.current_term(GRADES, "2026-09-27")["term"] == "GP2"
    assert display.current_term(GRADES, "2026-09-01")["term"] == "GP1"
    assert display.current_term(GRADES, "2026-12-01")["term"] == "GP2"
    assert display.current_term([{"term": "S1", "grade": "A"}], TODAY) is None
    assert display.current_term([], TODAY) is None


def test_grading_period():
    courses = [{"grades": GRADES}, {"grades": [{**GRADES[1], "grade": None}]}]
    ungraded = [{"grades": [{**g, "grade": None} for g in GRADES]}]
    assert display.grading_period(courses, "2026-09-27")["term"] == "GP2"
    assert display.grading_period(ungraded, "2026-09-01")["term"] == "GP1"
    assert display.grading_period(courses, "2026-09-19")["term"] == "GP1"
    assert display.grading_period(courses, "2026-12-01")["term"] == "GP2"
    assert display.grading_period(courses, "2026-07-01") is None
    assert display.grading_period([{"grades": [{"term": "GP1", "grade": "A"}]}], TODAY) is None


def test_in_period():
    gp2 = {"term": "GP2", "start_date": "2026-09-21", "end_date": "2026-10-30"}
    assert display.in_period({"due_date": "2026-09-21"}, gp2)
    assert display.in_period({"due_date": "2026-10-30"}, gp2)
    assert not display.in_period({"due_date": "2026-09-18"}, gp2)
    assert not display.in_period({"due_date": "2026-11-02"}, gp2)
    assert display.in_period({"due_date": None}, gp2)
    assert display.in_period({"due_date": "2026-08-14"}, None)


def test_struggling_and_bands():
    assert [display.is_struggling(g) for g in ("C-", "D+", "F")] == [True] * 3
    assert [display.is_struggling(g) for g in ("C", "B-")] == [False] * 2
    assert [display.is_struggling(g) for g in ("c-", " C- ", None)] == [True, True, False]
    assert [display.grade_band(g) for g in ("b+", " A- ", "F")] == ["B", "A", "F"]
    assert [display.grade_band(g) for g in ("P", "I", "93", "", None)] == [None] * 5


def test_percent_and_due_labels():
    assert display.format_percent(None) == ""
    assert display.format_percent(0) == "0.0%"
    assert display.format_percent(86.66) == "86.7%"
    assert display.format_percent(70.25) == "70.3%"  # toFixed rounds half up
    assert display.due_label("2026-09-27", TODAY) == "Today"
    assert display.due_label("2026-09-28", TODAY) == "Tomorrow"
    assert display.due_label("2026-09-30", TODAY) == "In 3 days"
    assert display.due_label("2026-09-26", TODAY) == "Yesterday"
    assert display.due_label("2026-09-24", TODAY) == "3 days ago"
    assert display.due_label("2026-09-21", TODAY) == "6 days ago"
    assert display.due_label("2026-10-20", TODAY) == "Tue Oct 20"
    assert display.due_label(None, TODAY) == "No due date"
    assert display.days_until("2027-01-01", TODAY) == 96
    assert display.days_until("2026-11-02", "2026-10-31") == 2


def test_names():
    assert display.first_name("STUDENT, DEMO") == "Demo"
    assert display.first_name("LAST, FIRST MIDDLE") == "First"
    assert display.first_name("DEMO") == "Demo"
    cases = {
        "ENGLISH 8 AP-I": "English 8 AP-I",
        "ART OF THE STARS & SEAS": "Art of the Stars & Seas",
        "SEMI-CONDUCTORS 9-I": "Semi-Conductors 9-I",
        "CONCERT CHOIR-II": "Concert Choir-II",
        "US HISTORY": "US History",
        "TEACHER A": "Teacher A",
        "HISTORY OF ART": "History of Art",
        "FORM ASSESSMENTS": "Form Assessments",
    }
    assert {name: display.course_title(name) for name in cases} == cases


def test_fold_keeps_to_printable_ascii():
    assert display.fold("“Café” – part two…") == '"Cafe" - part two...'
    assert display.fold("Rocket \U0001f680 lab") == "Rocket lab"
    assert display.fold("x" * 100, limit=10) == "xxxxxxx..."
    assert display.fold(None) == ""


def test_sleep_follows_the_sync_schedule_within_bounds():
    now = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)
    assert display.sleep_seconds(now + timedelta(hours=2), now) == 2 * 3600 + 600
    # Overnight: the next sync is tomorrow morning, capped at 12 hours.
    assert display.sleep_seconds(now + timedelta(hours=20), now) == 12 * 3600
    # Just before a sync, or with none scheduled.
    assert display.sleep_seconds(now - timedelta(minutes=9), now) == 15 * 60
    assert display.sleep_seconds(None, now) == 12 * 3600


def snapshot(missing=1, upcoming_due=date(2026, 9, 28), gp2="C-"):
    course = Course(
        student_section_id=10,
        student_id=1,
        name="CONCERT CHOIR-II",
        grades=[
            TermGrade(term="GP1", grade="A", percent=95.0, start_date=date(2026, 8, 5),
                      end_date=date(2026, 9, 18)),
            TermGrade(term="GP2", grade=gp2, percent=70.25, start_date=date(2026, 9, 21),
                      end_date=date(2026, 10, 30)),
        ],
    )  # fmt: skip
    assignments = [
        Assignment(id=100 + i, student_id=1, name=f"ASSIGNMENT {i:03}", course="CONCERT CHOIR-II",
                   due_date=date(2026, 9, 22), status="missing")
        for i in range(missing)
    ] + [
        # Missing, but in the last grading period: not on the display.
        Assignment(id=1, student_id=1, name="ASSIGNMENT OLD", course="CONCERT CHOIR-II",
                   due_date=date(2026, 9, 1), status="missing"),
        Assignment(id=2, student_id=1, name="ASSIGNMENT “NEXT”", course="CONCERT CHOIR-II",
                   due_date=upcoming_due, status="upcoming"),
    ]  # fmt: skip
    return Snapshot(
        students=[Student(id=1, name="STUDENT, DEMO")], courses=[course], assignments=assignments
    )


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    save(database, snapshot())
    return database


NOW = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)


def test_payload(db):
    body = display.build(db, now=NOW, next_run=NOW + timedelta(hours=3))
    assert body["v"] == 1 and body["sleep_seconds"] == 3 * 3600 + 600
    assert body["sync_error"] is None and body["stale"] is False
    [student] = body["students"]
    assert student["name"] == "Demo" and student["grading_period"] == "GP2"
    assert student["grades"] == [
        {"course": "Concert Choir-II", "letter": "C-", "percent": "70.3%", "struggling": True,
         "missing": 1}
    ]  # fmt: skip
    assert student["missing"] == {
        "count": 1,
        "items": [{"course": "Concert Choir-II", "title": "ASSIGNMENT 000", "due": "5 days ago",
                   "date": "Tue Sep 22"}],
        "more": 0,
    }  # fmt: skip
    assert student["upcoming"]["items"][0]["title"] == 'ASSIGNMENT "NEXT"'
    assert student["upcoming"]["items"][0]["due"] == "Tomorrow"
    assert student["upcoming"]["due_this_week"] == 1


def test_work_due_today_counts_as_due_this_week(tmp_path):
    database = Database(tmp_path / "t.db")
    save(database, snapshot(upcoming_due=date(2026, 9, 27)))
    [student] = display.build(database, now=NOW, next_run=None)["students"]
    assert student["upcoming"]["due_this_week"] == 1
    assert student["upcoming"]["items"][0]["due"] == "Today"


def test_lists_are_capped(tmp_path):
    database = Database(tmp_path / "t.db")
    save(database, snapshot(missing=20))
    missing = display.build(database, now=NOW, next_run=None)["students"][0]["missing"]
    assert missing["count"] == 20 and len(missing["items"]) == 12 and missing["more"] == 8


def test_hash_ignores_the_time_of_day_but_not_the_content(db):
    first = display.build(db, now=NOW, next_run=None)
    save(db, snapshot())  # another sync, nothing changed
    later = display.build(db, now=NOW + timedelta(hours=3), next_run=None)
    assert later["hash"] == first["hash"]
    save(db, snapshot(gp2="C"))
    assert display.build(db, now=NOW, next_run=None)["hash"] != first["hash"]


def finished_at(db, when: datetime):
    with db.connect() as conn:
        conn.execute("UPDATE sync_runs SET finished_at = ?", (when.isoformat(),))


def test_failed_and_stale_syncs_are_flagged(db):
    finished_at(db, NOW - timedelta(hours=1))
    body = display.build(db, now=NOW, next_run=None)
    assert body["updated"] == "Sun Sep 27" and body["stale"] is False
    run = db.start_run()
    db.finish_run(run, error="boom")
    assert display.build(db, now=NOW, next_run=None)["sync_error"] == "Last update failed"
    assert display.build(db, now=NOW, next_run=None, paused=True)["sync_error"] == (
        "Skyward sign-in rejected"
    )
    finished_at(db, NOW - timedelta(days=2))
    assert display.build(db, now=NOW, next_run=None)["stale"] is True


def test_updated_is_the_local_date(db):
    # 01:00 UTC on the 28th is still the 27th in a zone behind UTC.
    finished_at(db, datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc))
    behind = timezone(timedelta(hours=-6))
    now = datetime(2026, 9, 27, 20, 0, tzinfo=behind)
    assert display.build(db, now=now, next_run=None)["updated"] == "Sun Sep 27"


def test_empty_cache(tmp_path):
    body = display.build(Database(tmp_path / "t.db"), now=NOW, next_run=None)
    assert body["students"] == [] and body["stale"] is True and body["updated"] == ""


def test_clock():
    assert display.clock(datetime(2026, 9, 28, 9, 2)) == "9:02 AM"
    assert display.clock(datetime(2026, 9, 28, 0, 5)) == "12:05 AM"
    assert display.clock(datetime(2026, 9, 28, 12, 0)) == "12:00 PM"
    assert display.clock(datetime(2026, 9, 28, 15, 30)) == "3:30 PM"


def test_changed_is_the_last_sync_that_changed_something(db):
    first = datetime(2026, 9, 27, 13, 2, tzinfo=timezone.utc)
    finished_at(db, first)  # the seeded first sync
    utc = timezone.utc
    assert (
        display.build(db, now=NOW.astimezone(utc), next_run=None)["changed"]
        == "Sun Sep 27, 1:02 PM"
    )
    before = display.build(db, now=NOW, next_run=None)

    # A sync that changes nothing leaves it, and the hash, alone.
    save(db, snapshot())
    with db.connect() as conn:
        conn.execute(
            "UPDATE sync_runs SET finished_at = ? WHERE id = (SELECT MAX(id) FROM sync_runs)",
            ((first + timedelta(hours=3)).isoformat(),),
        )
    after = display.build(db, now=NOW, next_run=None)
    assert after["changed"] == before["changed"] and after["hash"] == before["hash"]

    # One that changes a grade moves it.
    save(db, snapshot(gp2="C"))
    with db.connect() as conn:
        conn.execute(
            "UPDATE sync_runs SET finished_at = ? WHERE id = (SELECT MAX(id) FROM sync_runs)",
            ((first + timedelta(hours=6)).isoformat(),),
        )
    assert display.build(db, now=NOW, next_run=None)["changed"] == "Sun Sep 27, 7:02 PM"
