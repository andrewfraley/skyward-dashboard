# Security

Skyward Dashboard holds a parent's school login and a child's school records, so security
reports are taken seriously.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this
repository. Don't open a public issue, and don't include anyone's real school data, names or
credentials in a report; describe the problem with made-up examples.

## What to expect from the project

- **Your data stays with you.** The app talks only to your district's Skyward server and keeps
  what it fetches in `./data` on your machine. It sends nothing anywhere else: no analytics, no
  telemetry, no third-party services.
- **No personal data in the repository.** Tests use scrubbed, made-up fixtures, and every commit
  is checked for identifying information (see `scripts/check_pii.py`).
- **Pinned supply chain.** Every dependency is pinned: GitHub Actions by commit SHA, base images
  by digest, Python packages by hash, npm packages by lockfile integrity. npm install scripts are
  disabled, and Python installs wheels only. Updates arrive as reviewed pull requests after a
  seven-day cooldown.
- **Verifiable images.** Published images carry build provenance and an SBOM:
  `docker buildx imagetools inspect afraley/skyward-dashboard:latest --format '{{ json .Provenance }}'`.

## Running it safely

- The dashboard has no login of its own. Keep it on your home network, or put it behind a
  reverse proxy with authentication. Don't expose port 8080 to the internet.
- `.env` holds your Skyward password in plain text, and `data/` holds your child's grades. Keep
  both readable only by you (`chmod 600 .env`).
