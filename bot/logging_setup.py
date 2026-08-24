from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import CoroutineType
from typing import TYPE_CHECKING, Any, override

from discord.ext import tasks
from loguru import logger

if TYPE_CHECKING:
    from loguru import Message

    from bot.config import Settings

type HeartbeatLoop = tasks.Loop[Callable[[], CoroutineType[Any, Any, None]]]


class _InterceptHandler(logging.Handler):
    @override
    def emit(self, record: logging.LogRecord) -> None:
        level: int | str
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging(settings: Settings) -> None:
    logger.remove()
    level = settings.log_level
    if settings.log_format == 'json':
        logger.add(_json_sink, level=level, enqueue=False)
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
            backtrace=False,
            diagnose=False,
            enqueue=False,
        )
    logging.basicConfig(
        handlers=[_InterceptHandler()], level=logging.WARNING, force=True
    )
    for name in ('discord.voice_client', 'discord.voice_state'):
        lg = logging.getLogger(name)
        lg.handlers = [_InterceptHandler()]
        lg.propagate = False
        lg.setLevel(logging.DEBUG)
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)


def _json_sink(message: Message) -> None:
    record = message.record
    payload: dict[str, object] = {
        'ts': record['time'].isoformat(),
        'level': record['level'].name,
        'logger': (f'{record["name"]}:{record["function"]}:{record["line"]}'),
        'message': record['message'],
        **{str(k): _jsonable(v) for k, v in record['extra'].items()},
    }
    if record['exception']:
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
        import sentry_sdk  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        logger.warning('SENTRY_DSN set but sentry_sdk not installed')
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        attach_stacktrace=True,
        include_local_variables=False,
    )
    logger.info(
        'Sentry initialised for environment={env}',
        env=settings.environment,
    )


def capture_exception(error: BaseException) -> None:
    try:
        import sentry_sdk  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return
    sentry_sdk.capture_exception(error)


def start_heartbeat(settings: Settings) -> HeartbeatLoop:
    path = Path(settings.heartbeat_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    @tasks.loop(seconds=30)
    async def _beat() -> None:
        path.touch()  # noqa: ASYNC240

    _beat.start()
    return _beat
