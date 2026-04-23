from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands import HelpCog, PlaybackCog, QueueCog
from bot.exceptions import (
    EmptyQueueError,
    NothingPlayingError,
    NotInVoiceError,
)
from bot.voice import GuildVoiceStateManager


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def crawler():
    return MagicMock()


@pytest.fixture
async def manager(settings):
    mgr = GuildVoiceStateManager(settings)
    try:
        yield mgr
    finally:
        await mgr.close_all()


@pytest.fixture
def playback_cog(bot, crawler, manager, settings):
    return PlaybackCog(
        bot,
        settings=settings,
        crawler=crawler,
        voice_states=manager,
    )


@pytest.fixture
def queue_cog(bot, crawler, manager, settings):
    return QueueCog(
        bot,
        settings=settings,
        crawler=crawler,
        voice_states=manager,
    )


@pytest.fixture
def help_cog(bot, crawler, manager, settings):
    return HelpCog(
        bot,
        settings=settings,
        crawler=crawler,
        voice_states=manager,
    )


def _interaction(
    guild_id: int = 1,
    *,
    user_in_voice: bool = False,
    user_id: int = 99,
):
    user_voice = None
    if user_in_voice:
        channel = MagicMock()
        channel.id = 77
        user_voice = SimpleNamespace(channel=channel)

    user = MagicMock()
    user.id = user_id
    user.voice = user_voice

    response = MagicMock()
    response.is_done.return_value = False
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
    followup = MagicMock()
    followup.send = AsyncMock()

    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user = user
    interaction.channel = MagicMock(send=AsyncMock())
    interaction.response = response
    interaction.followup = followup
    return interaction


async def test_leave_without_state_replies_not_connected(playback_cog):
    interaction = _interaction()
    await playback_cog.leave.callback(playback_cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs['ephemeral'] is True


async def test_leave_drops_state_and_sends_message(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = MagicMock()
    interaction = _interaction()
    await playback_cog.leave.callback(playback_cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    assert manager.get(1) is None


async def test_now_raises_when_nothing_playing(playback_cog):
    interaction = _interaction()
    with pytest.raises(NothingPlayingError):
        await playback_cog.now.callback(playback_cog, interaction)


async def test_queue_raises_when_empty(queue_cog):
    interaction = _interaction()
    with pytest.raises(EmptyQueueError):
        await queue_cog.queue.callback(queue_cog, interaction)


async def test_shuffle_raises_when_empty(queue_cog):
    interaction = _interaction()
    with pytest.raises(EmptyQueueError):
        await queue_cog.shuffle.callback(queue_cog, interaction)


async def test_loop_requires_currently_playing(playback_cog):
    interaction = _interaction()
    with pytest.raises(NothingPlayingError):
        await playback_cog.loop.callback(playback_cog, interaction)


async def test_pause_when_nothing_playing_raises(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = MagicMock()
    state.voice.is_playing.return_value = False
    interaction = _interaction()
    with pytest.raises(NothingPlayingError):
        await playback_cog.pause.callback(playback_cog, interaction)


async def test_volume_out_of_range_replies_ephemerally(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = MagicMock()
    state.current = MagicMock()
    interaction = _interaction()
    await playback_cog.volume.callback(playback_cog, interaction, 250)
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs['ephemeral'] is True


async def test_volume_updates_current_source(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = MagicMock()
    state.current = SimpleNamespace(source=SimpleNamespace(volume=0.5))
    interaction = _interaction()
    await playback_cog.volume.callback(playback_cog, interaction, 80)
    assert state.current.source.volume == pytest.approx(0.8)


async def test_skip_as_requester_skips_directly(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = MagicMock()
    state.voice.is_playing.return_value = True

    interaction = _interaction(user_id=42)
    state.current = SimpleNamespace(requester=interaction.user)
    await playback_cog.skip.callback(playback_cog, interaction)
    state.voice.stop.assert_called_once()


async def test_skip_requires_voice(playback_cog, manager):
    state = await manager.get_or_create(1)
    state.voice = None
    interaction = _interaction()
    with pytest.raises(NothingPlayingError):
        await playback_cog.skip.callback(playback_cog, interaction)


async def test_play_requires_user_in_voice(playback_cog):
    interaction = _interaction(user_in_voice=False)
    with pytest.raises(NotInVoiceError):
        await playback_cog.play.callback(playback_cog, interaction, 'foo')


async def test_remove_on_empty_queue_raises(queue_cog):
    interaction = _interaction()
    with pytest.raises(EmptyQueueError):
        await queue_cog.remove.callback(queue_cog, interaction, 1)


async def test_help_is_ephemeral(help_cog):
    interaction = _interaction()
    await help_cog.help_command.callback(help_cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs['ephemeral'] is True


async def test_notify_sink_passes_embed_as_kwarg(playback_cog, manager):
    interaction = _interaction()
    state = await playback_cog._state_for(interaction)
    import discord

    embed = discord.Embed(title='t', description='d')
    await state._notify(embed)
    interaction.channel.send.assert_awaited_once()
    call = interaction.channel.send.await_args
    assert call.kwargs.get('embed') is embed
    assert not call.args
