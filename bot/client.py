import asyncio
import math

import discord
from async_timeout import timeout
from discord import app_commands
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
                    await self.stop()
                    self.timed_out = True
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self._context.channel.send(embed=self.current.create_embed())

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
                "This command can't be used in DM channels."
            )
        return True

    async def interaction_check(self, interaction):
        logger.info(
            f'Slash Command: {interaction.command.name}\n'
            f'Message: {interaction.message}\n'
            f'User: {interaction.user}\n'
            f'Channel: {interaction.channel}\n'
            f'Guild: {interaction.guild}'
        )
        return True

    async def cog_command_error(self, context, error):
        await context.send(
            'An error occurred: {}'.format(str(error)), ephemeral=True
        )
        logger.error('An error occurred: {}'.format(str(error)))

    async def join(self, context):
        """Utility function to make the bot join the user's voice channel."""
        if not context.author.voice:
            raise VoiceError('You are not connected to a voice channel.')

        channel = context.author.voice.channel
        if context.voice_state.voice:
            return await context.voice_client.move_to(channel)
        context.voice_state.voice = await channel.connect()

    @app_commands.command(
        name='leave', description='Disconnect Myinstants bot.'
    )
    async def leave(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        if not voice_state.voice:
            return await interaction.response.send_message(
                'Not connected to any voice channel.'
            )

        await interaction.response.send_message('Leaving current channel.')
        await voice_state.stop()
        del self.voice_states[interaction.guild.id]

    @app_commands.command(name='volume', description='Set volume sound.')
    async def volume(self, interaction: discord.Interaction, volume: int):
        voice_state = self.get_voice_state(interaction)

        if not voice_state.is_playing:
            return await interaction.response.send_message(
                'Nothing being played at the moment.'
            )

        if volume < 0 or volume > 100:
            return await interaction.response.send_message(
                'Volume must be between 0 and 100'
            )

        voice_state.volume = volume / 100
        await interaction.response.send_message(
            f'Volume of the player set to {volume}%.'
        )

    @app_commands.command(
        name='now', description='Show sound currently playing.'
    )
    async def now(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        await interaction.response.send_message(
            embed=voice_state.current.create_embed()
        )

    @app_commands.command(name='pause', description='Pause my instants sound.')
    async def pause(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        if voice_state.voice and voice_state.voice.is_playing():
            await interaction.response.send_message('Pausing current sound.')
            voice_state.voice.pause()

    @app_commands.command(
        name='resume', description='Resume my instants sound.'
    )
    async def resume(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        if voice_state.voice and voice_state.voice.is_paused():
            await interaction.response.send_message('Resuming paused sound.')
            voice_state.voice.resume()

    @app_commands.command(name='skip', description='Skip current sound.')
    async def skip(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        if not voice_state.is_playing:
            return await interaction.response.send_message(
                'Not playing any sound right now...'
            )

        voter = interaction.user
        if voter == voice_state.current.requester:
            await interaction.response.send_message('Skipping current sound.')
            voice_state.skip()

        elif voter.id not in voice_state.skip_votes:
            voice_state.skip_votes.add(voter.id)
            total_votes = len(voice_state.skip_votes)

            if total_votes >= 3:
                voice_state.skip()
            else:
                await interaction.response.send_message(
                    f'Skip vote added, currently at **{total_votes}/3**'
                )

        else:
            await interaction.response.send_message(
                'You have already voted to skip this song.'
            )

    @app_commands.command(name='queue', description='See sound queue.')
    async def queue(self, interaction: discord.Interaction, page: int = 1):
        voice_state = self.get_voice_state(interaction)
        if len(voice_state.songs) == 0:
            return await interaction.response.send_message('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(
                i + 1, song
            )

        embed = discord.Embed(
            description=f'**{len(voice_state.songs)} sounds:**\n\n{queue}'
        ).set_footer(text=f'Viewing page {page}/{pages}')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='shuffle', description='Shuffle queue.')
    async def shuffle(self, interaction: discord.Interaction):
        voice_state = self.get_voice_state(interaction)
        if len(voice_state.songs) == 0:
            return await interaction.response.send_message('Empty queue.')

        voice_state.songs.shuffle()
        await interaction.response.send_message('Queue shuffled.')

    @app_commands.command(name='remove', description='Remove from queue.')
    async def remove(self, interaction: discord.Interaction, index: int):
        voice_state = self.get_voice_state(interaction)
        if len(voice_state.songs) == 0:
            return await interaction.response.send_message('Empty queue.')

        voice_state.songs.remove(index - 1)
        await interaction.response.send_message(
            f'Removed song at position {index}.'
        )

    @app_commands.command(
        name='loop', description='Loop last myinstants sound.'
    )
    async def loop(self, interaction: discord.Interaction):
        # voice_state = self.get_voice_state(interaction)
        # if not voice_state.is_playing:
        #     return await interaction.response.send_message(
        #         'Nothing being played at the moment.'
        #     )

        # # Inverse boolean value to loop and unloop.
        # voice_state.loop = not voice_state.loop
        # await interaction.response.send_message(
        #     f'Loop is now {"enabled" if voice_state.loop else "disabled"}.'
        # )

        # TODO Fix loop commmand
        await interaction.response.send_message(
            'Loop command is temporarily disabled.'
        )

    @app_commands.command(name='mi', description='Play myinstants sound.')
    async def play(self, interaction: discord.Interaction, search: str):
        voice_state = self.get_voice_state(interaction)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                'You are not connected to any voice channel.', ephemeral=True
            )

        if not voice_state.voice:
            channel = interaction.user.voice.channel
            voice_state.voice = await channel.connect()

        await interaction.response.defer()

        async with interaction.channel.typing():
            try:
                instant = self.crawler.get_single_search_result(search)
                if not instant:
                    raise YTDLError(
                        f"Couldn't retrieve any matches for `{search}`"
                    )

                mp3_link = self.crawler.get_instant_mp3_link(instant)
                instant_details = self.crawler.get_instant_details(instant)
                source = await YTDLSource.from_url(
                    interaction, mp3_link, instant_details, loop=self.bot.loop
                )
            except YTDLError as e:
                await interaction.followup.send(
                    'An error occurred while processing this request. '
                    f'Details: {str(e)}',
                    ephemeral=True,
                )
            else:
                song = Song(source)
                await voice_state.songs.put(song)
                await interaction.followup.send(f'Enqueued {str(source)}.')

    @app_commands.command(
        name='help', description='List and describe all available commands.'
    )
    async def help_command(self, interaction: discord.Interaction):
        commands_info = [
            ('/leave', 'Disconnect the bot from the voice channel.'),
            ('/now', 'Shows the current sound playing.'),
            ('/mi <search>', 'Play a sound from MyInstants.'),
            ('/pause', 'Pause the current playback.'),
            ('/resume', 'Resume playback.'),
            ('/skip', 'Skip the current track.'),
            ('/queue', 'Show the current playback queue.'),
            ('/shuffle', 'Shuffle the queue.'),
            (
                '/remove <index>',
                'Remove a track from the queue by its position.',
            ),
            ('/loop', 'Toggle looping of the current track.'),
            ('/volume <value>', 'Set the playback volume (0-100).'),
        ]

        description = '\n'.join(
            [f'**{cmd}**: {desc}' for cmd, desc in commands_info]
        )
        embed = discord.Embed(
            title='Command List',
            description=description,
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)
