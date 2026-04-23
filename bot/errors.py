from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias

import discord
from discord import app_commands
from loguru import logger

from bot.exceptions import MyInstantsBotError

SentryCapture: TypeAlias = Callable[
    [BaseException], Awaitable[None] | None
]


def install_error_handler(
    tree: app_commands.CommandTree,
    *,
    sentry_capture: SentryCapture | None = None,
) -> None:
    async def on_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await handle_app_command_error(
            interaction, error, sentry_capture=sentry_capture
        )

    tree.on_error = on_error  # type: ignore[method-assign]


async def handle_app_command_error(
    interaction: discord.Interaction,
    error: BaseException,
    *,
    sentry_capture: SentryCapture | None = None,
) -> None:
    root = _unwrap(error)
    command_name = (
        interaction.command.qualified_name if interaction.command else '<none>'
    )
    log = logger.bind(
        guild_id=interaction.guild_id,
        user_id=interaction.user.id,
        command=command_name,
    )

    if isinstance(root, MyInstantsBotError) and root.user_message is not None:
        log.info(
            'User-facing error in /{command}: {msg}',
            command=command_name,
            msg=root.user_message,
        )
        await _reply_ephemeral(interaction, root.user_message)
        return

    log.opt(exception=root).error(
        'Unhandled error in /{command}', command=command_name
    )
    if sentry_capture is not None:
        result = sentry_capture(root)
        if result is not None:
            await result
    await _reply_ephemeral(
        interaction,
        'Something broke on my end. The maintainer has been pinged.',
    )


def _unwrap(error: BaseException) -> BaseException:
    while isinstance(
        error,
        (
            app_commands.CommandInvokeError,
            app_commands.TransformerError,
        ),
    ):
        original = getattr(error, 'original', None)
        if original is None or original is error:
            return error
        error = original
    return error


async def _reply_ephemeral(
    interaction: discord.Interaction, message: str
) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException as exc:
        logger.warning('Failed to send error reply: {exc}', exc=exc)
