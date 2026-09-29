# CLAUDE.md

A parent's dashboard for Skyward Qmlativ Family Access: grades, missing assignments and upcoming
assignments. A scheduled sync scrapes Skyward into SQLite; the API and React UI read only that
cache. It's an open-source project: README.md is for people running it, DEVELOPING.md for
contributors (privacy, supply chain, releases), SECURITY.md for reporting problems.

## Privacy comes first

This repo handles a real child's school records. **The repo must never contain personally
identifying information.** This rule outranks convenience, test fidelity and speed.

Never commit, and never write into any tracked file (code, comments, tests, fixtures, docs,
commit messages, PR text):

- student, parent or teacher names (not even as an example in a comment or test)
- Skyward usernames, passwords, cookies, CSRF tokens, security hashes
- Skyward ids of any kind (student, guardian, enrollment/student-section, grade bucket, section,
  assignment, media)
- school or district names, the district's Skyward host, or anything placing the family
  geographically (state, city, timezone)
- real course names or assignment titles; they can name the school, district or state

Use made-up stand-ins instead: `STUDENT, DEMO` (shown as "Demo"), `TEACHER A`, `COURSE A`, `ASSIGNMENT 001`,
`EXAMPLE MIDDLE SCHOOL`, `skyward.example.org`, student id `100001`. For a realistic course name
in a test, invent one ("CONCERT CHOIR-II"), never copy one from the synced data. People are
always obvious stand-ins, never realistic invented names: a made-up "Jane Smith" in a screenshot
or example reads as a real person.

Real data lives only in gitignored places: `.env`, `data/`, `recordings/`, `.pii-terms`. Read
from them freely when debugging, but don't copy their contents into tracked files, and don't
quote real names or grades in commit messages.

**Guard rails:**

- `scripts/check_pii.py` scans every file git would commit for terms taken from the local
  `.env`, `data/skyward.db` and `.pii-terms`. It prints the kind of term, never the term itself.
  Run it after touching tests, fixtures or docs: `uv run python scripts/check_pii.py`.
- `tests/test_no_pii.py` runs the same check under pytest.
- `.githooks/pre-commit` runs it on staged files and `.githooks/commit-msg` on the commit
  message. Enable them per clone with `git config core.hooksPath .githooks`. Never bypass them
  (`--no-verify`); if one fires, fix the file or the message.
- `tests/test_fixture_hygiene.py` needs no private data, so it's the check CI runs: every
  title, course and teacher the parsers read from a fixture must be a stand-in.
- Test fixtures come only from `scripts/capture_fixtures.py`, which scrubs names, titles, ids,
  hashes and hosts, then deletes its output if `check_pii.py` flags anything. Never hand-edit
  real responses into `tests/fixtures/`. When Skyward adds a new place for identifying data,
  extend the `Scrubber`, and add to `check_pii.py` if the database can supply the term.
- If `check_pii.py` can't know a term (e.g. the parent's name, the district's full name), add
  it to `.pii-terms`, which is local and gitignored.

## Commands

```sh
uv sync                                         # dev tools; `--group tools` adds Playwright for scripts/
uv run pytest                                   # Python tests (parsers, db, API, PII guard)
uv run python scripts/check_pii.py              # PII scan of everything committable
uv run black app tests scripts                  # line length 100
uv run python -m app.sync                       # one real sync into ./data (logs in to Skyward)
uv run uvicorn app.main:app --port 8087 --reload
docker compose up -d --build                    # the working tree (override file); SKYWARD_PORT picks the host port
```

Frontend (`frontend/`, React 19 + MUI 9 + Vite, plain JSX, Prettier: no semicolons, single
quotes, width 100). Node isn't installed on the host, so run npm in a container:

```sh
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $PWD/frontend:/ui:z -w /ui node:22-alpine npm ci
# ... npm test | npm run build | npm run format | npm run format:check
```

## Ports

Host port 8080 is used by other local apps. Local dev servers use **8087** (uvicorn; Vite's
proxy targets it). The container still listens on 8080 internally.

## Layout

- `app/skyward/session.py`: HTTP session: sign-in, page parsing, `get_browse` (grid data),
  `open_panel` (details panels). The module docstring explains the Qmlativ request flow.
- `app/skyward/parse.py`: HTML/JSON to models. `client.py`: one sync's worth of fetching.
  `models.py`: pydantic records.
- `app/db.py`: SQLite. `save_snapshot` replaces the latest state, records grade history, and
  diffs against the previous sync into the `changes` feed.
- `app/sync.py`: the only code that talks to Skyward; one sync at a time.
- `app/main.py`: FastAPI routes (read-only over the cache, plus `POST /api/sync`), the
  APScheduler cron job (`SKYWARD_SYNC_CRON`), and the built UI.
- `scripts/`: dev tools. `record_session.py` (visible browser, you click), `explore.py`
  (headless, logs in from `.env`), `capture_fixtures.py`, `check_pii.py`. Playwright is in the
  opt-in `tools` dependency group only; CI and the image have no browser.
- `docker-compose.yml` pulls the published image and must stay usable on its own (users download
  only it and write a `.env`). Anything needing the source goes in `docker-compose.override.yml`.
- `app/display.py`: the `/api/display` payload for e-paper displays (versioned; v1 only gains
  fields). `display/esphome/`: the ESPHome firmware: `devices/` (hardware only), `common/`
  (fetch, redraw, sleep), `layouts/` (one display lambda per size). DISPLAY.md is the user doc.

## Skyward gotchas

- The site root `/` resets the connection. Always request a deep path such as
  `/Student/Gradebook/StudentAssignment/FamilyAccessAssignmentList`.
- One session per account: a sign-in can sign the parent out of Skyward in their browser, and
  Skyward emails the parent about sign-ins from a new device. Cookies are kept in
  `data/skyward-cookies.json` (`Settings.cookie_path`): the long-lived
  `LoginHistoryIdentifier-Student` device cookie makes a re-sign-in look like the same device,
  and a still-live session is reused with no sign-in at all. Everything that talks to Skyward
  (`app/sync.py`, `scripts/explore.py`, `scripts/capture_fixtures.py`) must use that file.
  Never create a throwaway session. Don't sync in loops; reuse `recordings/` for parser work.
  No keep-alive either: holding a session open would fight the parent's own browser sign-ins.
- That includes **local testing**, container tests too: anything that reaches the real site
  reuses `data/skyward-cookies.json`. For a container, mount the repo's `./data` (or copy the
  cookie file into its data dir, 0600) rather than starting from an empty data dir, and stop any
  other instance first so two don't share one session. Prefer offline work: `recordings/`,
  `tests/fixtures/`, and the fake site in `tests/test_session_cookies.py`.
- The assignments page filter (Current Term / All Year) is a server-side user preference.
  `fetch_assignments` sets All Year and must always restore Current in a `finally`.
- Grid requests need the per-page CSRF token (`sessionGuidHash`), window ids (`p`, `w`), and
  the hashes embedded in each `browseList[...]` config. Panels get a fresh random `p`.
- No LLM or Claude dependency at runtime; the app is plain Python.

## Conventions

- Follow the maintainer's Dapple project (github.com/andrewfraley/dapple) for structure and
  release model: FastAPI + pydantic, black at 100, pytest with fixtures, a multi-stage
  Dockerfile, a PUID/PGID entrypoint, a `/data` volume mounted with `:z` (SELinux).
- The UI never calls Skyward and the API never fetches live; everything shown comes from the
  cache.
- Grade colours use the fixed status palette (success/warning/error) and always sit beside the
  letter grade; colour never carries meaning alone.
- Phone layout below `sm` (bottom tab bar, one-line header); assignment lists instead of the
  DataGrid below `md`. Every UI change must pass `scripts/screenshots.py --check` (seed the demo
  data first; DEVELOPING.md has the commands) and the screenshots in `recordings/screens/`
  should be looked at, not just the exit code.
- README screenshots come only from `scripts/screenshots.py --readme` on the seeded demo data,
  **never from real data** or a real browser session. `check_pii.py` can't read images: look at
  every image before committing it.

## E-paper display

The test unit is a reTerminal E1001 on `/dev/ttyUSB0`. ESPHome and esptool live in the gitignored
`esphome-venv/`; Wi-Fi details are in `display/esphome/secrets.yaml` (gitignored). The user
sometimes has to power-cycle the unit: ask, don't retry in a loop.

**Screenshots of the display come from the preview, never from a photo of a real screen.**

1. Serve the demo data on :8087, with the Skyward login blanked so it can't sign in:
   `SKYWARD_DATA_DIR=recordings/demo SKYWARD_BASE_URL= SKYWARD_USER= SKYWARD_PASS= uv run uvicorn
   app.main:app --host 0.0.0.0 --port 8087` (run in the background; `seed_demo.py` first if
   `recordings/demo/` is empty). `--host 0.0.0.0` lets the unit fetch from it too.
2. `uv run python scripts/display_preview.py` builds `display/esphome/tests/preview.yaml` for
   ESPHome's host platform (needs `g++`), runs the real layout lambda against the dashboard and
   writes every page and status screen to `recordings/display-preview/*.png`. It refuses any
   dashboard with non-demo students. What it draws is the panel's output pixel for pixel, except
   ink bleed (white text on black looks thinner on the panel).
3. Look at the PNGs with Read. To inspect glyphs, crop and scale a region (1-bit PNGs are easy
   to decode with `zlib`; no Pillow). To compare variants, render each and put them side by
   side, then send the image with SendUserFile: the user can't see what Read shows you.
4. DISPLAY.md's `docs/screenshots/display-overview.png` is a copy of the preview's
   `student0-overview.png`. Look at it before committing.

Before changing a font size, run `esphome-venv/bin/python scripts/font_stems.py` on the font
(ESPHome caches gfonts in `display/esphome/.esphome/font/`) and pick a size that's 90%+ even.

Building and flashing:

- Wrap every compile in `systemd-run --user --scope -p MemoryMax=8G -p CPUWeight=20 nice -n 19`.
  An uncapped first ESP-IDF or LVGL build froze the user's desktop.
- `esphome-venv/bin/esphome upload <config> --device /dev/ttyUSB0`, then capture logs to a file
  with `timeout N esphome logs ... > file` in the background (piping them through grep buffers
  until exit). Only one process can hold the port: stop a log capture with TaskStop, never
  `pkill -f` a pattern that matches your own command line.
- Measure a change on the unit (`Awake N ms` in the log) before assuming it's cheap. The only
  way to see a real panel is to ask the user for a photo.

## Supply chain

Every published image reaches every install (`latest`, `pull_policy: always`), so every input
stays pinned. DEVELOPING.md's *Supply chain* section is the full list; the rules:

- GitHub Actions by full commit SHA with the version in a comment. Base images by digest and
  only from Docker Hub (`scripts/check_base_images.sh`, run in CI, enforces both): Dependabot's
  cooldown needs publish dates, which ghcr.io doesn't provide. uv comes from PyPI, hash-pinned in
  `tools/uv/requirements.txt`, the one uv pin for both the Dockerfile and CI.
- Python only from `uv.lock`; the image installs with `--require-hashes --only-binary=:all:`.
  Never `pip install` by name in the Dockerfile or CI, and don't add a `[build-system]`.
- npm only via `npm ci` from `package-lock.json`. Keep `frontend/.npmrc`'s `ignore-scripts`; if a
  new package needs an install script, don't add it.
- Keep dependencies few. Justify any new one in its PR (what it does, why a few lines of code
  won't do); prefer packages already in the lock. Nothing that phones home.
- Dependabot waits 7 days and skips majors. When reviewing its PR, read the lock diff. A PR
  saying "Cooldown could not be applied" is a blocker: check the release date by hand, and fix
  the source so the cooldown works rather than merging early. Major
  upgrades (React, MUI, Vite, a new Python) are their own PR with code changes. Don't loosen
  `.github/dependabot.yml`.

## Branches, pull requests and releases

- Work on a branch, never on `main`. Commit each logical change on its own. Push the branch and
  open a pull request with `gh pr create`.
- **Never merge a PR, push to `main`, or create a tag or GitHub release.** A person merges.
  Your job ends when the PR is open and its CI is green.
- Merging to `main` releases when `pyproject.toml` has a version with no `v<version>` tag: CI
  publishes the image as `latest`/`<version>`, tags the commit and creates the release from
  `docs/releases/<version>.md`. So a release PR bumps the version in `pyproject.toml` and
  `frontend/package.json`, refreshes both locks (`uv lock`, and
  `npm --prefix frontend install --package-lock-only`) and adds the notes file.
- **Every PR you open is a release**: bump the version and add notes, even for small changes.
  Before 1.0, patch (`0.1.0` → `0.1.1`) for fixes, hardening, dependency updates and docs; minor
  (`0.1.1` → `0.2.0`) for features and anything users must act on, and say what to do. Bump from
  the latest *tag*.
- Release notes are for people running the app, in the voice of README.md: what changed for them
  and how to upgrade. Not a commit log. They must pass the privacy rules like everything else.
- Dependabot PRs merge without releasing. After a Dependabot *security* update merges, suggest a
  patch release.
- `stable` is the last release, moved only by the release job with the `STABLE_DEPLOY_KEY`
  deploy key (two rulesets refuse anything else). It's there for a future Home Assistant add-on,
  which the Supervisor reads from git. Never push to it.

