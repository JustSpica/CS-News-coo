from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from core.models import Article, CollectionResult, TopicResult

log = logging.getLogger(__name__)

DIGEST_FILENAME_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DigestExporter:
    def export(self, result: CollectionResult) -> None:
        msg = f"{type(self).__name__} must implement export()"
        raise NotImplementedError(msg)


class JsonDigestExporter(DigestExporter):
    def __init__(self, output_dir: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        self.__output_dir = output_dir
        self.__clock = clock

    def export(self, result: CollectionResult) -> None:
        collected_at = self.__clock().astimezone(UTC)
        digest_path = self.__output_dir / self.__build_filename(collected_at)
        digest_json = json.dumps(
            self.__serialize_collection(result, collected_at),
            ensure_ascii=False,
            indent=2,
        )
        self.__write_atomically(digest_path, digest_json)
        log.info("Digest saved to %s", digest_path)

    def __build_filename(self, collected_at: datetime) -> str:
        return f"digest-{collected_at.strftime(DIGEST_FILENAME_TIMESTAMP_FORMAT)}.json"

    def __serialize_collection(
        self,
        result: CollectionResult,
        collected_at: datetime,
    ) -> dict[str, object]:
        return {
            "collected_at": collected_at.isoformat(),
            "total_articles": result.total_articles,
            "failed_sources": result.all_failed_sources,
            "topics": [self.__serialize_topic(topic) for topic in result.topic_results],
        }

    def __serialize_topic(self, topic_result: TopicResult) -> dict[str, object]:
        return {
            "key": topic_result.topic_key,
            "display_name": topic_result.topic_display_name,
            "article_count": len(topic_result.articles),
            "failed_sources": topic_result.failed_sources,
            "articles": [self.__serialize_article(article) for article in topic_result.articles],
        }

    def __serialize_article(self, article: Article) -> dict[str, str | None]:
        return {
            "title": article.title,
            "url": article.url,
            "source_name": article.source_name,
            "published_at": article.published_at.isoformat() if article.published_at else None,
        }

    def __write_atomically(self, digest_path: Path, digest_json: str) -> None:
        self.__output_dir.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=self.__output_dir,
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


class ConsoleDigestExporter(DigestExporter):
    def __init__(self, output_stream: TextIO = sys.stdout) -> None:
        self.__output_stream = output_stream

    def export(self, result: CollectionResult) -> None:
        lines = [
            f"Collected {result.total_articles} articles "
            f"across {len(result.topic_results)} topics:",
            *(self.__format_topic_line(topic) for topic in result.topic_results),
        ]
        if result.all_failed_sources:
            lines.append(f"Failed sources: {', '.join(result.all_failed_sources)}")

        self.__output_stream.write("\n".join(lines) + "\n")

    def __format_topic_line(self, topic_result: TopicResult) -> str:
        return f"  - {topic_result.topic_display_name}: {len(topic_result.articles)} articles"
