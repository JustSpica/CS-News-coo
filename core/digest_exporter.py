from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from core.models import Article, CollectionResult, TopicResult

DIGEST_FILENAME_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class JsonDigestExporter:
    """Writes a collection result to a timestamped JSON file in `output_dir`.

    The digest is written to a temporary file in the same directory and then
    atomically renamed, so an interrupted run never leaves a truncated digest.

    Output shape:
        {
          "collected_at": "2026-11-05T12:00:00+00:00",
          "total_articles": 2,
          "failed_sources": ["Bloomberg"],
          "topics": [
            {"key", "display_name", "article_count", "failed_sources",
             "articles": [{"title", "url", "source_name", "published_at"}]}
          ]
        }
    """

    def __init__(self, output_dir: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        self._output_dir = output_dir
        self._clock = clock

    def export(self, result: CollectionResult) -> Path:
        collected_at = self._clock().astimezone(UTC)
        digest_path = self._output_dir / self._build_filename(collected_at)
        digest_json = json.dumps(
            self._serialize_collection(result, collected_at),
            ensure_ascii=False,
            indent=2,
        )
        self._write_atomically(digest_path, digest_json)
        return digest_path

    @staticmethod
    def _build_filename(collected_at: datetime) -> str:
        return f"digest-{collected_at.strftime(DIGEST_FILENAME_TIMESTAMP_FORMAT)}.json"

    def _serialize_collection(
        self,
        result: CollectionResult,
        collected_at: datetime,
    ) -> dict[str, object]:
        return {
            "collected_at": collected_at.isoformat(),
            "total_articles": result.total_articles,
            "failed_sources": result.all_failed_sources,
            "topics": [self._serialize_topic(topic) for topic in result.topic_results],
        }

    def _serialize_topic(self, topic_result: TopicResult) -> dict[str, object]:
        return {
            "key": topic_result.topic_key,
            "display_name": topic_result.topic_display_name,
            "article_count": len(topic_result.articles),
            "failed_sources": topic_result.failed_sources,
            "articles": [self._serialize_article(article) for article in topic_result.articles],
        }

    @staticmethod
    def _serialize_article(article: Article) -> dict[str, str | None]:
        return {
            "title": article.title,
            "url": article.url,
            "source_name": article.source_name,
            "published_at": article.published_at.isoformat() if article.published_at else None,
        }

    def _write_atomically(self, digest_path: Path, digest_json: str) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=self._output_dir,
            prefix=".digest-",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
                temp_file.write(digest_json)
            temp_path.replace(digest_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
