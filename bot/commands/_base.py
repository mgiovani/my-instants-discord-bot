from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands

from bot.exceptions import NotInVoiceError

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.voice import GuildVoiceState, GuildVoiceStateManager
    from crawler.instants import InstantsCrawler


class BotCogBase(commands.Cog):
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
            # channel is narrowed by hasattr, not isinstance, so it also
            # matches test doubles that duck-type a Messageable channel.
            send = cast(discord.abc.Messageable, channel).send

            async def notify(embed: discord.Embed) -> None:
                await send(embed=embed)

            state.set_now_playing_sink(notify)
        return state

    def _require_voice_channel(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | discord.StageChannel:
        member = interaction.user
        voice = getattr(member, 'voice', None)
        if voice is None or voice.channel is None:
            raise NotInVoiceError
        channel = voice.channel
        if not isinstance(
            channel, (discord.VoiceChannel, discord.StageChannel)
        ):
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
            if live.channel.id != target.id:
                await live.move_to(target)
            state.voice = live
            return live

        voice = await target.connect(self_deaf=True)
        state.voice = voice
        return voice
