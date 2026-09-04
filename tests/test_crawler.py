from __future__ import annotations

import re
from pathlib import Path

import pytest
from curl_cffi.requests.exceptions import ConnectionError, Timeout

from bot.exceptions import (
    CrawlerHTTPError,
    CrawlerParseError,
    NoSearchResultsError,
)
from crawler.instants import InstantsCrawler
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


async def test_has_base_url():
    assert InstantsCrawler.BASE_URL == 'https://www.myinstants.com'


async def test_search_returns_parsed_summaries(
    crawler, session, search_results_body
):
    session.queue(
        'https://www.myinstants.com/search?name=discord',
        FakeResponse(200, search_results_body),
    )
    results = await crawler.search('discord')

    assert len(results) == 25
    assert results[0].name == 'Discord Notification'
    assert results[0].page_url.startswith(
        'https://www.myinstants.com/en/instant/'
    )
    assert results[0].mp3_url == (
        'https://www.myinstants.com/media/sounds/discord-notification.mp3'
    )


async def test_first_match_returns_first_result(
    crawler, session, search_results_body
):
    session.queue(
        'https://www.myinstants.com/search?name=discord',
        FakeResponse(200, search_results_body),
    )
    match = await crawler.first_match('discord')

    assert match.name == 'Discord Notification'


async def test_first_match_raises_when_no_results(crawler, session):
    empty_html = (
        b'<html><body><div class="nothing-to-see"></div></body></html>'
    )
    session.queue(
        'https://www.myinstants.com/search?name=nomatch',
        FakeResponse(200, empty_html),
    )
    with pytest.raises(NoSearchResultsError):
        await crawler.first_match('nomatch')


async def test_http_5xx_raises_crawler_http_error(crawler, session):
    session.queue(
        'https://www.myinstants.com/search?name=x', FakeResponse(503)
    )
    with pytest.raises(CrawlerHTTPError):
        await crawler.search('x')


async def test_connection_error_raises_crawler_http_error(crawler, session):
    session.queue(
        'https://www.myinstants.com/search?name=x',
        ConnectionError('boom'),
    )
    with pytest.raises(CrawlerHTTPError):
        await crawler.search('x')


async def test_malformed_search_result_raises_parse_error(crawler, session):
    bad_html = b"""
        <div class="instant">
          <a class="instant-link">broken</a>
        </div>
    """
    session.queue(
        'https://www.myinstants.com/search?name=x', FakeResponse(200, bad_html)
    )
    with pytest.raises(CrawlerParseError):
        await crawler.search('x')


async def test_search_skips_unparseable_results(crawler, session):
    mixed_html = b"""
        <div class="instant">
          <a class="instant-link" href="/instant/good-one/">Good One</a>
          <button class="small-button"
            onclick="play('/media/sounds/good-one.mp3')"></button>
        </div>
        <div class="instant">
          <a class="instant-link">broken</a>
        </div>
    """
    session.queue(
        'https://www.myinstants.com/search?name=x',
        FakeResponse(200, mixed_html),
    )
    results = await crawler.search('x')

    assert len(results) == 1
    assert results[0].name == 'Good One'


async def test_search_parses_uppercase_mp3_extension(crawler, session):
    # MyInstants serves some clips with an uppercase .MP3 extension; the URL
    # regex must match case-insensitively or a valid card looks unparseable.
    html = b"""
        <div class="instant">
          <a class="instant-link" href="/instant/test-your-might/">Might</a>
          <button class="small-button"
            onclick="play('/media/sounds/test-your-might.MP3')"></button>
        </div>
    """
    session.queue(
        'https://www.myinstants.com/search?name=x', FakeResponse(200, html)
    )
    results = await crawler.search('x')

    assert len(results) == 1
    assert results[0].mp3_url.endswith('/media/sounds/test-your-might.MP3')


async def test_fetch_retries_on_transient(session, search_results_body):
    crawler = build_crawler(session, max_retries=2, retry_backoff_seconds=0)
    url = 'https://www.myinstants.com/search?name=discord'
    session.queue(
        url, FakeResponse(503), FakeResponse(200, search_results_body)
    )
    results = await crawler.search('discord')

    assert len(results) > 0
    assert session.request_count(url) == 2


async def test_fetch_exhausts_retries_on_repeated_5xx(session):
    crawler = build_crawler(session, max_retries=2, retry_backoff_seconds=0)
    url = 'https://www.myinstants.com/search?name=x'
    session.queue(url, FakeResponse(503))
    with pytest.raises(CrawlerHTTPError, match='failed after retries'):
        await crawler.search('x')
    assert session.request_count(url) == 3


async def test_fetch_retries_on_timeout(session, search_results_body):
    crawler = build_crawler(session, max_retries=2, retry_backoff_seconds=0)
    url = 'https://www.myinstants.com/search?name=discord'
    session.queue(
        url, Timeout('timed out'), FakeResponse(200, search_results_body)
    )
    results = await crawler.search('discord')

    assert len(results) > 0


async def test_4xx_not_retried(session):
    crawler = build_crawler(session, max_retries=2, retry_backoff_seconds=0)
    url = 'https://www.myinstants.com/search?name=x'
    session.queue(url, FakeResponse(404))
    with pytest.raises(CrawlerHTTPError):
        await crawler.search('x')
    assert session.request_count(url) == 1


async def test_get_details_parses_expected_fields(
    crawler, session, search_results_body, instant_details_body
):
    session.queue(
        'https://www.myinstants.com/search?name=discord',
        FakeResponse(200, search_results_body),
    )
    results = await crawler.search('discord')

    target = results[0]
    session.queue(target.page_url, FakeResponse(200, instant_details_body))
    details = await crawler.get_details(target)

    assert details.title == 'Discord Notification'
    assert details.uploader_name == 'Anonymous'
    assert details.uploader_url is None
    assert details.likes and re.match(r'[\d,]+ users', details.likes)
    assert details.views and re.match(r'[\d,]+ views', details.views)
    assert details.description is None


def test_parse_views_matches_singular_and_plural():
    from bs4 import BeautifulSoup

    from crawler.instants import _parse_views

    for text, expected in [('1 view', '1 view'), ('42 views', '42 views')]:
        soup = BeautifulSoup(
            f'<div id="instant-page-likes"></div><div>{text}</div>',
            'html.parser',
        )
        assert _parse_views(soup) == expected


async def test_to_ytdl_data_shape(crawler, session, instant_details_body):
    # Re-use the details fixture alone by manufacturing a summary.
    from crawler.instants import InstantSummary

    summary = InstantSummary(
        name='x',
        page_url='https://www.myinstants.com/instant/x/',
        mp3_url='https://www.myinstants.com/media/sounds/x.mp3',
    )
    session.queue(summary.page_url, FakeResponse(200, instant_details_body))
    details = await crawler.get_details(summary)
    payload = details.to_ytdl_data()
    assert set(payload.keys()) == {
        'title',
        'description',
        'likes',
        'uploader_name',
        'uploader_url',
        'views',
    }
