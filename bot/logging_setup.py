"""Loguru + Sentry bootstrap shared by `bot.run` and future entrypoints.

The heartbeat loop lives here too because it's tiny and tied to the log
sink lifecycle (restart the bot → fresh heartbeat + fresh sinks).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext import tasks
from loguru import logger

if TYPE_CHECKING:
    from bot.config import Settings


def configure_logging(settings: Settings) -> None:
    logger.remove()
    level = settings.log_level
    if settings.log_format == 'json':
        logger.add(
            _json_sink,
            level=level,
            enqueue=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            colorize=True,
            format=(
                '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
                '<level>{level: <8}</level> | '
                '<cyan>{name}</cyan>:<cyan>{function}</cyan>:'
                '<cyan>{line}</cyan> - <level>{message}</level>'
            ),
            enqueue=False,
        )


def _json_sink(message: object) -> None:
    record = getattr(message, 'record', None)
    if record is None:
        sys.stderr.write(str(message))
        return
    extra = record.get('extra') or {}
    payload: dict[str, object] = {
        'ts': record['time'].isoformat(),
        'level': record['level'].name,
        'logger': (f'{record["name"]}:{record["function"]}:{record["line"]}'),
        'message': record['message'],
        **{str(k): _jsonable(v) for k, v in dict(extra).items()},
    }
    if record.get('exception'):
        payload['exception'] = str(record['exception'])
    sys.stderr.write(json.dumps(payload, default=str) + '\n')
    sys.stderr.flush()


def _jsonable(value: object) -> object:
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def configure_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return
    try:
        import sentry_sdk  # noqa: PLC0415 — optional dep, import only if DSN set
    except ImportError:  # pragma: no cover
        logger.warning('SENTRY_DSN set but sentry_sdk not installed')
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        attach_stacktrace=True,
    )
    logger.info(
        'Sentry initialised for environment={env}',
        env=settings.environment,
    )


def capture_exception(error: BaseException) -> None:
    """Safe no-op if sentry_sdk isn't configured."""
    try:
        import sentry_sdk  # noqa: PLC0415 — optional dep
    except ImportError:  # pragma: no cover
        return
    sentry_sdk.capture_exception(error)


def start_heartbeat(settings: Settings) -> tasks.Loop:
    path = Path(settings.heartbeat_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    @tasks.loop(seconds=30)
    async def _beat() -> None:
        path.touch()  # noqa: ASYNC240 — a single inode touch is fine

    _beat.start()
    return _beat
