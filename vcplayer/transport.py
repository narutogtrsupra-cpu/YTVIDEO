import asyncio

from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import GroupCallConfig, MediaStream
from pytgcalls.types.raw import AudioParameters, VideoParameters


class CallTransport:
    def __init__(self, calls, settings):
        self.calls = calls
        self.settings = settings

    async def play(self, source, mode, height):
        stream = MediaStream(
            source.video_url,
            audio_path=source.audio_url,
            audio_parameters=AudioParameters(48000, 1),
            video_parameters=VideoParameters(
                640 if height == 360 else 426, height, self.settings.video_fps
            ),
            audio_flags=MediaStream.Flags.REQUIRED,
            video_flags=(
                MediaStream.Flags.IGNORE if mode == "audio" else MediaStream.Flags.REQUIRED
            ),
            headers=source.headers,
            ffmpeg_parameters=(
                f"-threads {self.settings.ffmpeg_threads} -filter_threads 1 "
                f"-rw_timeout 15000000 -atend -threads 1 -t {source.duration}"
            ),
        )
        # Calls and probes must not hold the command lock indefinitely.
        async with asyncio.timeout(90):
            await self.calls.play(self.settings.chat_id, stream, GroupCallConfig(auto_start=False))
            # Replacing a paused native stream can preserve its paused state.
            await self.calls.resume(self.settings.chat_id)

    async def pause(self):
        async with asyncio.timeout(20):
            await self.calls.pause(self.settings.chat_id)

    async def resume(self):
        async with asyncio.timeout(20):
            await self.calls.resume(self.settings.chat_id)

    async def volume(self, value):
        async with asyncio.timeout(20):
            await self.calls.change_volume_call(self.settings.chat_id, value)

    async def leave(self):
        try:
            async with asyncio.timeout(20):
                await self.calls.leave_call(self.settings.chat_id)
        except (NotInCallError, NoActiveGroupCall):
            pass
