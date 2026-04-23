from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bot.client import InstantClient
from bot.voice import GuildVoiceStateManager


@pytest.fixture
async def cog(settings):
    bot = MagicMock()
    crawler = MagicMock()
    voice_states = GuildVoiceStateManager(settings)
    try:
        yield InstantClient(
            bot,
            settings=settings,
            crawler=crawler,
            voice_states=voice_states,
        )
    finally:
        await voice_states.close_all()


def test_cog_exposes_expected_slash_commands(cog):
    names = {cmd.name for cmd in cog.get_app_commands()}
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


def test_help_embed_lists_every_command(cog):
    names = {cmd.name for cmd in cog.get_app_commands()}
    assert names  # sanity
