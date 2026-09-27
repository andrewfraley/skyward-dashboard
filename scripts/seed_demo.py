"""Seed a made-up account for screenshots and UI checks: never real data.

Simulates five weeks of twice-weekly syncs of one invented student ("DOE, JANE Q" at
EXAMPLE MIDDLE SCHOOL) with invented classes, teachers and assignments, so the
grade trends and the changes feed have something to show. Grades are computed
from the assignments as they stood on each sync day, so everything agrees.
Dates are relative to today; the random seed is fixed, so runs are repeatable.

Writes recordings/demo/skyward.db (gitignored), replacing it. Never touches data/.

    uv run python scripts/seed_demo.py
"""

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.db as dbmod  # noqa: E402
from app.skyward.models import (  # noqa: E402
    Assignment,
    Category,
    Course,
    Snapshot,
    Student,
    TermGrade,
)

DEMO_DIR = ROOT / "recordings" / "demo"
DEMO_STUDENT = Student(
    id=100001, name="DOE, JANE Q", school="EXAMPLE MIDDLE SCHOOL", school_year="2026-2027"
)

# name, period, teacher, how well she does (0-1), categories with point sizes, assignment titles
COURSES = [
    ("ENGLISH 8", "Period 1 - Semester 1", "ALEX MORGAN", 0.93,
     [("Classwork", 10), ("Essays", 50), ("Quizzes", 20)],
     ["Reading Response: Ch. 1-3", "Vocabulary Quiz 1", "Personal Narrative Draft",
      "Reading Response: Ch. 4-6", "Vocabulary Quiz 2", "Poetry Analysis",
      "Personal Narrative Final", "Reading Response: Ch. 7-9", "Vocabulary Quiz 3",
      "Book Talk Slides"]),
    ("ALGEBRA I", "Period 2 - Semester 1", "PRIYA SHAH", 0.85,
     [("Homework", 20), ("Quizzes", 25), ("Tests", 100)],
     ["1.1 Expressions Practice", "1.2 Order of Operations", "Unit 1 Quiz", "1.4 Solving Equations",
      "1.5 Literal Equations", "Unit 1 Test", "2.1 Inequalities Practice", "2.2 Compound Inequalities",
      "Unit 2 Quiz", "2.4 Absolute Value", "Unit 2 Test"]),
    ("EARTH SCIENCE", "Period 3 - Semester 1", "SAM OKAFOR", 0.86,
     [("Labs", 30), ("Homework", 10), ("Tests", 80)],
     ["Rock Cycle Lab", "Minerals Worksheet", "Plate Tectonics Reading", "Earthquake Lab",
      "Unit 1 Test", "Weathering Lab", "Erosion Worksheet", "Soil Profile Project"]),
    ("US HISTORY", "Period 4 - Semester 1", "DANA WHITFIELD", 0.8,
     [("Classwork", 15), ("Projects", 60), ("Quizzes", 20)],
     ["Colonies Map", "Primary Source Analysis", "Chapter 2 Quiz", "Revolution Timeline",
      "Declaration Close Reading", "Chapter 3 Quiz", "Founders Debate Prep", "Constitution Project"]),
    ("SPANISH I", "Period 5 - Semester 1", "RENATA ALVES", 0.9,
     [("Practice", 10), ("Quizzes", 20), ("Speaking", 25)],
     ["Greetings Practice", "Numbers Quiz", "Classroom Objects", "Speaking Check 1",
      "Verbs -ar Practice", "Vocab Quiz: Family", "Speaking Check 2"]),
    ("CONCERT CHOIR-II", "Period 6 - Semester 1", "JORDAN BELL", 0.98,
     [("Participation", 20), ("Performance", 50)],
     ["Week 1 Participation", "Sight Reading Check", "Week 3 Participation",
      "Section Rehearsal", "Fall Concert"]),
    ("FITNESS & SPORT", "Period 7 - Semester 1", "CASEY NGUYEN", 0.95,
     [("Participation", 10), ("Fitness", 20)],
     ["Week 1 Participation", "Mile Run", "Week 2 Participation", "Volleyball Skills",
      "Week 3 Participation", "Fitness Log"]),
]  # fmt: skip

# (course, assignment index) never turned in: small classwork/homework items, as in real
# life. One of the history ones is turned in late, so the changes feed shows that too.
MISSING = [("US HISTORY", 3), ("US HISTORY", 6), ("EARTH SCIENCE", 1), ("ALGEBRA I", 3),
           ("ENGLISH 8", 3), ("SPANISH I", 3)]  # fmt: skip

SCALE = [(97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"), (77, "C+"),
         (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-"), (0, "F")]  # fmt: skip


def letter(percent: float | None) -> str | None:
    if percent is None:
        return None
    return next(mark for floor, mark in SCALE if percent >= floor)


def plan_assignments(today: date, rng: random.Random) -> list[dict]:
    """Every assignment's fixed facts: due date, points, final score or missing."""
    plans, next_id = [], 5001
    for c_index, (course, _, teacher, skill, categories, titles) in enumerate(COURSES):
        # Spread due dates from ~6 weeks ago to ~10 days ahead.
        for i, title in enumerate(titles):
            due = today - timedelta(days=44) + timedelta(days=round(i * 54 / (len(titles) - 1)))
            due += timedelta(days=c_index % 3)
            category, points = categories[i % len(categories)]
            missing = (course, i) in MISSING and due < today
            drawn = min(1.0, rng.gauss(skill, 0.06)) * points  # always drawn: stable scores
            earned = 0.0 if missing else drawn
            plans.append(
                dict(id=next_id, course=course, teacher=teacher, name=title, due=due,
                     category=category, points=float(points), missing=missing,
                     earned=round(max(0.0, earned) * 2) / 2,
                     average=round(min(100, rng.gauss(84, 5)), 2))
            )  # fmt: skip
            next_id += 1
    # One missing assignment gets turned in late, so the feed shows that too.
    late = next(p for p in plans if p["missing"] and p["course"] == "US HISTORY")
    late["turned_in_after"] = late["due"] + timedelta(days=9)
    return plans


def snapshot_on(day: date, plans: list[dict], today: date) -> Snapshot:
    gp1 = (today - timedelta(days=50), today - timedelta(days=21))
    gp2 = (today - timedelta(days=20), today + timedelta(days=30))
    visible = [p for p in plans if p["due"] <= day + timedelta(days=10)]  # posted ~10 days ahead

    def state(p):
        if p["due"] > day:
            return "upcoming", None
        if p["missing"] and not (p.get("turned_in_after") and day >= p["turned_in_after"]):
            return "missing", 0.0
        if p.get("turned_in_after"):
            return "past", round(p["points"] * 0.7 * 2) / 2
        return "past", p["earned"]

    assignments, courses = [], []
    for index, (course, period, teacher, *_rest) in enumerate(COURSES):
        mine = [p for p in visible if p["course"] == course]
        grades = []
        for term, (start, end) in (("GP1", gp1), ("GP2", gp2), ("S1", (gp1[0], gp2[1]))):
            if start > day:
                grades.append(TermGrade(term=term))
                continue
            scored = [(p, state(p)[1]) for p in mine if start <= p["due"] <= min(end, day)]
            scored = [(p, s) for p, s in scored if s is not None]
            if not scored:
                grades.append(TermGrade(term=term, start_date=start, end_date=end))
                continue
            cats = []
            for name in dict.fromkeys(p["category"] for p, _ in scored):
                earned = sum(s for p, s in scored if p["category"] == name)
                possible = sum(p["points"] for p, _ in scored if p["category"] == name)
                pct = round(100 * earned / possible, 2)
                cats.append(Category(name=name.upper(), grade=letter(pct), percent=pct,
                                     points_earned=earned, points_possible=possible))  # fmt: skip
            pct = round(100 * sum(s for _, s in scored) / sum(p["points"] for p, _ in scored), 2)
            grades.append(
                TermGrade(term=term, grade=letter(pct), percent=pct, start_date=start,
                          end_date=end, categories=cats if term != "S1" else [],
                          assignment_ids=[p["id"] for p, _ in scored])
            )  # fmt: skip
        missing = [p for p in mine if state(p)[0] == "missing"]
        courses.append(
            Course(student_section_id=2001 + index, student_id=DEMO_STUDENT.id, name=course,
                   course_code=f"DEMO{index + 1}", period=period, teacher=teacher,
                   missing_count=len(missing), grades=grades)
        )  # fmt: skip
        for p in mine:
            status, score = state(p)
            pct = None if score is None else 100 * score / p["points"]
            assignments.append(
                Assignment(id=p["id"], student_id=DEMO_STUDENT.id, name=p["name"], course=course,
                           section_code=f"{index + 1:02d}", teacher=teacher,
                           category=p["category"], due_date=p["due"], grade=letter(pct),
                           score=score, max_score=p["points"], weight=1.0,
                           class_average=p["average"] if status == "past" else None,
                           status=status)
            )  # fmt: skip
    return Snapshot(students=[DEMO_STUDENT], courses=courses, assignments=assignments)


def main() -> None:
    today = date.today()
    rng = random.Random(20260927)
    plans = plan_assignments(today, rng)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DEMO_DIR / "skyward.db"
    db_path.unlink(missing_ok=True)
    db = dbmod.Database(db_path)

    real_now = dbmod.now
    try:
        # Twice a week for five weeks; the last one two hours ago.
        for days_ago in (35, 31, 28, 24, 21, 17, 14, 10, 7, 3, 0):
            day = today - timedelta(days=days_ago)
            stamp = datetime.combine(day, time(15, 0), tzinfo=timezone.utc)
            if days_ago == 0:
                stamp = datetime.now(timezone.utc) - timedelta(hours=2)
            dbmod.now = lambda stamp=stamp: stamp.isoformat(timespec="seconds")
            run = db.start_run()
            changes = db.save_snapshot(run, snapshot_on(day, plans, today))
            db.finish_run(run, changes=changes)
    finally:
        dbmod.now = real_now

    snap = snapshot_on(today, plans, today)
    by_status = {
        s: sum(a.status == s for a in snap.assignments) for s in ("missing", "upcoming", "past")
    }
    print(f"Seeded {db_path.relative_to(ROOT)}: {len(snap.courses)} classes, {by_status}, "
          f"{len(db.changes(limit=500))} changes")  # fmt: skip


if __name__ == "__main__":
    main()
