from unittest.mock import AsyncMock

from pytgcalls.ffmpeg import build_command
from pytgcalls.types import MediaStream
from pytgcalls.types.raw import VideoParameters

from vcplayer.resolver import Source
from vcplayer.transport import CallTransport


async def test_real_stream_parameters_and_thread_limits(settings):
    calls = AsyncMock()
    transport = CallTransport(calls, settings)
    await transport.play(
        Source("https://media.example/video", "https://media.example/audio", {}, 19), "video", 360
    )
    calls.resume.assert_awaited_once_with(settings.chat_id)
    stream = calls.play.await_args.args[1]
    assert stream._video_parameters.height == 360
    assert stream._video_parameters.frame_rate == 15
    assert calls.play.await_args.args[2].auto_start is False
    command = build_command(
        "ffmpeg",
        stream._ffmpeg_parameters,
        "https://media.example/video",
        VideoParameters(640, 360, 15),
    )
    assert command[command.index("-threads") + 1] == "1"
    assert command[command.index("-filter_threads") + 1] == "1"
    assert command[command.index("-t") + 1] == "19"
    await transport.play(Source("https://media.example/audio", None, {}, 19), "audio", 240)
    stream = calls.play.await_args.args[1]
    assert stream._video_flags == MediaStream.Flags.IGNORE
    assert stream.camera is None
