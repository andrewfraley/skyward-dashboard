# Developing Skyward Dashboard

FastAPI + React, one container, one `/data` volume with a SQLite file.

```
app/skyward/session.py  HTTP session: sign-in, page parsing, grid (GetBrowse) and panel requests
app/skyward/parse.py    Skyward HTML/JSON → models
app/skyward/client.py   one sync's worth of fetching: grades, breakdowns, assignments
app/db.py               SQLite: latest state, grade history, the changes feed
app/sync.py             the only code that talks to Skyward; one sync at a time
app/main.py             FastAPI routes over the cache, the cron schedule, the built UI
frontend/src/           React + MUI, Vite build
scripts/                tools for studying Skyward, capturing fixtures, and the PII check
```

## Running from source

```sh
cp .env.example .env                      # your Skyward address and login
git config core.hooksPath .githooks       # the PII check on every commit (see Privacy)
uv sync                                   # .venv, pinned to uv.lock, with the dev tools
uv run pytest                             # no network, no Skyward
uv run python -m app.sync                 # one real sync into ./data
uv run uvicorn app.main:app --port 8087 --reload

npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run dev             # UI on :5173, proxying /api to :8087
```

Without Node installed, run npm in a container:

```sh
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $PWD/frontend:/ui:z -w /ui node:22-alpine npm ci
```

`docker compose up -d --build` builds and runs the working tree, because
`docker-compose.override.yml` (present only in a checkout) swaps the published image for
`build: .`. Set `SKYWARD_PORT=8088` in `.env` to run it beside something already on 8080.

Python is formatted with Black and `frontend/` with Prettier, both at 100 columns
(`uv run black .`, `npm --prefix frontend run format`). CI fails on anything they would change.

## How the Skyward client works

`app/skyward/session.py` explains it in detail. In short:

- **Sign-in:** a form POST to `/StudentSTS`, then a hand-off form that establishes the session.
- **Page state:** each page embeds a CSRF token, window ids, and a config per data grid.
- **Grid data:** rows come from `POST …/GetBrowse`, built from that config.
- **Grade detail:** percentages and categories come from the breakdown panel behind each grade.
- **Assignments:** the page's Current Term / All Year filter is a saved preference. The sync sets
  All Year and always puts Current back.
- **Site root:** `/` resets the connection, so the client never requests it.
- **Cookies persist** in `data/skyward-cookies.json` (owner-only). Skyward sets a long-lived
  device cookie at sign-in and emails the parent about sign-ins from new devices; keeping it
  means a sync that has to sign in again looks like the same device, and keeping the session
  cookie means a sync soon after the last one doesn't sign in at all. The sync log says which
  happened. The dev scripts share the file, so studying the site doesn't flood the inbox either.

If Skyward changes and a sync starts failing, the tools in `scripts/` help find what moved. They
need Playwright, which isn't installed by default:

```sh
uv sync --group tools && uv run playwright install chromium
uv run python scripts/record_session.py        # visible browser; you click, it records
uv run python scripts/explore.py --menu PATH   # headless: logs in from .env, records PATH
```

Recordings go to `recordings/`, which is gitignored: they contain your session cookies and your
student's data. Passwords are redacted before anything is written.

## Privacy

This project handles children's school records, and the repository must never contain anything
that identifies a family: names, Skyward ids, schools, districts, hosts, real course or
assignment titles.

- **`scripts/check_pii.py`** takes its list of sensitive terms from local, gitignored sources:
  `.env`, `data/skyward.db`, and an optional `.pii-terms` file of anything else (one term per
  line). It then scans every file git would commit, and prints only the kind of match, never the
  term itself. It runs as the pre-commit hook and in `tests/test_no_pii.py`.
- **`tests/test_fixture_hygiene.py`** runs everywhere, CI included, and needs no private data. It
  checks that fixtures carry only placeholder hashes, tokens, hosts and names.
- **Fixtures come only from `scripts/capture_fixtures.py`**, which replaces names, titles, ids,
  hashes and hosts with stand-ins, then deletes its output if `check_pii.py` flags anything.
  Review the diff before committing. Never hand-copy a real response into `tests/`.

## Supply chain

Everyone runs `latest` with `pull_policy: always`, so anything that reaches a published image
reaches every install. Every input is pinned, and nothing updates on its own:

- **GitHub Actions** by full commit SHA with the version in a comment. The repository refuses
  unpinned actions.
- **Base images** by digest (`python:3.12-slim@sha256:…`), and only from Docker Hub.
  Dependabot's cooldown needs the registry to report when an image was published; ghcr.io and
  others don't, so Dependabot proposes their new images immediately.
  `scripts/check_base_images.sh` (run in CI) fails on any image that isn't digest-pinned or is
  hosted elsewhere.
- **uv**, which the image build and CI both use, comes from PyPI (where the cooldown works), hash-pinned in
  `tools/uv/requirements.txt`. The Dockerfile installs it with `--require-hashes
  --only-binary=:all:`, and CI's `setup-uv` reads its version from the same file. Dependabot
  updates it; to change it by hand, follow the comment at the top of that file.
- **Python** only from `uv.lock`, installed in the image with `--require-hashes` and
  `--only-binary=:all:`: every file is hash-checked and no package's build code runs. There is no
  `[build-system]`, since the app runs from source and building it would fetch a build backend
  unpinned. Don't `pip install` anything by name in the Dockerfile or CI.
- **npm** only from `package-lock.json` via `npm ci`. `frontend/.npmrc` sets `ignore-scripts`, so
  no package runs an install script, and `save-exact` for anything newly added.
- **Few dependencies.** Plain `uvicorn` rather than `uvicorn[standard]`; Playwright only in the
  opt-in `tools` group. Think twice before adding a dependency, and prefer a few lines of code.
- **Dependabot** (`.github/dependabot.yml`) proposes updates weekly as grouped PRs, only after a
  release is seven days old (hijacked packages are usually caught and pulled within days), and
  never major versions or new Python/Node versions. Read the lock diff before merging: a hash
  proves you got the version you asked for, not that the version is safe.
- **Published images** carry build provenance and an SBOM:
  `docker buildx imagetools inspect afraley/skyward-dashboard:latest --format '{{ json .Provenance }}'`.

After changing dependencies in `pyproject.toml`, run `uv lock`. To take newer versions
deliberately, `uv lock --upgrade`, run the tests, and commit the lock.

## Releases

`.github/workflows/docker.yml` checks formatting, runs the Python and JS tests, then builds a
`linux/amd64` + `linux/arm64` image. Pull requests only build it. Pushes publish it to Docker Hub:

| Push | Tags |
|---|---|
| `main`, releasing a new version (below) | `latest`, `1.2.3`, `1.2`, `main`, `sha-<commit>` |
| `main`, no new version (e.g. a Dependabot bump) | `main`, `sha-<commit>` |
| any other branch, e.g. `new-feature` | `new-feature`, `sha-<commit>` |

`latest` is always the newest release. Nothing else moves it, so work in progress, or a merge that
doesn't release, never reaches anyone.

**Changes reach `main` only through pull requests, and a person merges them.**

**Releasing is a pull request that bumps the version.** In that PR:

1. Set the new version in `pyproject.toml` and `frontend/package.json`, then run `uv lock` and
   `npm --prefix frontend install --package-lock-only` so both lock files follow. CI fails if the
   versions differ or `uv.lock` is stale.
2. Add release notes as `docs/releases/<version>.md`, written for people running the app. CI
   fails on a PR whose version has no tag and no notes file.

When the PR merges, the `main` build sees a version with no `v<version>` tag. It pushes the image
as `latest`, `<version>` and `<major>.<minor>`, then tags the merge commit and creates the GitHub
release from the notes file.

**The `stable` branch is the last release, for a Home Assistant add-on.** The Supervisor reads an
add-on's `config.yaml` straight from git, so if it read `main` it would offer a new version the
moment a PR merged, minutes before that image reached Docker Hub. Once the image is pushed and
the GitHub release created, the release job pushes the merge commit to `stable`.

- It pushes with a deploy key, because the workflow's own token may not push a commit that
  changes `.github/workflows/`. The private key is the `STABLE_DEPLOY_KEY` secret in the
  `release` environment, which only `main` can use.
- Two rulesets guard `stable`. "Only the release job moves stable" lets nothing but a deploy key
  update it. "Protect stable", which nothing bypasses, refuses deletion, force pushes, unsigned
  commits and commits without passing `test` and `image` checks.
- `stable` is left out of branch builds, since a deploy-key push starts a workflow run.
- If moving `stable` fails, re-run the job. It skips the existing release, and pushing the same
  commit again does nothing.

To rotate the key:

```sh
ssh-keygen -t ed25519 -N "" -C "skyward-dashboard release job: stable branch" -f stable
gh repo deploy-key add stable.pub --allow-write --title "Release job: move stable"
gh secret set STABLE_DEPLOY_KEY --env release < stable
shred -u stable stable.pub
gh repo deploy-key list    # then delete the old one: gh repo deploy-key delete <id>
```

Dependabot PRs can't bump the version, so they merge without releasing and ship with the next
release. After merging a Dependabot *security* update, release soon rather than waiting.

## GitHub setup (once, by the maintainer)

Publishing needs a repository **variable** `DOCKERHUB_USERNAME` and a **secret**
`DOCKERHUB_TOKEN` (a dedicated Docker Hub personal access token for this project, Read & Write). Without them
the workflow still builds and skips the push.

Repository settings that the model above relies on:

```sh
repo=andrewfraley/skyward-dashboard

# Actions: require SHA-pinned actions; the workflow token is read-only unless a job asks for more.
gh api -X PUT repos/$repo/actions/permissions -F enabled=true -f allowed_actions=all -F sha_pinning_required=true
gh api -X PUT repos/$repo/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false

# Secret scanning with push protection, and Dependabot security updates.
gh api -X PATCH repos/$repo -F 'security_and_analysis[secret_scanning][status]=enabled' \
  -F 'security_and_analysis[secret_scanning_push_protection][status]=enabled' -F delete_branch_on_merge=true
gh api -X PUT repos/$repo/vulnerability-alerts
gh api -X PUT repos/$repo/automated-security-fixes
gh api -X PUT repos/$repo/private-vulnerability-reporting

# The release job's environment: only main may deploy to it.
gh api -X PUT repos/$repo/environments/release --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
gh api -X POST repos/$repo/environments/release/deployment-branch-policies -f name=main -f type=branch
```

The `stable` deploy key, its secret and its two rulesets are described under *Releases* above.

And a ruleset protecting `main`: no deletion or force pushes, signed commits, changes only
through pull requests, and the `test` and `image` checks passing:

```sh
gh api -X POST repos/$repo/rulesets --input - <<'JSON'
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_signatures"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false,
      "require_last_push_approval": false, "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
      "required_status_checks": [{"context": "test"}, {"context": "image"}]}}
  ]
}
JSON
```
