from __future__ import annotations

import os
from typing import Any, cast

import pytest
from curl_cffi import AsyncSession
from curl_cffi.requests import Response

from crawler.instants import InstantsCrawler

os.environ.setdefault('MYINSTANTS_BOT_TOKEN', 'test-token')
os.environ.setdefault('MYINSTANTS_ENV', 'dev')
os.environ.setdefault(
    'MYINSTANTS_PII_HASH_KEY',
    'test-key-do-not-use-in-prod',
)


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b'') -> None:
        self.status_code = status_code
        self.content = content


class FakeSession:
    """Fake curl_cffi AsyncSession: queues canned responses/errors per URL.

    Queued items are consumed in order; once a URL's queue is down to its
    last item, that item is returned for every further call (mirrors a
    "register a response for this endpoint" mock without needing tests to
    guess how many retry attempts will hit it).
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[FakeResponse | Exception]] = {}
        self.requests: list[str] = []

    def queue(self, url: str, *items: FakeResponse | Exception) -> None:
        self._queues.setdefault(url, []).extend(items)

    async def get(self, url: str, **_kwargs: object) -> FakeResponse:
        self.requests.append(url)
        queue = self._queues.get(url)
        if not queue:
            raise AssertionError(f'FakeSession: no queued response for {url}')
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def request_count(self, url: str) -> int:
        return self.requests.count(url)

    async def close(self) -> None:
        pass


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


def build_crawler(session: FakeSession, **kwargs: Any) -> InstantsCrawler:
    # The fake only mimics curl_cffi's AsyncSession.get() interface, so tell
    # pyright to trust it rather than making it a real subclass.
    return InstantsCrawler(
        session=cast(AsyncSession[Response], session), **kwargs
    )


@pytest.fixture
def settings():
    from bot.config import Settings

    Settings.model_config['env_file'] = None
    return Settings(
        bot_token='test-token',  # type: ignore[arg-type]
    )
