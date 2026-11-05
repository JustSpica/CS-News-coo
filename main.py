from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from config.settings import DIGEST_OUTPUT_DIR, FEEDS_PATH
from core.collector import FeedCollector
from core.digest_exporter import JsonDigestExporter
from core.feed_loader import FeedConfigError, load_feeds_config

log = logging.getLogger("news-coo")


class NewsCollectionRunner:
    def __init__(self, collector: FeedCollector, exporter: JsonDigestExporter) -> None:
        self._collector = collector
        self._exporter = exporter

    async def run(self) -> Path:
        result = await self._collector.collect()
        if result.total_articles == 0:
            log.warning("Collection returned no articles; exporting an empty digest")
        return self._exporter.export(result)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    try:
        settings, topics = load_feeds_config(FEEDS_PATH)
    except (FeedConfigError, OSError) as exc:
        log.error("Could not load feeds config %s: %s", FEEDS_PATH, exc)
        return 1

    runner = NewsCollectionRunner(
        collector=FeedCollector(settings, topics),
        exporter=JsonDigestExporter(DIGEST_OUTPUT_DIR),
    )

    try:
        digest_path = asyncio.run(runner.run())
    except OSError as exc:
        log.error("Could not write digest to %s: %s", DIGEST_OUTPUT_DIR, exc)
        return 1

    log.info("Digest saved to %s", digest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
