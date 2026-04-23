from __future__ import annotations

import asyncio
import functools
import subprocess
from typing import TYPE_CHECKING, Any

import discord
import yt_dlp
from loguru import logger

from bot.exceptions import YTDLError

if TYPE_CHECKING:
    from bot.config import Settings
    from crawler.instants import InstantDetails

yt_dlp.utils.bug_reports_message = lambda *_args, **_kwargs: ''


_YTDL_OPTIONS: dict[str, Any] = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
}


_FFMPEG_OPTIONS: dict[str, str] = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn',
}


_ytdl = yt_dlp.YoutubeDL(_YTDL_OPTIONS)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(
        self,
        *,
        interaction: discord.Interaction,
        stream_url: str,
        data: dict[str, Any],
        volume: float = 0.5,
    ) -> None:
        super().__init__(_spawn_ffmpeg(stream_url), volume=volume)
        self.stream_url = stream_url
        self.requester = interaction.user
        self.channel = interaction.channel
        self.data = data

        self.uploader: str | None = data.get('uploader_name')
        self.uploader_url: str | None = data.get('uploader_url')
        self.description: str | None = data.get('description')
        self.title: str | None = data.get('title')
        self.url: str | None = data.get('webpage_url') or stream_url
        self.views: str | None = data.get('views')
        self.likes: str | None = data.get('likes')
        self.thumbnail: str = data.get('thumbnail') or data.get(
            'fallback_thumbnail',
            'https://images-na.ssl-images-amazon.com/images/I/61LNAo2K9RL.png',
        )
        upload_date: str | None = data.get('upload_date')
        self.upload_date: str | None = (
            f'{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}'
            if upload_date
            else None
        )

    def __str__(self) -> str:
        return f'**{self.title}** by **{self.uploader}**'

    def reset_stream(self) -> None:
        previous = self.original
        self.original = _spawn_ffmpeg(self.stream_url)
        cleanup = getattr(previous, 'cleanup', None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception as exc:
                logger.debug(
                    'cleanup on replaced FFmpeg source failed: {exc}',
                    exc=exc,
                )

    @classmethod
    async def from_url(
        cls,
        interaction: discord.Interaction,
        url: str,
        instant_details: InstantDetails,
        *,
        settings: Settings,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> YTDLSource:
        loop = loop or asyncio.get_running_loop()
        extractor = functools.partial(
            _ytdl.extract_info, url, download=False, process=False
        )
        try:
            info = await loop.run_in_executor(None, extractor)
        except yt_dlp.utils.DownloadError as exc:
            raise YTDLError(f'Could not fetch {url}: {exc}') from exc

        if info is None:
            raise YTDLError(f'Could not fetch {url}')

        merged: dict[str, Any] = {**info, **instant_details.to_ytdl_data()}
        merged.setdefault('webpage_url', url)
        merged.setdefault(
            'fallback_thumbnail', settings.fallback_thumbnail_url
        )

        return cls(
            interaction=interaction,
            stream_url=url,
            data=merged,
            volume=settings.default_volume,
        )


def _spawn_ffmpeg(stream_url: str) -> discord.FFmpegPCMAudio:
    try:
        return discord.FFmpegPCMAudio(
            stream_url,
            stderr=subprocess.PIPE,
            **_FFMPEG_OPTIONS,
        )
    except discord.ClientException as exc:
        logger.error(
            'FFmpeg could not start for {url}: {exc}',
            url=stream_url,
            exc=exc,
        )
        raise YTDLError(f'FFmpeg failed to start: {exc}') from exc
