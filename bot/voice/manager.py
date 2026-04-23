from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger

from bot.voice.state import GuildVoiceState

if TYPE_CHECKING:
    from bot.config import Settings


class GuildVoiceStateManager:
    """Owns the lifecycle of `GuildVoiceState` instances per guild.

    All lookups serialise through a per-guild `asyncio.Lock` to prevent
    two concurrent slash commands from creating duplicate states — the
    bug that caused double voice connects in production.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._states: dict[int, GuildVoiceState] = {}
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get_or_create(self, guild_id: int) -> GuildVoiceState:
        async with self._locks[guild_id]:
            state = self._states.get(guild_id)
            if state is None:
                state = GuildVoiceState(
                    guild_id=guild_id,
                    idle_timeout_seconds=self._settings.idle_timeout_seconds,
                    skip_vote_threshold=self._settings.skip_vote_threshold,
                    default_volume=self._settings.default_volume,
                    on_idle=self._reap,
                )
                state.start()
                self._states[guild_id] = state
                logger.debug(
                    'Created voice state for guild {guild_id}',
                    guild_id=guild_id,
                )
            return state

    def get(self, guild_id: int) -> GuildVoiceState | None:
        return self._states.get(guild_id)

    async def drop(self, guild_id: int) -> None:
        async with self._locks[guild_id]:
            state = self._states.pop(guild_id, None)
        if state is not None:
            await state.close()
            logger.debug(
                'Dropped voice state for guild {guild_id}',
                guild_id=guild_id,
            )

    async def close_all(self) -> None:
        guilds = list(self._states.keys())
        for guild_id in guilds:
            await self.drop(guild_id)

    async def _reap(self, guild_id: int) -> None:
        async with self._locks[guild_id]:
            self._states.pop(guild_id, None)
        logger.debug(
            'Reaped idle voice state for guild {guild_id}',
            guild_id=guild_id,
        )
