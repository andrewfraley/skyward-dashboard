"""Fail if anything identifying the family would be committed.

The sensitive terms are gathered only from local, gitignored sources, so this
script itself never contains them:

  .env              SKYWARD_USER, SKYWARD_PASS, the district host and domain, TZ
  data/skyward.db   student names (each part), student ids, schools, teacher
                    names (whole and surname), the ids Skyward uses for
                    enrollments and assignments, and course and assignment titles
  .pii-terms        anything else, one term per line (parent names, the
                    district's full name, a street, ...); a # at the start of
                    a line or after a space starts a comment

Then every file git would commit is searched for them, its path included, and
binary files too (a database or archive can hold names as plain text): words
case-insensitively, not inside a longer word, numbers as whole numbers. Each
term is also looked for as HTML and JSON would escape it.

    uv run python scripts/check_pii.py                  # working tree (what `git add -A` would take)
    uv run python scripts/check_pii.py --staged         # the index; .githooks/pre-commit
    uv run python scripts/check_pii.py --message FILE   # a commit message; .githooks/commit-msg

Exit status 1 lists each hit as file:line and the kind of term, never the
term itself, so the output is safe to paste anywhere.
"""

import html
import json
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


# Timezones that say nothing about where anyone lives.
NEUTRAL_TIMEZONES = {"UTC", "Etc/UTC", "GMT", "Etc/GMT", "UCT", "Zulu"}


def gather_terms(sources: list[str] | None = None) -> dict[str, str]:
    """term -> what kind of thing it is (shown instead of the term).

    `sources`, when given, collects the names of the places terms came from.
    """
    terms: dict[str, str] = {}
    sources = sources if sources is not None else []

    def add(term, kind) -> bool:
        term = str(term or "").strip()
        if term.isdigit():
            if len(term) >= MIN_NUMBER_LENGTH:
                terms[term] = kind
                return True
        elif len(term) >= MIN_WORD_LENGTH:
            terms[term] = kind
            return True
        return False

    settings = load_settings()
    if settings.username or settings.password or settings.base_url:
        sources.append(".env")
    add(settings.username, "Skyward username")
    add(settings.password, "Skyward password")
    if settings.timezone and settings.timezone not in NEUTRAL_TIMEZONES:
        add(settings.timezone, "timezone")
        for part in re.split(r"[/_]", settings.timezone)[1:]:
            add(part, "timezone city")
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
        sources.append("the database")
        db = sqlite3.connect(db_path)
        for sid, name, school in db.execute("SELECT id, name, school FROM students"):
            add(sid, "student id")
            add(name, "student name")
            for part in re.split(r"[\s,]+", name or ""):
                add(part, "student name part")
            add(school, "school name")
        teachers = set()
        for ssid, teacher in db.execute("SELECT student_section_id, teacher FROM courses"):
            add(ssid, "student enrollment id")
            teachers.add(teacher)
        for (teacher,) in db.execute("SELECT DISTINCT teacher FROM assignments"):
            teachers.add(teacher)
        for teacher in teachers:
            add(teacher, "teacher name")
            # "Surname, Given": the surname alone ("Mrs. Surname") names them
            # too. Given names are left out; too many are ordinary words.
            if "," in (teacher or ""):
                add(teacher.split(",", 1)[0], "teacher surname")
        for (aid,) in db.execute("SELECT id FROM assignments"):
            add(aid, "assignment id")
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
        sources.append(".pii-terms")
        skipped = 0
        for line in extra.read_text().splitlines():
            line = re.split(r"(?:^|\s)#", line, maxsplit=1)[0].strip()
            if line and not add(line, ".pii-terms entry"):
                skipped += 1
        if skipped:
            print(
                f"check_pii: warning: {skipped} .pii-terms entr{'y is' if skipped == 1 else 'ies are'}"
                f" too short to search for (words under {MIN_WORD_LENGTH} letters, numbers under"
                f" {MIN_NUMBER_LENGTH} digits) and not checked",
                file=sys.stderr,
            )
    return with_escapes(terms)


def escapings(term: str) -> set[str]:
    """`term` as a page or a JSON reply can hold it: plain, HTML-escaped (with
    either spelling of an apostrophe), and any of those in a JSON string, with
    or without \\u00XX escapes for & ' < > ("O'Brien" -> "O&#39;Brien",
    "O\\u0027Brien")."""
    variants = {term, html.escape(term), html.escape(term, quote=False)}
    variants |= {v.replace("&#x27;", "&#39;") for v in variants}
    variants |= {v.replace("'", "&#39;") for v in variants}
    in_json = {json.dumps(v)[1:-1] for v in variants}
    unicode = {v.translate({ord(c): f"\\u{ord(c):04x}" for c in "&'<>"}) for v in in_json}
    return variants | in_json | unicode


def with_escapes(terms: dict[str, str]) -> dict[str, str]:
    """Each term plus every escaped form of it (see escapings)."""
    out = dict(terms)
    for term, kind in terms.items():
        for form in escapings(term):
            out.setdefault(form, kind)
    return out


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


# A word term mustn't be part of a longer word, but digits and underscores
# around it don't make one: "smith_notes" and "smith2" still name a Smith.
_NOT_AFTER_LETTER = r"(?<![^\W\d_])"
_NOT_BEFORE_LETTER = r"(?![^\W\d_])"


def compile_patterns(terms: dict[str, str]) -> tuple[re.Pattern, dict[str, str]]:
    """One alternation over every term, plus a lookup from matched text to its kind."""
    parts, kinds = [], {}
    for term, kind in sorted(terms.items(), key=lambda t: -len(t[0])):
        if term.isdigit():
            parts.append(rf"(?<!\d){term}(?!\d)")
        else:
            parts.append(rf"{_NOT_AFTER_LETTER}{re.escape(term)}{_NOT_BEFORE_LETTER}")
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
        binary = b"\0" in data[:8000]
        # Binary files too: a database or an uncompressed archive holds its
        # text as plain bytes. Its "lines" mean little, so it's reported whole.
        text = data.decode("utf-8", errors="replace")
        # Whitespace squeezed, so a name wrapped onto the next line is a candidate.
        haystack = re.sub(r"\s+", " ", f"{name}\n{text}").lower()
        candidates = {lowered[t]: terms[lowered[t]] for t in lowered if t in haystack}
        if not candidates:
            continue
        pattern, kinds = compile_patterns(candidates)
        for m in pattern.finditer(name):
            hits.add(f"{name}: file name: {kinds.get(m.group(0).lower(), 'term')}")
        # One line per line, but across line breaks too: Markdown wraps a
        # name onto the next line ("Jane\nDoe").
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            joined = (
                line
                if binary
                else f"{line} {lines[lineno].lstrip()}" if lineno < len(lines) else line
            )
            for m in pattern.finditer(joined):
                where = "binary file" if binary else f"{lineno}"
                hits.add(f"{name}:{where}: {kinds.get(m.group(0).lower(), 'term')}")
    return sorted(hits)


def main() -> int:
    staged = "--staged" in sys.argv
    sources: list[str] = []
    terms = gather_terms(sources)
    if not terms:
        print(
            "check_pii: no local sources (.env, data/skyward.db, .pii-terms); nothing to check against"
        )
        return 0
    if "--message" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--message") + 1])
        # Drop git's own # comment lines, which list the files being committed.
        text = "\n".join(l for l in path.read_text().splitlines() if not l.startswith("#"))
        files = [("commit message", text.encode())]
    else:
        files = files_to_check(staged)
    hits = find_hits(files, terms)
    if hits:
        print("check_pii: identifying information found:\n  " + "\n  ".join(hits))
        return 1
    note = "" if "the database" in sources else "; no data/skyward.db, so names and titles weren't"
    print(f"check_pii: clean ({len(terms)} terms from {', '.join(sources)}{note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
