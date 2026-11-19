from __future__ import annotations

import asyncio
import logging
import urllib.parse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from core.feed_downloader import GoogleNewsFeedDownloader
from core.models import (
    Article,
    CollectionResult,
    FeedSettings,
    Source,
    Topic,
    TopicResult,
)

log = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"

LANGUAGE_PARAMS: dict[str, dict[str, str]] = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "pt": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
}


class FeedCollector:
    def __init__(
        self,
        settings: FeedSettings,
        topics: list[Topic],
        feed_downloader: GoogleNewsFeedDownloader,
    ) -> None:
        self.__settings = settings
        self.__topics = topics
        self.__feed_downloader = feed_downloader

    async def collect(self) -> CollectionResult:
        topic_results = await asyncio.gather(
            *(self.__collect_topic(topic) for topic in self.__topics)
        )

        result = CollectionResult(topic_results=list(topic_results))

        log.info(
            "Collection done: %d articles across %d topics (%d source failures)",
            result.total_articles,
            len(result.topic_results),
            len(result.all_failed_sources),
        )
        return result

    async def __collect_topic(self, topic: Topic) -> TopicResult:
        topic_result = TopicResult(
            topic_key=topic.key,
            topic_display_name=topic.display_name,
        )

        try:
            articles = await asyncio.to_thread(self.__fetch_topic_articles, topic)
        except Exception as exc:
            log.error("Failed to fetch topic %s: %s", topic.key, exc)
            topic_result.failed_sources = [source.name for source in topic.sources]
            return topic_result

        topic_result.articles = articles[: self.__settings.max_articles_per_topic]
        log.info("Topic '%s': %d articles", topic.display_name, len(topic_result.articles))
        return topic_result

    def __fetch_topic_articles(self, topic: Topic) -> list[Article]:
        url = self.__build_google_news_url(topic)
        log.info("Fetching topic '%s': %s", topic.display_name, url)
        raw_content = self.__feed_downloader.download(url)
        return self.__parse_feed_entries(raw_content, topic)

    def __parse_feed_entries(self, raw: bytes | str, topic: Topic) -> list[Article]:
        parsed = feedparser.parse(raw)
        if parsed.bozo and not parsed.entries:
            raise parsed.bozo_exception

        articles: list[Article] = []
        for entry in parsed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            source_url = getattr(entry.get("source", {}), "href", "")
            articles.append(
                Article(
                    url=link,
                    title=title,
                    source_name=self.__identify_source_name(source_url, topic.sources),
                    published_at=self.__parse_date(entry),
                )
            )

        log.debug("Parsed %d entries for topic %s", len(articles), topic.key)
        return articles

    def __build_google_news_url(self, topic: Topic) -> str:
        keywords_part = " OR ".join(topic.keywords)
        sites_part = " OR ".join(f"site:{source.domain}" for source in topic.sources)
        params = {
            "q": f"{keywords_part} ({sites_part}) when:7d",
            **self.__language_params(topic.language),
        }
        encoded_params = urllib.parse.urlencode(params, safe="():")
        return f"{GOOGLE_NEWS_RSS_BASE}?{encoded_params}"

    def __language_params(self, language: str) -> dict[str, str]:
        try:
            return LANGUAGE_PARAMS[language]
        except KeyError:
            supported = ", ".join(sorted(LANGUAGE_PARAMS))
            msg = f"Unsupported topic language: {language}. Supported: {supported}"
            raise ValueError(msg) from None

    def __identify_source_name(self, source_url: str, sources: list[Source]) -> str:
        hostname = urllib.parse.urlparse(source_url).hostname or ""
        for source in sources:
            if hostname == source.domain or hostname.endswith(f".{source.domain}"):
                return source.name
        return "Unknown"

    def __parse_date(self, entry: dict) -> datetime | None:
        for date_field in ("published", "updated"):
            raw = entry.get(date_field)
            if not raw:
                continue
            try:
                return parsedate_to_datetime(raw).astimezone(UTC)
            except ValueError, TypeError:
                continue
        return None
