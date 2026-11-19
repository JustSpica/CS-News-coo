from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30
FETCH_RETRY_ATTEMPTS = 2
FETCH_RETRY_BACKOFF_SECONDS = 0.5
MAX_FEED_BYTES = 2_000_000
USER_AGENT = "news-coo/1.0"


class GoogleNewsFeedDownloader:
    def download(self, url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            msg = f"Unsupported URL scheme: {url}"
            raise ValueError(msg)

        for attempt in range(FETCH_RETRY_ATTEMPTS + 1):
            try:
                return self.__download_once(url)
            except urllib.error.HTTPError:
                raise
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == FETCH_RETRY_ATTEMPTS:
                    raise
                log.warning("Feed download failed, retrying: %s", exc)
                time.sleep(FETCH_RETRY_BACKOFF_SECONDS * (attempt + 1))

        msg = f"Failed to download feed: {url}"
        raise RuntimeError(msg)

    def __download_once(self, url: str) -> bytes:
        encoded_url = urllib.parse.quote(url, safe=":/?&=+%()")
        request = urllib.request.Request(encoded_url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            content = response.read(MAX_FEED_BYTES + 1)
        if len(content) > MAX_FEED_BYTES:
            msg = f"Feed response exceeded {MAX_FEED_BYTES} bytes"
            raise ValueError(msg)
        return content
