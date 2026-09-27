"""Settings from .env."""

import os

import pytest

from app.config import load_dotenv


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
