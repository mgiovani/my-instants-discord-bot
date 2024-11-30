import os
from unittest import mock

import pytest
from bs4 import BeautifulSoup

from crawler.instants import InstantsCrawler


def get_fixture(file_name: str) -> dict:
    path = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(path, 'fixtures', file_name)
    with open(full_path, 'rb') as f:
        return f.read()


@pytest.fixture
def search_results_page():
    return get_fixture('search_results.html')


@pytest.fixture
def instant_details_page():
    return get_fixture('instant_details.html')


@pytest.fixture
def instants_crawler():
    return InstantsCrawler()


@pytest.fixture
def instant_result(search_results_page, instants_crawler):
    with mock.patch('crawler.instants.requests.get') as mock_requests:
        mock_requests.return_value.content = search_results_page
        instant_result = instants_crawler.get_single_search_result('discord')
    return instant_result


@pytest.fixture
def soup_instant_details(instant_details_page):
    return BeautifulSoup(instant_details_page, 'html.parser')


def test_instants_crawler_has_base_url():
    crawler = InstantsCrawler()
    assert crawler.BASE_URL == 'https://www.myinstants.com'


@mock.patch('crawler.instants.requests.get')
def test_instants_crawler_get_search_results(
    mock_requests, search_results_page, instants_crawler
):
    mock_requests.return_value.content = search_results_page

    results = instants_crawler.get_search_results('discord')
    assert len(results) == 25
    assert 'Discord Notification' in results[0].text
    assert 'discordjoin' in results[1].text
    assert 'discord call' in results[2].text


@mock.patch('crawler.instants.requests.get')
def test_instants_crawler_get_single_search_result(
    mock_requests, search_results_page, instants_crawler
):
    mock_requests.return_value.content = search_results_page

    result = instants_crawler.get_single_search_result('discord')
    assert 'Discord Notification' in result.text


def test_get_instant_name(instants_crawler, instant_result):
    instant_name = instants_crawler.get_instant_name(instant_result)
    assert instant_name == 'Discord Notification'


def test_get_instant_mp3_link(instants_crawler, instant_result):
    instant_mp3_link = instants_crawler.get_instant_mp3_link(instant_result)
    assert instant_mp3_link == (
        'https://www.myinstants.com/media/sounds/discord-notification.mp3'
    )


def test_get_instant_link(instants_crawler, instant_result):
    instant_link = instants_crawler.get_instant_link(instant_result)
    assert instant_link == (
        'https://www.myinstants.com/instant/discord-notification-38119/'
    )


def test_get_instant_details(
    instants_crawler, instant_result, instant_details_page
):
    with mock.patch('crawler.instants.requests.get') as mock_requests:
        mock_requests.return_value.content = instant_details_page
        instant_details = instants_crawler.get_instant_details(instant_result)
    assert instant_details == {
        'description': None,
        'likes': '43,960 users',
        'title': 'Discord Notification',
        'uploader_name': 'Anonymous',
        'uploader_url': None,
        'views': '660,100 views',
    }


def test_get_instant_title(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_title(soup_instant_details)
    assert result == 'Discord Notification'


def test_get_instant_description(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_description(soup_instant_details)
    assert result is None


def test_get_instant_likes(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_likes(soup_instant_details)
    assert result == '43,960 users'


def test_get_instant_views(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_views(soup_instant_details)
    assert result == '660,100 views'


def test_get_instant_uploader_name(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_uploader_name(soup_instant_details)
    assert result == 'Anonymous'


def test_get_instant_uploader_url(soup_instant_details, instants_crawler):
    result = instants_crawler.get_instant_uploader_url(soup_instant_details)
    assert result is None
