"""Share the app's saved Skyward cookies with a Playwright browser, both ways.

Skyward emails the parent about every sign-in from a new device, and allows one
session per account. Starting a browser from data/skyward-cookies.json makes it
the same device (and reuses a live session); saving its cookies back lets the
app reuse whatever session the browser ends with.
"""

import http.cookiejar
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import load_settings  # noqa: E402
from app.skyward.session import cookie_owner, load_cookies, save_cookies  # noqa: E402


def use_saved_cookies(context, base: str, user: str) -> None:
    """Start from the app's saved cookies, so a still-live session is reused and a
    new sign-in comes from a known device rather than triggering Skyward's email."""
    jar = http.cookiejar.CookieJar()
    load_cookies(jar, load_settings().cookie_path, cookie_owner(base, user))
    context.add_cookies(
        [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expires": c.expires if c.expires is not None else -1,
                "secure": c.secure,
                "httpOnly": c.has_nonstandard_attr("HttpOnly"),
            }
            for c in jar
        ]
    )


def keep_cookies(context, base: str, user: str) -> None:
    """Save the browser's Skyward cookies back for the app and the next run."""
    host = base.split("://", 1)[-1].split("/", 1)[0]
    jar = http.cookiejar.CookieJar()
    for c in context.cookies():
        if c["domain"].lstrip(".") != host:
            continue
        jar.set_cookie(
            http.cookiejar.Cookie(
                0, c["name"], c["value"], None, False, c["domain"], False,
                c["domain"].startswith("."), c["path"], True, c["secure"],
                None if c["expires"] == -1 else int(c["expires"]), c["expires"] == -1,
                None, None, {"HttpOnly": None} if c["httpOnly"] else {},
            )  # fmt: skip
        )
    save_cookies(jar, load_settings().cookie_path, cookie_owner(base, user))


def save_storage_state(context, path: Path) -> None:
    """Playwright's storage state (live session cookies included), owner-only."""
    context.storage_state(path=path)
    os.chmod(path, 0o600)
