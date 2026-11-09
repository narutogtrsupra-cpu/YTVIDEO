import asyncio
from collections import deque
from contextlib import asynccontextmanager, suppress

from .resolver import PlayerError


class Player:
    """One call, one bounded queue, and one extraction/playback operation at a time."""

    def __init__(self, settings, resolver, transport, notify):
        self.settings = settings
        self.resolver = resolver
        self.transport = transport
        self.notify = notify
        self.queue = deque()
        self.current = None
        self.paused = False
        self.mode = settings.default_mode
        self.height = settings.video_height
        self.volume = settings.default_volume
        self._lock = asyncio.Lock()
        self._operation = None
        self._idle_task = None

    @asynccontextmanager
    async def operation(self, *, wait=False):
        if self._lock.locked() and not wait:
            raise PlayerError("Player is busy. Try again shortly, or /stop to cancel.")
        async with self._lock:
            self._operation = asyncio.current_task()
            try:
                yield
            finally:
                self._operation = None

    def _cancel_idle(self):
        if self._idle_task and self._idle_task is not asyncio.current_task():
            self._idle_task.cancel()
        self._idle_task = None

    def _arm_idle(self):
        self._cancel_idle()
        self._idle_task = asyncio.create_task(self._idle_disconnect())

    async def _idle_disconnect(self):
        await asyncio.sleep(self.settings.idle_seconds)
        # Stop also clears paused tracks so they cannot hold a call indefinitely.
        try:
            await self.stop()
            await self.notify("Disconnected after the idle timeout.")
        except Exception:
            await self.notify("Idle disconnect failed. Use /stop to retry.")

    async def add(self, query):
        async with self.operation():
            if len(self.queue) >= self.settings.max_queue:
                raise PlayerError("Queue is full. Use /remove or /clear first.")
            track = await self.resolver.lookup(query)
            if self.current:
                self.queue.append(track)
                return f"Queued #{len(self.queue)}: {track.title}"
            await self._play(track)
            return f"Playing: {track.title}"

    async def _play(self, track):
        self._cancel_idle()
        try:
            source = await self.resolver.source(track, self.mode, self.height)
            await self.transport.play(source, self.mode, self.height)
        except BaseException:
            self.current = None
            self.paused = False
            self._arm_idle()
            raise
        self.current = track
        self.paused = False
        try:
            await self.transport.volume(self.volume)
        except Exception:
            await self.notify("Playing, but volume could not be set. Check assistant permissions.")

    async def _advance(self):
        self.current = None
        self.paused = False
        # Continue past inaccessible items, with at most MAX_QUEUE attempts.
        while self.queue:
            track = self.queue.popleft()
            try:
                await self._play(track)
                return f"Playing: {track.title}"
            except PlayerError as exc:
                await self.notify(f"Skipped {track.title}: {exc}")
            except Exception:
                await self.notify(f"Could not stream {track.title}; skipped.")
        await self.transport.leave()
        self._cancel_idle()
        return "Queue finished; left the call."

    async def ended(self):
        # Wait for metadata lookup without losing the end event. If another
        # operation replaced/stopped this track, its delayed event is obsolete.
        expected = self.current
        if expected is None:
            return
        async with self.operation(wait=True):
            if self.current is not expected or self.paused:
                return
            await self.notify(await self._advance())

    async def skip(self):
        async with self.operation():
            if not self.current:
                raise PlayerError("Nothing is playing.")
            return await self._advance()

    async def pause(self):
        async with self.operation():
            if not self.current:
                raise PlayerError("Nothing is playing.")
            await self.transport.pause()
            self.paused = True
            self._arm_idle()
            return f"Paused. Disconnecting in {self.settings.idle_seconds}s if not resumed."

    async def resume(self):
        async with self.operation():
            if not self.current:
                raise PlayerError("Nothing to resume. Use /play.")
            await self.transport.resume()
            self.paused = False
            self._cancel_idle()
            return "Resumed."

    async def set_volume(self, value):
        if not 1 <= value <= 100:
            raise PlayerError("Volume must be 1–100.")
        async with self.operation():
            if self.current:
                await self.transport.volume(value)
            self.volume = value
            return f"Volume: {value}%"

    async def stop(self):
        running = self._operation
        if running and running is not asyncio.current_task():
            running.cancel()
            with suppress(asyncio.CancelledError):
                await running
        async with self.operation():
            self._cancel_idle()
            self.queue.clear()
            self.current = None
            self.paused = False
            await self.transport.leave()
            return "Stopped, cleared queue, and left the call."

    async def clear(self):
        async with self.operation():
            self.queue.clear()
            return "Queue cleared."

    async def remove(self, position):
        async with self.operation():
            if not 1 <= position <= len(self.queue):
                raise PlayerError("Choose a queue position from /queue.")
            track = self.queue[position - 1]
            del self.queue[position - 1]
            return f"Removed: {track.title}"

    async def set_mode(self, mode):
        if mode not in {"audio", "video"}:
            raise PlayerError("Use /mode audio or /mode video.")
        async with self.operation():
            self.mode = mode
            return f"Mode: {mode}. Applies to the next track."

    async def set_quality(self, height):
        if height not in {240, 360}:
            raise PlayerError("Use /quality 240 or /quality 360.")
        async with self.operation():
            self.height = height
            return f"Video quality: {height}p. Applies to the next track."

    def status(self):
        track = self.current.title if self.current else "Nothing playing"
        state = "paused" if self.paused else "playing" if self.current else "idle"
        return (
            f"{track}\nState: {state} | Volume: {self.volume}%\n"
            f"Next track: {self.mode}, {self.height}p/{self.settings.video_fps}fps\n"
            f"Queue: {len(self.queue)}/{self.settings.max_queue}"
        )

    def queue_text(self):
        return (
            "\n".join(f"{i}. {t.title[:65]}" for i, t in enumerate(self.queue, 1))
            or "Queue is empty."
        )
