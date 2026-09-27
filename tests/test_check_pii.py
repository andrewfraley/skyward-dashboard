"""The PII scanner itself, with made-up terms (tests/test_no_pii.py runs it for real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_pii  # noqa: E402

TERMS = check_pii.with_escapes({"O'Doe": "teacher surname", "Roe, Jane": "student name"})


def hits(name: str, text: str | bytes) -> list[str]:
    data = text if isinstance(text, bytes) else text.encode()
    return check_pii.find_hits([(name, data)], TERMS)


def test_plain_and_escaped_forms_are_found():
    assert hits("a.md", "Ask Mrs. O'Doe")
    assert hits("a.html", "Ask Mrs. O&#39;Doe")
    assert hits("a.html", "Ask Mrs. O&#x27;Doe")
    assert hits("a.json", '{"t": "Mrs. O\\u0027Doe"}')
    assert hits("a.json", '{"t": "Mrs. O&#39;Doe"}')


def test_underscores_and_digits_do_not_hide_a_name():
    assert hits("a.txt", "o'doe_notes")
    assert hits("a.txt", "o'doe2")
    assert not hits("a.txt", "xo'doe")  # inside a longer word: something else


def test_file_names_are_checked():
    assert hits("docs/o'doe-report.md", "nothing here")[0].endswith("file name: teacher surname")


def test_binary_files_are_checked():
    assert hits("data.db", b"SQLite format 3\0\0\0Roe, Jane\0")


def test_a_name_wrapped_across_lines_is_found():
    assert hits("a.md", "Roe,\nJane")


def test_short_pii_terms_are_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_pii, "ROOT", tmp_path)
    monkeypatch.setattr(check_pii, "load_settings", lambda: _NoSettings(tmp_path))
    (tmp_path / ".pii-terms").write_text("Al\nLongname # a comment\nC#Lang\n")
    terms = check_pii.gather_terms()
    assert "Longname" in terms and "C#Lang" in terms and "Al" not in terms
    assert "1 .pii-terms entry is too short" in capsys.readouterr().err


class _NoSettings:
    username = password = base_url = ""
    timezone = None

    def __init__(self, root):
        self.db_path = root / "missing.db"
