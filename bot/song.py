from __future__ import annotations

import asyncio
import itertools
import random
from typing import TYPE_CHECKING, overload

import discord

from bot.exceptions import QueueIndexError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from bot.ytdl import YTDLSource


class Song:
    __slots__ = ('requester', 'source')

    def __init__(self, source: YTDLSource) -> None:
        self.source = source
        self.requester = source.requester

    def create_embed(self) -> discord.Embed:
        source = self.source
        return (
            discord.Embed(
                title='Now playing',
                description=f'```css\n{source.title}\n```',
                color=discord.Color.blurple(),
            )
            .add_field(name='Requested by', value=self.requester.mention)
            .add_field(
                name='Uploader',
                value=f'[{source.uploader}]({source.uploader_url})',
            )
            .add_field(name='URL', value=f'[Click]({source.url})')
            .add_field(name='Views', value=source.views or '—')
            .add_field(name='Likes', value=source.likes or '—')
            .set_thumbnail(url=source.thumbnail)
        )


class SongQueue(asyncio.Queue[Song]):
    @overload
    def __getitem__(self, item: int) -> Song: ...

    @overload
    def __getitem__(self, item: slice) -> list[Song]: ...

    def __getitem__(self, item: int | slice) -> Song | list[Song]:
        if isinstance(item, slice):
            return list(
                itertools.islice(self._queue, item.start, item.stop, item.step)
            )
        return self._queue[item]

    def __iter__(self) -> Iterator[Song]:
        return iter(self._queue)

    def __len__(self) -> int:
        return self.qsize()

    def clear(self) -> None:
        self._queue.clear()

    def shuffle(self) -> None:
        random.shuffle(self._queue)

    def remove(self, index: int) -> None:
        length = len(self)
        if length == 0 or not 0 <= index < length:
            raise QueueIndexError(index, max(length, 1))
        del self._queue[index]
