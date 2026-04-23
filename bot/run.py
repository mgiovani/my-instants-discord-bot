from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

import discord
from discord import Activity, ActivityType, Intents
from discord.ext import commands
from loguru import logger

from bot.client import InstantClient
from bot.config import get_settings
from bot.errors import install_error_handler
from bot.exceptions import MissingBotToken
from bot.voice import GuildVoiceStateManager
from crawler.instants import InstantsCrawler

if TYPE_CHECKING:
    from bot.config import Settings


def build_intents() -> Intents:
    intents = Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = False
    intents.message_content = False
    return intents


class MyInstantsBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or('>'),
            description='Play audio from MyInstants',
            intents=build_intents(),
            activity=Activity(
                type=ActivityType.listening,
                name='/mi',
            ),
        )
        self.settings = settings
        self.crawler = InstantsCrawler(
            timeout_seconds=settings.myinstants_timeout_seconds,
            connect_timeout_seconds=settings.myinstants_connect_timeout_seconds,
            search_limit=settings.search_result_limit,
        )
        self.voice_states = GuildVoiceStateManager(settings)

    async def setup_hook(self) -> None:
        install_error_handler(self.tree)
        await self.add_cog(
            InstantClient(
                self,
                settings=self.settings,
                crawler=self.crawler,
                voice_states=self.voice_states,
            )
        )
        await self._sync_commands()
        self._install_signal_handlers()

    async def _sync_commands(self) -> None:
        settings = self.settings
        if settings.dev_guild_id is not None and not settings.sync_global:
            guild = discord.Object(id=settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(
                'Synced {count} commands to dev guild {guild_id}',
                count=len(synced),
                guild_id=settings.dev_guild_id,
            )
            return
        if settings.sync_global:
            synced = await self.tree.sync()
            logger.info('Synced {count} global commands', count=len(synced))
            return
        logger.info(
            'Skipping slash-command sync. Set MYINSTANTS_DEV_GUILD_ID for a '
            'dev guild or MYINSTANTS_SYNC_GLOBAL=true for a global sync.'
        )

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(self._shutdown(s))
                )
            except NotImplementedError:
                logger.debug('Signal handlers not available on this platform')
                break

    async def _shutdown(self, sig: signal.Signals) -> None:
        logger.info('Received {sig}, shutting down', sig=sig.name)
        await self.voice_states.close_all()
        await self.crawler.aclose()
        await self.close()

    async def on_ready(self) -> None:
        user = self.user
        if user is not None:
            logger.info('Logged in as {user} ({user_id})', user=user, user_id=user.id)


def main() -> None:
    settings = get_settings()
    token = settings.bot_token.get_secret_value()
    if not token:
        raise MissingBotToken(
            'MYINSTANTS_BOT_TOKEN is required; see env.example'
        )
    bot = MyInstantsBot(settings)
    bot.run(token, log_handler=None)


if __name__ == '__main__':
    main()
