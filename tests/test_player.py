import asyncio
from dataclasses import replace

import pytest

from vcplayer.resolver import PlayerError


async def test_play_queue_auto_advance_and_leave(player, track):
    await player.add("first")
    await player.add("second")
    assert player.current == track and len(player.queue) == 1
    assert player.resolver.source.await_count == 1  # queued URLs resolved just in time
    await player.ended()
    assert player.current == track and not player.queue
    assert player.resolver.source.await_count == 2
    await player.ended()
    assert player.current is None
    player.transport.leave.assert_awaited_once()


async def test_queue_is_bounded_before_lookup(player):
    player.settings = replace(player.settings, max_queue=1)
    await player.add("first")
    await player.add("second")
    with pytest.raises(PlayerError, match="full"):
        await player.add("third")
    assert player.resolver.lookup.await_count == 2
    await player.stop()


async def test_skip_bad_queued_track(player, track):
    await player.add("first")
    await player.add("second")
    await player.add("third")
    player.resolver.source.side_effect = [
        PlayerError("Unavailable"),
        player.resolver.source.return_value,
    ]
    assert "Playing" in await player.skip()
    assert not player.queue and player.current == track
    assert "Skipped" in player.notify.await_args_list[0].args[0]
    await player.stop()


async def test_stop_cancels_extraction_and_clears_queue(player):
    entered = asyncio.Event()

    async def slow(*_):
        entered.set()
        await asyncio.Event().wait()

    player.resolver.lookup.side_effect = slow
    task = asyncio.create_task(player.add("slow"))
    await entered.wait()
    await player.stop()
    assert task.cancelled()
    assert not player.queue and player.current is None and player._idle_task is None
    player.transport.leave.assert_awaited_once()


async def test_busy_commands_fail_without_starting_more_extractors(player):
    async with player.operation():
        with pytest.raises(PlayerError, match="busy"):
            await player.add("more")
    player.resolver.lookup.assert_not_awaited()


async def test_pause_resume_and_idle_disconnect(player):
    player.settings = replace(player.settings, idle_seconds=0.01)
    await player.add("first")
    await player.pause()
    assert player.paused
    await player.resume()
    assert player._idle_task is None and not player.paused
    await player.pause()
    timer = player._idle_task
    await asyncio.wait_for(timer, 1)
    assert player.current is None
    player.transport.leave.assert_awaited_once()


async def test_stop_is_idempotent(player):
    await player.stop()
    await player.stop()
    assert player.current is None and not player.queue


async def test_mode_quality_apply_to_next_track(player):
    await player.add("first")
    await player.add("second")
    await player.set_mode("audio")
    await player.set_quality(240)
    assert player.resolver.source.await_count == 1
    await player.skip()
    assert player.resolver.source.await_args.args[1:] == ("audio", 240)
    await player.stop()


async def test_volume_remove_clear(player):
    await player.set_volume(50)
    player.transport.volume.assert_not_awaited()
    await player.add("first")
    player.transport.volume.assert_awaited_with(50)
    await player.add("second")
    with pytest.raises(PlayerError):
        await player.remove(0)
    await player.remove(1)
    assert not player.queue
    await player.add("third")
    await player.clear()
    assert not player.queue and player.current
    await player.stop()


@pytest.mark.parametrize(
    "method,value",
    [("set_volume", 101), ("set_volume", 0), ("set_mode", "4k"), ("set_quality", 1080)],
)
async def test_invalid_settings(player, method, value):
    with pytest.raises(PlayerError):
        await getattr(player, method)(value)


async def test_failed_start_arms_cleanup(player):
    player.transport.play.side_effect = RuntimeError("Synthetic failure")
    with pytest.raises(RuntimeError):
        await player.add("first")
    assert player.current is None and player._idle_task is not None
    await player.stop()


async def test_volume_failure_does_not_skip_playing_track(player):
    player.transport.volume.side_effect = RuntimeError("No permission")
    await player.add("first")
    assert player.current
    player.notify.assert_awaited_once()
    await player.stop()


async def test_ended_while_paused_does_not_advance(player):
    await player.add("first")
    await player.add("second")
    await player.pause()
    await player.ended()
    assert len(player.queue) == 1
    await player.stop()


async def test_end_event_waits_for_lookup_without_stalling_queue(player, track):
    await player.add("first")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow(*_):
        entered.set()
        await release.wait()
        return replace(track, title="Second")

    player.resolver.lookup.side_effect = slow
    adding = asyncio.create_task(player.add("second"))
    await entered.wait()
    ending = asyncio.create_task(player.ended())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(adding, ending)
    assert player.current.title == "Second" and not player.queue
    await player.stop()


async def test_delayed_end_for_replaced_track_ignored(player, track):
    await player.add("first")
    player.queue.append(replace(track, title="Second"))
    async with player.operation():
        ending = asyncio.create_task(player.ended())
        await asyncio.sleep(0)
        await player._advance()
    await ending
    assert player.current.title == "Second"
    await player.stop()
