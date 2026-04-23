from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.voice.manager import GuildVoiceStateManager
from bot.voice.state import GuildVoiceState


@pytest.fixture
def state(settings):
    return GuildVoiceState(
        guild_id=42,
        idle_timeout_seconds=1,
        skip_vote_threshold=settings.skip_vote_threshold,
        default_volume=settings.default_volume,
    )


async def test_is_playing_false_without_voice(state):
    assert state.is_playing is False


async def test_register_skip_vote_tracks_voters(state):
    assert state.register_skip_vote(1) == 1
    assert state.register_skip_vote(2) == 2
    assert state.register_skip_vote(1) == 2  # idempotent


async def test_skip_clears_votes_and_stops_voice(state):
    voice = MagicMock()
    voice.is_playing.return_value = True
    state.voice = voice
    state.register_skip_vote(1)
    state.register_skip_vote(2)

    state.skip()

    assert state.skip_votes == set()
    voice.stop.assert_called_once()


async def test_player_loop_reaps_on_timeout(settings):
    reaped: list[int] = []

    async def on_idle(guild_id: int) -> None:
        reaped.append(guild_id)

    state = GuildVoiceState(
        guild_id=7,
        idle_timeout_seconds=0,  # immediate timeout
        skip_vote_threshold=settings.skip_vote_threshold,
        default_volume=settings.default_volume,
        on_idle=on_idle,
    )
    state.start()
    await asyncio.sleep(0.05)  # let the loop run one iteration
    assert reaped == [7]


@pytest.fixture
async def manager(settings):
    mgr = GuildVoiceStateManager(settings)
    try:
        yield mgr
    finally:
        await mgr.close_all()


async def test_manager_get_or_create_returns_same_instance(manager):
    first = await manager.get_or_create(123)
    second = await manager.get_or_create(123)
    assert first is second


async def test_manager_parallel_get_or_create_no_duplicate(manager):
    results = await asyncio.gather(
        *(manager.get_or_create(999) for _ in range(20))
    )
    assert all(s is results[0] for s in results)


async def test_manager_drop_reaps_state(manager):
    state = await manager.get_or_create(55)
    voice = AsyncMock()
    state.voice = voice
    await manager.drop(55)
    assert manager.get(55) is None
    voice.disconnect.assert_awaited_once()


async def test_reap_callback_removes_entry_from_manager(manager):
    state = await manager.get_or_create(17)
    assert manager.get(17) is state
    try:
        await manager._reap(17)
        assert manager.get(17) is None
    finally:
        await state.close()
