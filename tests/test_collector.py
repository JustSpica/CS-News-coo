from __future__ import annotations

import asyncio
import urllib.parse
from datetime import UTC, datetime

import pytest

from core.collector import FeedCollector
from core.feed_downloader import GoogleNewsFeedDownloader
from core.models import CollectionResult, FeedSettings, Source, Topic


def _build_rss(items: list[tuple[str, str, str]]) -> str:
    entries = "\n".join(
        f"    <item><title>{title}</title><link>{url}</link>"
        f'<source url="{source_url}">Source</source>'
        f"<pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate></item>"
        for title, url, source_url in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n  <channel>\n'
        f"    <title>Test</title>\n{entries}\n"
        "  </channel>\n</rss>"
    )


SAMPLE_RSS = _build_rss(
    [
        ("First Article", "https://news.google.com/article-1", "https://example.com"),
        ("Second Article", "https://news.google.com/article-2", "https://example.com"),
        ("Third Article", "https://news.google.com/article-3", "https://example.com"),
        ("Fourth Article", "https://news.google.com/article-4", "https://example.com"),
    ]
)

SAMPLE_RSS_TWO_SOURCES = _build_rss(
    [
        ("A1", "https://news.google.com/a1", "https://source-a.com"),
        ("A2", "https://news.google.com/a2", "https://source-a.com"),
        ("A3", "https://news.google.com/a3", "https://source-a.com"),
        ("A4", "https://news.google.com/a4", "https://source-a.com"),
        ("A5", "https://news.google.com/a5", "https://source-a.com"),
        ("B1", "https://news.google.com/b1", "https://source-b.com"),
    ]
)

MALFORMED_RSS = "this is not valid xml at all"


class CannedFeedDownloader(GoogleNewsFeedDownloader):
    """Returns canned RSS for the first URL fragment found in the requested URL."""

    def __init__(self, rss_by_url_fragment: dict[str, str]) -> None:
        self.__rss_by_url_fragment = rss_by_url_fragment
        self.requested_urls: list[str] = []

    def download(self, url: str) -> bytes:
        self.requested_urls.append(url)
        for url_fragment, rss in self.__rss_by_url_fragment.items():
            if url_fragment in url:
                return rss.encode("utf-8")
        msg = f"No canned RSS for {url}"
        raise ConnectionError(msg)


def _make_source(name: str = "TestSource", domain: str = "example.com") -> Source:
    return Source(name=name, domain=domain)


def _make_topic(
    sources: list[Source] | None = None,
    key: str = "test_topic",
    keywords: list[str] | None = None,
    language: str = "en",
) -> Topic:
    return Topic(
        key=key,
        display_name="Test Topic",
        keywords=keywords or ["test", "news"],
        language=language,
        sources=sources or [_make_source()],
    )


def _collect(
    topics: list[Topic],
    downloader: GoogleNewsFeedDownloader,
    max_articles_per_topic: int = 15,
) -> CollectionResult:
    collector = FeedCollector(
        FeedSettings(max_articles_per_topic=max_articles_per_topic),
        topics,
        downloader,
    )
    return asyncio.run(collector.collect())


def _requested_url_for(topic: Topic) -> str:
    downloader = CannedFeedDownloader({})
    _collect([topic], downloader)
    (url,) = downloader.requested_urls
    return url


class TestFeedCollectorParsing:
    def test_valid_rss_returns_articles_with_correct_metadata(self) -> None:
        result = _collect([_make_topic()], CannedFeedDownloader({"site:example.com": SAMPLE_RSS}))

        topic_result = result.topic_results[0]
        first = topic_result.articles[0]
        assert len(topic_result.articles) == 4
        assert first.title == "First Article"
        assert first.source_name == "TestSource"
        assert first.topic_key == "test_topic"
        assert first.topic_display_name == "Test Topic"
        assert first.published_at == datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
        assert topic_result.failed_sources == []

    def test_malformed_rss_records_all_sources_as_failed(self) -> None:
        result = _collect(
            [_make_topic()],
            CannedFeedDownloader({"site:example.com": MALFORMED_RSS}),
        )

        topic_result = result.topic_results[0]
        assert topic_result.articles == []
        assert topic_result.failed_sources == ["TestSource"]

    def test_download_failure_records_all_sources_as_failed(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]

        result = _collect([_make_topic(sources=sources)], CannedFeedDownloader({}))

        topic_result = result.topic_results[0]
        assert topic_result.articles == []
        assert topic_result.failed_sources == ["SourceA", "SourceB"]


class TestArticleRanking:
    def test_articles_keep_google_ranking_order_up_to_the_limit(self) -> None:
        sources = [
            _make_source("SourceA", "source-a.com"),
            _make_source("SourceB", "source-b.com"),
        ]

        result = _collect(
            [_make_topic(sources=sources)],
            CannedFeedDownloader({"site:source-a.com": SAMPLE_RSS_TWO_SOURCES}),
            max_articles_per_topic=4,
        )

        topic_result = result.topic_results[0]
        assert [a.title for a in topic_result.articles] == ["A1", "A2", "A3", "A4"]
        assert topic_result.failed_sources == []

    def test_multiple_topics_collect_articles_independently(self) -> None:
        topic_a = _make_topic(key="topic_a")
        topic_b = _make_topic(sources=[_make_source("OtherSource", "other.com")], key="topic_b")
        downloader = CannedFeedDownloader(
            {
                "site:example.com": SAMPLE_RSS,
                "site:other.com": SAMPLE_RSS.replace("example.com", "other.com"),
            }
        )

        result = _collect([topic_a, topic_b], downloader)

        assert len(result.topic_results) == 2
        assert result.total_articles == 8
        assert len(downloader.requested_urls) == 2


class TestGoogleNewsUrl:
    def test_english_topic_requests_combined_search_url(self) -> None:
        topic = _make_topic(
            keywords=["artificial intelligence", "machine learning"],
            sources=[
                Source(name="Reuters", domain="reuters.com"),
                Source(name="WIRED", domain="wired.com"),
            ],
        )

        url = _requested_url_for(topic)

        assert url.startswith("https://news.google.com/rss/search?")
        assert "artificial+intelligence+OR+machine+learning" in url
        assert "(site:reuters.com+OR+site:wired.com)" in url
        assert "when:7d" in url
        assert "hl=en-US" in url
        assert "gl=US" in url
        assert "ceid=US:en" in url

    def test_portuguese_topic_uses_brazilian_locale(self) -> None:
        url = _requested_url_for(_make_topic(language="pt"))

        assert "hl=pt-BR" in url
        assert "gl=BR" in url

    def test_query_values_are_url_encoded(self) -> None:
        topic = _make_topic(
            keywords=["market & trade", "GDP=now"],
            sources=[Source(name="Reuters", domain="reuters.com")],
        )

        url = _requested_url_for(topic)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"]

        assert query == ["market & trade OR GDP=now (site:reuters.com) when:7d"]

    def test_unknown_language_fails_topic_without_downloading(self) -> None:
        downloader = CannedFeedDownloader({})

        result = _collect([_make_topic(language="fr")], downloader)

        assert downloader.requested_urls == []
        assert result.topic_results[0].failed_sources == ["TestSource"]


class TestSourceIdentification:
    @pytest.mark.parametrize(
        ("source_url", "expected_source_name"),
        [
            ("https://reuters.com", "Reuters"),
            ("https://www.reuters.com", "Reuters"),
            ("https://asia.nikkei.com", "Nikkei"),
            ("https://unknown.com", "Unknown"),
        ],
    )
    def test_article_source_is_identified_by_feed_source_domain(
        self,
        source_url: str,
        expected_source_name: str,
    ) -> None:
        sources = [
            Source(name="Reuters", domain="reuters.com"),
            Source(name="Nikkei", domain="asia.nikkei.com"),
        ]
        rss = _build_rss([("Title", "https://news.google.com/x", source_url)])

        result = _collect(
            [_make_topic(sources=sources)],
            CannedFeedDownloader({"site:reuters.com": rss}),
        )

        assert result.topic_results[0].articles[0].source_name == expected_source_name
