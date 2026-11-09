import asyncio
import os

from telethon import TelegramClient

from .config import Settings


async def login(settings):
    async with TelegramClient(
        str(settings.state_dir / "assistant"), settings.api_id, settings.api_hash
    ) as client:
        me = await client.get_me()
        if me.bot:
            raise ValueError("Sign in with a Telegram user account, not the control bot.")
        # Cache dialogs so Telethon can resolve the configured numeric group ID.
        async for _ in client.iter_dialogs():
            pass
        print("Assistant session saved. Keep .state private. You can now run vc-player.")


def main():
    os.umask(0o077)
    try:
        settings = Settings.load()
        settings.prepare_state()
        asyncio.run(login(settings))
    except (ValueError, EOFError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
