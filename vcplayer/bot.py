import asyncio
import logging

from telethon import Button, events

from .resolver import PlayerError

log = logging.getLogger(__name__)
HELP = """YouTube voice chat player
/play <YouTube link or search> — play or queue
/pause /resume /skip /stop
/queue /clear /remove <position>
/volume <1–100>
/mode audio|video — next track
/quality 240|360 — next track
/status — current track and controls
/help

Start a group video chat first. Audio mode uses less CPU and battery.
Only configured owners and enabled group admins can control playback.
The queue and settings reset when the process restarts."""
BUTTONS = [
    [Button.inline("Pause", b"pause"), Button.inline("Resume", b"resume")],
    [Button.inline("Skip", b"skip"), Button.inline("Stop", b"stop")],
    [Button.inline("Queue", b"queue"), Button.inline("Status", b"status")],
]


async def authorized(event, bot, settings):
    if event.sender_id is None:
        return False
    if event.is_private:
        return event.sender_id in settings.owner_ids
    if event.chat_id != settings.chat_id:
        return False
    if event.sender_id in settings.owner_ids:
        return True
    if not settings.allow_group_admins:
        return False
    try:
        permissions = await bot.get_permissions(event.chat_id, event.sender_id)
        return bool(permissions.is_admin or permissions.is_creator)
    except Exception:
        return False


class Controller:
    def __init__(self, bot, player, settings, username):
        self.bot = bot
        self.player = player
        self.settings = settings
        self.username = username.lower()
        self._pending = set()

    async def execute(self, command, argument):
        player = self.player
        if command in {"help", "start"}:
            return HELP
        if command in {"status", "now"}:
            return player.status()
        if command == "queue":
            return player.queue_text()
        if command == "play":
            return await player.add(argument)
        if command in {"pause", "resume", "skip", "stop", "clear"}:
            return await getattr(player, command)()
        if command == "mode":
            return await player.set_mode(argument.lower())
        if command in {"volume", "quality", "remove"}:
            try:
                value = int(argument)
            except ValueError:
                raise PlayerError(f"/{command} needs a number. See /help.") from None
            method = {
                "volume": player.set_volume,
                "quality": player.set_quality,
                "remove": player.remove,
            }[command]
            return await method(value)
        raise PlayerError("Unknown command. Use /help.")

    async def handle(self, event, callback=False):
        if not await authorized(event, self.bot, self.settings):
            if callback:
                await event.answer("You do not have permission to control this player.", alert=True)
            return
        if callback:
            command, argument = event.data.decode("ascii"), ""
            await event.answer()
        else:
            token, _, argument = event.raw_text.partition(" ")
            target = token.partition("@")[2]
            if target and target.lower() != self.username:
                return
            command = token.partition("@")[0].lstrip("/").lower()
            argument = argument.strip()
        # Bound pending requests from each controller; /stop always remains available.
        if event.sender_id in self._pending and command != "stop":
            await event.respond("Your previous command is still running. Use /stop to cancel.")
            return
        owns_pending = command != "stop"
        if owns_pending:
            self._pending.add(event.sender_id)
        try:
            response = await self.execute(command, argument)
        except PlayerError as exc:
            response = str(exc)
        except asyncio.CancelledError:
            # /stop cancels an in-progress lookup or playback setup.
            raise
        except Exception as exc:
            # Exception messages may contain signed media URLs or session data.
            log.warning("Command failed (%s)", type(exc).__name__)
            response = (
                "Playback/control failed. Start the group video chat, add the assistant "
                "account, and allow it to speak and share video. Then try /stop and /play."
            )
        finally:
            if owns_pending:
                self._pending.discard(event.sender_id)
        await event.respond(response[:3900], buttons=BUTTONS, parse_mode=None, link_preview=False)

    def install(self):
        self.bot.add_event_handler(self.handle, events.NewMessage(incoming=True, pattern=r"^/"))

        async def callback(event):
            await self.handle(event, callback=True)

        self.bot.add_event_handler(
            callback, events.CallbackQuery(pattern=rb"^(pause|resume|skip|stop|queue|status)$")
        )
