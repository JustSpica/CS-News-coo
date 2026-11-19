from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from core.models import SUPPORTED_TOPIC_LANGUAGES, FeedSettings, Source, Topic

_FEED_SETTINGS_FIELDS = {f.name for f in dataclasses.fields(FeedSettings)}
_DEFAULT_FEED_SETTINGS = FeedSettings()
_MAX_ARTICLES_PER_TOPIC_LIMIT = 50
_TOPIC_FIELDS = {"display_name", "keywords", "language", "sources"}
_SOURCE_FIELDS = {"name", "domain"}
_DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class FeedConfigError(ValueError):
    pass


class FeedConfigLoader:
    def __init__(self, path: Path) -> None:
        self.__path = path

    def load(self) -> tuple[FeedSettings, list[Topic]]:
        with self.__path.open(encoding="utf-8") as yaml_file:
            raw_config = yaml.safe_load(yaml_file)

        config = self.__require_mapping(raw_config, "feeds config")
        settings = self.__load_settings(config.get("settings", {}))
        topics = self.__load_topics(config.get("topics", {}))

        return settings, topics

    def __load_settings(self, raw_settings: object) -> FeedSettings:
        settings = self.__require_mapping(
            {} if raw_settings is None else raw_settings,
            "settings",
        )
        self.__reject_unknown_fields(settings, _FEED_SETTINGS_FIELDS, "Unknown feed setting(s)")

        max_articles = self.__validate_max_articles_per_topic(
            settings.get(
                "max_articles_per_topic",
                _DEFAULT_FEED_SETTINGS.max_articles_per_topic,
            )
        )
        return FeedSettings(max_articles_per_topic=max_articles)

    def __load_topics(self, raw_topics: object) -> list[Topic]:
        topics_mapping = self.__require_mapping(
            {} if raw_topics is None else raw_topics,
            "topics",
        )
        return [
            self.__load_topic(topic_key, raw_topic_entry)
            for topic_key, raw_topic_entry in topics_mapping.items()
        ]

    def __load_topic(self, topic_key: object, raw_topic_entry: object) -> Topic:
        if not isinstance(topic_key, str) or not topic_key:
            msg = "Topic keys must be non-empty strings"
            raise FeedConfigError(msg)

        label = f"topic '{topic_key}'"
        topic_entry = self.__require_mapping(raw_topic_entry, label)
        self.__reject_unknown_fields(topic_entry, _TOPIC_FIELDS, f"Unknown field(s) in {label}")

        return Topic(
            key=topic_key,
            display_name=self.__require_non_empty_string(
                topic_entry.get("display_name"),
                f"{label} display_name",
            ),
            keywords=self.__require_string_list(topic_entry.get("keywords"), f"{label} keywords"),
            language=self.__validate_language(topic_entry.get("language", "en"), topic_key),
            sources=self.__load_sources(topic_key, topic_entry.get("sources")),
        )

    def __load_sources(self, topic_key: str, raw_sources: object) -> list[Source]:
        if not isinstance(raw_sources, list) or not raw_sources:
            msg = f"topic '{topic_key}' sources must be a non-empty list"
            raise FeedConfigError(msg)

        return [
            self.__load_source(raw_source, f"topic '{topic_key}' source #{index}")
            for index, raw_source in enumerate(raw_sources, start=1)
        ]

    def __load_source(self, raw_source: object, label: str) -> Source:
        source_entry = self.__require_mapping(raw_source, label)
        self.__reject_unknown_fields(source_entry, _SOURCE_FIELDS, f"Unknown field(s) in {label}")

        return Source(
            name=self.__require_non_empty_string(source_entry.get("name"), f"{label} name"),
            domain=self.__validate_domain(source_entry.get("domain"), label),
        )

    def __validate_language(self, value: object, topic_key: str) -> str:
        language = self.__require_non_empty_string(value, f"topic '{topic_key}' language")
        if language not in SUPPORTED_TOPIC_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_TOPIC_LANGUAGES))
            msg = (
                f"Unsupported language for topic '{topic_key}': {language}. Supported: {supported}"
            )
            raise FeedConfigError(msg)
        return language

    def __validate_domain(self, value: object, label: str) -> str:
        domain = self.__require_non_empty_string(value, f"{label} domain")
        if (
            not _DOMAIN_PATTERN.fullmatch(domain)
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            msg = f"{label} domain is invalid: {domain}"
            raise FeedConfigError(msg)
        return domain

    def __validate_max_articles_per_topic(self, value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            msg = "settings.max_articles_per_topic must be an integer"
            raise FeedConfigError(msg)
        if not 1 <= value <= _MAX_ARTICLES_PER_TOPIC_LIMIT:
            msg = (
                "settings.max_articles_per_topic must be between "
                f"1 and {_MAX_ARTICLES_PER_TOPIC_LIMIT}"
            )
            raise FeedConfigError(msg)
        return value

    def __reject_unknown_fields(
        self,
        entry: Mapping[str, object],
        allowed_fields: set[str],
        message_prefix: str,
    ) -> None:
        unknown_fields = sorted(set(entry) - allowed_fields)
        if unknown_fields:
            msg = f"{message_prefix}: {', '.join(unknown_fields)}"
            raise FeedConfigError(msg)

    def __require_mapping(self, value: object, label: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            msg = f"{label} must be a mapping"
            raise FeedConfigError(msg)
        if not all(isinstance(key, str) for key in value):
            msg = f"{label} keys must be strings"
            raise FeedConfigError(msg)
        return value

    def __require_non_empty_string(self, value: object, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            msg = f"{label} must be a non-empty string"
            raise FeedConfigError(msg)
        return value.strip()

    def __require_string_list(self, value: object, label: str) -> list[str]:
        if not isinstance(value, list) or not value:
            msg = f"{label} must be a non-empty list"
            raise FeedConfigError(msg)
        return [self.__require_non_empty_string(item, label) for item in value]
