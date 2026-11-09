import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from vcplayer.resolver import PlayerError, Resolver, youtube_query


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/jNQXAC9IVRw?t=1",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=ignore",
        "youtube.com/shorts/jNQXAC9IVRw",
        "https://m.youtube.com/live/jNQXAC9IVRw",
    ],
)
def test_youtube_urls_canonicalized(url):
    assert youtube_query(url) == "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video",
        "file:///etc/passwd",
        "https://youtube.com/playlist?list=foo",
        "https://youtube.com.evil/watch?v=jNQXAC9IVRw",
        "https://user@youtube.com/watch?v=jNQXAC9IVRw",
        "",
        "a" * 251,
    ],
)
def test_non_video_urls_rejected(url):
    with pytest.raises(PlayerError):
        youtube_query(url)


def test_search_not_executed_as_url_or_shell():
    assert youtube_query("cats; $(whoami)") == "ytsearch1:cats; $(whoami)"


async def test_flat_search_result(settings):
    resolver = Resolver(settings)
    resolver._extract = AsyncMock(
        return_value={"entries": [{"id": "jNQXAC9IVRw", "title": "Example", "duration": 19}]}
    )
    track = await resolver.lookup("example")
    assert track.duration == 19
    assert resolver._extract.await_args.args == ("ytsearch1:example", "--flat-playlist")


@pytest.mark.parametrize(
    "extra",
    [{"is_live": True}, {"live_status": "is_upcoming"}, {"duration": None}, {"duration": 7201}],
)
async def test_unbounded_media_rejected(settings, extra):
    resolver = Resolver(settings)
    resolver._extract = AsyncMock(return_value={"id": "jNQXAC9IVRw", "duration": 19, **extra})
    with pytest.raises(PlayerError):
        await resolver.lookup("example")


async def test_separate_audio_video_and_quality_cap(settings, track):
    resolver = Resolver(settings)
    resolver._extract = AsyncMock(
        return_value={
            "id": track.video_id,
            "duration": 19,
            "http_headers": {"User-Agent": "test"},
            "requested_formats": [
                {"url": "https://media.example/video", "vcodec": "avc1", "acodec": "none"},
                {"url": "https://media.example/audio", "vcodec": "none", "acodec": "opus"},
            ],
        }
    )
    source = await resolver.source(track, "video", 240)
    assert source.video_url.endswith("video") and source.audio_url.endswith("audio")
    assert source.duration == 19
    fmt = resolver._extract.await_args.args[2]
    assert fmt.count("height<=240") == 4 and "360" not in fmt
    source = await resolver.source(track, "audio", 240)
    assert source.video_url.endswith("audio") and source.audio_url is None


async def test_extractor_process_reaped_on_cancellation(settings, monkeypatch):
    process = AsyncMock(returncode=None)
    process.kill = lambda: setattr(process, "returncode", -9)
    entered = asyncio.Event()

    async def slow(_):
        entered.set()
        await asyncio.Event().wait()

    process.stdout.read.side_effect = slow
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    task = asyncio.create_task(Resolver(settings)._extract("ytsearch1:hello"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode == -9
    process.wait.assert_awaited_once()


async def test_extractor_timeout_kills_process(settings, monkeypatch):
    settings = replace(settings, extract_timeout_seconds=0.01)
    process = AsyncMock(returncode=None)
    process.kill = lambda: setattr(process, "returncode", -9)

    async def slow(_):
        await asyncio.Event().wait()

    process.stdout.read.side_effect = slow
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(TimeoutError):
        await Resolver(settings)._extract("ytsearch1:hello")
    assert process.returncode == -9


async def test_extractor_output_limit(settings, monkeypatch):
    process = AsyncMock(returncode=None)
    process.kill = lambda: setattr(process, "returncode", -9)
    process.stdout.read.return_value = b"x" * (4 * 1024 * 1024 + 1)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(PlayerError, match="large"):
        await Resolver(settings)._extract("ytsearch1:hello")
    assert process.returncode == -9


async def test_extractor_argv_and_json(settings, monkeypatch):
    process = AsyncMock(returncode=0)
    process.stdout.read.side_effect = [json.dumps({"id": "jNQXAC9IVRw"}).encode(), b""]
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    assert await Resolver(settings)._extract("ytsearch1:$(uname)") == {"id": "jNQXAC9IVRw"}
    assert spawn.await_args.args[-2:] == ("--", "ytsearch1:$(uname)")
