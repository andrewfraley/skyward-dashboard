"""Log in to Skyward headlessly and record the pages it visits.

Credentials come from .env (SKYWARD_BASE_URL, SKYWARD_USER, SKYWARD_PASS) and
are never printed or written out. Traffic is recorded exactly like
record_session.py, into recordings/<timestamp>/.

    uv run python scripts/explore.py                 # log in, list the site's links
    uv run python scripts/explore.py PATH [PATH ...] # also visit these paths
    uv run python scripts/explore.py --menu          # also dump the main menu

After each page it prints the page title, the links on it, and any buttons or
tabs, so the next paths to visit can be picked from the output.
"""

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

from record_session import Recorder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import load_settings  # noqa: E402
from browser_cookies import keep_cookies, save_storage_state, use_saved_cookies  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
START_PATH = "/Student/Gradebook/StudentAssignment/FamilyAccessAssignmentList"


def describe(page: Page) -> None:
    print(f"\n== {page.title()!r}  {page.url}")
    links = page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => [a.innerText.trim().replace(/\\s+/g, ' '), a.getAttribute('href')])
                    .filter(([t, h]) => h && !h.startsWith('#') && !h.startsWith('javascript'))""",
    )
    seen = set()
    for text, href in links:
        url = urljoin(page.url, href)
        if url not in seen:
            seen.add(url)
            print(f"  link  {text[:50]!r:52} {url}")
    controls = page.eval_on_selector_all(
        "button, [role=tab], [role=menuitem], [data-action], [onclick]",
        """els => els.map(e => [e.tagName, e.innerText.trim().replace(/\\s+/g, ' ').slice(0, 50),
                               e.id || e.getAttribute('data-action') || ''])
                    .filter(([, t]) => t)""",
    )
    for tag, text, ident in controls[:60]:
        print(f"  ctrl  {tag:8} {text!r:52} {ident}")


def dump_menu(page: Page, out_dir: Path) -> None:
    page.click(".js-skywardMainMenuVisibilityToggle")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    page.screenshot(path=out_dir / "menu.png")
    items = page.eval_on_selector_all(
        ".skywardMainMenu a, .skywardMainMenu [data-url], .skywardMainMenu li",
        """els => els.map(e => [e.tagName, e.innerText.trim().replace(/\\s+/g, ' ').slice(0, 60),
                               e.getAttribute('href') || e.getAttribute('data-url') || ''])
                    .filter(([, t, h]) => t && !(h || '').startsWith('#'))""",
    )
    print("\n== main menu")
    for tag, text, href in items:
        print(f"  {tag:3} {text!r:62} {href}")
    page.keyboard.press("Escape")


def credentials() -> tuple[str, str, str]:
    """Return (base_url, user, password) from .env / the environment."""
    settings = load_settings()
    if not settings.has_credentials:
        sys.exit("SKYWARD_BASE_URL, SKYWARD_USER and SKYWARD_PASS must be set in .env")
    return settings.base_url, settings.username, settings.password


def login(page: Page, base: str, user: str, password: str, path: str = START_PATH) -> None:
    """Land on `path`, signing in through the form if the session isn't live."""
    page.goto(base + path)
    page.wait_for_load_state("networkidle")
    if "Signin" not in page.url:
        return  # the saved session is still good
    page.fill("input[name=UserName]", user)
    page.fill("input[name=Password]", password)
    with page.expect_navigation():
        page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    if "Signin" in page.url:
        error = page.locator(
            ".validation-summary-errors, .field-validation-error, .error"
        ).all_inner_texts()
        sys.exit(f"Login failed: {' '.join(error) or 'still on the sign-in page'}")


def main() -> None:
    show_menu = "--menu" in sys.argv
    paths = [a for a in sys.argv[1:] if a != "--menu"]

    base, user, password = credentials()

    out_dir = ROOT / "recordings" / datetime.now().strftime("%Y%m%d-%H%M%S")
    recorder = Recorder(out_dir)
    print(f"Recording to {out_dir}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        use_saved_cookies(context, base, user)
        context.on("response", recorder.on_response)
        page = context.new_page()

        login(page, base, user, password)
        page.screenshot(path=out_dir / "after_login.png", full_page=True)
        describe(page)
        if show_menu:
            dump_menu(page, out_dir)

        for i, path in enumerate(paths, 1):
            page.goto(urljoin(base + "/", path.lstrip("/")))
            page.wait_for_load_state("networkidle")
            page.screenshot(path=out_dir / f"page_{i:02d}.png", full_page=True)
            describe(page)

        save_storage_state(context, out_dir / "storage_state.json")
        keep_cookies(context, base, user)
        browser.close()
    recorder.close()
    print(f"\nSaved {recorder.count} requests to {out_dir}")


if __name__ == "__main__":
    main()
