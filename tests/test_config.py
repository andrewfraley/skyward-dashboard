"""Settings from .env."""

import os

import pytest

from app.config import load_dotenv, timezone_warning


@pytest.mark.parametrize(
    "raw, value",
    [
        ('"quoted"', "quoted"),
        ("'single'", "single"),
        ('ends"', 'ends"'),
        ("'", "'"),
        ("a$b", "a$b"),
    ],
)
def test_env_values_lose_only_a_matching_pair_of_quotes(tmp_path, monkeypatch, raw, value):
    monkeypatch.delenv("SKYWARD_TEST_VALUE", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"SKYWARD_TEST_VALUE={raw}\n")
    load_dotenv(env)
    assert os.environ.pop("SKYWARD_TEST_VALUE") == value


@pytest.mark.parametrize("tz", [None, "", "UTC", "Etc/UTC"])
def test_timezone_warning_when_unset_or_utc(tz):
    assert "TZ=America/Chicago" in timezone_warning(tz)


def test_no_timezone_warning_for_a_local_zone():
    assert timezone_warning("America/Chicago") is None
