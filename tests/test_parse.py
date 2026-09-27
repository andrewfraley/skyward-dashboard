"""Parsers against scrubbed live responses (see scripts/capture_fixtures.py)."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.skyward.parse import (
    browse_student_id,
    clean_grade,
    parse_assignments,
    parse_breakdown_grid,
    parse_breakdown_header,
    parse_grades,
    parse_students,
)
from app.skyward.parse import _term_label
from app.skyward.session import Browse, parse_browse_configs, parse_page, parse_register_browse

FIXTURES = Path(__file__).parent / "fixtures"
STUDENT_ID = 100001


def load_browse(name: str) -> Browse:
    d = json.loads((FIXTURES / name).read_text())
    return Browse(html=d["html"], meta=d["meta"])


def load_page(name: str):
    url = "https://skyward.example/Student/Grading/StudentSection/FamilyAccess/General?p=abc&w=def"
    return parse_page(url, (FIXTURES / name).read_text())


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("B minusB-", "B-"),
        ("A plusA+", "A+"),
        ("F", "F"),
        ("", None),
        ("C+Opens Details Panel", "C+"),
    ],
)
def test_clean_grade(raw, expected):
    assert clean_grade(raw) == expected


def test_page_has_csrf_and_window_ids():
    page = load_page("grades_page.html")
    assert page.csrf == "TESTCSRFTOKEN"
    assert (page.p, page.w) == ("abc", "def")


def test_browse_configs_carry_what_getbrowse_needs():
    configs = parse_browse_configs((FIXTURES / "assignments_page.html").read_text())
    names = {c["browseName"] for c in configs.values()}
    assert {
        "StudentUpcomingAssignmentsFamilyAccess",
        "StudentMissingAssignmentsFamilyAccess",
        "StudentPastAssignmentsFamilyAccess",
    } <= names
    cfg = next(
        c for c in configs.values() if c["browseName"] == "StudentMissingAssignmentsFamilyAccess"
    )
    assert cfg["routeModule"] == "Gradebook" and cfg["routeObject"] == "Assignment"
    assert len(cfg["requestDataHash"]) == 64
    assert isinstance(cfg["data"], dict) and "filter" in cfg["data"]
    assert browse_student_id(cfg) == STUDENT_ID


def test_students():
    [student] = parse_students(load_page("grades_page.html"))
    assert student.id == STUDENT_ID
    assert student.name == "STUDENT, DEMO"
    assert student.school and student.school_year


def test_grades():
    courses = parse_grades(load_browse("grades_browse.json"), STUDENT_ID)
    assert len(courses) >= 5
    course, cells = next((c, cells) for c, cells in courses if cells)
    assert course.student_section_id > 0 and course.name and course.period.startswith("Period")
    terms = [g.term for g in course.grades]
    assert terms[:2] == ["GP1", "GP2"] and "S1" in terms
    # Every clickable cell has a grade and a bucket id to open its breakdown.
    for cell in cells:
        assert cell.grade and cell.bucket_id
        assert cell.breakdown_path.endswith(f"/{cell.bucket_id}")
    assert sum(c.missing_count for c, _ in courses) > 0


def test_breakdown_header():
    header = parse_breakdown_header((FIXTURES / "breakdown_panel.html").read_text())
    assert header["grade"]
    assert 0 <= header["percent"] <= 110
    assert header["start_date"] < header["end_date"]
    assert header["teacher"].startswith("TEACHER ")


def test_breakdown_grid():
    categories, assignment_ids = parse_breakdown_grid(load_browse("breakdown_browse.json"))
    assert categories and assignment_ids
    for c in categories:
        assert c.name and c.percent is not None
        assert c.points_possible and c.points_earned is not None


@pytest.mark.parametrize(
    "fixture, status",
    [
        ("StudentMissingAssignmentsFamilyAccess.json", "missing"),
        ("StudentUpcomingAssignmentsFamilyAccess.json", "upcoming"),
        ("StudentPastAssignmentsFamilyAccess.json", "past"),
    ],
)
def test_assignments(fixture, status):
    browse = load_browse(fixture)
    assignments = parse_assignments(browse, STUDENT_ID, status)
    assert len(assignments) == browse.meta["recordCount"]
    assert len({a.id for a in assignments}) == len(assignments)
    for a in assignments:
        assert a.name and a.course and a.status == status
        assert isinstance(a.due_date, date)
        assert a.teacher.startswith("TEACHER ")
    if status == "missing":
        assert all(a.max_score for a in assignments)


def test_term_labels_are_unique():
    labels = ["Course", "Missing", "GP1", "", "GP1", "S1"]
    terms = [_term_label(labels, i) for i in range(2, 7)]
    assert terms == ["GP1", "col3", "GP1 (4)", "S1", "col6"]
    assert len(set(terms)) == len(terms)


def test_register_browse_stops_at_the_end_of_its_object():
    script = 'a.registerBrowse({"recordCount": 2, "x": "})"});\nother({b: 1});'
    assert parse_register_browse({"script": script}) == {"recordCount": 2, "x": "})"}
    assert parse_register_browse({"script": ""}) == {}
