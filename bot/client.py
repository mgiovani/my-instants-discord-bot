from __future__ import annotations

import math
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from bot.exceptions import (
    EmptyQueueError,
    NotInVoiceError,
    NothingPlayingError,
)
from bot.song import Song
from bot.ytdl import YTDLSource

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.voice import GuildVoiceState, GuildVoiceStateManager
    from crawler.instants import InstantsCrawler


class InstantClient(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        settings: Settings,
        crawler: InstantsCrawler,
        voice_states: GuildVoiceStateManager,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.crawler = crawler
        self.voice_states = voice_states

    async def _state_for(
        self, interaction: discord.Interaction
    ) -> GuildVoiceState:
        if interaction.guild_id is None:
            raise NotInVoiceError('Command used outside a guild.')
        state = await self.voice_states.get_or_create(interaction.guild_id)
        channel = interaction.channel
        if channel is not None and hasattr(channel, 'send'):
            state.set_now_playing_sink(channel.send)  # type: ignore[assignment]
        return state

    def _require_voice_channel(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | discord.StageChannel:
        member = interaction.user
        voice = getattr(member, 'voice', None)
        if voice is None or voice.channel is None:
            raise NotInVoiceError
        channel = voice.channel
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise NotInVoiceError
        return channel

    async def _ensure_connected(
        self,
        interaction: discord.Interaction,
        state: GuildVoiceState,
    ) -> discord.VoiceClient:
        target = self._require_voice_channel(interaction)
        live = interaction.guild.voice_client if interaction.guild else None

        if isinstance(live, discord.VoiceClient) and live.is_connected():
            if live.channel is not None and live.channel.id != target.id:
                await live.move_to(target)
            state.voice = live
            return live

        voice = await target.connect(self_deaf=True)
        state.voice = voice
        return voice

    @app_commands.command(name='leave', description='Disconnect from voice.')
    async def leave(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            raise NotInVoiceError('Command used outside a guild.')
        state = self.voice_states.get(interaction.guild_id)
        if state is None or state.voice is None:
            await interaction.response.send_message(
                'Not connected to any voice channel.', ephemeral=True
            )
            return
        await interaction.response.send_message('Leaving current channel.')
        await self.voice_states.drop(interaction.guild_id)

    @app_commands.command(name='volume', description='Set volume (0-100).')
    async def volume(
        self, interaction: discord.Interaction, volume: int
    ) -> None:
        state = await self._state_for(interaction)
        if not state.is_playing:
            raise NothingPlayingError
        if not 0 <= volume <= 100:
            await interaction.response.send_message(
                'Volume must be between 0 and 100.', ephemeral=True
            )
            return
        state.volume = volume / 100
        if state.current is not None:
            state.current.source.volume = state.volume
        await interaction.response.send_message(
            f'Volume set to {volume}%.'
        )

    @app_commands.command(
        name='now', description='Show the currently playing sound.'
    )
    async def now(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if state.current is None:
            raise NothingPlayingError
        await interaction.response.send_message(
            embed=state.current.create_embed()
        )

    @app_commands.command(name='pause', description='Pause playback.')
    async def pause(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if state.voice is None or not state.voice.is_playing():
            raise NothingPlayingError
        state.voice.pause()
        await interaction.response.send_message('Pausing current sound.')

    @app_commands.command(name='resume', description='Resume playback.')
    async def resume(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if state.voice is None or not state.voice.is_paused():
            await interaction.response.send_message(
                'Nothing is paused right now.', ephemeral=True
            )
            return
        state.voice.resume()
        await interaction.response.send_message('Resuming paused sound.')

    @app_commands.command(name='skip', description='Skip the current sound.')
    async def skip(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if not state.is_playing or state.current is None:
            raise NothingPlayingError

        voter = interaction.user
        if voter == state.current.requester:
            state.skip()
            await interaction.response.send_message('Skipping current sound.')
            return

        if voter.id in state.skip_votes:
            await interaction.response.send_message(
                'You have already voted to skip.', ephemeral=True
            )
            return

        total = state.register_skip_vote(voter.id)
        threshold = state.skip_vote_threshold
        if total >= threshold:
            state.skip()
            await interaction.response.send_message(
                f'Skip passed ({total}/{threshold}).'
            )
            return
        await interaction.response.send_message(
            f'Skip vote added, currently at **{total}/{threshold}**.'
        )

    @app_commands.command(name='queue', description='Show the queue.')
    async def queue(
        self, interaction: discord.Interaction, page: int = 1
    ) -> None:
        state = await self._state_for(interaction)
        total = len(state.songs)
        if total == 0:
            raise EmptyQueueError

        items_per_page = self.settings.queue_page_size
        pages = max(1, math.ceil(total / items_per_page))
        page = max(1, min(page, pages))

        start = (page - 1) * items_per_page
        end = start + items_per_page

        lines = [
            f'`{idx + 1}.` [**{song.source.title}**]({song.source.url})'
            for idx, song in enumerate(
                state.songs[start:end], start=start
            )
        ]
        embed = discord.Embed(
            description=f'**{total} sound(s):**\n\n' + '\n'.join(lines),
        ).set_footer(text=f'Viewing page {page}/{pages}')
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='shuffle', description='Shuffle the queue.')
    async def shuffle(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if len(state.songs) == 0:
            raise EmptyQueueError
        state.songs.shuffle()
        await interaction.response.send_message('Queue shuffled.')

    @app_commands.command(name='remove', description='Remove from the queue.')
    async def remove(
        self, interaction: discord.Interaction, index: int
    ) -> None:
        state = await self._state_for(interaction)
        if len(state.songs) == 0:
            raise EmptyQueueError
        state.songs.remove(index - 1)
        await interaction.response.send_message(
            f'Removed song at position {index}.'
        )

    @app_commands.command(name='loop', description='Toggle loop for playing.')
    async def loop(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if not state.is_playing:
            raise NothingPlayingError
        state.loop_current = not state.loop_current
        status = 'enabled' if state.loop_current else 'disabled'
        await interaction.response.send_message(f'Loop is now {status}.')

    @app_commands.command(name='mi', description='Play a MyInstants sound.')
    async def play(
        self, interaction: discord.Interaction, search: str
    ) -> None:
        self._require_voice_channel(interaction)
        await interaction.response.defer()

        state = await self._state_for(interaction)
        await self._ensure_connected(interaction, state)

        instant = await self.crawler.first_match(search)
        details = await self.crawler.get_details(instant)
        source = await YTDLSource.from_url(
            interaction,
            instant.mp3_url,
            details,
            settings=self.settings,
            loop=self.bot.loop,
        )
        song = Song(source)
        await state.songs.put(song)
        logger.info(
            'Enqueued {title!r} in guild {guild_id}',
            title=source.title or instant.name,
            guild_id=interaction.guild_id,
        )
        await interaction.followup.send(f'Enqueued {source!s}.')

    @app_commands.command(name='help', description='List commands.')
    async def help_command(
        self, interaction: discord.Interaction
    ) -> None:
        lines = [
            ('/mi <search>', 'Play a sound from MyInstants.'),
            ('/leave', 'Disconnect the bot from the voice channel.'),
            ('/now', 'Show the current sound playing.'),
            ('/pause', 'Pause the current playback.'),
            ('/resume', 'Resume playback.'),
            ('/skip', 'Skip the current track (vote if not requester).'),
            ('/queue [page]', 'Show the queue.'),
            ('/shuffle', 'Shuffle the queue.'),
            ('/remove <index>', 'Remove a track from the queue.'),
            ('/loop', 'Toggle looping of the current track.'),
            ('/volume <value>', 'Set the playback volume (0-100).'),
        ]
        embed = discord.Embed(
            title='Command List',
            description='\n'.join(
                f'**{cmd}**: {desc}' for cmd, desc in lines
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
