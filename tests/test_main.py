from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import main
from core.collector import FeedCollector
from core.digest_exporter import JsonDigestExporter
from core.models import Article, CollectionResult, FeedSettings, TopicResult


class CannedResultCollector(FeedCollector):
    """Returns a fixed collection result instead of fetching RSS feeds."""

    def __init__(self, canned_result: CollectionResult) -> None:
        super().__init__(FeedSettings(), [])
        self._canned_result = canned_result

    async def collect(self) -> CollectionResult:
        return self._canned_result


def _fixed_clock() -> datetime:
    return datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _single_article_result() -> CollectionResult:
    article = Article(
        url="https://news.google.com/a1",
        title="A1",
        source_name="Reuters",
        topic_key="world_economy",
        topic_display_name="Economia Mundial",
    )
    return CollectionResult(
        topic_results=[
            TopicResult(
                topic_key="world_economy",
                topic_display_name="Economia Mundial",
                articles=[article],
            )
        ]
    )


class TestNewsCollectionRunner:
    def test_run_exports_collected_articles_to_json(self, tmp_path) -> None:
        runner = main.NewsCollectionRunner(
            collector=CannedResultCollector(_single_article_result()),
            exporter=JsonDigestExporter(tmp_path, clock=_fixed_clock),
        )

        digest_path = asyncio.run(runner.run())

        digest = json.loads(digest_path.read_text(encoding="utf-8"))
        assert digest["total_articles"] == 1
        assert digest["topics"][0]["articles"][0]["title"] == "A1"

    def test_run_still_exports_digest_when_no_articles_were_found(self, tmp_path) -> None:
        runner = main.NewsCollectionRunner(
            collector=CannedResultCollector(CollectionResult()),
            exporter=JsonDigestExporter(tmp_path, clock=_fixed_clock),
        )

        digest_path = asyncio.run(runner.run())

        assert json.loads(digest_path.read_text(encoding="utf-8"))["total_articles"] == 0


class TestMainEntrypoint:
    def test_main_returns_error_code_when_feeds_config_is_missing(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(main, "FEEDS_PATH", tmp_path / "missing.yaml")

        assert main.main() == 1

    def test_main_returns_error_code_when_feeds_config_is_invalid(
        self, tmp_path, monkeypatch
    ) -> None:
        invalid_config = tmp_path / "feeds.yaml"
        invalid_config.write_text("topics: not-a-mapping\n", encoding="utf-8")
        monkeypatch.setattr(main, "FEEDS_PATH", invalid_config)

        assert main.main() == 1
