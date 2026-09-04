from __future__ import annotations

import os
from typing import Any

import pytest

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
    """Fake curl_cffi AsyncSession: queues canned responses/errors per URL."""

    def __init__(self) -> None:
        self._queues: dict[str, list[FakeResponse | Exception]] = {}
        self.calls: list[tuple[str, str, tuple[float, float]]] = []

    def queue(self, url: str, *items: FakeResponse | Exception) -> None:
        self._queues.setdefault(url, []).extend(items)

    async def get(
        self,
        url: str,
        *,
        impersonate: str,
        timeout: tuple[float, float],  # noqa: ASYNC109 -- curl_cffi's name
    ) -> FakeResponse:
        self.calls.append((url, impersonate, timeout))
        queue = self._queues.get(url)
        if not queue:
            raise AssertionError(f'FakeSession: no queued response for {url}')
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def request_count(self, url: str) -> int:
        return sum(call[0] == url for call in self.calls)

    async def close(self) -> None:
        pass


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


def build_crawler(session: FakeSession, **kwargs: Any) -> InstantsCrawler:
    return InstantsCrawler(session=session, **kwargs)


@pytest.fixture
def settings():
    from bot.config import Settings

    Settings.model_config['env_file'] = None
    return Settings(
        bot_token='test-token',  # type: ignore[arg-type]
    )
