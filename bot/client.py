import asyncio
import math

import discord
from async_timeout import timeout
from discord.ext import commands
from loguru import logger

from bot.exceptions import VoiceError, YTDLError
from bot.song import Song, SongQueue
from bot.ytdl import YTDLSource
from crawler.instants import InstantsCrawler


class VoiceState:
    def __init__(self, bot, context):
        self.bot = bot
        self._context = context
        self.timed_out = False

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
                    self.timed_out = True
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(
                embed=self.current.create_embed())

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
        if not state or state.timed_out:
            state = VoiceState(self.bot, context)
            self.voice_states[context.guild.id] = state
        return state

    def cog_check(self, context):
        if not context.guild:
            raise commands.NoPrivateMessage(
                'This command can\'t be used in DM channels.')
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
        await context.send('An error occurred: {}'.format(str(error)))
        logger.error('An error occurred: {}'.format(str(error)))

    @commands.hybrid_command(name="join", with_app_command= True, description="Make Myinstants bot join.")
    async def join(self, context):
        if not context.author.voice:
            raise VoiceError('You are not connected to a voice channel.')

        await context.send(f"Joining user's current channel.")
        channel = context.author.voice.channel
        if context.voice_state.voice:
            return await context.voice_client.move_to(channel)
        context.voice_state.voice = await channel.connect()

    @commands.hybrid_command(name="leave", with_app_command= True, description="Disconnect Myinstants bot.")
    async def leave(self, context):
        if not context.voice_state.voice:
            return await context.send('Not connected to any voice channel.')

        await context.send(f"Leaving user's current channel.")
        await context.voice_state.stop()
        del self.voice_states[context.guild.id]

    @commands.hybrid_command(name="volume", with_app_command= True, description="Set volume sound.")
    async def volume(self, context, *, volume: int):
        if not context.voice_state.is_playing:
            return await context.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await context.send('Volume must be between 0 and 100')

        context.voice_state.volume = volume / 100
        await context.send(f'Volume of the player set to {volume}%')

    @commands.hybrid_command(name="now", with_app_command= True, description="Show sound currently playing.")
    async def now(self, context):
        await context.send(embed=context.voice_state.current.create_embed())

    @commands.hybrid_command(name="pause", with_app_command= True, description="Pause my instants sound.")
    async def pause(self, context):
        if (
                not context.voice_state.is_playing
                and context.voice_state.voice.is_playing()
        ):
            await context.send(f"Pausing current sound.")
            context.voice_state.voice.pause()
            await context.message.add_reaction('⏯')

    @commands.hybrid_command(name="resume", with_app_command= True, description="Resume my instants sound.")
    async def resume(self, context):
        if (
                not context.voice_state.is_playing
                and context.voice_state.voice.is_paused()
        ):
            await context.send(f"Resuming paused sound.")
            context.voice_state.voice.resume()
            await context.message.add_reaction('⏯')

    @commands.hybrid_command(name="skip", with_app_command= True, description="Skip current sound.")
    async def skip(self, context):
        if not context.voice_state.is_playing:
            return await context.send('Not playing any sound right now...')

        voter = context.message.author
        if voter == context.voice_state.current.requester:
            await context.message.add_reaction('⏭')
            context.send('Skipping current sound.')
            context.voice_state.skip()

        elif voter.id not in context.voice_state.skip_votes:
            context.voice_state.skip_votes.add(voter.id)
            total_votes = len(context.voice_state.skip_votes)

            if total_votes >= 3:
                await context.message.add_reaction('⏭')
                context.voice_state.skip()
            else:
                await context.send(
                    'Skip vote added, currently at **{}/3**'.format
                    (total_votes))

        else:
            await context.send('You have already voted to skip this song.')

    @commands.hybrid_command(name="queue", with_app_command= True, description="See sound queue.")
    async def queue(self, context, *, page: int = 1):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(context.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(
                context.voice_state.songs[start:end], start=start):
            queue += (
                '`{0}.` [**{1.source.title}**]({1.source.url})\n'
                .format(i + 1, song))

        embed = (discord.Embed(
            description='**{} sounds:**\n\n{}'
            .format(len(context.voice_state.songs), queue))
            .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await context.send(embed=embed)

    @commands.hybrid_command(name="shuffle", with_app_command= True, description="Shuffle queue.")
    async def shuffle(self, context: commands.Context):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        context.voice_state.songs.shuffle()
        await context.message.add_reaction('✅')

    @commands.hybrid_command(name="remove", with_app_command= True, description="Remove from queue.")
    async def remove(self, context: commands.Context, index: int):
        if len(context.voice_state.songs) == 0:
            return await context.send('Empty queue.')

        context.voice_state.songs.remove(index - 1)
        await context.message.add_reaction('✅')

    @commands.hybrid_command(name="loop", with_app_command= True, description="Loop last myinstants sound")
    async def loop(self, context: commands.Context):
        if not context.voice_state.is_playing:
            return await context.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        context.voice_state.loop = not context.voice_state.loop
        await context.message.add_reaction('✅')

    @commands.hybrid_command(name="play", with_app_command= True, description="Play myinstants sound")
    async def play(self, context: commands.Context, *, search: str):
        if not context.voice_state.voice:
            await context.invoke(self.join)

        async with context.typing():
            try:
                instant = self.crawler.get_single_search_result(search)
                if not instant:
                    await context.message.add_reaction('❌')
                    raise YTDLError(
                        'Couldn\'t retrieve any matches for `{}`'
                        .format(search))
                    return

                mp3_link = self.crawler.get_instant_mp3_link(instant)
                instant_details = self.crawler.get_instant_details(instant)
                source = await YTDLSource.from_url(
                    context, mp3_link, instant_details, loop=self.bot.loop)
            except YTDLError as e:
                await context.send(
                    'An error occurred while processing this request: {}'
                    .format(str(e)))
            else:
                song = Song(source)

                await context.voice_state.songs.put(song)
                await context.send('Enqueued {}'.format(str(source)))

    @join.before_invoke
    @play.before_invoke
    async def ensure_voice_state(self, context: commands.Context):
        if not context.author.voice or not context.author.voice.channel:
            raise commands.CommandError(
                'You are not connected to any voice channel.')

        if context.voice_client:
            if context.voice_client.channel != context.author.voice.channel:
                raise commands.CommandError(
                    'Bot is already in a voice channel.')
    