from unittest.mock import AsyncMock

import pytest

from vcplayer.config import Settings
from vcplayer.player import Player
from vcplayer.resolver import Source, Track


@pytest.fixture
def settings(tmp_path):
    return Settings(
        1,
        "synthetic-hash",
        "synthetic-token",
        -100123,
        frozenset({7}),
        state_dir=tmp_path / "state",
    )


@pytest.fixture
def track():
    return Track("jNQXAC9IVRw", "Example video", 19)


@pytest.fixture
def player(settings, track):
    resolver = AsyncMock()
    resolver.lookup.return_value = track
    resolver.source.return_value = Source("https://media.example/video", None, {}, 19)
    return Player(settings, resolver, AsyncMock(), AsyncMock())
