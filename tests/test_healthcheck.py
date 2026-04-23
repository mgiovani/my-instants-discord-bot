from __future__ import annotations

import os
import time

import pytest

from bot import healthcheck


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / 'hb'
    monkeypatch.setenv('MYINSTANTS_HEARTBEAT_FILE', str(path))
    return path


def test_missing_file_returns_nonzero(heartbeat_file):
    assert not heartbeat_file.exists()
    assert healthcheck.main() == 1


def test_fresh_file_returns_zero(heartbeat_file):
    heartbeat_file.touch()
    assert healthcheck.main() == 0


def test_stale_file_returns_nonzero(heartbeat_file, monkeypatch):
    heartbeat_file.touch()
    monkeypatch.setenv('MYINSTANTS_HEARTBEAT_MAX_AGE_SECONDS', '0.1')
    past = time.time() - 10
    os.utime(heartbeat_file, (past, past))
    assert healthcheck.main() == 1
