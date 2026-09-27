"""Nothing identifying the family may be in files git would commit.

Terms come from local, gitignored sources (.env, data/skyward.db, .pii-terms),
so this only has teeth on a machine that has synced; elsewhere it skips.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_pii  # noqa: E402


def test_no_identifying_information_in_repo():
    terms = check_pii.gather_terms()
    if not terms:
        pytest.skip("no local .env / data/skyward.db / .pii-terms to check against")
    hits = check_pii.find_hits(check_pii.files_to_check(staged=False), terms)
    assert not hits, "identifying information found:\n" + "\n".join(hits)
