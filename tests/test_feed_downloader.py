from __future__ import annotations

import pytest

from core.feed_downloader import MAX_FEED_BYTES, GoogleNewsFeedDownloader


class OversizedFeedResponse:
    def __enter__(self) -> OversizedFeedResponse:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return b"x" * (MAX_FEED_BYTES + 1)


class TestGoogleNewsFeedDownloader:
    def test_oversized_response_raises_clear_error(self, monkeypatch) -> None:
        def fake_urlopen(_request, timeout):
            return OversizedFeedResponse()

        monkeypatch.setattr("core.feed_downloader.urllib.request.urlopen", fake_urlopen)

        with pytest.raises(ValueError, match="Feed response exceeded"):
            GoogleNewsFeedDownloader().download("https://example.com/rss")

    def test_non_http_url_is_rejected_before_download(self) -> None:
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            GoogleNewsFeedDownloader().download("file:///etc/passwd")
