# Every input is pinned: base images by digest as well as tag (a tag can be
# re-pointed, a digest can't), Python packages by hash from uv.lock, npm
# packages by integrity hash from package-lock.json, and uv itself by hash
# from tools/uv/requirements.txt. Dependabot proposes updates, each only once
# it's a week old; see .github/dependabot.yml. Base images come only from
# Docker Hub, where that cooldown works (CI checks this).

# ---- build the React UI ----------------------------------------------------
# The output is static files, so build it natively even for an arm64 image
# rather than running npm under emulation.
FROM --platform=$BUILDPLATFORM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS ui

WORKDIR /ui
# .npmrc turns off install scripts, so no package runs code during npm ci.
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- pinned dependencies ---------------------------------------------------
# uv.lock turned into a plain requirements file with hashes, so the runtime
# image installs exactly what CI tested and doesn't need uv itself. uv comes
# from PyPI, hash-checked and wheels only (see tools/uv/requirements.txt for
# why not the uv image).
FROM --platform=$BUILDPLATFORM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS lock

COPY tools/uv/requirements.txt /tmp/uv-requirements.txt
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/uv-requirements.txt
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-emit-project --no-dev -o /requirements.txt

# ---- runtime ---------------------------------------------------------------
# No browser here: the Skyward client is plain HTTP (httpx). Playwright is a
# dev-only tool for studying the site.
FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SKYWARD_DATA_DIR=/data

WORKDIR /srv

# Dependencies before the app, so a code change doesn't reinstall them. Every
# line in requirements.txt carries hashes, and --require-hashes refuses anything
# that doesn't match. --only-binary means wheels only: building an sdist would
# run its setup code. The app itself runs from source rather than being built
# into a package, because building one would fetch a build backend unpinned.
COPY --from=lock /requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt
COPY pyproject.toml ./
COPY app/ ./app/

COPY --from=ui /ui/dist/ ./static/

# Starts as root only long enough for the entrypoint to claim /data, then runs
# as PUID:PGID.
COPY scripts/entrypoint.sh /usr/local/bin/skyward-entrypoint
RUN mkdir -p /data

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/ping', timeout=4).status == 200 else 1)"

ENTRYPOINT ["skyward-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
