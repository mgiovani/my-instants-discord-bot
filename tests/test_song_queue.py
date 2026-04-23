from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.exceptions import QueueIndexError
from bot.song import Song, SongQueue


def _song(title: str) -> Song:
    source = SimpleNamespace(
        title=title,
        url=f'https://example.com/{title}',
        uploader='tester',
        uploader_url='https://example.com/u',
        views='1',
        likes='0',
        thumbnail='https://example.com/t.png',
        requester=SimpleNamespace(mention=f'@{title}'),
        volume=0.5,
    )
    song = Song.__new__(Song)
    song.source = source  # type: ignore[assignment]
    song.requester = source.requester
    return song


async def test_len_tracks_put_and_get():
    queue = SongQueue()
    assert len(queue) == 0
    await queue.put(_song('a'))
    await queue.put(_song('b'))
    assert len(queue) == 2
    _ = await queue.get()
    assert len(queue) == 1


async def test_iter_and_slice():
    queue = SongQueue()
    for name in ('a', 'b', 'c'):
        await queue.put(_song(name))
    names = [song.source.title for song in queue]
    assert names == ['a', 'b', 'c']
    assert [song.source.title for song in queue[:2]] == ['a', 'b']


async def test_shuffle_preserves_items():
    queue = SongQueue()
    for name in ('a', 'b', 'c', 'd'):
        await queue.put(_song(name))
    queue.shuffle()
    titles: list[str] = [str(song.source.title) for song in queue]
    assert sorted(titles) == ['a', 'b', 'c', 'd']


async def test_clear_empties_queue():
    queue = SongQueue()
    await queue.put(_song('a'))
    queue.clear()
    assert len(queue) == 0


async def test_remove_valid_index():
    queue = SongQueue()
    for name in ('a', 'b', 'c'):
        await queue.put(_song(name))
    queue.remove(1)
    assert [song.source.title for song in queue] == ['a', 'c']


async def test_remove_rejects_out_of_bounds():
    queue = SongQueue()
    await queue.put(_song('a'))
    with pytest.raises(QueueIndexError):
        queue.remove(5)
    with pytest.raises(QueueIndexError):
        queue.remove(-1)


async def test_remove_from_empty_raises():
    queue = SongQueue()
    with pytest.raises(QueueIndexError):
        queue.remove(0)
