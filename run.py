import asyncio
import functools
import itertools
import math
import os
import random

import discord
import youtube_dl
from async_timeout import timeout
from discord.ext import commands
from loguru import logger

from instants import InstantsCrawler

# Ignore console errors
youtube_dl.utils.bug_reports_message = lambda: ''

class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


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
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, context: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = context.author
        self.channel = context.channel
        self.data = data

        self.uploader = data.get('uploader_name')
        self.uploader_url = data.get('uploader_url')
        self.description = data.get('description')
        date = data.get('upload_date')
        self.upload_date = date[0:4] + '-' + date[4:6] + '-' + date[6:8] if date else None
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.views = data.get('views')
        self.likes = data.get('likes')
        self.thumbnail = 'https://images-na.ssl-images-amazon.com/images/I/61LNAo2K9RL.png'

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
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
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(webpage_url))

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @classmethod
    async def from_url(cls, context, url: str, instant_details, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        partial = functools.partial(cls.ytdl.extract_info, url, download=False, process=False)
        info = await loop.run_in_executor(None, partial)
        info = info | instant_details

        if info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(url))
        return cls(context, discord.FFmpegPCMAudio(info['webpage_url'], **cls.FFMPEG_OPTIONS), data=info)


    @classmethod
    async def from_url2(cls, context, url: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: cls.ytdl.extract_info(url, download=False))
        return cls(context, discord.FFmpegPCMAudio(data['url'], **cls.FFMPEG_OPTIONS), data=data)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='Now playing',
                               description='```css\n{0.source.title}\n```'.format(self),
                               color=discord.Color.blurple())
                 .add_field(name='Requested by', value=self.requester.mention)
                 .add_field(name='Uploader', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                 .add_field(name='URL', value='[Click]({0.source.url})'.format(self))
                 .add_field(name='Views', value=self.source.views)
                 .add_field(name='Likes', value=self.source.likes)
                 .set_thumbnail(url=self.source.thumbnail))

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
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


class VoiceState:
    def __init__(self, bot, context):
        self.bot = bot
        self._context = context

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None

class InstantClient(commands.Cog):
    crawler = InstantsCrawler()

    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, context):
        state = self.voice_states.get(context.guild.id)
        if not state:
            state = VoiceState(self.bot, context)
            self.voice_states[context.guild.id] = state
        return state

    def cog_check(self, context):
        if not context.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')
        return True

    async def cog_before_invoke(self, context):
        logger.info(
            '\n'
            f'Command: {context.command}\n'
            f'Author: {context.author}\n'
            f'Channel: {context.channel}\n'
            f'Guild: {context.guild}\n'
            f'Messsage: {context.message.clean_content}'
        )
        context.voice_state = self.get_voice_state(context)

    async def cog_command_error(self, context, error):
        await context.send('An error occurred. Please try again.')
        logger.error('An error occurred: {}'.format(str(error)))

    @commands.command(invoke_without_subcommand=True)
    async def join(self, context):
        if not context.author.voice:
            raise VoiceError('You are not connected to a voice channel.')

        channel = context.author.voice.channel
        if context.voice_state.voice:
            return await context.voice_client.move_to(channel)
        context.voice_state.voice = await channel.connect()

    @commands.command(aliases=['disconnect', 'stop'])
    async def leave(self, context):
        if not context.voice_state.voice:
            return await context.send('Not connected to any voice channel.')

        await context.voice_state.stop()
        del self.voice_states[context.guild.id]

    @commands.command()
    async def volume(self, context, *, volume: int):
        if not context.voice_state.is_playing:
            return await context.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await context.send('Volume must be between 0 and 100')

        context.voice_state.volume = volume / 100
        await context.send(f'Volume of the player set to {volume}%')

    @commands.command(aliases=['current', 'playing'])
    async def now(self, context):
        await context.send(embed=context.voice_state.current.create_embed())

    @commands.command()
    async def pause(self, context):
        if not context.voice_state.is_playing and context.voice_state.voice.is_playing():
            context.voice_state.voice.pause()
            await context.message.add_reaction('⏯')

    @commands.command()
    async def resume(self, context):
        if not context.voice_state.is_playing and context.voice_state.voice.is_paused():
            context.voice_state.voice.resume()
            await context.message.add_reaction('⏯')

    @commands.command()
    async def skip(self, context):
        if not context.voice_state.is_playing:
            return await context.send('Not playing any sound right now...')

        voter = context.message.author
        if voter == context.voice_state.current.requester:
            await context.message.add_reaction('⏭')
            context.voice_state.skip()

        elif voter.id not in context.voice_state.skip_votes:
            context.voice_state.skip_votes.add(voter.id)
            total_votes = len(context.voice_state.skip_votes)

            if total_votes >= 3:
                await context.message.add_reaction('⏭')
                context.voice_state.skip()
            else:
                await context.send('Skip vote added, currently at **{}/3**'.format(total_votes))

        else:
            await context.send('You have already voted to skip this song.')

    @commands.command()
    async def queue(self, context, *, page: int = 1):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(context.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(context.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='**{} sounds:**\n\n{}'.format(len(context.voice_state.songs), queue))
                 .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await context.send(embed=embed)

    @commands.command()
    async def shuffle(self, context: commands.Context):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        context.voice_state.songs.shuffle()
        await context.message.add_reaction('✅')

    @commands.command()
    async def remove(self, context: commands.Context, index: int):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        context.voice_state.songs.remove(index - 1)
        await context.message.add_reaction('✅')

    @commands.command()
    async def loop(self, context: commands.Context):
        if not context.voice_state.is_playing:
            return await context.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        context.voice_state.loop = not context.voice_state.loop
        await context.message.add_reaction('✅')

    @commands.command()
    async def play(self, context: commands.Context, *, search: str):
        if not context.voice_state.voice:
            await context.invoke(self.join)

        async with context.typing():
            try:
                instant = self.crawler.get_single_search_result(search)
                if not instant:
                    await context.message.add_reaction('❌')
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(search))
                    return

                name = self.crawler.get_instant_name(instant)
                mp3_link = self.crawler.get_instant_mp3_link(instant)
                instant_details = self.crawler.get_instant_details(instant)
                source = await YTDLSource.from_url(context, mp3_link, instant_details, loop=self.bot.loop)
            except YTDLError as e:
                await context.send('An error occurred while processing this request: {}'.format(str(e)))
            else:
                song = Song(source)

                await context.voice_state.songs.put(song)
                await context.send('Enqueued {}'.format(str(source)))

    @join.before_invoke
    @play.before_invoke
    async def ensure_voice_state(self, context: commands.Context):
        if not context.author.voice or not context.author.voice.channel:
            raise commands.CommandError('You are not connected to any voice channel.')

        if context.voice_client:
            if context.voice_client.channel != context.author.voice.channel:
                raise commands.CommandError('Bot is already in a voice channel.')


bot = commands.Bot(command_prefix=commands.when_mentioned_or(">"),
                   description='Play audio from myinstants')
@bot.event
async def on_ready():
    logger.debug(f'Logged in as: {bot.user.name} - {bot.user.id}')

bot.add_cog(InstantClient(bot))
bot.run(os.getenv('MYINSTANTS_BOT_TOKEN'))
