"""Fail if anything identifying the family would be committed.

The sensitive terms are gathered only from local, gitignored sources, so this
script itself never contains them:

  .env              SKYWARD_USER, SKYWARD_PASS, the district host and domain
  data/skyward.db   student names (each part), student ids, schools, teacher
                    names, the per-student enrollment ids Skyward uses, and
                    course and assignment titles
  .pii-terms        anything else, one term per line (parent names, the
                    district's full name, a street, ...); # starts a comment

Then every file git would commit is searched for them: words case-insensitively
on word boundaries, numbers as whole numbers.

    uv run python scripts/check_pii.py            # working tree (what `git add -A` would take)
    uv run python scripts/check_pii.py --staged   # the index; used by .githooks/pre-commit

Exit status 1 lists each hit as file:line and the kind of term, never the
term itself, so the output is safe to paste anywhere.
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402

# Words too common to search for on their own, even when they're part of a name.
MIN_WORD_LENGTH = 3
MIN_NUMBER_LENGTH = 5


def gather_terms() -> dict[str, str]:
    """term -> what kind of thing it is (shown instead of the term)."""
    terms: dict[str, str] = {}

    def add(term, kind):
        term = str(term or "").strip()
        if term.isdigit():
            if len(term) >= MIN_NUMBER_LENGTH:
                terms[term] = kind
        elif len(term) >= MIN_WORD_LENGTH:
            terms[term] = kind

    settings = load_settings()
    add(settings.username, "Skyward username")
    add(settings.password, "Skyward password")
    host = urlsplit(settings.base_url).hostname or ""
    if host:
        add(host, "district host")
        labels = host.split(".")
        add(".".join(labels[-2:]), "district domain")
        for label in labels[:-1]:
            if label not in ("www", "skyward", "com", "org", "edu", "net", "k12"):
                add(label, "district host label")

    db_path = settings.db_path
    if db_path.exists():
        db = sqlite3.connect(db_path)
        for sid, name, school in db.execute("SELECT id, name, school FROM students"):
            add(sid, "student id")
            add(name, "student name")
            for part in re.split(r"[\s,]+", name or ""):
                add(part, "student name part")
            add(school, "school name")
        for ssid, teacher in db.execute("SELECT student_section_id, teacher FROM courses"):
            add(ssid, "student enrollment id")
            add(teacher, "teacher name")
        for (teacher,) in db.execute("SELECT DISTINCT teacher FROM assignments"):
            add(teacher, "teacher name")
        # Titles can name the school, district or state. Short generic ones
        # ("Quiz", "Bellwork") would only produce noise, so skip those.
        for (course,) in db.execute(
            "SELECT name FROM courses UNION SELECT course FROM assignments"
        ):
            if len(course or "") >= 8:
                add(course, "course name")
        for (title,) in db.execute("SELECT DISTINCT name FROM assignments"):
            if len(title or "") >= 12 and " " in title:
                add(title, "assignment title")
        db.close()

    extra = ROOT / ".pii-terms"
    if extra.exists():
        for line in extra.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            add(line, ".pii-terms entry")
    return terms


def files_to_check(staged: bool) -> list[tuple[str, bytes]]:
    def git(*args) -> bytes:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout

    if staged:
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
        return [(n.decode(), git("show", f":{n.decode()}")) for n in names if n]
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
    return [
        (n.decode(), (ROOT / n.decode()).read_bytes())
        for n in names
        if n and (ROOT / n.decode()).is_file()
    ]


def compile_patterns(terms: dict[str, str]) -> tuple[re.Pattern, dict[str, str]]:
    """One alternation over every term, plus a lookup from matched text to its kind."""
    parts, kinds = [], {}
    for term, kind in sorted(terms.items(), key=lambda t: -len(t[0])):
        if term.isdigit():
            parts.append(rf"(?<!\d){term}(?!\d)")
        else:
            parts.append(rf"(?<!\w){re.escape(term)}(?!\w)")
        kinds[term.lower()] = kind
    return re.compile("|".join(parts), re.IGNORECASE), kinds


def find_hits(files: list[tuple[str, bytes]], terms: dict[str, str]) -> list[str]:
    """'path:line: kind' for every line of every text file that contains a term.

    A plain substring test picks the candidate terms per file first; the
    word-boundary regex then only runs where one of them actually occurs.
    """
    lowered = {t.lower(): t for t in terms}
    hits = set()
    for name, data in files:
        if b"\0" in data[:8000]:
            continue  # binary
        text = data.decode("utf-8", errors="replace")
        text_lower = text.lower()
        candidates = {lowered[t]: terms[lowered[t]] for t in lowered if t in text_lower}
        if not candidates:
            continue
        pattern, kinds = compile_patterns(candidates)
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                hits.add(f"{name}:{lineno}: {kinds.get(m.group(0).lower(), 'term')}")
    return sorted(hits)


def main() -> int:
    staged = "--staged" in sys.argv
    terms = gather_terms()
    if not terms:
        print(
            "check_pii: no local sources (.env, data/skyward.db, .pii-terms); nothing to check against"
        )
        return 0
    hits = find_hits(files_to_check(staged), terms)
    if hits:
        print("check_pii: identifying information found:\n  " + "\n  ".join(hits))
        return 1
    print(f"check_pii: clean ({len(terms)} terms checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
