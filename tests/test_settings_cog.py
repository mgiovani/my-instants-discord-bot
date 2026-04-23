from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.commands.settings import SettingsCog, _parse_update
from bot.db.models import Base
from bot.db.repositories import GuildSettingsRepository
from bot.privacy import hash_guild
from bot.voice.manager import GuildVoiceStateManager


@pytest.fixture
async def session_factory():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def settings_repo(session_factory):
    return GuildSettingsRepository(session_factory)


@pytest.fixture
async def manager(settings, settings_repo):
    mgr = GuildVoiceStateManager(settings, settings_repo=settings_repo)
    try:
        yield mgr
    finally:
        await mgr.close_all()


@pytest.fixture
def cog(settings, settings_repo, manager):
    return SettingsCog(
        MagicMock(),
        settings=settings,
        repo=settings_repo,
        voice_states=manager,
    )


def _interaction(guild_id: int = 1):
    response = MagicMock()
    response.send_message = AsyncMock()
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response = response
    interaction.user = SimpleNamespace(id=2)
    return interaction


async def test_view_defaults_before_any_override(cog):
    interaction = _interaction()
    await cog.view.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs['ephemeral'] is True
    embed = call.kwargs['embed']
    assert 'default' in embed.description


async def test_set_idle_timeout_persists(cog, settings_repo, settings):
    interaction = _interaction(guild_id=1234)
    await cog.set_.callback(cog, interaction, 'idle_timeout', '600')
    secret = settings.require_pii_hash_key().get_secret_value()
    row = await settings_repo.get(hash_guild(1234, secret=secret))
    assert row is not None
    assert row.idle_timeout_seconds == 600


async def test_reset_clears_overrides(cog, settings_repo, settings):
    interaction = _interaction(guild_id=5555)
    await cog.set_.callback(cog, interaction, 'volume', '75')
    await cog.reset.callback(cog, interaction)
    secret = settings.require_pii_hash_key().get_secret_value()
    row = await settings_repo.get(hash_guild(5555, secret=secret))
    assert row is None


async def test_new_voice_state_reads_persisted_idle_timeout(
    manager, settings_repo, settings
):
    secret = settings.require_pii_hash_key().get_secret_value()
    await settings_repo.upsert(
        hash_guild(42, secret=secret), idle_timeout_seconds=900
    )
    state = await manager.get_or_create(42)
    assert state.idle_timeout_seconds == 900


async def test_voice_state_falls_back_to_defaults_without_row(
    manager, settings
):
    state = await manager.get_or_create(77)
    assert state.idle_timeout_seconds == settings.idle_timeout_seconds
    assert state.skip_vote_threshold == settings.skip_vote_threshold
    assert state.volume == settings.default_volume


@pytest.mark.parametrize(
    ('key', 'raw', 'expected'),
    [
        ('idle_timeout', '600', {'idle_timeout_seconds': 600}),
        ('skip_votes', '3', {'skip_vote_threshold': 3}),
        ('volume', '75', {'default_volume_pct': 75}),
        ('locale', 'pt-BR', {'locale': 'pt-BR'}),
    ],
)
def test_parse_update_happy_paths(key, raw, expected):
    assert _parse_update(key, raw) == expected


@pytest.mark.parametrize(
    ('key', 'raw'),
    [
        ('idle_timeout', '5'),  # below range
        ('idle_timeout', 'abc'),
        ('skip_votes', '0'),  # below range
        ('volume', '150'),
        ('locale', 'x'),  # too short
    ],
)
def test_parse_update_rejects_invalid_values(key, raw):
    with pytest.raises(ValueError):
        _parse_update(key, raw)
