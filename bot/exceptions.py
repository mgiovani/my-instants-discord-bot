from __future__ import annotations

from collections.abc import Sequence


class MyInstantsBotError(Exception):
    user_message: str | None = None


class MissingBotToken(MyInstantsBotError):
    pass


class VoiceError(MyInstantsBotError):
    pass


class NotInVoiceError(VoiceError):
    user_message = 'You need to be in a voice channel to use this.'


class VoiceConnectError(VoiceError):
    user_message = (
        'I could not join your voice channel. Something went wrong on '
        "Discord's side, so it is worth trying again in a moment."
    )


class VoiceChannelOverrideError(VoiceError):
    def __init__(self, channel_name: str, missing: Sequence[str]) -> None:
        super().__init__(
            f'Channel override blocks {", ".join(missing)} on {channel_name!r}'
        )
        self.user_message = (
            f'I cannot join **{channel_name}**. My server-wide permissions '
            'are fine, but that channel has its own permission settings that '
            f'block me ({_humanise(missing)}). Open **Edit Channel > '
            'Permissions** on it, add my role, and allow **View Channel**, '
            '**Connect** and **Speak**. Re-inviting me will not fix this, '
            'since the invite screen only sets server-wide permissions.'
        )


class VoiceMissingPermissionError(VoiceError):
    def __init__(self, channel_name: str, missing: Sequence[str]) -> None:
        super().__init__(f'Missing {", ".join(missing)} on {channel_name!r}')
        self.user_message = (
            f'I cannot join **{channel_name}** because I am missing '
            f'{_humanise(missing)}. Ask a server admin to grant my role those '
            'permissions.'
        )


class VoiceChannelFullError(VoiceError):
    def __init__(self, channel_name: str) -> None:
        super().__init__(f'Channel {channel_name!r} is full')
        self.user_message = (
            f'**{channel_name}** is full, so I cannot join it. Free up a slot '
            'or raise the channel user limit.'
        )


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


class CrawlerNotFoundError(CrawlerHTTPError):
    pass


class YTDLError(MyInstantsBotError):
    user_message = 'Could not load the audio stream. Try again in a bit.'


def _humanise(names: Sequence[str]) -> str:
    formatted = [f'**{name}**' for name in names]
    if len(formatted) == 1:
        return formatted[0]
    return f'{", ".join(formatted[:-1])} and {formatted[-1]}'
