from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vcplayer.bot import Controller, authorized


@pytest.mark.parametrize(
    "sender,chat,private,admin,expected",
    [
        (7, 7, True, False, True),
        (8, 8, True, True, False),
        (7, -999, False, True, False),
        (8, -100123, False, False, False),
        (8, -100123, False, True, True),
        (None, -100123, False, True, False),
    ],
)
async def test_permissions(settings, sender, chat, private, admin, expected):
    bot = AsyncMock()
    bot.get_permissions.return_value = SimpleNamespace(is_admin=admin, is_creator=False)
    event = SimpleNamespace(sender_id=sender, chat_id=chat, is_private=private)
    assert await authorized(event, bot, settings) is expected


async def test_admin_access_can_be_disabled(settings):
    event = SimpleNamespace(sender_id=8, chat_id=settings.chat_id, is_private=False)
    bot = AsyncMock()
    assert not await authorized(event, bot, replace(settings, allow_group_admins=False))
    bot.get_permissions.assert_not_awaited()


async def test_callback_permissions_rechecked(settings, player):
    event = AsyncMock(sender_id=8, chat_id=settings.chat_id, is_private=False)
    bot = AsyncMock()
    bot.get_permissions.return_value = SimpleNamespace(is_admin=False, is_creator=False)
    await Controller(bot, player, settings, "player_bot").handle(event, callback=True)
    event.answer.assert_awaited_once()
    event.respond.assert_not_awaited()
    player.transport.leave.assert_not_awaited()


async def test_commands_for_other_bots_ignored(settings, player):
    event = AsyncMock(sender_id=7, chat_id=7, is_private=True, raw_text="/stop@other_bot")
    await Controller(AsyncMock(), player, settings, "player_bot").handle(event)
    player.transport.leave.assert_not_awaited()


async def test_titles_sent_as_plain_text(settings, player):
    event = AsyncMock(sender_id=7, chat_id=7, is_private=True, raw_text="/status")
    await Controller(AsyncMock(), player, settings, "player_bot").handle(event)
    assert event.respond.await_args.kwargs["parse_mode"] is None
