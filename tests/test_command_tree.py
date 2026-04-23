from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bot.commands import HelpCog, PlaybackCog, QueueCog
from bot.voice import GuildVoiceStateManager


@pytest.fixture
async def cogs(settings):
    bot = MagicMock()
    crawler = MagicMock()
    voice_states = GuildVoiceStateManager(settings)
    try:
        yield [
            cls(
                bot,
                settings=settings,
                crawler=crawler,
                voice_states=voice_states,
            )
            for cls in (PlaybackCog, QueueCog, HelpCog)
        ]
    finally:
        await voice_states.close_all()


def _all_command_names(cogs) -> set[str]:
    names: set[str] = set()
    for cog in cogs:
        names.update(cmd.name for cmd in cog.get_app_commands())
    return names


def test_cog_exposes_expected_slash_commands(cogs):
    names = _all_command_names(cogs)
    expected = {
        'mi',
        'leave',
        'now',
        'pause',
        'resume',
        'skip',
        'queue',
        'shuffle',
        'remove',
        'loop',
        'volume',
        'help',
    }
    assert expected.issubset(names), f'Missing: {expected - names}'


def test_help_embed_lists_every_command(cogs):
    names = _all_command_names(cogs)
    assert names
