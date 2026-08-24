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

# aiohttp 3.14 added a required keyword-only `stream_writer` argument to
# ClientResponse.__init__ (only its `.output_size` is read). aioresponses
# 0.7.9 (latest release) doesn't pass it yet — fix is merged upstream but
# unreleased (github.com/pnuckowski/aioresponses/pull/288). Default it here
# instead of pinning an unreleased git commit as a dependency.
if ClientResponse.__init__.__kwdefaults__ is None:
    ClientResponse.__init__.__kwdefaults__ = {}
ClientResponse.__init__.__kwdefaults__.setdefault(
    'stream_writer', Mock(output_size=0)
)


@pytest.fixture
def settings():
    from bot.config import Settings

    Settings.model_config['env_file'] = None
    return Settings(
        bot_token='test-token',  # type: ignore[arg-type]
    )
