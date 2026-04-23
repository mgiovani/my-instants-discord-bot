from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord
from loguru import logger

from bot.song import SongQueue

if TYPE_CHECKING:
    from bot.song import Song


type ReapCallback = Callable[[int], Awaitable[None]]
type NowPlayingSink = Callable[[discord.Embed], Awaitable[None]]


class GuildVoiceState:
    """Per-guild playback state.

    The background `_player_loop` pulls the next song (blocking on the
    queue with a timeout) and plays it on the guild's voice client. When
    the queue stays empty for `idle_timeout_seconds`, the loop asks the
    manager to reap this state and returns. Exceptions inside the play
    iteration are logged and the loop continues so transient failures
    don't leave the guild in a zombie state.
    """

    def __init__(
        self,
        *,
        guild_id: int,
        idle_timeout_seconds: int,
        skip_vote_threshold: int,
        default_volume: float,
        on_idle: ReapCallback | None = None,
    ) -> None:
        self.guild_id = guild_id
        self.idle_timeout_seconds = idle_timeout_seconds
        self.skip_vote_threshold = skip_vote_threshold
        self.voice: discord.VoiceClient | None = None
        self.current: Song | None = None
        self.songs: SongQueue = SongQueue()
        self.skip_votes: set[int] = set()
        self.volume = default_volume
        self.loop_current = False
        self._notify: NowPlayingSink | None = None
        self._on_idle = on_idle
        self._next_event = asyncio.Event()
        self._closed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._player_loop(), name=f'player-{self.guild_id}'
            )

    def set_now_playing_sink(self, sink: NowPlayingSink | None) -> None:
        self._notify = sink

    @property
    def is_playing(self) -> bool:
        return self.voice is not None and self.current is not None

    def register_skip_vote(self, user_id: int) -> int:
        self.skip_votes.add(user_id)
        return len(self.skip_votes)

    def skip(self) -> None:
        self.skip_votes.clear()
        if self.voice is not None and self.voice.is_playing():
            self.voice.stop()

    async def close(self) -> None:
        self._closed.set()
        self._next_event.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._disconnect()

    async def _disconnect(self) -> None:
        self.songs.clear()
        self.current = None
        voice = self.voice
        if voice is not None:
            self.voice = None
            try:
                await voice.disconnect(force=False)
            except Exception as exc:
                logger.warning(
                    'Error disconnecting voice for guild {guild_id}: {exc}',
                    guild_id=self.guild_id,
                    exc=exc,
                )

    async def _player_loop(self) -> None:
        is_loop_replay = False
        while not self._closed.is_set():
            self._next_event.clear()
            song = await self._next_song(is_loop_replay)
            if song is None:
                await self._disconnect()
                if self._on_idle is not None:
                    await self._on_idle(self.guild_id)
                return

            if is_loop_replay:
                song.source.reset_stream()

            self.current = song
            song.source.volume = self.volume
            try:
                await self._play_current(song, announce=not is_loop_replay)
            except Exception as exc:
                logger.exception(
                    'Playback failed in guild {guild_id}: {exc}',
                    guild_id=self.guild_id,
                    exc=exc,
                )
                self._next_event.set()
            await self._next_event.wait()
            is_loop_replay = self.loop_current and not self._closed.is_set()

    async def _next_song(self, is_loop_replay: bool) -> Song | None:
        if is_loop_replay and self.current is not None:
            return self.current
        try:
            async with asyncio.timeout(self.idle_timeout_seconds):
                return await self.songs.get()
        except TimeoutError:
            return None

    async def _play_current(self, song: Song, *, announce: bool) -> None:
        voice = self.voice
        if voice is None:
            logger.warning(
                'No voice client for guild {guild_id}, dropping song',
                guild_id=self.guild_id,
            )
            self._next_event.set()
            return
        voice.play(song.source, after=self._on_after_play)
        if announce and self._notify is not None:
            try:
                await self._notify(song.create_embed())
            except Exception as exc:
                logger.warning('now-playing embed failed: {exc}', exc=exc)

    def _on_after_play(self, error: Exception | None) -> None:
        if error is not None:
            logger.error(
                'Voice playback error in guild {guild_id}: {error}',
                guild_id=self.guild_id,
                error=error,
            )
        self._next_event.set()
