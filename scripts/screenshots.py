"""Check the UI at phone, tablet and desktop widths, and take the README screenshots.

Runs only against the made-up demo data from scripts/seed_demo.py: it starts
the app on :8087 with SKYWARD_DATA_DIR=recordings/demo and the Skyward
credentials blanked, so it never contacts Skyward, and refuses to take a single
screenshot unless the only student is the demo one.

    uv run python scripts/seed_demo.py
    npm --prefix frontend run build          # the app serves frontend/dist
    uv run --group tools python scripts/screenshots.py --check    # fails on sideways scroll or console errors
    uv run --group tools python scripts/screenshots.py --readme   # writes docs/screenshots/*.png

--check writes its screenshots to recordings/screens/ for review.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "recordings" / "demo"
PORT = 8087
BASE = f"http://127.0.0.1:{PORT}"
DEMO_STUDENT = "DOE, JANE Q"

PHONES = [(360, 740), (390, 844)]

# Regions that scroll sideways inside the page (a wide table in its own scroller
# doesn't make the page overflow, but it's just as bad on a phone). Scrollable
# tab strips are meant to scroll.
INNER_SCROLL_JS = """
() => [...document.querySelectorAll('*')].filter(el => {
  const style = getComputedStyle(el)
  return ['auto', 'scroll'].includes(style.overflowX)
    && el.scrollWidth > el.clientWidth + 1
    && !el.closest('.MuiTabs-root')
}).map(el => (el.className && el.className.baseVal === undefined ? el.className : el.tagName)
  .toString().split(' ').find(c => c.startsWith('Mui')) || el.tagName)
"""
LARGER = [(768, 1024), (1024, 768), (1280, 900)]


def get_json(path: str):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.load(r)


def start_server() -> subprocess.Popen:
    if not (DEMO_DIR / "skyward.db").exists():
        sys.exit("No demo data: run `uv run python scripts/seed_demo.py` first")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        sys.exit("No built UI: run `npm --prefix frontend run build` first")
    try:
        get_json("/api/ping")
        sys.exit(f"Something is already listening on :{PORT}; stop it first")
    except OSError:
        pass
    env = {
        **os.environ,
        "SKYWARD_DATA_DIR": str(DEMO_DIR),
        # Set but empty, so .env can't supply them: no credentials, no syncing.
        "SKYWARD_BASE_URL": "",
        "SKYWARD_USER": "",
        "SKYWARD_PASS": "",
        "SKYWARD_LOG_LEVEL": "WARNING",
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--no-access-log"],
        cwd=ROOT,
        env=env,
    )
    for _ in range(50):
        try:
            get_json("/api/ping")
            break
        except OSError:
            time.sleep(0.2)
    else:
        server.terminate()
        sys.exit("The app didn't start")
    names = {s["name"] for s in get_json("/api/students")}
    if names != {DEMO_STUDENT}:
        server.terminate()
        sys.exit("Refusing to take screenshots: the database isn't only the demo student")
    return server


def routes() -> list[str]:
    student = get_json("/api/students")[0]["id"]
    courses = get_json(f"/api/students/{student}/courses")
    # The class with the most grade history, so its page shows a trend.
    details = [get_json(f"/api/courses/{c['student_section_id']}") for c in courses]
    course = max(details, key=lambda c: (len(c["history"]), len(c["grades"])))
    return [
        "overview",
        "assignments/missing",
        "assignments/upcoming",
        "assignments/past",
        "assignments/all",
        "changes",
        f"course/{course['student_section_id']}",
    ]


def open_page(browser, width, height, scheme, route, scale=1):
    page = browser.new_page(
        viewport={"width": width, "height": height}, color_scheme=scheme, device_scale_factor=scale
    )
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/#{route}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)  # charts animate in
    return page, errors


def check(browser) -> int:
    out = ROOT / "recordings" / "screens"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    problems = []
    for width, height in PHONES + LARGER:
        for scheme in ("light", "dark"):
            for route in routes():
                page, errors = open_page(browser, width, height, scheme, route)
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                label = f"{width}x{height} {scheme} #{route}"
                if overflow > 0:
                    problems.append(f"{label}: scrolls sideways by {overflow}px")
                inner = sorted(set(page.evaluate(INNER_SCROLL_JS)))
                if inner:
                    problems.append(f"{label}: a region scrolls sideways ({', '.join(inner)})")
                problems += [f"{label}: console error: {e}" for e in errors]
                name = f"{width}x{height}-{scheme}-{route.replace('/', '-')}.png"
                page.screenshot(path=out / name, full_page=True)
                page.close()
    # Installable: the manifest and its icons load.
    page = browser.new_page()
    page.goto(BASE + "/")
    link = page.query_selector("link[rel=manifest]")
    href = link.get_attribute("href") if link else None
    if not href:
        problems.append("no <link rel=manifest>")
    else:
        manifest = page.request.get(f"{BASE}/{href}").json()
        for icon in manifest.get("icons", []):
            if page.request.get(f"{BASE}/{icon['src']}").status != 200:
                problems.append(f"manifest icon {icon['src']} doesn't load")
    page.close()
    print(f"Screenshots in {out.relative_to(ROOT)}/")
    if problems:
        print("Problems:\n  " + "\n  ".join(problems))
        return 1
    print("check: no sideways scrolling or console errors at any width")
    return 0


def readme(browser) -> int:
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    course = routes()[-1]
    shots = [
        ("desktop-overview.png", 1280, 860, "light", "overview", 1),
        ("desktop-class.png", 1280, 860, "dark", course, 1),
        ("phone-overview.png", 390, 844, "light", "overview", 2),
        ("phone-assignments.png", 390, 844, "light", "assignments/missing", 2),
    ]
    for name, width, height, scheme, route, scale in shots:
        page, errors = open_page(browser, width, height, scheme, route, scale)
        if errors:
            sys.exit(f"{name}: console errors: {errors}")
        raw = out / f".{name}"
        page.screenshot(path=raw)
        page.close()
        # No metadata, and small enough for a README.
        subprocess.run(
            ["magick", raw, "-strip", "-define", "png:compression-level=9", out / name], check=True
        )
        raw.unlink()
        print(f"wrote {(out / name).relative_to(ROOT)}")
    print("Look at every image before committing: only demo data may appear.")
    return 0


def main() -> None:
    mode = next((a for a in sys.argv[1:] if a in ("--check", "--readme")), None)
    if not mode:
        sys.exit(__doc__)
    server = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            status = check(browser) if mode == "--check" else readme(browser)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    sys.exit(status)


if __name__ == "__main__":
    main()
