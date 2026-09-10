from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from loguru import logger

from bot.exceptions import (
    NotInVoiceError,
    VoiceChannelFullError,
    VoiceChannelOverrideError,
    VoiceConnectError,
    VoiceMissingPermissionError,
)

_REQUIRED_TO_JOIN = (('View Channel', 'view_channel'), ('Connect', 'connect'))

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
        self._check_can_join(target)
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
                    state.voice = None
                    await self._force_disconnect(live)
                    raise VoiceConnectError(str(exc) or repr(exc)) from exc
                state.voice = live
                return live
            await self._force_disconnect(live)

        try:
            voice = await target.connect(
                self_deaf=True,
                timeout=self.settings.voice_connect_timeout_seconds,
            )
        except (TimeoutError, discord.ClientException) as exc:
            state.voice = None
            self._log_unexplained_failure(
                target, exc, had_client=live is not None
            )
            raise VoiceConnectError(str(exc) or repr(exc)) from exc
        state.voice = voice
        return voice

    def _check_can_join(
        self, target: discord.VoiceChannel | discord.StageChannel
    ) -> None:
        me = target.guild.me
        effective = target.permissions_for(me)
        server_wide = me.guild_permissions
        name = discord.utils.escape_markdown(target.name)

        denied = [
            (label, getattr(server_wide, attr))
            for label, attr in _REQUIRED_TO_JOIN
            if not getattr(effective, attr)
        ]
        blocked_by_channel = [
            label
            for label, allowed_server_wide in denied
            if allowed_server_wide
        ]
        if blocked_by_channel:
            raise VoiceChannelOverrideError(name, blocked_by_channel)
        if denied:
            raise VoiceMissingPermissionError(
                name, [label for label, _ in denied]
            )

        if (
            target.user_limit
            and len(target.members) >= target.user_limit
            and not effective.move_members
        ):
            raise VoiceChannelFullError(
                discord.utils.escape_markdown(target.name)
            )

    def _log_unexplained_failure(
        self,
        target: discord.VoiceChannel | discord.StageChannel,
        exc: BaseException,
        *,
        had_client: bool,
    ) -> None:
        me = target.guild.me
        effective = target.permissions_for(me)
        bot_voice = me.voice.channel if me.voice else None
        logger.bind(
            guild_id=target.guild.id,
            channel_id=target.id,
            channel_type=str(target.type),
            can_view=effective.view_channel,
            can_connect=effective.connect,
            can_speak=effective.speak,
            can_move_members=effective.move_members,
            user_limit=target.user_limit,
            occupancy=len(target.members),
            rtc_region=target.rtc_region,
            bot_voice_channel=bot_voice.id if bot_voice else None,
            had_voice_client=had_client,
        ).warning(
            'Voice connect failed despite passing pre-flight: {exc!r}', exc=exc
        )

    async def _force_disconnect(self, voice: discord.VoiceClient) -> None:
        try:
            async with asyncio.timeout(
                self.settings.voice_cleanup_timeout_seconds
            ):
                await voice.disconnect(force=True)
        except Exception as exc:
            logger.warning(
                'Could not clear stale voice client: {exc}', exc=exc
            )
            voice.cleanup()
