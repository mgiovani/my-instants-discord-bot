from __future__ import annotations


class MyInstantsBotError(Exception):
    user_message: str | None = None


class MissingBotToken(MyInstantsBotError):
    pass


class VoiceError(MyInstantsBotError):
    pass


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
    user_message = 'MyInstants is having a moment. Try again in a bit.'


class CrawlerParseError(CrawlerError):
    user_message = (
        'MyInstants changed their layout. The maintainer has been nudged.'
    )


class CrawlerHTTPError(CrawlerError):
    pass


class YTDLError(MyInstantsBotError):
    user_message = 'Could not load the audio stream. Try again in a bit.'
