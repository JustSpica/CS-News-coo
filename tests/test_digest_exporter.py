from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from core.digest_exporter import JsonDigestExporter
from core.models import Article, CollectionResult, TopicResult

FIXED_COLLECTED_AT = datetime(2026, 11, 5, 12, 30, 45, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return FIXED_COLLECTED_AT


def _make_collection_result() -> CollectionResult:
    article = Article(
        url="https://news.google.com/article-1",
        title="Inflação desacelera",
        source_name="Reuters",
        topic_key="world_economy",
        topic_display_name="Economia Mundial",
        published_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
    )
    undated_article = Article(
        url="https://news.google.com/article-2",
        title="Undated article",
        source_name="Unknown",
        topic_key="world_economy",
        topic_display_name="Economia Mundial",
    )
    return CollectionResult(
        topic_results=[
            TopicResult(
                topic_key="world_economy",
                topic_display_name="Economia Mundial",
                articles=[article, undated_article],
                failed_sources=["Bloomberg"],
            ),
            TopicResult(topic_key="tech", topic_display_name="Tecnologia"),
        ]
    )


def _export_and_load(tmp_path, result: CollectionResult) -> dict:
    exporter = JsonDigestExporter(tmp_path, clock=_fixed_clock)
    digest_path = exporter.export(result)
    return json.loads(digest_path.read_text(encoding="utf-8"))


class TestJsonDigestExporter:
    def test_export_writes_file_named_after_collection_timestamp(self, tmp_path) -> None:
        exporter = JsonDigestExporter(tmp_path, clock=_fixed_clock)

        digest_path = exporter.export(_make_collection_result())

        assert digest_path == tmp_path / "digest-20261105T123045Z.json"
        assert digest_path.is_file()

    def test_export_creates_missing_output_directory(self, tmp_path) -> None:
        output_dir = tmp_path / "nested" / "output"
        exporter = JsonDigestExporter(output_dir, clock=_fixed_clock)

        digest_path = exporter.export(_make_collection_result())

        assert digest_path.parent == output_dir

    def test_export_includes_collection_summary(self, tmp_path) -> None:
        digest = _export_and_load(tmp_path, _make_collection_result())

        assert digest["collected_at"] == "2026-11-05T12:30:45+00:00"
        assert digest["total_articles"] == 2
        assert digest["failed_sources"] == ["Bloomberg"]
        assert [topic["key"] for topic in digest["topics"]] == ["world_economy", "tech"]

    def test_export_serializes_topic_and_article_fields(self, tmp_path) -> None:
        digest = _export_and_load(tmp_path, _make_collection_result())
        topic = digest["topics"][0]

        assert topic["display_name"] == "Economia Mundial"
        assert topic["article_count"] == 2
        assert topic["articles"][0] == {
            "title": "Inflação desacelera",
            "url": "https://news.google.com/article-1",
            "source_name": "Reuters",
            "published_at": "2026-11-04T10:00:00+00:00",
        }

    def test_export_writes_null_for_article_without_publication_date(self, tmp_path) -> None:
        digest = _export_and_load(tmp_path, _make_collection_result())

        assert digest["topics"][0]["articles"][1]["published_at"] is None

    def test_export_keeps_non_ascii_titles_readable(self, tmp_path) -> None:
        exporter = JsonDigestExporter(tmp_path, clock=_fixed_clock)

        digest_path = exporter.export(_make_collection_result())

        assert "Inflação desacelera" in digest_path.read_text(encoding="utf-8")

    def test_export_of_empty_result_writes_empty_topic_list(self, tmp_path) -> None:
        digest = _export_and_load(tmp_path, CollectionResult())

        assert digest["total_articles"] == 0
        assert digest["topics"] == []

    def test_failed_write_leaves_no_temporary_file_behind(self, tmp_path, monkeypatch) -> None:
        def fail_replace(_self, _target) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("pathlib.Path.replace", fail_replace)
        exporter = JsonDigestExporter(tmp_path, clock=_fixed_clock)

        with pytest.raises(OSError, match="disk full"):
            exporter.export(_make_collection_result())

        assert list(tmp_path.iterdir()) == []
