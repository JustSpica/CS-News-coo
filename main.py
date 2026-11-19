from __future__ import annotations

import asyncio
import logging

from config.settings import DIGEST_OUTPUT_DIR, FEEDS_PATH
from core.collector import FeedCollector
from core.digest_exporter import ConsoleDigestExporter, DigestExporter, JsonDigestExporter
from core.feed_loader import FeedConfigError, FeedConfigLoader

log = logging.getLogger("news-coo")


class NewsCollectionRunner:
    def __init__(self, collector: FeedCollector, exporters: list[DigestExporter]) -> None:
        if not exporters:
            msg = "NewsCollectionRunner requires at least one exporter"
            raise ValueError(msg)
        self.__collector = collector
        self.__exporters = exporters

    async def run(self) -> None:
        result = await self.__collector.collect()
        if result.total_articles == 0:
            log.warning("Collection returned no articles; exporting an empty digest")

        for exporter in self.__exporters:
            exporter.export(result)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    config_loader = FeedConfigLoader(FEEDS_PATH)
    try:
        settings, topics = config_loader.load()
    except (FeedConfigError, OSError) as exc:
        log.error("Could not load feeds config %s: %s", FEEDS_PATH, exc)
        return 1

    runner = NewsCollectionRunner(
        collector=FeedCollector(settings, topics),
        exporters=[ConsoleDigestExporter(), JsonDigestExporter(DIGEST_OUTPUT_DIR)],
    )

    try:
        asyncio.run(runner.run())
    except OSError as exc:
        log.error("Could not write digest to %s: %s", DIGEST_OUTPUT_DIR, exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
