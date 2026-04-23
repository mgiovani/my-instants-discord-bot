from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger

from bot.privacy import hash_guild
from bot.voice.state import GuildVoiceState

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.repositories import GuildSettingsRepository


class GuildVoiceStateManager:
    def __init__(
        self,
        settings: Settings,
        *,
        settings_repo: GuildSettingsRepository | None = None,
    ) -> None:
        self._settings = settings
        self._settings_repo = settings_repo
        self._states: dict[int, GuildVoiceState] = {}
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pending_close: set[asyncio.Task[None]] = set()

    def attach_settings_repo(self, repo: GuildSettingsRepository) -> None:
        self._settings_repo = repo

    async def get_or_create(self, guild_id: int) -> GuildVoiceState:
        async with self._locks[guild_id]:
            state = self._states.get(guild_id)
            if state is None:
                state = await self._build_state(guild_id)
                state.start()
                self._states[guild_id] = state
                logger.debug(
                    'Created voice state for guild {guild_id}',
                    guild_id=guild_id,
                )
            return state

    def invalidate(self, guild_id: int) -> None:
        state = self._states.pop(guild_id, None)
        if state is not None:
            task = asyncio.create_task(state.close())
            self._pending_close.add(task)
            task.add_done_callback(self._pending_close.discard)

    async def _build_state(self, guild_id: int) -> GuildVoiceState:
        idle_timeout = self._settings.idle_timeout_seconds
        skip_threshold = self._settings.skip_vote_threshold
        volume = self._settings.default_volume
        if self._settings_repo is not None:
            secret = self._settings.require_pii_hash_key().get_secret_value()
            row = await self._settings_repo.get(
                hash_guild(guild_id, secret=secret)
            )
            if row is not None:
                if row.idle_timeout_seconds is not None:
                    idle_timeout = row.idle_timeout_seconds
                if row.skip_vote_threshold is not None:
                    skip_threshold = row.skip_vote_threshold
                if row.default_volume_pct is not None:
                    volume = row.default_volume_pct / 100
        return GuildVoiceState(
            guild_id=guild_id,
            idle_timeout_seconds=idle_timeout,
            skip_vote_threshold=skip_threshold,
            default_volume=volume,
            on_idle=self._reap,
        )

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
