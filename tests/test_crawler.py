from __future__ import annotations

from pathlib import Path

import aiohttp
import pytest
from aioresponses import aioresponses

from bot.exceptions import (
    CrawlerHTTPError,
    CrawlerParseError,
    NoSearchResultsError,
)
from crawler.instants import InstantsCrawler

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


async def test_has_base_url():
    assert InstantsCrawler.BASE_URL == 'https://www.myinstants.com'


async def test_search_returns_parsed_summaries(crawler, search_results_body):
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=discord',
            status=200,
            body=search_results_body,
        )
        results = await crawler.search('discord')

    assert len(results) == 25
    assert results[0].name == 'Discord Notification'
    assert results[0].page_url.startswith('https://www.myinstants.com/instant/')
    assert results[0].mp3_url == (
        'https://www.myinstants.com/media/sounds/discord-notification.mp3'
    )


async def test_first_match_returns_first_result(crawler, search_results_body):
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=discord',
            status=200,
            body=search_results_body,
        )
        match = await crawler.first_match('discord')

    assert match.name == 'Discord Notification'


async def test_first_match_raises_when_no_results(crawler):
    empty_html = b'<html><body><div class="nothing-to-see"></div></body></html>'
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=nomatch',
            status=200,
            body=empty_html,
        )
        with pytest.raises(NoSearchResultsError):
            await crawler.first_match('nomatch')


async def test_http_5xx_raises_crawler_http_error(crawler):
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=x',
            status=503,
        )
        with pytest.raises(CrawlerHTTPError):
            await crawler.search('x')


async def test_connection_error_raises_crawler_http_error(crawler):
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=x',
            exception=aiohttp.ClientConnectionError('boom'),
        )
        with pytest.raises(CrawlerHTTPError):
            await crawler.search('x')


async def test_malformed_search_result_raises_parse_error(crawler):
    bad_html = b"""
        <div class="instant">
          <a class="instant-link">broken</a>
        </div>
    """
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=x',
            status=200,
            body=bad_html,
        )
        with pytest.raises(CrawlerParseError):
            await crawler.search('x')


async def test_get_details_parses_expected_fields(
    crawler, search_results_body, instant_details_body
):
    with aioresponses() as mocked:
        mocked.get(
            'https://www.myinstants.com/search?name=discord',
            status=200,
            body=search_results_body,
        )
        results = await crawler.search('discord')

    target = results[0]
    with aioresponses() as mocked:
        mocked.get(
            target.page_url,
            status=200,
            body=instant_details_body,
        )
        details = await crawler.get_details(target)

    assert details.title == 'Discord Notification'
    assert details.uploader_name == 'Anonymous'
    assert details.uploader_url is None
    assert details.likes == '43,960 users'
    assert details.views == '660,100 views'
    assert details.description is None


async def test_to_ytdl_data_shape(crawler, instant_details_body):
    # Re-use the details fixture alone by manufacturing a summary.
    from crawler.instants import InstantSummary

    summary = InstantSummary(
        name='x',
        page_url='https://www.myinstants.com/instant/x/',
        mp3_url='https://www.myinstants.com/media/sounds/x.mp3',
    )
    with aioresponses() as mocked:
        mocked.get(summary.page_url, status=200, body=instant_details_body)
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
