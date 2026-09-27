"""What the Skyward client returns: plain records, independent of storage."""

from datetime import date

from pydantic import BaseModel


class Student(BaseModel):
    id: int
    name: str
    school: str = ""
    school_year: str = ""


class Category(BaseModel):
    """A grading category's subtotal within one grading period (e.g. Bellwork)."""

    name: str
    grade: str | None = None
    percent: float | None = None
    points_earned: float | None = None
    points_possible: float | None = None


class TermGrade(BaseModel):
    """A class's grade for one grading period column (GP1, S1, EX1, ...)."""

    term: str
    grade: str | None = None
    percent: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    bucket_id: int | None = None
    categories: list[Category] = []
    assignment_ids: list[int] = []


class Course(BaseModel):
    """A class the student is enrolled in (a Skyward "student section")."""

    student_section_id: int
    student_id: int
    name: str
    course_code: str = ""
    period: str = ""
    teacher: str = ""
    missing_count: int = 0
    grades: list[TermGrade] = []


class Assignment(BaseModel):
    id: int
    student_id: int
    name: str
    course: str
    section_code: str = ""
    teacher: str = ""
    category: str = ""
    due_date: date | None = None
    grade: str | None = None
    score: float | None = None
    max_score: float | None = None
    weight: float | None = None
    class_average: float | None = None
    status: str = "past"  # upcoming | missing | past


class Snapshot(BaseModel):
    """Everything one sync fetched for the account."""

    students: list[Student]
    courses: list[Course]
    assignments: list[Assignment]
