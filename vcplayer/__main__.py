import asyncio
import logging
import os
import shutil
import signal

from pytgcalls import PyTgCalls
from pytgcalls.types import Device, StreamEnded
from telethon import TelegramClient

from .bot import Controller
from .config import Settings
from .player import Player
from .resolver import Resolver
from .transport import CallTransport


async def run(settings):
    for binary in ("ffmpeg", "ffprobe", "node"):
        if not shutil.which(binary):
            raise ValueError(f"Install {binary} before starting. See README.md.")
    assistant = TelegramClient(
        str(settings.state_dir / "assistant"), settings.api_id, settings.api_hash
    )
    bot = TelegramClient(str(settings.state_dir / "bot"), settings.api_id, settings.api_hash)
    player = None
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await assistant.connect()
        if not await assistant.is_user_authorized():
            raise ValueError("Run vc-login once to sign in to the assistant user account.")
        if (await assistant.get_me()).bot:
            raise ValueError("The assistant must be a Telegram user account. Run vc-login again.")
        await assistant.get_entity(settings.chat_id)
        await bot.start(bot_token=settings.bot_token)
        calls = PyTgCalls(assistant)

        async def notify(message):
            try:
                await bot.send_message(
                    settings.chat_id, message[:3900], parse_mode=None, link_preview=False
                )
            except Exception:
                logging.getLogger(__name__).warning("Could not send a player notification")

        player = Player(settings, Resolver(settings), CallTransport(calls, settings), notify)
        controller = Controller(bot, player, settings, (await bot.get_me()).username)
        controller.install()

        @calls.on_update()
        async def stream_ended(_, update):
            if (
                isinstance(update, StreamEnded)
                and update.chat_id == settings.chat_id
                and update.stream_type == StreamEnded.Type.AUDIO
                and update.device == Device.MICROPHONE
            ):
                try:
                    await player.ended()
                except Exception:
                    await notify("Queue advance failed. Use /stop, then /play to reconnect.")

        await calls.start()
        print("Player ready. Use /help in Telegram. Press Ctrl+C to stop.", flush=True)
        # Exit if a client disconnects permanently as well as on process signals.
        waiters = [
            asyncio.create_task(stopped.wait()),
            asyncio.ensure_future(bot.disconnected),
            asyncio.ensure_future(assistant.disconnected),
        ]
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
    finally:
        try:
            if player:
                await player.stop()
        finally:
            await bot.disconnect()
            await assistant.disconnect()


def main():
    os.umask(0o077)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    # Upstream debug/info output may include media and authentication details.
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
    logging.getLogger("pytgcalls").setLevel(logging.CRITICAL)
    try:
        settings = Settings.load()
        settings.prepare_state()
        asyncio.run(run(settings))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit(
            f"Startup failed ({type(exc).__name__}). Check configuration and connectivity."
        ) from None


if __name__ == "__main__":
    main()
