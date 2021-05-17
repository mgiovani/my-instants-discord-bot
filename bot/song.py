import asyncio
import itertools
import random

import discord
from bot.ytdl import YTDLSource


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(
            title='Now playing',
            description='```css\n{0.source.title}\n```'.format(self),
            color=discord.Color.blurple())
            .add_field(name='Requested by', value=self.requester.mention)
            .add_field(name='Uploader', value=(
                '[{0.source.uploader}]({0.source.uploader_url})'.format(self)))
            .add_field(name='URL', value=(
                '[Click]({0.source.url})'.format(self)))
            .add_field(name='Views', value=self.source.views)
            .add_field(name='Likes', value=self.source.likes)
            .set_thumbnail(url=self.source.thumbnail))

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(
                self._queue, item.start, item.stop, item.step
            ))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]
