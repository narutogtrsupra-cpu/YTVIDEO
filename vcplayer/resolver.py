import asyncio
import json
import re
import sys
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


class PlayerError(Exception):
    """A safe, actionable error that can be shown in Telegram."""


@dataclass(frozen=True)
class Track:
    video_id: str
    title: str
    duration: int

    @property
    def url(self):
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True)
class Source:
    video_url: str
    audio_url: str | None
    headers: dict
    duration: int


def youtube_query(text: str) -> str:
    text = text.strip()
    if not text or len(text) > 250:
        raise PlayerError("Send a YouTube link or search text (up to 250 characters).")
    if "://" not in text and not text.startswith(("www.", "youtu.be/", "youtube.com/")):
        return f"ytsearch1:{text}"
    parsed = urlparse(text if "://" in text else "https://" + text)
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.port:
        raise PlayerError("Use a regular YouTube video link.")
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        video_id = parsed.path.strip("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        parts = parsed.path.strip("/").split("/")
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        raise PlayerError("Only YouTube video links are supported.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise PlayerError("Send a single YouTube video, not a playlist or channel.")
    return f"https://www.youtube.com/watch?v={video_id}"


class Resolver:
    def __init__(self, settings):
        self.settings = settings

    async def _extract(self, query, *options):
        args = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            "--no-cache-dir",
            "--socket-timeout",
            "12",
            "--retries",
            "1",
            "--extractor-retries",
            "1",
            "--js-runtimes",
            "node",
            *options,
        ]
        if self.settings.cookies_file:
            args += ["--cookies", str(self.settings.cookies_file)]
        args += ["--", query]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(self.settings.extract_timeout_seconds):
                # Bound extractor output rather than buffering an arbitrary JSON response.
                output = bytearray()
                while chunk := await proc.stdout.read(65536):
                    output.extend(chunk)
                    if len(output) > 4 * 1024 * 1024:
                        raise PlayerError("Video metadata is too large. Try another video.")
                await proc.wait()
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            raise PlayerError(
                "YouTube could not load this video. It may be restricted or need an updated "
                "yt-dlp, JavaScript runtime, or cookies. Try another public video."
            )
        try:
            return json.loads(output)
        except (ValueError, TypeError):
            raise PlayerError("YouTube returned invalid metadata. Try again.") from None

    def _track(self, info):
        video_id = info.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise PlayerError("No matching YouTube video found.")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise PlayerError("Live and upcoming streams are disabled to limit resource use.")
        duration = int(info.get("duration") or 0)
        if not 0 < duration <= self.settings.max_duration_seconds:
            raise PlayerError(
                f"Choose a video under {self.settings.max_duration_seconds // 60} minutes "
                "with a known duration."
            )
        return Track(video_id, str(info.get("title") or "YouTube video")[:160], duration)

    async def lookup(self, text):
        try:
            info = await self._extract(youtube_query(text), "--flat-playlist")
        except (TimeoutError, ValueError):
            raise PlayerError(
                "YouTube lookup timed out or the link is invalid. Try again."
            ) from None
        entries = info.get("entries")
        if entries is not None:
            info = next((item for item in entries if item), {})
        return self._track(info)

    async def source(self, track, mode, height):
        if mode == "audio":
            fmt = "bestaudio[acodec!=none]/best[acodec!=none]"
        else:
            fmt = (
                f"best[height<={height}][vcodec^=avc1][acodec!=none]/"
                f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio/"
                f"best[height<={height}][vcodec!=none][acodec!=none]/"
                f"bestvideo[height<={height}]+bestaudio"
            )
        try:
            info = await self._extract(track.url, "--format", fmt)
        except TimeoutError:
            raise PlayerError("Video extraction timed out. Try again.") from None
        validated = self._track(info)  # Recheck immediately before playback.
        formats = info.get("requested_formats") or [info]
        video = next((v for v in formats if v.get("vcodec") != "none"), formats[0])
        audio = next((v for v in formats if v.get("acodec") != "none"), formats[0])
        selected = audio if mode == "audio" else video
        if not selected.get("url") or not audio.get("url"):
            raise PlayerError("No usable stream was returned for this video.")
        # Never expose signed media URLs or cookies in Telegram or application logs.
        return Source(
            selected["url"],
            audio["url"] if mode == "video" else None,
            info.get("http_headers") or selected.get("http_headers") or {},
            validated.duration,
        )
