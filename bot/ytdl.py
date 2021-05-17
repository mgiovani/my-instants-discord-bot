import asyncio
import functools

import discord
import youtube_dl
from discord.ext import commands

from bot.exceptions import YTDLError


# Ignore console errors
youtube_dl.utils.bug_reports_message = lambda: ''


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',  # noqa
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(
            self, context: commands.Context, source: discord.FFmpegPCMAudio, *,
            data: dict, volume: float = 0.5
    ):
        super().__init__(source, volume)

        self.requester = context.author
        self.channel = context.channel
        self.data = data

        self.uploader = data.get('uploader_name')
        self.uploader_url = data.get('uploader_url')
        self.description = data.get('description')
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.views = data.get('views')
        self.likes = data.get('likes')
        self.thumbnail = (
            'https://images-na.ssl-images-amazon.com/images/I/61LNAo2K9RL.png'
        )
        date = data.get('upload_date')
        if date:
            self.upload_date = date[0:4] + '-' + date[4:6] + '-' + date[6:8]
        else:
            self.upload_date = None

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(
        cls, ctx: commands.Context, search: str, *,
        loop: asyncio.BaseEventLoop = None
    ):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(
            cls.ytdl.extract_info, search, download=False, process=False
        )
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(
                'Couldn\'t find anything that matches `{}`'.format(search)
            )

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError(
                    'Couldn\'t find anything that matches `{}`'.format(search)
                )

        webpage_url = process_info['webpage_url']
        partial = functools.partial(
            cls.ytdl.extract_info, webpage_url, download=False
        )
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(
                        'Couldn\'t retrieve any matches for `{}`'
                        .format(webpage_url)
                    )

        return cls(
            ctx, discord.FFmpegPCMAudio(
                info['url'], **cls.FFMPEG_OPTIONS), data=info
        )

    @classmethod
    async def from_url(
        cls, context, url: str, instant_details, *,
        loop: asyncio.BaseEventLoop = None
    ):
        loop = loop or asyncio.get_event_loop()
        partial = functools.partial(
            cls.ytdl.extract_info, url, download=False, process=False
        )
        info = await loop.run_in_executor(None, partial)
        info = info | instant_details

        if info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(url))
        return cls(
            context, discord.FFmpegPCMAudio(
                info['webpage_url'], **cls.FFMPEG_OPTIONS), data=info
        )
