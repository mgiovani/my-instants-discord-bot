from __future__ import annotations

import os
from unittest.mock import Mock

import pytest
from aiohttp.client_reqrep import ClientResponse

os.environ.setdefault('MYINSTANTS_BOT_TOKEN', 'test-token')
os.environ.setdefault('MYINSTANTS_ENV', 'dev')
os.environ.setdefault(
    'MYINSTANTS_PII_HASH_KEY',
    'test-key-do-not-use-in-prod',
)


# ponytail: aiohttp 3.14 added a required keyword-only `stream_writer`
# argument to ClientResponse.__init__ (only its `.output_size` is read).
# aioresponses 0.7.9 (latest release) doesn't pass it yet — fix is merged
# upstream but unreleased (github.com/pnuckowski/aioresponses/pull/288).
# Default it for the test session instead of pinning an unreleased git
# commit as a dependency. Drop this fixture once aioresponses ships that
# fix in a release and aioresponses~=0.7 is bumped past it.
@pytest.fixture(autouse=True, scope='session')
def _aioresponses_stream_writer_default():
    init = ClientResponse.__init__
    original = init.__kwdefaults__
    init.__kwdefaults__ = {
        **(original or {}),
        'stream_writer': Mock(spec=['output_size'], output_size=0),
    }
    yield
    init.__kwdefaults__ = original


@pytest.fixture
def settings():
    from bot.config import Settings

    Settings.model_config['env_file'] = None
    return Settings(
        bot_token='test-token',  # type: ignore[arg-type]
    )
