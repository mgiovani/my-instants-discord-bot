from __future__ import annotations

from bot.ytdl import _YTDL_OPTIONS


def test_ytdl_requests_browser_impersonation():
    generic = _YTDL_OPTIONS['extractor_args']['generic']
    assert generic['impersonate'] == ['']
