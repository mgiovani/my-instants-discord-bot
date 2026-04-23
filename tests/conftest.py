from __future__ import annotations

import os

import pytest

os.environ.setdefault('MYINSTANTS_BOT_TOKEN', 'test-token')
os.environ.setdefault('MYINSTANTS_ENV', 'dev')
os.environ.setdefault(
    'MYINSTANTS_PII_HASH_KEY',
    'test-key-do-not-use-in-prod',
)


@pytest.fixture
def settings():
    from bot.config import Settings

    Settings.model_config['env_file'] = None
    return Settings(
        bot_token='test-token',  # type: ignore[arg-type]
    )
