"""Fixtures must look scrubbed, checked without any private data (so this runs in CI).

tests/test_no_pii.py compares against the real names and ids, but only where a
local sync exists. These catch the shape of a leak everywhere: a real security
hash or token, a real host, a person's name where only stand-ins belong.
"""

import re
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures").iterdir())


@pytest.fixture(params=FIXTURES, ids=lambda p: p.name)
def text(request):
    return request.param.read_text(encoding="utf-8")


def test_security_hashes_are_zeroed(text):
    hashes = set(re.findall(r"(?<![0-9A-Fa-f])[0-9A-F]{64}(?![0-9A-Fa-f])", text))
    assert hashes <= {"0" * 64}


def test_tokens_and_guids_are_placeholders(text):
    assert set(re.findall(r"sessionGuidHash='([^']*)'", text)) <= {"TESTCSRFTOKEN"}
    assert set(re.findall(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", text)) <= {"f" * 32}
    assert not re.search(r"mediaVerificationToken=(?!X\b)", text)


# Public hosts the Skyward pages reference; nothing that locates a district.
PUBLIC_HOSTS = {"hub.skyward.com", "cdn.jsdelivr.net", "code.jquery.com"}


def test_only_the_example_host(text):
    hosts = set(re.findall(r"https?://([a-z0-9.-]+)", text, re.IGNORECASE))
    unexpected = {
        h
        for h in hosts
        if "example" not in h and not h.endswith("w3.org") and h not in PUBLIC_HOSTS
    }
    assert not unexpected


def test_people_are_stand_ins(text):
    teachers = set(re.findall(r'staffPopup[^>]*>\s*<span[^>]*class="anchorText">([^<]+)<', text))
    assert teachers <= {f"TEACHER {c}" for c in "ABCDEFGHIJKLMNOP"}
    parents = set(re.findall(r'utilitiesButtonMain__text--username">([^<]*)<', text))
    assert parents <= {"PARENT"}
    names = set(re.findall(r'familyAccessStudentNameText">([^<]*)<', text))
    assert names <= {"STUDENT,", "DEMO", "More"}
