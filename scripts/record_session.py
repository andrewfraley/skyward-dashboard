"""Record a Skyward Family Access session so its requests can be studied.

Opens a visible Chromium at the district's Skyward site. You log in and click
around as usual; every page load and XHR/fetch call is written to
recordings/<timestamp>/requests.jsonl, with each response body saved alongside
in bodies/. Close the browser window (or press Ctrl+C) to finish.

Password fields are redacted before anything touches disk. Cookies are kept,
since replaying the session is the point, so recordings/ is gitignored and must
stay on this machine.

    uv run python scripts/record_session.py [URL]

Without a URL it opens SKYWARD_BASE_URL (from .env) at the assignments page. The
site root (/) resets the connection, so it always starts from a deeper path.
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from playwright.sync_api import Error, Response, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import load_settings  # noqa: E402

START_PATH = "/Student/Gradebook/StudentAssignment/FamilyAccessAssignmentList"


RECORDED_TYPES = {"document", "xhr", "fetch"}
SECRET_KEY = re.compile(r"pass|pwd", re.IGNORECASE)
REDACTED = "***REDACTED***"


def redact_post_data(data: str | None, content_type: str) -> str | None:
    """Blank out any field whose name looks like a password."""
    if not data:
        return data
    if "json" in content_type:
        try:
            return json.dumps(_redact_json(json.loads(data)))
        except ValueError:
            pass
    if "x-www-form-urlencoded" in content_type or "=" in data:
        pairs = parse_qsl(data, keep_blank_values=True)
        if pairs:
            return urlencode([(k, REDACTED if SECRET_KEY.search(k) else v) for k, v in pairs])
    # Unknown format: redact anything shaped like "password": "..." or password=...
    return re.sub(
        r'((?:\w*(?:pass|pwd)\w*)["\']?\s*[:=]\s*["\']?)[^"\'&,}\s]+',
        rf"\1{REDACTED}",
        data,
        flags=re.IGNORECASE,
    )


def _redact_json(value):
    if isinstance(value, dict):
        return {
            k: (
                REDACTED
                if SECRET_KEY.search(k) and not isinstance(v, (dict, list))
                else _redact_json(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(v) for v in value]
    return value


def extension_for(content_type: str) -> str:
    for marker, ext in (("json", "json"), ("html", "html"), ("javascript", "js"), ("xml", "xml")):
        if marker in content_type:
            return ext
    return "txt"


class Recorder:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.bodies = out_dir / "bodies"
        self.bodies.mkdir(parents=True)
        self.log = (out_dir / "requests.jsonl").open("a", encoding="utf-8")
        self.count = 0

    def on_response(self, response: Response) -> None:
        request = response.request
        if request.resource_type not in RECORDED_TYPES:
            return
        self.count += 1
        seq = self.count
        try:
            req_headers = request.all_headers()
            resp_headers = response.all_headers()
        except Error:
            req_headers, resp_headers = request.headers, response.headers
        content_type = resp_headers.get("content-type", "")

        body_file = None
        try:
            body = response.body()
        except Error:
            body = None  # redirects and aborted requests have no body
        if body:
            body_file = f"bodies/{seq:04d}.{extension_for(content_type)}"
            (self.out_dir / body_file).write_bytes(body)

        entry = {
            "seq": seq,
            "time": datetime.now().isoformat(timespec="seconds"),
            "type": request.resource_type,
            "method": request.method,
            "url": request.url,
            "status": response.status,
            "redirected_to": resp_headers.get("location"),
            "request_headers": req_headers,
            "post_data": redact_post_data(request.post_data, req_headers.get("content-type", "")),
            "response_content_type": content_type,
            "response_headers": resp_headers,
            "body_file": body_file,
            "body_bytes": len(body) if body else 0,
        }
        self.log.write(json.dumps(entry) + "\n")
        self.log.flush()
        print(f"[{seq:4d}] {response.status} {request.method:4} {request.url[:120]}")

    def close(self) -> None:
        self.log.close()


def main() -> None:
    if len(sys.argv) > 1:
        url = sys.argv[1]
    elif base := load_settings().base_url:
        url = base + START_PATH
    else:
        sys.exit("Pass a URL, or set SKYWARD_BASE_URL in .env")
    out_dir = (
        Path(__file__).resolve().parent.parent
        / "recordings"
        / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    recorder = Recorder(out_dir)
    print(f"Recording to {out_dir}\nLog in and click around; close the browser window when done.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(no_viewport=True)
        context.on("response", recorder.on_response)
        page = context.new_page()
        try:
            page.goto(url)
        except Error as e:
            print(
                f"Couldn't open {url} ({e.message.splitlines()[0]}); navigate manually in the window."
            )

        state_file = out_dir / "storage_state.json"
        try:
            # Closing the last window doesn't end a Playwright browser, so poll
            # for it. The sync API only dispatches events inside Playwright
            # calls, hence wait_for_timeout rather than time.sleep. Cookies are
            # saved as we go in case the browser dies first.
            last_save = 0.0
            while browser.is_connected() and context.pages:
                try:
                    context.pages[0].wait_for_timeout(500)
                    if time.monotonic() - last_save > 5:
                        context.storage_state(path=state_file)
                        last_save = time.monotonic()
                except Error:
                    continue  # the page we waited on was closed; re-check
        except KeyboardInterrupt:
            pass
        finally:
            try:
                context.storage_state(path=state_file)
                browser.close()
            except Error:
                pass
            recorder.close()

    print(f"\nSaved {recorder.count} requests to {out_dir}")


if __name__ == "__main__":
    main()
