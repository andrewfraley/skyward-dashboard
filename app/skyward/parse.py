"""Turn Skyward pages and grids into models.

Grids arrive as HTML tables. Each row appears twice (an "unlocked" scrolling
copy and a "locked" frozen-column copy), so only unlocked rows are read. Cells
in assignment grids carry a clean `data-field-value`; the grades grid and the
grade breakdown don't, so their text is cleaned up instead.
"""

import re
from datetime import date, datetime

from selectolax.parser import HTMLParser, Node

from app.skyward.models import Assignment, Category, Course, Student, TermGrade
from app.skyward.session import Browse, Page, SkywardError

GRADE_BREAKDOWN_PATH = "/Student/Gradebook/ProgressReport/GradeBucketBreakdownFamilyAccess/{}"


def _rows(html: str) -> list[Node]:
    return [
        tr
        for tr in HTMLParser(html).css("tr")
        if re.search(r"_unlockedRow\d+$", tr.attributes.get("id") or "")
    ]


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node else ""


def _num(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _date(value: str | None) -> date | None:
    """'2026-09-25T00:00:00.0000000' or '09/25/2026' -> date."""
    value = (value or "").strip()
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value[:10])
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def clean_grade(text: str) -> str | None:
    """'B minusB-' (screen-reader text + mark) -> 'B-'; '' -> None."""
    text = re.sub(r"^[A-F] (?:minus|plus)", "", text.strip())
    text = text.replace("Opens Details Panel", "").strip()
    return text or None


def parse_students(page: Page) -> list[Student]:
    """The student tiles in the Family Access header."""
    students = []
    for tile in HTMLParser(page.html).css(".familyAccessHeaderSelectTile[data-studentid]"):
        a = tile.attributes
        label = tile.css_first(".familyAccessHeaderSelectTileLabelDiv")
        name = " ".join(label.text(separator=" ", strip=True).split()) if label else ""
        students.append(
            Student(
                id=int(a["data-studentid"]),
                name=name,
                school=a.get("data-entity-name") or "",
                school_year=a.get("data-entity-year") or "",
            )
        )
    return students


def browse_student_id(cfg: dict) -> int | None:
    """Which student a grid on an ALL STUDENTS page belongs to."""
    for source in (cfg.get("queryParameterData") or {}, cfg.get("data") or {}):
        if source.get("StudentID"):
            return int(source["StudentID"])
    return None


class GradeCell:
    """A grade in the grades grid, with what's needed to open its breakdown."""

    def __init__(self, term: str, grade: str | None, attrs: dict[str, str]):
        self.term = term
        self.grade = grade
        self.attrs = attrs
        self.bucket_id = int(attrs["data-student-grade-bucket-id"])

    @property
    def breakdown_path(self) -> str:
        return GRADE_BREAKDOWN_PATH.format(self.bucket_id)


def parse_grades(browse: Browse, student_id: int) -> list[tuple[Course, list[GradeCell]]]:
    """Classes from the StudentGrades grid, each with its clickable grade cells."""
    doc = HTMLParser(browse.html)
    header = doc.css_first("tr[id$=_unlockedHeaderRow]")
    labels = [_text(td) for td in header.css("td")] if header else []

    _check_complete(browse, "grades")
    result = []
    for tr in _rows(browse.html):
        tds = tr.css("td")
        link = tr.css_first("a[data-studentsectionid]")
        if link is None:
            continue
        a = link.attributes
        spans = [s.text(strip=True) for s in link.css("span")]
        missing = _text(tds[1]) if len(tds) > 1 else ""
        course = Course(
            student_section_id=int(a["data-studentsectionid"]),
            student_id=int(a.get("data-studentid") or student_id),
            name=a.get("data-coursedescription") or (spans[0] if spans else ""),
            course_code=a.get("data-coursecode") or "",
            period=spans[1] if len(spans) > 1 else "",
            missing_count=int(missing) if missing.isdigit() else 0,
        )
        cells = []
        for i, td in enumerate(tds[2:], start=2):
            term = _term_label(labels, i)
            grade = clean_grade(td.text(strip=True))
            course.grades.append(TermGrade(term=term, grade=grade))
            if grade and td.attributes.get("data-student-grade-bucket-id"):
                course.grades[-1].bucket_id = int(td.attributes["data-student-grade-bucket-id"])
                cells.append(GradeCell(term, grade, {k: v or "" for k, v in td.attributes.items()}))
        result.append((course, cells))
    return result


def _term_label(labels: list[str], i: int) -> str:
    """Column i's header, made unique: a term is part of term_grades' key."""
    label = labels[i] if i < len(labels) and labels[i] else f"col{i}"
    if label in labels[:i]:
        label = f"{label} ({i})"
    return label


def _check_complete(browse: Browse, what: str) -> None:
    """Refuse a grid with fewer rows than Skyward says it has.

    Saving part of a grid would make the missing rows look deleted, so a
    Skyward change that starts paging grids should fail loudly instead. An
    empty grid still reports a recordCount of 1 (its "no records" row) but no
    primaryKeys, so the count only means something when there are keys.
    """
    keys = browse.meta.get("primaryKeys") or []
    expected = browse.meta.get("recordCount")
    if keys and isinstance(expected, int) and expected > len(keys):
        raise SkywardError(f"The {what} grid has {expected} rows but only {len(keys)} arrived")


def parse_breakdown_header(html: str) -> dict:
    """Teacher, term dates, letter grade and percent from a grade breakdown panel."""
    doc = HTMLParser(html)
    info = doc.css(
        ".SegmentedAssignmentsReferenceInformation.white .SegmentedAssignmentsInformationCell"
    )
    out: dict = {}
    if info:
        teacher = info[0].css_first("a[data-click-action='progressreport.staffPopup'] .anchorText")
        out["teacher"] = _text(teacher)
    if len(info) > 1:
        labels = [s.text(strip=True) for s in info[1].css(".decorativeLabel")]
        if len(labels) > 1 and "-" in labels[1]:
            start, _, end = labels[1].partition("-")
            out["start_date"], out["end_date"] = _date(start), _date(end)
    out["grade"] = clean_grade(_text(doc.css_first(".grademarkWithPercentage .gradeMarkLabel")))
    out["percent"] = _num(_text(doc.css_first(".grademarkWithPercentage .header")))
    return out


def parse_breakdown_grid(browse: Browse) -> tuple[list[Category], list[int]]:
    """Category subtotals and the assignment ids in a grade breakdown grid.

    Category rows are `segmentedBrowseParentRowN`; assignment rows link to an
    assignment popup carrying `data-assignment-id`.
    """
    categories, assignment_ids = [], []
    for tr in HTMLParser(browse.html).css("tr"):
        row_id = tr.attributes.get("id") or ""
        if not re.search(r"_unlockedRow\d+$", row_id):
            continue
        texts = [td.text(strip=True) for td in tr.css("td")]
        if "segmentedBrowseParentRow" in (tr.attributes.get("class") or ""):
            earned, _, possible = (texts[5] if len(texts) > 5 else "").partition("/")
            categories.append(
                Category(
                    name=texts[1],
                    grade=clean_grade(texts[3]) if len(texts) > 3 else None,
                    percent=_num(texts[4]) if len(texts) > 4 else None,
                    points_earned=_num(earned),
                    points_possible=_num(possible),
                )
            )
            continue
        link = tr.css_first("a[data-assignment-id]")
        if link is not None:
            assignment_ids.append(int(link.attributes["data-assignment-id"]))
    return categories, assignment_ids


# Assignment grid columns, by the field name Skyward reports for them.
_ASSIGNMENT_FIELDS = {
    "DueDate": "due_date",
    "Name": "name",
    "Section.SpecifiedStudentSection.CourseOrTransferDescription": "course",
    "Section.Code": "section_code",
    "Section.StaffCurrentStoredPrimary.FamilyStudentAccessStaffNameToUse": "teacher",
    "Category.Description": "category",
    "StudentAssignment.CecsSafeGradeMarkCodeToUse": "grade",
    "StudentAssignment.CecsSafeStudentOnlineAssignmentDisplayPointsEarned": "score",
    "CecsSafeMaxScoreDisplay": "max_score",
    "CecsSafeWeightDisplay": "weight",
    "CecsSafeAveragePercentDisplay": "class_average",
}


def parse_assignments(browse: Browse, student_id: int, status: str) -> list[Assignment]:
    """Rows of an upcoming/missing/past assignments grid.

    Row n's assignment id is primaryKeys[n]. Cells are matched to fields via
    each cell's data-column index into columnFieldNames.
    """
    _check_complete(browse, f"{status} assignments")
    fields = browse.fields
    keys = browse.meta.get("primaryKeys") or []
    if len(keys) != len(_rows(browse.html)):
        # Row n's id is keys[n]; a stray row would shift every id after it.
        raise SkywardError(
            f"The {status} assignments grid has {len(_rows(browse.html))} rows "
            f"but {len(keys)} ids"
        )
    out = []
    for n, tr in enumerate(_rows(browse.html)):
        if n >= len(keys):
            break
        values: dict[str, str] = {}
        for td in tr.css("td[data-column]"):
            idx = int(td.attributes["data-column"])
            field = _ASSIGNMENT_FIELDS.get(fields[idx] if idx < len(fields) else None)
            if field:
                raw = td.attributes.get("data-field-value")
                values[field] = raw if raw is not None else td.text(strip=True)
        out.append(
            Assignment(
                id=int(keys[n]),
                student_id=student_id,
                name=values.get("name", ""),
                course=values.get("course", ""),
                section_code=values.get("section_code", ""),
                teacher=values.get("teacher", ""),
                category=values.get("category", ""),
                due_date=_date(values.get("due_date")),
                grade=clean_grade(values.get("grade", "")),
                score=_num(values.get("score")),
                max_score=_num(values.get("max_score")),
                weight=_num(values.get("weight")),
                class_average=_num(values.get("class_average")),
                status=status,
            )
        )
    return out
