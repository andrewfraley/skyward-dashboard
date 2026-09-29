"""Settings from environment variables (and ./.env when running locally)."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every 3 hours from 6am to 9pm local time. Skyward allows one session per
# account, so each sync may sign the parent out of a browser session.
DEFAULT_SYNC_CRON = "0 6-21/3 * * *"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), _unquote(value.strip()))


def _unquote(value: str) -> str:
    """Strip one pair of matching quotes, and only a pair: a password may end in one."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


@dataclass(frozen=True)
class Settings:
    base_url: str
    username: str
    password: str
    data_dir: Path
    sync_cron: str
    timezone: str | None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "skyward.db"

    @property
    def cookie_path(self) -> Path:
        """Skyward cookies kept between syncs, so each sync isn't a new-device sign-in."""
        return self.data_dir / "skyward-cookies.json"

    @property
    def has_credentials(self) -> bool:
        return bool(self.base_url and self.username and self.password)


UTC_NAMES = {"UTC", "Etc/UTC", "Etc/UCT", "UCT", "GMT", "Etc/GMT", "Zulu", "Etc/Zulu"}


def timezone_warning(timezone: str | None) -> str | None:
    """A warning to log when the timezone is unset or UTC, which is rarely where a family is.

    The schedule runs in it and the e-paper display shows times in it, while the web UI shows
    the browser's local time, so a wrong TZ is easy to miss.
    """
    if timezone and timezone not in UTC_NAMES:
        return None
    return (
        f"TZ is {'not set' if not timezone else timezone}: the sync schedule and the times on an "
        "e-paper display are in UTC. If you're elsewhere, set TZ in docker-compose.yml, such "
        "as TZ=America/Chicago, and run `docker compose up -d`."
    )


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        base_url=os.environ.get("SKYWARD_BASE_URL", "").rstrip("/"),
        username=os.environ.get("SKYWARD_USER", ""),
        password=os.environ.get("SKYWARD_PASS", ""),
        data_dir=Path(os.environ.get("SKYWARD_DATA_DIR", ROOT / "data")),
        sync_cron=os.environ.get("SKYWARD_SYNC_CRON", DEFAULT_SYNC_CRON),
        timezone=os.environ.get("TZ") or None,
    )
