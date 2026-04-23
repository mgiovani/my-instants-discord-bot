from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GuildSettings(Base):
    __tablename__ = 'guild_settings'

    guild_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    idle_timeout_seconds: Mapped[int | None] = mapped_column(Integer())
    skip_vote_threshold: Mapped[int | None] = mapped_column(Integer())
    default_volume_pct: Mapped[int | None] = mapped_column(Integer())
    locale: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = (
        UniqueConstraint(
            'user_hash',
            'guild_hash',
            'instant_id',
            name='uq_fav_user_guild_instant',
        ),
        Index('ix_fav_user_guild', 'user_hash', 'guild_hash'),
    )

    id: Mapped[int] = mapped_column(
        Integer(), primary_key=True, autoincrement=True
    )
    user_hash: Mapped[str] = mapped_column(String(64))
    guild_hash: Mapped[str] = mapped_column(String(64))
    instant_id: Mapped[str] = mapped_column(String(128))
    instant_name: Mapped[str] = mapped_column(String(255))
    page_url: Mapped[str | None] = mapped_column(String(512))
    mp3_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class PlayHistory(Base):
    __tablename__ = 'play_history'
    __table_args__ = (
        Index('ix_play_guild_at', 'guild_hash', 'played_at'),
        Index('ix_play_instant', 'instant_id'),
    )

    id: Mapped[int] = mapped_column(
        Integer(), primary_key=True, autoincrement=True
    )
    user_hash: Mapped[str] = mapped_column(String(64))
    guild_hash: Mapped[str] = mapped_column(String(64))
    instant_id: Mapped[str] = mapped_column(String(128))
    instant_name: Mapped[str] = mapped_column(String(255))
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
