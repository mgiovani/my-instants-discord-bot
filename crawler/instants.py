from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from aiocache import Cache  # pyright: ignore[reportMissingTypeStubs]
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup, Tag
from curl_cffi import AsyncSession, CurlError
from curl_cffi.requests import Response
from loguru import logger

from bot.exceptions import (
    CrawlerHTTPError,
    CrawlerParseError,
    NoSearchResultsError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_BASE_URL = 'https://www.myinstants.com'
_MP3_PATH_RE = re.compile(r'/media[^\s"\']+\.mp3', re.IGNORECASE)
_VIEWS_RE = re.compile(r'[\d,]+\s*views?', re.IGNORECASE)
# Cloudflare 403s any client whose TLS fingerprint isn't a real browser;
# a full browser header set alone does not get through.
_IMPERSONATE = 'chrome'


@dataclass(frozen=True, slots=True)
class InstantSummary:
    name: str
    page_url: str
    mp3_url: str


@dataclass(frozen=True, slots=True)
class InstantDetails:
    title: str | None
    description: str | None
    likes: str | None
    uploader_name: str
    uploader_url: str | None
    views: str | None

    def to_ytdl_data(self) -> dict[str, str | None]:
        return {
            'title': self.title,
            'description': self.description,
            'likes': self.likes,
            'uploader_name': self.uploader_name,
            'uploader_url': self.uploader_url,
            'views': self.views,
        }


class _AsyncCache(Protocol):
    """Typed view of the aiocache methods we use (aiocache has no stubs)."""

    async def get(self, key: str) -> object | None: ...
    async def set(self, key: str, value: object) -> None: ...


class _HTTPResponse(Protocol):
    status_code: int
    content: bytes


class _AsyncClientSession(Protocol):
    """Typed view of the curl_cffi session methods we use (lets a
    structural test double stand in without subclassing AsyncSession)."""

    async def get(
        self,
        url: str,
        *,
        impersonate: str,
        timeout: tuple[float, float],  # noqa: ASYNC109 -- curl_cffi's name
    ) -> _HTTPResponse: ...
    async def close(self) -> None: ...


class InstantsCrawler:
    BASE_URL = _BASE_URL

    def __init__(
        self,
        *,
        session: _AsyncClientSession | None = None,
        timeout_seconds: float = 10.0,
        connect_timeout_seconds: float = 5.0,
        search_limit: int = 25,
        search_ttl_seconds: int = 600,
        details_ttl_seconds: int = 3600,
        rate_limit_per_sec: float = 5.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._owns_session = session is None
        self._timeout: tuple[float, float] = (
            connect_timeout_seconds,
            # curl_cffi sums the tuple into one ceiling, so the read half
            # is the remaining budget, not the full total.
            max(timeout_seconds - connect_timeout_seconds, 0.0),
        )
        self._session: _AsyncClientSession | None = session
        self._search_limit = search_limit
        self._search_cache: _AsyncCache = Cache(
            Cache.MEMORY, ttl=search_ttl_seconds
        )
        self._details_cache: _AsyncCache = Cache(
            Cache.MEMORY, ttl=details_ttl_seconds
        )
        self._limiter = AsyncLimiter(max(rate_limit_per_sec, 0.1), 1.0)
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    async def aclose(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> _AsyncClientSession:
        if self._session is None:
            self._session = AsyncSession[Response]()
        return self._session

    async def _fetch_soup(self, url: str) -> BeautifulSoup:
        body = await self._get_with_retry(url)
        return BeautifulSoup(body, 'html.parser')

    async def _get_with_retry(self, url: str) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._get_body(url)
            except CurlError as exc:
                last_exc = exc
            else:
                if response.status_code < 400:
                    return response.content
                if response.status_code < 500:
                    raise CrawlerHTTPError(
                        f'GET {url} failed: HTTP {response.status_code}'
                    )
                last_exc = CrawlerHTTPError(f'HTTP {response.status_code}')
            if attempt < self._max_retries:
                await asyncio.sleep(
                    self._retry_backoff_seconds * (attempt + 1)
                )
        raise CrawlerHTTPError(
            f'GET {url} failed after retries: {last_exc}'
        ) from last_exc

    async def _get_body(self, url: str) -> _HTTPResponse:
        session = await self._get_session()
        async with self._limiter:
            return await session.get(
                url, impersonate=_IMPERSONATE, timeout=self._timeout
            )

    async def search(self, query: str) -> list[InstantSummary]:
        cleaned = query.strip()
        key = cleaned.lower()
        cached = cast(
            'list[InstantSummary] | None',
            await self._search_cache.get(key),
        )
        if cached is not None:
            logger.debug('Cache hit: search {key!r}', key=key)
            return cached
        logger.debug('Searching myinstants for {query!r}', query=cleaned)
        soup = await self._fetch_soup(
            f'{_BASE_URL}/search?name={cleaned}',
        )
        results = self._parse_search_results(soup)
        await self._search_cache.set(key, results)
        return results

    def _parse_search_results(
        self, soup: BeautifulSoup
    ) -> list[InstantSummary]:
        instants = soup.select('.instant')
        results: list[InstantSummary] = []
        for tag in instants:
            if len(results) == self._search_limit:
                break
            try:
                results.append(self._parse_summary(tag))
            except CrawlerParseError as exc:
                logger.warning(
                    'Skipping unparseable search result: {exc}', exc=exc
                )
        if instants and not results:
            raise CrawlerParseError(
                'No search results could be parsed (layout may have changed)'
            )
        return results

    async def first_match(self, query: str) -> InstantSummary:
        results = await self.search(query)
        if not results:
            raise NoSearchResultsError(query)
        return results[0]

    async def get_details(self, instant: InstantSummary) -> InstantDetails:
        key = instant.page_url
        cached = cast(
            'InstantDetails | None', await self._details_cache.get(key)
        )
        if cached is not None:
            logger.debug('Cache hit: details {key!r}', key=key)
            return cached
        soup = await self._fetch_soup(instant.page_url)
        details = InstantDetails(
            title=_safe_text(soup.select_one('#instant-page-title')),
            description=_safe_text(
                soup.select_one('#instant-page-description p')
            ),
            likes=_safe_text(soup.select_one('#instant-page-likes b')),
            uploader_name=_parse_uploader_name(soup),
            uploader_url=_parse_uploader_url(soup),
            views=_parse_views(soup),
        )
        await self._details_cache.set(key, details)
        return details

    def _parse_summary(self, tag: Tag) -> InstantSummary:
        name_el = tag.select_one('.instant-link')
        if name_el is None:
            raise CrawlerParseError(
                'Could not find `.instant-link` on a search result'
            )
        page_href = _href(name_el.attrs)
        if page_href is None:
            raise CrawlerParseError('`.instant-link` has no `href`')

        mp3_container = tag.select_one('.small-button')
        if mp3_container is None:
            raise CrawlerParseError(
                'Could not find `.small-button` on a search result'
            )
        mp3_match = _MP3_PATH_RE.search(str(mp3_container))
        if mp3_match is None:
            raise CrawlerParseError(
                'Could not extract mp3 URL from `.small-button`'
            )

        return InstantSummary(
            name=name_el.get_text(strip=True),
            page_url=f'{_BASE_URL}{page_href}',
            mp3_url=f'{_BASE_URL}{mp3_match.group(0)}',
        )


def _href(attrs: Mapping[str, object]) -> str | None:
    value = attrs.get('href')
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    return None


def _safe_text(element: Tag | None) -> str | None:
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None


def _uploader_block(soup: BeautifulSoup) -> Tag | None:
    likes_block = soup.select_one('#instant-page-likes')
    if likes_block is None:
        return None
    sibling = likes_block.find_next_sibling()
    return sibling if isinstance(sibling, Tag) else None


def _parse_uploader_name(soup: BeautifulSoup) -> str:
    block = _uploader_block(soup)
    if block is None:
        return 'Anonymous'
    anchor = block.find('a')
    if not isinstance(anchor, Tag):
        return 'Anonymous'
    text = anchor.get_text(strip=True)
    return text or 'Anonymous'


def _parse_uploader_url(soup: BeautifulSoup) -> str | None:
    block = _uploader_block(soup)
    if block is None:
        return None
    anchor = block.find('a')
    if not isinstance(anchor, Tag):
        return None
    href = _href(anchor.attrs)
    return f'{_BASE_URL}{href}' if href else None


def _parse_views(soup: BeautifulSoup) -> str | None:
    block = _uploader_block(soup)
    if block is None:
        return None
    match = _VIEWS_RE.search(block.get_text(' ', strip=True))
    return match.group(0) if match else None
