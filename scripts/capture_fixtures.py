"""Capture live Skyward responses as scrubbed test fixtures in tests/fixtures/.

Logs in with .env credentials, saves one of each response the parsers read,
and replaces everything identifying with stand-ins:

- student, parent and teacher names; school and district names; the host
- course and assignment titles (they can name the school, district or state)
- every number of 5+ digits (student, enrollment, grade-bucket, assignment,
  media ids, ...) via one consistent mapping, so ids still line up across files
- security hashes, CSRF tokens, window/page guids

It finishes by running scripts/check_pii.py over the result and refuses to
leave fixtures behind if anything is flagged. Review the diff before committing.

    uv run python scripts/capture_fixtures.py [--keep]   # --keep: leave flagged files to debug
"""

import itertools
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from check_pii import escapings  # noqa: E402  (scripts/ is on sys.path when run directly)
from app.skyward import client  # noqa: E402
from app.skyward.parse import (  # noqa: E402
    parse_assignments,
    parse_breakdown_header,
    parse_grades,
    parse_students,
)
from app.skyward.session import Browse, SkywardSession  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures"
FAKE_STUDENT_ID = "100001"
FAKE_STUDENT_NAME = "STUDENT, DEMO"
# Any further students on the account: STUDENT, DEMO B / 100002, and so on.
FAKE_SCHOOL = "EXAMPLE MIDDLE SCHOOL"
FAKE_HOST = "skyward.example.org"


class Scrubber:
    def __init__(self, base_url: str, students: list[tuple[str, str]], schools: list[str]):
        """`students`: (id, "LAST, GIVEN") for every student on the account."""
        self.words: dict[str, str] = {}
        self.numbers: dict[str, str] = {}
        for i, (student_id, student_name) in enumerate(students):
            suffix = "" if i == 0 else f" {chr(ord('A') + i)}"
            self.numbers[student_id] = str(int(FAKE_STUDENT_ID) + i)
            # Replaced longest first, so the full name goes before its parts.
            # Every given name (first and any middle ones, together or alone)
            # becomes DEMO.
            last, _, given = student_name.partition(",")
            self._add(student_name, FAKE_STUDENT_NAME + suffix)
            self._add(last.strip(), "STUDENT")
            if given.strip():
                self._add(given.strip(), "DEMO" + suffix)
                for part in given.split():
                    self._add(part, "DEMO" + suffix)
        for school in schools:
            self._add(school, FAKE_SCHOOL)
        self.host = urlsplit(base_url).hostname or ""
        self._next_number = itertools.count(900001)
        self.teacher_names: dict[str, str] = {}  # real name -> TEACHER X
        self.teachers: dict[str, str] = {}  # every escaping of each -> TEACHER X

    def _add(self, real: str, fake: str) -> None:
        for form in escapings(real):
            self.words.setdefault(form, fake)

    def add_teacher(self, name: str) -> None:
        if name and name not in self.teacher_names:
            fake = f"TEACHER {chr(ord('A') + len(self.teacher_names))}"
            self.teacher_names[name] = fake
            for form in escapings(name):
                self.teachers.setdefault(form, fake)

    def add_title(self, real: str, fake: str) -> None:
        """A course or assignment name, in every escaping it can appear in."""
        self._add(real, fake)

    def _number(self, m: re.Match) -> str:
        n = m.group(0)
        if set(n) == {"0"}:
            return n  # zero padding in timestamps, not an id
        if n not in self.numbers:
            self.numbers[n] = str(next(self._next_number))
        return self.numbers[n]

    def __call__(self, text: str) -> str:
        replacements = {**self.teachers, **self.words}
        for real in sorted(replacements, key=len, reverse=True):
            pattern = rf"(?<!\w){re.escape(real)}(?!\w)"
            text = re.sub(pattern, replacements[real], text, flags=re.IGNORECASE)
        if self.host:
            text = re.sub(re.escape(self.host), FAKE_HOST, text, flags=re.IGNORECASE)
        text = re.sub(  # the signed-in parent's name in the header
            r'(<p class="utilitiesButtonMain__text--username">)[^<]*', r"\1PARENT", text
        )
        text = re.sub(  # the district's name in the banner
            r'(<p class="environmentPurpose__text">)[^<]*', r"\1Example School District", text
        )
        text = re.sub(r"(?<![0-9A-Fa-f])[0-9A-F]{64}(?![0-9A-Fa-f])", "0" * 64, text)  # hashes
        text = re.sub(r"(sessionGuidHash=')[^']+", r"\1TESTCSRFTOKEN", text)
        text = re.sub(r"(mediaVerificationToken=)[0-9A-Fa-f]+", r"\1X", text)
        text = re.sub(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", "f" * 32, text)  # guids
        # ids, even glued to text as in element ids like "StudentGrades-123456Label"
        text = re.sub(r"(?<![0-9.])\d{5,}(?!\d)", self._number, text)
        return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}
    settings = load_settings()
    if not settings.has_credentials:
        sys.exit("SKYWARD_BASE_URL, SKYWARD_USER and SKYWARD_PASS must be set in .env")
    base_url, user, password = settings.base_url, settings.username, settings.password
    # The app's saved cookies, so this isn't another new-device sign-in email.
    with SkywardSession(base_url, user, password, cookie_file=settings.cookie_path) as s:
        grades_page = s.page(client.GRADES_PATH)
        students = parse_students(grades_page)
        student = students[0]
        scrub = Scrubber(
            base_url, [(str(x.id), x.name) for x in students], [x.school for x in students]
        )

        grid_id = next(
            k for k, v in grades_page.browses.items() if v.get("browseName") == "StudentGrades"
        )
        grades = s.get_browse(grades_page, grid_id)
        saved["grades_page.html"] = grades_page.html
        saved["grades_browse.json"] = json.dumps({"html": grades.html, "meta": grades.meta})

        course, cells = next((c, cells) for c, cells in parse_grades(grades, student.id) if cells)
        panel = s.open_panel(grades_page, cells[0].breakdown_path, cells[0].attrs)
        breakdown = s.get_browse(panel, client.BREAKDOWN_GRID)
        saved["breakdown_panel.html"] = panel.html
        saved["breakdown_browse.json"] = json.dumps(
            {"html": breakdown.html, "meta": breakdown.meta}
        )

        page = s.page(client.ASSIGNMENTS_PATH)
        client._set_date_range(s, page, "AllYear")
        try:
            page = s.page(client.ASSIGNMENTS_PATH)
            saved["assignments_page.html"] = page.html
            for name in client.ASSIGNMENT_GRIDS:
                gid = next(k for k, v in page.browses.items() if v.get("browseName") == name)
                b = s.get_browse(page, gid)
                saved[f"{name}.json"] = json.dumps({"html": b.html, "meta": b.meta})
        finally:
            client._set_date_range(s, page, "Current")

    # Teacher, course and assignment names, from the parsed data, so each gets
    # one stand-in. Titles can reveal the school or district, so none are kept.
    scrub.add_teacher(parse_breakdown_header(saved["breakdown_panel.html"]).get("teacher", ""))
    courses = [c.name for c, _ in parse_grades(grades, student.id)]
    assignments = []
    for name in client.ASSIGNMENT_GRIDS:
        d = json.loads(saved[f"{name}.json"])
        for a in parse_assignments(Browse(d["html"], d["meta"]), student.id, "past"):
            scrub.add_teacher(a.teacher)
            courses.append(a.course)
            assignments.append(a.name)
    for i, course_name in enumerate(dict.fromkeys(courses)):
        scrub.add_title(course_name, f"COURSE {chr(ord('A') + i)}")
    for i, assignment_name in enumerate(dict.fromkeys(assignments), 1):
        scrub.add_title(assignment_name, f"ASSIGNMENT {i:03d}")

    for filename, content in saved.items():
        (OUT / filename).write_text(scrub(content), encoding="utf-8")
        print(f"wrote tests/fixtures/{filename}")
    print(f"scrubbed {len(scrub.teacher_names)} teacher names, {len(scrub.numbers)} ids")

    check = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_pii.py")], cwd=ROOT)
    if check.returncode and "--keep" not in sys.argv:
        for filename in saved:
            (OUT / filename).unlink(missing_ok=True)
        sys.exit("Removed the new fixtures: check_pii.py flagged them. Extend the Scrubber.")


if __name__ == "__main__":
    main()
