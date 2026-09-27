"""Cookies persist between runs, so a sync isn't a new-device sign-in every time.

A fake Family Access site (httpx.MockTransport) plays the sign-in dance from
app/skyward/session.py and remembers which device ids it has seen: the thing
that decides whether Skyward emails the parent about a new sign-in.
"""

import json
import stat

import httpx
import pytest

from app.skyward.session import SkywardSession

BASE = "https://skyward.example.org"
PAGE = "/Student/Grading/StudentSection/FamilyAccess"


class FakeSkyward:
    def __init__(self):
        self.live_sessions: set[str] = set()
        self.sign_ins: list[str | None] = []  # the device id each sign-in arrived with
        self._next = 0

    def _cookies(self, request: httpx.Request) -> dict[str, str]:
        header = request.headers.get("cookie", "")
        return dict(p.strip().split("=", 1) for p in header.split(";") if "=" in p)

    def handler(self, request: httpx.Request) -> httpx.Response:
        cookies = self._cookies(request)
        path = request.url.path
        if path == PAGE and request.method == "GET":
            if cookies.get("SessionIDStudent") in self.live_sessions:
                html = "<html><script>window._skyward.global.sessionGuidHash='T';</script></html>"
                return httpx.Response(200, html=html)
            return httpx.Response(302, headers={"Location": "/StudentSTS/Session/Signin?a=1"})
        if path == "/StudentSTS/Session/Signin":
            return httpx.Response(
                200,
                html='<form class="signIn"><input name="UserName"><input name="Password">'
                '<input name="Area" type="hidden" value="Grading"></form>',
            )
        if path == "/StudentSTS" and request.method == "POST":
            device = cookies.get("LoginHistoryIdentifier-Student")
            self.sign_ins.append(device)
            self._next += 1
            session = f"s{self._next}"
            self.live_sessions.add(session)
            headers = [
                ("Set-Cookie", "SessionIDStudent=" + session + "; path=/; secure; httponly"),
                (
                    "Set-Cookie",
                    f"LoginHistoryIdentifier-Student={device or 'device-' + str(self._next)}; "
                    "expires=Fri, 27 Sep 2126 16:20:39 GMT; path=/; secure; httponly",
                ),
            ]
            html = (
                f'<form method="post" action="{BASE}{PAGE}">'
                '<input name="SessionAuthenticationID" value="x">'
                '<input name="SessionAuthenticationHash" value="y"></form>'
            )
            return httpx.Response(200, headers=headers, html=html)
        if path == PAGE and request.method == "POST":
            return httpx.Response(302, headers={"Location": PAGE + "?p=1&w=2"})
        return httpx.Response(404)


@pytest.fixture
def site():
    return FakeSkyward()


def run(site, cookie_file, user="parent"):
    """One sync's worth: open a session, load a page, close. Returns sign-ins done."""
    with SkywardSession(
        BASE, user, "pw", cookie_file=cookie_file, transport=httpx.MockTransport(site.handler)
    ) as s:
        page = s.page(PAGE)
        assert page.csrf == "T"
        return s.sign_ins


def test_first_run_signs_in_and_saves_owner_only_cookies(site, tmp_path):
    jar = tmp_path / "skyward-cookies.json"
    assert run(site, jar) == 1
    assert stat.S_IMODE(jar.stat().st_mode) == 0o600
    names = {c["name"] for c in json.loads(jar.read_text())["cookies"]}
    assert {"SessionIDStudent", "LoginHistoryIdentifier-Student"} <= names
    assert "parent" not in jar.read_text()  # the owner is a hash, not the username


def test_next_run_reuses_the_live_session(site, tmp_path):
    jar = tmp_path / "skyward-cookies.json"
    run(site, jar)
    assert run(site, jar) == 0
    assert len(site.sign_ins) == 1


def test_expired_session_signs_in_again_as_the_same_device(site, tmp_path):
    jar = tmp_path / "skyward-cookies.json"
    run(site, jar)
    site.live_sessions.clear()  # Skyward timed the session out
    assert run(site, jar) == 1
    assert site.sign_ins == [None, "device-1"]  # the second sign-in is from a known device


def test_without_a_cookie_file_every_run_is_a_new_device(site, tmp_path):
    run(site, None)
    run(site, None)
    assert site.sign_ins == [None, None]


def test_another_accounts_cookies_are_ignored(site, tmp_path):
    jar = tmp_path / "skyward-cookies.json"
    run(site, jar, user="parent")
    site.live_sessions.clear()
    run(site, jar, user="someone-else")
    assert site.sign_ins == [None, None]


def test_unreadable_cookie_file_is_ignored(site, tmp_path):
    jar = tmp_path / "skyward-cookies.json"
    jar.write_text("not json")
    assert run(site, jar) == 1
    assert json.loads(jar.read_text())["cookies"]
