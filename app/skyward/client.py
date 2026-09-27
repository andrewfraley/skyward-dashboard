"""Fetch everything the dashboard shows in one pass: grades and assignments."""

import logging

from app.skyward.models import Assignment, Course, Snapshot, Student
from app.skyward.parse import (
    browse_student_id,
    parse_assignments,
    parse_breakdown_grid,
    parse_breakdown_header,
    parse_grades,
    parse_students,
)
from app.skyward.session import Page, SkywardSession

log = logging.getLogger(__name__)

GRADES_PATH = "/Student/Grading/StudentSection/FamilyAccess"
ASSIGNMENTS_PATH = "/Student/Gradebook/StudentAssignment/FamilyAccessAssignmentList"
DATE_RANGE_PATH = "/Student/Gradebook/StudentAssignment/SetDateRangeModeFamilyAccess"
BREAKDOWN_GRID = "detailsPanel_SegmentedGradeBucketAssignments"

# Grid name prefix -> assignment status. When an assignment shows up in more
# than one grid, the earlier status here wins.
ASSIGNMENT_GRIDS = {
    "StudentMissingAssignmentsFamilyAccess": "missing",
    "StudentUpcomingAssignmentsFamilyAccess": "upcoming",
    "StudentPastAssignmentsFamilyAccess": "past",
}


def fetch_snapshot(session: SkywardSession) -> Snapshot:
    grades_page = session.page(GRADES_PATH)
    students = parse_students(grades_page)
    courses = fetch_courses(session, grades_page, students)
    assignments = fetch_assignments(session)
    return Snapshot(students=students, courses=courses, assignments=assignments)


def _student_grids(page: Page, browse_name: str, students: list[Student]) -> list[tuple[str, int]]:
    """(grid id, student id) for every grid named `browse_name` on the page."""
    fallback = students[0].id if len(students) == 1 else None
    grids = []
    for grid_id, cfg in page.browses.items():
        if cfg.get("browseName") == browse_name:
            student_id = browse_student_id(cfg) or fallback
            if student_id is None:
                log.warning("Skipping grid %s: can't tell which student it belongs to", grid_id)
                continue
            grids.append((grid_id, student_id))
    return grids


def fetch_courses(session: SkywardSession, page: Page, students: list[Student]) -> list[Course]:
    courses = []
    for grid_id, student_id in _student_grids(page, "StudentGrades", students):
        for course, cells in parse_grades(session.get_browse(page, grid_id), student_id):
            by_term = {g.term: g for g in course.grades}
            for cell in cells:
                panel = session.open_panel(page, cell.breakdown_path, cell.attrs)
                header = parse_breakdown_header(panel.html)
                term = by_term[cell.term]
                term.percent = header.get("percent")
                term.start_date = header.get("start_date")
                term.end_date = header.get("end_date")
                course.teacher = course.teacher or header.get("teacher", "")
                if BREAKDOWN_GRID in panel.browses:
                    term.categories, term.assignment_ids = parse_breakdown_grid(
                        session.get_browse(panel, BREAKDOWN_GRID)
                    )
            courses.append(course)
    return courses


def fetch_assignments(session: SkywardSession) -> list[Assignment]:
    """All of this year's assignments, not just the current term's.

    The assignments page filters by a per-user preference, so switch it to
    All Year for the fetch and back to Current Term afterwards, leaving the
    parent's own view of Skyward as it was.
    """
    page = session.page(ASSIGNMENTS_PATH)
    students = parse_students(page)
    _set_date_range(session, page, "AllYear")
    try:
        page = session.page(ASSIGNMENTS_PATH)
        found: dict[int, Assignment] = {}
        for browse_name, status in ASSIGNMENT_GRIDS.items():
            for grid_id, student_id in _student_grids(page, browse_name, students):
                for a in parse_assignments(session.get_browse(page, grid_id), student_id, status):
                    found.setdefault(a.id, a)
        return list(found.values())
    finally:
        _set_date_range(session, page, "Current")


def _set_date_range(session: SkywardSession, page: Page, mode: str) -> None:
    r = session.client.post(
        DATE_RANGE_PATH,
        params={"w": page.w, "p": page.p},
        data={"DateRangeMode": mode},
        headers={
            "X-CSRF-Token": page.csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": page.url,
        },
    )
    r.raise_for_status()
