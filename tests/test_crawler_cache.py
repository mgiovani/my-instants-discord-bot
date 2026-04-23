from __future__ import annotations

import time
from pathlib import Path

import aiohttp
import pytest
from aioresponses import aioresponses
from yarl import URL

from crawler.instants import InstantsCrawler, InstantSummary

FIXTURES = Path(__file__).parent / 'fixtures'


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def search_results_body() -> bytes:
    return _fixture('search_results.html')


@pytest.fixture
def instant_details_body() -> bytes:
    return _fixture('instant_details.html')


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def crawler(session):
    return InstantsCrawler(session=session)


async def test_search_cache_hit_skips_http(crawler, search_results_body):
    url = 'https://www.myinstants.com/search?name=discord'
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=search_results_body)
        first = await crawler.search('discord')
        second = await crawler.search('discord')
        assert len(mocked.requests[('GET', URL(url))]) == 1

    assert first == second


async def test_search_cache_miss_on_distinct_queries(
    crawler, search_results_body
):
    url_foo = 'https://www.myinstants.com/search?name=foo'
    url_bar = 'https://www.myinstants.com/search?name=bar'
    with aioresponses() as mocked:
        mocked.get(url_foo, status=200, body=search_results_body)
        mocked.get(url_bar, status=200, body=search_results_body)
        await crawler.search('foo')
        await crawler.search('bar')
        assert len(mocked.requests[('GET', URL(url_foo))]) == 1
        assert len(mocked.requests[('GET', URL(url_bar))]) == 1


async def test_search_cache_key_is_normalized(crawler, search_results_body):
    url = 'https://www.myinstants.com/search?name=Foo'
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=search_results_body)
        first = await crawler.search('Foo')
        second = await crawler.search('foo')
        third = await crawler.search('  FOO  ')
        assert len(mocked.requests[('GET', URL(url))]) == 1

    assert first == second == third


async def test_get_details_cache_hit_skips_http(session, instant_details_body):
    crawler = InstantsCrawler(session=session)
    summary = InstantSummary(
        name='x',
        page_url='https://www.myinstants.com/instant/x/',
        mp3_url='https://www.myinstants.com/media/sounds/x.mp3',
    )
    with aioresponses() as mocked:
        mocked.get(summary.page_url, status=200, body=instant_details_body)
        first = await crawler.get_details(summary)
        second = await crawler.get_details(summary)
        assert len(mocked.requests[('GET', URL(summary.page_url))]) == 1

    assert first == second


async def test_rate_limiter_serialises_distinct_requests(
    session, search_results_body
):
    crawler = InstantsCrawler(session=session, rate_limit_per_sec=2.0)
    queries = ['a', 'b', 'c']
    with aioresponses() as mocked:
        for q in queries:
            mocked.get(
                f'https://www.myinstants.com/search?name={q}',
                status=200,
                body=search_results_body,
            )
        start = time.monotonic()
        for q in queries:
            await crawler.search(q)
        elapsed = time.monotonic() - start

    assert elapsed >= 0.4
