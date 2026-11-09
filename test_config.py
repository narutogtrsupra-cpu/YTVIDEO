import os

import pytest

from vcplayer.config import Settings


@pytest.fixture
def env(monkeypatch):
    # Do not read or depend on a developer's local .env.
    monkeypatch.setattr("vcplayer.config.load_dotenv", lambda: None)
    for key in list(os.environ):
        if key in {
            "API_ID",
            "API_HASH",
            "BOT_TOKEN",
            "CHAT_ID",
            "OWNER_IDS",
            "VIDEO_HEIGHT",
            "DEFAULT_MODE",
            "ALLOW_GROUP_ADMINS",
        }:
            monkeypatch.delenv(key)
    for key, value in {
        "API_ID": "1",
        "API_HASH": "synthetic",
        "BOT_TOKEN": "synthetic",
        "CHAT_ID": "-100123",
        "OWNER_IDS": "7,8",
    }.items():
        monkeypatch.setenv(key, value)


def test_config_defaults_and_private_state(env, tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    settings = Settings.load()
    assert settings.owner_ids == frozenset({7, 8}) and settings.video_height == 360
    settings.prepare_state()
    assert settings.state_dir.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    "key,value",
    [
        ("CHAT_ID", "1"),
        ("API_ID", "0"),
        ("OWNER_IDS", "bad"),
        ("VIDEO_HEIGHT", "1080"),
        ("DEFAULT_MODE", "4k"),
        ("ALLOW_GROUP_ADMINS", "yes"),
    ],
)
def test_invalid_config(env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings.load()
