from __future__ import annotations

import time
from pathlib import Path

import pytest

from crawler.instants import InstantsCrawler, InstantSummary
from tests.conftest import FakeResponse, FakeSession, build_crawler

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
def crawler(session: FakeSession) -> InstantsCrawler:
    return build_crawler(session)


async def test_search_cache_hit_skips_http(
    crawler, session, search_results_body
):
    url = 'https://www.myinstants.com/search?name=discord'
    session.queue(url, FakeResponse(200, search_results_body))
    first = await crawler.search('discord')
    second = await crawler.search('discord')

    assert session.request_count(url) == 1
    assert first == second


async def test_search_cache_miss_on_distinct_queries(
    crawler, session, search_results_body
):
    url_foo = 'https://www.myinstants.com/search?name=foo'
    url_bar = 'https://www.myinstants.com/search?name=bar'
    session.queue(url_foo, FakeResponse(200, search_results_body))
    session.queue(url_bar, FakeResponse(200, search_results_body))
    await crawler.search('foo')
    await crawler.search('bar')

    assert session.request_count(url_foo) == 1
    assert session.request_count(url_bar) == 1


async def test_search_cache_key_is_normalized(
    crawler, session, search_results_body
):
    url = 'https://www.myinstants.com/search?name=Foo'
    session.queue(url, FakeResponse(200, search_results_body))
    first = await crawler.search('Foo')
    second = await crawler.search('foo')
    third = await crawler.search('  FOO  ')

    assert session.request_count(url) == 1
    assert first == second == third


async def test_get_details_cache_hit_skips_http(session, instant_details_body):
    crawler = build_crawler(session)
    summary = InstantSummary(
        name='x',
        page_url='https://www.myinstants.com/instant/x/',
        mp3_url='https://www.myinstants.com/media/sounds/x.mp3',
    )
    session.queue(summary.page_url, FakeResponse(200, instant_details_body))
    first = await crawler.get_details(summary)
    second = await crawler.get_details(summary)

    assert session.request_count(summary.page_url) == 1
    assert first == second


async def test_rate_limiter_serialises_distinct_requests(
    session, search_results_body
):
    crawler = build_crawler(session, rate_limit_per_sec=2.0)
    queries = ['a', 'b', 'c']
    for q in queries:
        session.queue(
            f'https://www.myinstants.com/search?name={q}',
            FakeResponse(200, search_results_body),
        )
    start = time.monotonic()
    for q in queries:
        await crawler.search(q)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.4
