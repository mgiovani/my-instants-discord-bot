from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands
from discord.errors import ClientException

from bot.errors import handle_app_command_error
from bot.exceptions import (
    EmptyQueueError,
    NothingPlayingError,
    NotInVoiceError,
    VoiceConnectError,
)


def _interaction(done: bool = False):
    response = MagicMock()
    response.is_done.return_value = done
    response.send_message = AsyncMock()
    followup = MagicMock()
    followup.send = AsyncMock()

    interaction = MagicMock()
    interaction.response = response
    interaction.followup = followup
    interaction.guild_id = 1
    interaction.user = SimpleNamespace(id=2)
    interaction.command = SimpleNamespace(qualified_name='mi')
    return interaction


async def test_user_facing_error_replies_ephemerally():
    interaction = _interaction(done=False)
    await handle_app_command_error(interaction, NotInVoiceError())
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs['ephemeral'] is True


async def test_deferred_interaction_uses_followup():
    interaction = _interaction(done=True)
    await handle_app_command_error(interaction, EmptyQueueError())
    interaction.followup.send.assert_awaited_once()


async def test_unexpected_error_sends_generic_message_and_captures():
    interaction = _interaction(done=False)
    captured: list[BaseException] = []

    def capture(exc: BaseException) -> None:
        captured.append(exc)

    boom = RuntimeError('boom')
    await handle_app_command_error(interaction, boom, sentry_capture=capture)

    interaction.response.send_message.assert_awaited_once()
    assert captured == [boom]


async def test_command_invoke_error_is_unwrapped():
    interaction = _interaction(done=False)
    wrapped = app_commands.CommandInvokeError(
        command=MagicMock(), e=NothingPlayingError()
    )
    await handle_app_command_error(interaction, wrapped)
    call = interaction.response.send_message.await_args
    assert NothingPlayingError.user_message in call.args[0]


@pytest.mark.parametrize(
    ('error_cls',),
    [(NotInVoiceError,), (NothingPlayingError,), (EmptyQueueError,)],
)
async def test_user_facing_errors_dont_reach_sentry(error_cls):
    interaction = _interaction(done=False)
    captured: list[BaseException] = []

    def capture(exc: BaseException) -> None:
        captured.append(exc)

    await handle_app_command_error(
        interaction, error_cls(), sentry_capture=capture
    )
    assert captured == []


@pytest.mark.parametrize(
    'exc',
    [
        TimeoutError(),
        ClientException('Already connected to a voice channel.'),
    ],
)
async def test_voice_connect_failures_are_user_facing(exc):
    interaction = _interaction(done=True)
    await handle_app_command_error(
        interaction, VoiceConnectError(str(exc) or repr(exc))
    )

    interaction.followup.send.assert_awaited_once()
    message = interaction.followup.send.await_args.args[0]
    assert 'View Channel' in message
    assert 'Connect' in message
    assert 'broke on my end' not in message
