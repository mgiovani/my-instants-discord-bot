from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.db.models import Base

if TYPE_CHECKING:
    from bot.config import Settings


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(
    settings: Settings | None = None,
    *,
    url: str | None = None,
    echo: bool = False,
) -> AsyncEngine:
    global _engine, _session_factory  # noqa: PLW0603
    resolved_url = url or (settings.database_url if settings else None)
    if not resolved_url:
        raise ValueError('database URL must be provided via settings or url=')

    _ensure_sqlite_parent(resolved_url)
    _engine = create_async_engine(
        resolved_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )
    logger.info('DB engine ready for {url}', url=_safe_url(resolved_url))
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError(
            'Database engine is not initialised. Call create_engine() first.'
        )
    return _session_factory


async def run_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info('DB engine closed')


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith('sqlite'):
        return
    try:
        path = url.rsplit(':///', maxsplit=1)[-1]
    except IndexError:
        return
    if not path or path == ':memory:':
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _safe_url(url: str) -> str:
    if '@' not in url:
        return url
    head, tail = url.split('@', 1)
    scheme_sep = head.rfind(':')
    return f'{head[:scheme_sep]}://***@{tail}'
