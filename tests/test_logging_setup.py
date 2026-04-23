from __future__ import annotations

import json

import pytest
from loguru import logger

from bot.logging_setup import (
    capture_exception,
    configure_logging,
    configure_sentry,
)


@pytest.fixture(autouse=True)
def _clean_loguru():
    yield
    logger.remove()


def test_configure_logging_pretty_writes_colorized(settings, capfd):
    configure_logging(settings)
    logger.bind(guild_id=1).info('hello')
    logger.complete()
    err = capfd.readouterr().err
    assert 'hello' in err


def test_json_sink_produces_structured_records(capsys):
    from bot.logging_setup import _json_sink

    logger.remove()
    logger.add(_json_sink, level='DEBUG', enqueue=False)
    logger.bind(guild_id=42, command='mi').info('played')
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, 'expected at least one log line'
    payload = json.loads(lines[-1])
    assert payload['message'] == 'played'
    assert payload['guild_id'] == 42
    assert payload['command'] == 'mi'
    assert payload['level'] == 'INFO'
    assert 'ts' in payload
    assert payload['logger'].startswith('tests.test_logging_setup')


def test_configure_sentry_is_noop_without_dsn(settings):
    assert settings.sentry_dsn is None
    configure_sentry(settings)  # should not raise


def test_capture_exception_is_safe_without_sentry():
    capture_exception(RuntimeError('x'))  # no sentry init; must not raise
