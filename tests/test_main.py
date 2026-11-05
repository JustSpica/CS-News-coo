from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

import main
from core.collector import FeedCollector
from core.digest_exporter import DigestExporter, JsonDigestExporter
from core.models import Article, CollectionResult, FeedSettings, TopicResult


class CannedResultCollector(FeedCollector):
    def __init__(self, canned_result: CollectionResult) -> None:
        super().__init__(FeedSettings(), [])
        self._canned_result = canned_result

    async def collect(self) -> CollectionResult:
        return self._canned_result


class RecordingDigestExporter(DigestExporter):
    def __init__(self, name: str, export_log: list[tuple[str, CollectionResult]]) -> None:
        self.name = name
        self.export_log = export_log

    def export(self, result: CollectionResult) -> None:
        self.export_log.append((self.name, result))


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


def _read_only_digest(output_dir) -> dict:
    (digest_path,) = output_dir.iterdir()
    return json.loads(digest_path.read_text(encoding="utf-8"))


class TestNewsCollectionRunner:
    def test_run_sends_collected_result_to_every_exporter_in_order(self) -> None:
        result = _single_article_result()
        export_log: list[tuple[str, CollectionResult]] = []
        runner = main.NewsCollectionRunner(
            collector=CannedResultCollector(result),
            exporters=[
                RecordingDigestExporter("first", export_log),
                RecordingDigestExporter("second", export_log),
            ],
        )

        asyncio.run(runner.run())

        assert export_log == [("first", result), ("second", result)]

    def test_run_exports_collected_articles_to_json(self, tmp_path) -> None:
        runner = main.NewsCollectionRunner(
            collector=CannedResultCollector(_single_article_result()),
            exporters=[JsonDigestExporter(tmp_path, clock=_fixed_clock)],
        )

        asyncio.run(runner.run())

        digest = _read_only_digest(tmp_path)
        assert digest["total_articles"] == 1
        assert digest["topics"][0]["articles"][0]["title"] == "A1"

    def test_run_still_exports_digest_when_no_articles_were_found(self, tmp_path) -> None:
        runner = main.NewsCollectionRunner(
            collector=CannedResultCollector(CollectionResult()),
            exporters=[JsonDigestExporter(tmp_path, clock=_fixed_clock)],
        )

        asyncio.run(runner.run())

        assert _read_only_digest(tmp_path)["total_articles"] == 0

    def test_runner_rejects_empty_exporter_list(self) -> None:
        with pytest.raises(ValueError, match="at least one exporter"):
            main.NewsCollectionRunner(
                collector=CannedResultCollector(CollectionResult()),
                exporters=[],
            )


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
