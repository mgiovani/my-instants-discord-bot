from __future__ import annotations

import discord
from discord import app_commands
from loguru import logger

from bot.commands._base import BotCogBase
from bot.exceptions import NothingPlayingError, NotInVoiceError
from bot.song import Song
from bot.ytdl import YTDLSource


class PlaybackCog(BotCogBase):
    @app_commands.command(name='mi', description='Play a MyInstants sound.')
    async def play(
        self, interaction: discord.Interaction, search: str
    ) -> None:
        self._require_voice_channel(interaction)
        await interaction.response.defer()

        # Resolved before joining: a failed search should not drag the bot
        # into the channel, and a doomed handshake should not stall the lookup.
        instant = await self.crawler.first_match(search)
        details = await self.crawler.get_details(instant)

        state = await self._state_for(interaction)
        await self._ensure_connected(interaction, state)

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

    @app_commands.command(name='loop', description='Toggle loop for playing.')
    async def loop(self, interaction: discord.Interaction) -> None:
        state = await self._state_for(interaction)
        if not state.is_playing:
            raise NothingPlayingError
        state.loop_current = not state.loop_current
        if state.loop_current:
            await interaction.response.send_message(
                f'Loop enabled (auto-off after '
                f'{state.loop_max_iterations} replays).'
            )
        else:
            await interaction.response.send_message('Loop disabled.')

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
        await interaction.response.send_message(f'Volume set to {volume}%.')
