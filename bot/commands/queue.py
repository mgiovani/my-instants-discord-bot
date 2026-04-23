from __future__ import annotations

import math

import discord
from discord import app_commands

from bot.commands._base import BotCogBase
from bot.exceptions import EmptyQueueError


class QueueCog(BotCogBase):
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
            for idx, song in enumerate(state.songs[start:end], start=start)
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
