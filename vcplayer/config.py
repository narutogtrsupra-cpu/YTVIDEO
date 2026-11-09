import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    chat_id: int
    owner_ids: frozenset[int]
    allow_group_admins: bool = True
    default_mode: str = "video"
    video_height: int = 360
    video_fps: int = 15
    ffmpeg_threads: int = 1
    default_volume: int = 70
    max_queue: int = 20
    max_duration_seconds: int = 7200
    idle_seconds: int = 60
    extract_timeout_seconds: int = 45
    state_dir: Path = Path(".state")
    cookies_file: Path | None = None

    @classmethod
    def load(cls):
        load_dotenv()

        def required(name):
            value = os.getenv(name, "").strip()
            if not value:
                raise ValueError(f"Set {name} in .env")
            return value

        def integer(name, default, low, high):
            try:
                value = int(os.getenv(name, str(default)))
            except ValueError:
                raise ValueError(f"{name} must be an integer") from None
            if not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
            return value

        try:
            owners = frozenset(int(v.strip()) for v in required("OWNER_IDS").split(","))
        except ValueError:
            raise ValueError("OWNER_IDS must contain comma-separated positive user IDs") from None
        if not owners or min(owners) <= 0:
            raise ValueError("OWNER_IDS must contain positive user IDs")
        mode = os.getenv("DEFAULT_MODE", "video").lower()
        if mode not in {"audio", "video"}:
            raise ValueError("DEFAULT_MODE must be audio or video")
        height = integer("VIDEO_HEIGHT", 360, 240, 360)
        if height not in {240, 360}:
            raise ValueError("VIDEO_HEIGHT must be 240 or 360")
        admins = os.getenv("ALLOW_GROUP_ADMINS", "true").lower()
        if admins not in {"true", "false"}:
            raise ValueError("ALLOW_GROUP_ADMINS must be true or false")
        cookies = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
        if cookies and not Path(cookies).is_file():
            raise ValueError("YOUTUBE_COOKIES_FILE must point to an existing file")
        return cls(
            api_id=integer("API_ID", 0, 1, 2**31 - 1),
            api_hash=required("API_HASH"),
            bot_token=required("BOT_TOKEN"),
            chat_id=integer("CHAT_ID", 0, -(2**63), -1),
            owner_ids=owners,
            allow_group_admins=admins == "true",
            default_mode=mode,
            video_height=height,
            video_fps=integer("VIDEO_FPS", 15, 5, 20),
            ffmpeg_threads=integer("FFMPEG_THREADS", 1, 1, 2),
            default_volume=integer("DEFAULT_VOLUME", 70, 1, 100),
            max_queue=integer("MAX_QUEUE", 20, 1, 50),
            max_duration_seconds=integer("MAX_DURATION_SECONDS", 7200, 30, 14400),
            idle_seconds=integer("IDLE_SECONDS", 60, 10, 600),
            extract_timeout_seconds=integer("EXTRACT_TIMEOUT_SECONDS", 45, 10, 120),
            state_dir=Path(os.getenv("STATE_DIR", ".state")),
            cookies_file=Path(cookies) if cookies else None,
        )

    def prepare_state(self):
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_dir.chmod(0o700)
