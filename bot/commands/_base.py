from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from loguru import logger

from bot.exceptions import NotInVoiceError, VoiceConnectError

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
        async with state.connect_lock:
            return await self._connect_locked(interaction, target, state)

    async def _connect_locked(
        self,
        interaction: discord.Interaction,
        target: discord.VoiceChannel | discord.StageChannel,
        state: GuildVoiceState,
    ) -> discord.VoiceClient:
        live = interaction.guild.voice_client if interaction.guild else None

        if isinstance(live, discord.VoiceClient):
            if live.is_connected():
                try:
                    if live.channel.id != target.id:
                        await live.move_to(
                            target,
                            timeout=self.settings.voice_connect_timeout_seconds,
                        )
                except (TimeoutError, discord.ClientException) as exc:
                    # A move that times out leaves an unreachable client
                    # registered; clear it so the next call can reconnect.
                    state.voice = None
                    await self._force_disconnect(live)
                    raise VoiceConnectError(str(exc) or repr(exc)) from exc
                state.voice = live
                return live
            # discord.py rejects connect() while any voice client exists for
            # the guild, so a half-open one has to go or every retry raises.
            await self._force_disconnect(live)

        try:
            voice = await target.connect(
                self_deaf=True,
                timeout=self.settings.voice_connect_timeout_seconds,
            )
        except (TimeoutError, discord.ClientException) as exc:
            state.voice = None
            raise VoiceConnectError(str(exc) or repr(exc)) from exc
        state.voice = voice
        return voice

    @staticmethod
    async def _force_disconnect(voice: discord.VoiceClient) -> None:
        try:
            await voice.disconnect(force=True)
        except Exception as exc:
            logger.warning(
                'Could not clear stale voice client: {exc}', exc=exc
            )
            # disconnect() only deregisters via cleanup() once it returns, so
            # a raise would otherwise leave the client wedged in the guild.
            voice.cleanup()
