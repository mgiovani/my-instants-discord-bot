"""PII hashing primitive.

We never store raw Discord user/guild IDs. Everything keyed on a user
or guild goes through `hash_id(...)` with a category namespace so the
same raw ID can't be correlated across kinds (e.g. a user hash is not
comparable to a guild hash).

Rotating `MYINSTANTS_PII_HASH_KEY` invalidates all existing hashes —
that's intentional: if the key leaks, rotation wipes the correlation
without exposing the underlying IDs to anyone.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Literal

type Category = Literal['user', 'guild']

_HASH_LENGTH = 32  # hex chars of truncated digest


def hash_id(raw_id: int | str, *, category: Category, secret: str) -> str:
    """Return a stable hex digest of `raw_id` scoped to `category`."""
    if not secret:
        raise ValueError(
            'PII hash secret must not be empty. Set MYINSTANTS_PII_HASH_KEY.'
        )
    message = f'{category}:{raw_id}'.encode()
    digest = hmac.new(
        secret.encode('utf-8'), msg=message, digestmod=sha256
    ).hexdigest()
    return digest[:_HASH_LENGTH]


def hash_user(user_id: int | str, *, secret: str) -> str:
    return hash_id(user_id, category='user', secret=secret)


def hash_guild(guild_id: int | str, *, secret: str) -> str:
    return hash_id(guild_id, category='guild', secret=secret)
