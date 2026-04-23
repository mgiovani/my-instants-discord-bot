from __future__ import annotations


class MyInstantsBotError(Exception):
    """Base for all bot-raised errors.

    Subclasses whose instances carry a user-safe `message` attribute are
    surfaced directly in the slash-command reply; anything else is treated
    as an unexpected failure, logged with full context, and reported to
    Sentry when configured.
    """

    user_message: str | None = None


class MissingBotToken(MyInstantsBotError):
    user_message = None


class VoiceError(MyInstantsBotError):
    """Voice-channel precondition failure (not connected, already joined)."""


class NotInVoiceError(VoiceError):
    user_message = 'You need to be in a voice channel to use this.'


class NothingPlayingError(MyInstantsBotError):
    user_message = 'Nothing is playing right now.'


class EmptyQueueError(MyInstantsBotError):
    user_message = 'The queue is empty.'


class QueueIndexError(MyInstantsBotError):
    def __init__(self, index: int, length: int) -> None:
        super().__init__(
            f'Queue index {index} is out of range (0-{length - 1}).'
        )
        self.user_message = (
            f'Index {index + 1} is not in the queue (have 1-{length}).'
        )


class NoSearchResultsError(MyInstantsBotError):
    def __init__(self, search: str) -> None:
        super().__init__(f'No results for {search!r}')
        self.user_message = (
            f'Could not find any sounds matching **{search}** on MyInstants.'
        )


class CrawlerError(MyInstantsBotError):
    """Base for scraping failures against myinstants.com."""

    user_message = 'MyInstants is having a moment. Try again in a bit.'


class CrawlerParseError(CrawlerError):
    """Markup we depend on has drifted."""

    user_message = (
        'MyInstants changed their layout. The maintainer has been nudged.'
    )


class CrawlerHTTPError(CrawlerError):
    """Non-2xx response or connection failure."""


class YTDLError(MyInstantsBotError):
    user_message = 'Could not load the audio stream. Try again in a bit.'
