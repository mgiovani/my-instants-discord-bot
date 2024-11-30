import discord
import youtube_dl
import asyncio
import functools
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
        'before_options': (
            '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        ),
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(
        self,
        interaction: discord.Interaction,
        source: discord.FFmpegPCMAudio,
        *,
        data: dict,
        volume: float = 0.5,
    ):
        super().__init__(source, volume)

        self.requester = interaction.user
        self.channel = interaction.channel
        self.data = data

        self.uploader = data.get('uploader_name')
        self.uploader_url = data.get('uploader_url')
        self.description = data.get('description')
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.views = data.get('views')
        self.likes = data.get('likes')
        self.thumbnail = data.get(
            'thumbnail',
            'https://images-na.ssl-images-amazon.com/images/I/61LNAo2K9RL.png',
        )
        date = data.get('upload_date')
        self.upload_date = (
            f'{date[0:4]}-{date[4:6]}-{date[6:8]}' if date else None
        )

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(
        cls,
        interaction: discord.Interaction,
        search: str,
        *,
        loop: asyncio.BaseEventLoop = None,
    ):
        loop = loop or asyncio.get_event_loop()
        partial = functools.partial(
            cls.ytdl.extract_info, search, download=False, process=False
        )
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(f"Couldn't find anything that matches `{search}`")

        if 'entries' not in data:
            process_info = data
        else:
            process_info = next(
                (entry for entry in data['entries'] if entry), None
            )

            if process_info is None:
                raise YTDLError(
                    f"Couldn't find anything that matches `{search}`"
                )

        webpage_url = process_info['webpage_url']
        partial = functools.partial(
            cls.ytdl.extract_info, webpage_url, download=False
        )
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError(f"Couldn't fetch `{webpage_url}`")

        info = (
            processed_info
            if 'entries' not in processed_info
            else next(
                (entry for entry in processed_info['entries'] if entry), None
            )
        )

        if info is None:
            raise YTDLError(
                f"Couldn't retrieve any matches for `{webpage_url}`"
            )
        print('ASLAOSDOASD')
        print(info)
        return cls(
            interaction,
            discord.FFmpegPCMAudio(info['webpage_url'], **cls.FFMPEG_OPTIONS),
            data=info,
        )

    @classmethod
    async def from_url(
        cls,
        interaction: discord.Interaction,
        url: str,
        instant_details,
        *,
        loop: asyncio.BaseEventLoop = None,
    ):
        loop = loop or asyncio.get_event_loop()
        partial = functools.partial(
            cls.ytdl.extract_info, url, download=False, process=False
        )
        info = await loop.run_in_executor(None, partial)

        if info is None:
            raise YTDLError(f"Couldn't fetch `{url}`")

        # Merge instant details with the extracted info
        info.update(instant_details)
        return cls(
            interaction,
            discord.FFmpegPCMAudio(info['webpage_url'], **cls.FFMPEG_OPTIONS),
            data=info,
        )
