from __future__ import annotations

import discord
from discord import app_commands

from bot.commands._base import BotCogBase


class HelpCog(BotCogBase):
    @app_commands.command(name='help', description='List commands.')
    async def help_command(self, interaction: discord.Interaction) -> None:
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
            description='\n'.join(f'**{cmd}**: {desc}' for cmd, desc in lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
