"""One sync's fetching against a fake Family Access site built from the fixtures.

The fake is already signed in (tests/test_session_cookies.py covers signing
in) and records the assignments filter, the server-side preference that
fetch_assignments must always put back to Current Term.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest

from app.skyward.client import ASSIGNMENTS_PATH, DATE_RANGE_PATH, fetch_assignments
from app.skyward.session import SessionExpired, SkywardError, SkywardSession

BASE = "https://skyward.example.org"
FIXTURES = Path(__file__).parent / "fixtures"
SIGNIN = "/StudentSTS/Session/Signin"


def getbrowse_reply(fixture: str) -> dict:
    """A GetBrowse reply as Skyward sends it: the grid's HTML plus a script."""
    d = json.loads((FIXTURES / fixture).read_text())
    script = f"x.registerBrowse({json.dumps(d['meta'])});\nfoo({{a: 1}});"
    return {"html": d["html"], "script": script}


class FakeSite:
    def __init__(self):
        self.date_range = "Current"
        self.date_range_posts: list[str] = []
        self.fail_date_range: set[str] = set()  # modes whose POST errors (after saving)
        self.expire_at_getbrowse = False
        self.expired = False
        self.reply = getbrowse_reply  # fixture name -> GetBrowse reply

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.expired and path != SIGNIN:
            return httpx.Response(302, headers={"Location": SIGNIN + "?a=1"})
        if path == SIGNIN:
            return httpx.Response(200, html="<form class='signIn'></form>")
        if path == ASSIGNMENTS_PATH:
            html = (FIXTURES / "assignments_page.html").read_text()
            return httpx.Response(200, html=html)
        if path == DATE_RANGE_PATH:
            mode = dict(httpx.QueryParams(request.content.decode()))["DateRangeMode"]
            self.date_range_posts.append(mode)
            self.date_range = mode
            if mode in self.fail_date_range:
                return httpx.Response(500)
            return httpx.Response(200, json={})
        if path.endswith("/GetBrowse"):
            if self.expire_at_getbrowse:
                self.expired = True
                return httpx.Response(302, headers={"Location": SIGNIN + "?a=1"})
            name = dict(httpx.QueryParams(request.content.decode()))["browseName"]
            return httpx.Response(200, json=self.reply(f"{name}.json"))
        return httpx.Response(404)


@pytest.fixture
def site():
    return FakeSite()


def session(site) -> SkywardSession:
    return SkywardSession(BASE, "parent", "pw", transport=httpx.MockTransport(site.handler))


def test_fetches_all_year_and_puts_current_back(site):
    with session(site) as s:
        found = fetch_assignments(s)
    assert {a.status for a in found} == {"missing", "upcoming", "past"}
    assert site.date_range_posts == ["AllYear", "Current"]
    assert site.date_range == "Current"


def test_current_is_put_back_when_switching_to_all_year_fails(site):
    # Skyward saved the preference, then the reply failed (a timeout, say).
    site.fail_date_range = {"AllYear"}
    with session(site) as s, pytest.raises(httpx.HTTPStatusError):
        fetch_assignments(s)
    assert site.date_range_posts == ["AllYear", "Current"]
    assert site.date_range == "Current"


def test_a_failed_put_back_is_logged_not_raised(site, caplog):
    site.fail_date_range = {"Current"}
    with session(site) as s, caplog.at_level(logging.ERROR):
        found = fetch_assignments(s)
    assert found  # the fetch itself worked, so the sync keeps its result
    assert "Current Term" in caplog.text


def test_session_ended_part_way_is_an_error_not_silence(site):
    # The parent signs in on their browser; Skyward sends the grid request to
    # the sign-in page, which answers 200.
    site.expire_at_getbrowse = True
    with session(site) as s, pytest.raises(SessionExpired):
        fetch_assignments(s)


def with_meta(fixture: str, **changes) -> dict:
    d = json.loads((FIXTURES / fixture).read_text())
    return {"html": d["html"], "script": f"registerBrowse({json.dumps(d['meta'] | changes)})"}


def test_a_grid_missing_rows_is_refused(site):
    # As if Skyward started paging: fewer rows (and keys) than its count.
    site.reply = lambda fixture: with_meta(fixture, recordCount=10_000)
    with session(site) as s, pytest.raises(SkywardError, match="rows"):
        fetch_assignments(s)
    assert site.date_range == "Current"


def test_empty_grids_are_fine(site):
    # What Skyward sends for an empty grid: a "no records" row, a recordCount
    # of 1 and no primaryKeys.
    site.reply = lambda fixture: {
        "html": '<table><tr class="noRecordsInBrowse browseRow"><td>None</td></tr></table>',
        "script": 'registerBrowse({"recordCount": 1, "primaryKeys": []})',
    }
    with session(site) as s:
        assert fetch_assignments(s) == []


def test_unparseable_grid_metadata_is_an_error(site):
    site.reply = lambda fixture: {"html": "", "script": "registerBrowse({not json})"}
    with session(site) as s, pytest.raises(SkywardError, match="registerBrowse"):
        fetch_assignments(s)
