from __future__ import annotations

from bot.exceptions import (
    CrawlerError,
    CrawlerHTTPError,
    CrawlerParseError,
    EmptyQueueError,
    MyInstantsBotError,
    NoSearchResultsError,
    NothingPlayingError,
    NotInVoiceError,
    QueueIndexError,
    YTDLError,
)


def test_user_messages_are_set_where_expected():
    assert NotInVoiceError.user_message is not None
    assert NothingPlayingError.user_message is not None
    assert EmptyQueueError.user_message is not None
    assert CrawlerError.user_message is not None
    assert CrawlerParseError.user_message is not None
    assert YTDLError.user_message is not None


def test_queue_index_error_has_human_message():
    err = QueueIndexError(5, 3)
    assert err.user_message is not None
    assert '6' in err.user_message  # 1-indexed to user
    assert '3' in err.user_message


def test_no_search_results_quotes_input():
    err = NoSearchResultsError('banana phone')
    assert err.user_message is not None
    assert 'banana phone' in err.user_message


def test_crawler_http_error_inherits_from_crawler_error():
    assert issubclass(CrawlerHTTPError, CrawlerError)
    assert issubclass(CrawlerParseError, CrawlerError)


def test_bot_error_base_class():
    for cls in (NotInVoiceError, YTDLError, CrawlerError):
        assert issubclass(cls, MyInstantsBotError)
