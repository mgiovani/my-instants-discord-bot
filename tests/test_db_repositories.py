from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.db.models import Base, PlayHistory
from bot.db.repositories import (
    FavoriteRepository,
    GuildSettingsRepository,
    PlayHistoryRepository,
)


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


async def test_guild_settings_upsert_and_read(session_factory):
    repo = GuildSettingsRepository(session_factory)
    assert await repo.get('g1') is None

    await repo.upsert('g1', idle_timeout_seconds=600, skip_vote_threshold=5)
    row = await repo.get('g1')
    assert row is not None
    assert row.idle_timeout_seconds == 600
    assert row.skip_vote_threshold == 5

    # Second upsert replaces partial values without clobbering others
    await repo.upsert('g1', idle_timeout_seconds=900)
    row = await repo.get('g1')
    assert row is not None
    assert row.idle_timeout_seconds == 900


async def test_guild_settings_delete(session_factory):
    repo = GuildSettingsRepository(session_factory)
    await repo.upsert('g2', locale='pt-BR')
    await repo.delete('g2')
    assert await repo.get('g2') is None


async def test_favorites_add_list_and_remove(session_factory):
    repo = FavoriteRepository(session_factory)
    fav = await repo.add(
        user_hash='u1',
        guild_hash='g1',
        instant_id='i1',
        instant_name='Cat meow',
        page_url='https://ex.com/i1',
        mp3_url='https://ex.com/i1.mp3',
    )
    assert fav.instant_id == 'i1'

    listed = await repo.list_for(user_hash='u1', guild_hash='g1')
    assert len(listed) == 1

    # duplicate add returns existing row instead of blowing up
    dup = await repo.add(
        user_hash='u1',
        guild_hash='g1',
        instant_id='i1',
        instant_name='Cat meow',
        page_url=None,
        mp3_url=None,
    )
    assert dup.id == fav.id

    removed = await repo.remove(
        user_hash='u1', guild_hash='g1', instant_id='i1'
    )
    assert removed is True
    assert await repo.list_for(user_hash='u1', guild_hash='g1') == []


async def test_favorites_scoped_per_user_and_guild(session_factory):
    repo = FavoriteRepository(session_factory)
    await repo.add(
        user_hash='u1',
        guild_hash='g1',
        instant_id='i1',
        instant_name='n',
        page_url=None,
        mp3_url=None,
    )
    await repo.add(
        user_hash='u2',
        guild_hash='g1',
        instant_id='i1',
        instant_name='n',
        page_url=None,
        mp3_url=None,
    )
    await repo.add(
        user_hash='u1',
        guild_hash='g2',
        instant_id='i1',
        instant_name='n',
        page_url=None,
        mp3_url=None,
    )
    u1g1 = await repo.list_for(user_hash='u1', guild_hash='g1')
    u1g2 = await repo.list_for(user_hash='u1', guild_hash='g2')
    u2g1 = await repo.list_for(user_hash='u2', guild_hash='g1')
    assert len(u1g1) == 1
    assert len(u1g2) == 1
    assert len(u2g1) == 1


async def test_play_history_record_and_recent(session_factory):
    repo = PlayHistoryRepository(session_factory)
    await repo.record(
        user_hash='u',
        guild_hash='g',
        instant_id='i1',
        instant_name='n1',
    )
    await repo.record(
        user_hash='u',
        guild_hash='g',
        instant_id='i2',
        instant_name='n2',
    )
    recent = await repo.recent_for_user(
        user_hash='u', guild_hash='g', limit=10
    )
    assert [r.instant_id for r in recent] == ['i2', 'i1']


async def test_play_history_top_in_guild(session_factory):
    repo = PlayHistoryRepository(session_factory)
    for _ in range(3):
        await repo.record(
            user_hash='u',
            guild_hash='g',
            instant_id='popular',
            instant_name='Popular',
        )
    await repo.record(
        user_hash='u',
        guild_hash='g',
        instant_id='niche',
        instant_name='Niche',
    )
    top = await repo.top_in_guild(guild_hash='g', days=30, limit=10)
    assert top[0].instant_id == 'popular'
    assert top[0].plays == 3
    assert {t.instant_id for t in top} == {'popular', 'niche'}


async def test_play_history_prune(session_factory):
    repo = PlayHistoryRepository(session_factory)
    # Insert via repo, then backdate via direct session
    await repo.record(
        user_hash='u',
        guild_hash='g',
        instant_id='x',
        instant_name='X',
    )
    async with session_factory() as session:
        row = (await session.execute(PlayHistory.__table__.select())).one()
        id_ = row.id
        past = datetime.now(UTC) - timedelta(days=400)
        await session.execute(
            PlayHistory.__table__.update()
            .where(PlayHistory.id == id_)
            .values(played_at=past)
        )
        await session.commit()
    pruned = await repo.prune_older_than(days=180)
    assert pruned == 1
