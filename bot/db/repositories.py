from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bot.db.models import (
    Favorite as FavoriteRow,
)
from bot.db.models import (
    GuildSettings as GuildSettingsRow,
)
from bot.db.models import (
    PlayHistory as PlayHistoryRow,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class GuildSettingsDTO:
    idle_timeout_seconds: int | None
    skip_vote_threshold: int | None
    default_volume_pct: int | None
    locale: str | None


@dataclass(frozen=True, slots=True)
class FavoriteDTO:
    id: int
    instant_id: str
    instant_name: str
    page_url: str | None
    mp3_url: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlayHistoryDTO:
    id: int
    instant_id: str
    instant_name: str
    played_at: datetime


@dataclass(frozen=True, slots=True)
class TopInstantDTO:
    instant_id: str
    instant_name: str
    plays: int


def _session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncSession:
    return session_factory()


class GuildSettingsRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(self, guild_hash: str) -> GuildSettingsDTO | None:
        async with _session(self._session_factory) as session:
            row = await session.get(GuildSettingsRow, guild_hash)
        if row is None:
            return None
        return GuildSettingsDTO(
            idle_timeout_seconds=row.idle_timeout_seconds,
            skip_vote_threshold=row.skip_vote_threshold,
            default_volume_pct=row.default_volume_pct,
            locale=row.locale,
        )

    async def upsert(
        self,
        guild_hash: str,
        *,
        idle_timeout_seconds: int | None = None,
        skip_vote_threshold: int | None = None,
        default_volume_pct: int | None = None,
        locale: str | None = None,
    ) -> None:
        values = {
            'guild_hash': guild_hash,
            'idle_timeout_seconds': idle_timeout_seconds,
            'skip_vote_threshold': skip_vote_threshold,
            'default_volume_pct': default_volume_pct,
            'locale': locale,
        }
        stmt = sqlite_insert(GuildSettingsRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GuildSettingsRow.guild_hash],
            set_={k: v for k, v in values.items() if k != 'guild_hash'},
        )
        async with _session(self._session_factory) as session:
            await session.execute(stmt)
            await session.commit()

    async def delete(self, guild_hash: str) -> None:
        async with _session(self._session_factory) as session:
            await session.execute(
                delete(GuildSettingsRow).where(
                    GuildSettingsRow.guild_hash == guild_hash
                )
            )
            await session.commit()


class FavoriteRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def add(
        self,
        *,
        user_hash: str,
        guild_hash: str,
        instant_id: str,
        instant_name: str,
        page_url: str | None,
        mp3_url: str | None,
    ) -> FavoriteDTO:
        async with _session(self._session_factory) as session:
            row = FavoriteRow(
                user_hash=user_hash,
                guild_hash=guild_hash,
                instant_id=instant_id,
                instant_name=instant_name,
                page_url=page_url,
                mp3_url=mp3_url,
            )
            session.add(row)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                existing = await self._get_by_natural_key(
                    session,
                    user_hash=user_hash,
                    guild_hash=guild_hash,
                    instant_id=instant_id,
                )
                if existing is None:
                    raise
                return existing
            await session.refresh(row)
            return _fav_to_dto(row)

    async def list_for(
        self, *, user_hash: str, guild_hash: str, limit: int = 50
    ) -> list[FavoriteDTO]:
        async with _session(self._session_factory) as session:
            stmt = (
                select(FavoriteRow)
                .where(
                    FavoriteRow.user_hash == user_hash,
                    FavoriteRow.guild_hash == guild_hash,
                )
                .order_by(FavoriteRow.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [_fav_to_dto(row) for row in rows]

    async def remove(
        self, *, user_hash: str, guild_hash: str, instant_id: str
    ) -> bool:
        async with _session(self._session_factory) as session:
            result = await session.execute(
                delete(FavoriteRow).where(
                    FavoriteRow.user_hash == user_hash,
                    FavoriteRow.guild_hash == guild_hash,
                    FavoriteRow.instant_id == instant_id,
                )
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def _get_by_natural_key(
        self,
        session: AsyncSession,
        *,
        user_hash: str,
        guild_hash: str,
        instant_id: str,
    ) -> FavoriteDTO | None:
        stmt = select(FavoriteRow).where(
            FavoriteRow.user_hash == user_hash,
            FavoriteRow.guild_hash == guild_hash,
            FavoriteRow.instant_id == instant_id,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        return _fav_to_dto(row) if row is not None else None


class PlayHistoryRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        *,
        user_hash: str,
        guild_hash: str,
        instant_id: str,
        instant_name: str,
    ) -> None:
        async with _session(self._session_factory) as session:
            session.add(
                PlayHistoryRow(
                    user_hash=user_hash,
                    guild_hash=guild_hash,
                    instant_id=instant_id,
                    instant_name=instant_name,
                )
            )
            await session.commit()

    async def recent_for_user(
        self,
        *,
        user_hash: str,
        guild_hash: str,
        limit: int = 20,
    ) -> list[PlayHistoryDTO]:
        async with _session(self._session_factory) as session:
            stmt = (
                select(PlayHistoryRow)
                .where(
                    PlayHistoryRow.user_hash == user_hash,
                    PlayHistoryRow.guild_hash == guild_hash,
                )
                .order_by(PlayHistoryRow.played_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            PlayHistoryDTO(
                id=row.id,
                instant_id=row.instant_id,
                instant_name=row.instant_name,
                played_at=row.played_at,
            )
            for row in rows
        ]

    async def top_in_guild(
        self,
        *,
        guild_hash: str,
        days: int = 30,
        limit: int = 10,
    ) -> list[TopInstantDTO]:
        since = datetime.now(UTC) - timedelta(days=days)
        async with _session(self._session_factory) as session:
            stmt = (
                select(
                    PlayHistoryRow.instant_id,
                    PlayHistoryRow.instant_name,
                    func.count().label('plays'),
                )
                .where(
                    PlayHistoryRow.guild_hash == guild_hash,
                    PlayHistoryRow.played_at >= since,
                )
                .group_by(
                    PlayHistoryRow.instant_id, PlayHistoryRow.instant_name
                )
                .order_by(func.count().desc())
                .limit(limit)
            )
            rows = await session.execute(stmt)
        return [
            TopInstantDTO(
                instant_id=row.instant_id,
                instant_name=row.instant_name,
                plays=int(row.plays),
            )
            for row in rows.all()
        ]

    async def prune_older_than(self, *, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        async with _session(self._session_factory) as session:
            result = await session.execute(
                delete(PlayHistoryRow).where(PlayHistoryRow.played_at < cutoff)
            )
            await session.commit()
            return result.rowcount or 0


def _fav_to_dto(row: FavoriteRow) -> FavoriteDTO:
    return FavoriteDTO(
        id=row.id,
        instant_id=row.instant_id,
        instant_name=row.instant_name,
        page_url=row.page_url,
        mp3_url=row.mp3_url,
        created_at=row.created_at,
    )
