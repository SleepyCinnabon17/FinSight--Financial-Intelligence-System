from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.chatbot import news
from backend.models.news import NewsContext


class Response:
    content = b"feed"
    text = "feed"

    def raise_for_status(self) -> None:
        return None


def _entry(title: str, hours_old: int = 1) -> SimpleNamespace:
    published = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    return SimpleNamespace(
        title=title,
        summary="<p>Summary</p>",
        published=published.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        published_parsed=published.timetuple(),
    )


def test_fetch_rss_with_mock_feedparser(monkeypatch) -> None:
    monkeypatch.setattr(news.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(news.feedparser, "parse", lambda *_: SimpleNamespace(entries=[_entry("Headline")]))
    items = news.fetch_rss("https://example.test")
    assert items[0]["title"] == "Headline"
    assert items[0]["summary"] == "Summary"


def test_fetch_rss_network_error_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(news.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network")))
    monkeypatch.setattr(news.feedparser, "parse", lambda *_: (_ for _ in ()).throw(RuntimeError("parse")))
    assert news.fetch_rss("https://example.test") == []


def test_headline_deduplication(monkeypatch) -> None:
    monkeypatch.setattr(news, "fetch_rss", lambda url: [{"title": "Same", "summary": "One", "published": "now"}])
    monkeypatch.setattr(news, "RSS_SOURCES", {"a": "url-a", "b": "url-b"})
    assert news.fetch_all_headlines(["a", "b"]) == ["Same. One"]


def test_age_filter_excludes_old_headline(monkeypatch) -> None:
    monkeypatch.setattr(news.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(news.feedparser, "parse", lambda *_: SimpleNamespace(entries=[_entry("Old", hours_old=72)]))
    assert news.fetch_rss("https://example.test") == []


def test_summarize_headlines_valid_json(monkeypatch) -> None:
    monkeypatch.setattr(news, "_call_llm_summary", lambda _: json.dumps({"macro_trends": ["A"], "sector_signals": {"Banking": "B"}, "fund_developments": ["C"]}))
    context = news.summarize_headlines(["A headline"])
    assert context.macro_trends == ["A"]
    assert context.sector_signals == {"Banking": "B"}


def test_summarize_headlines_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(news, "_call_llm_summary", lambda _: "not json")
    context = news.summarize_headlines(["A headline"])
    assert context.macro_trends == []
    assert context.sector_signals == {}


def test_get_news_context_fresh_cache_no_fetch(monkeypatch) -> None:
    cached = NewsContext(fetched_at=datetime.now(timezone.utc).isoformat(), sources_used=["et"], headline_count=1, macro_trends=["cached"])
    monkeypatch.setattr(news, "load_news_cache", lambda _: cached)
    fetch = lambda _: (_ for _ in ()).throw(AssertionError("fetch should not run"))
    monkeypatch.setattr(news, "fetch_all_headlines", fetch)
    assert news.get_news_context() == cached


def test_get_news_context_stale_cache_fetches_and_updates(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "news_cache.json"
    monkeypatch.setattr(news, "NEWS_CACHE_PATH", cache_path)
    monkeypatch.setattr(news, "fetch_all_headlines", lambda _: ["Headline"])
    monkeypatch.setattr(news, "_call_llm_summary", lambda _: json.dumps({"macro_trends": ["fresh"], "sector_signals": {}, "fund_developments": []}))
    context = news.get_news_context(force_refresh=True)
    assert context is not None
    assert context.macro_trends == ["fresh"]
    assert cache_path.exists()


def test_get_news_context_fetch_failure_uses_stale_cache_under_24h(monkeypatch) -> None:
    cached = NewsContext(fetched_at=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), sources_used=["et"], headline_count=1, macro_trends=["stale"])
    monkeypatch.setattr(news, "load_news_cache", lambda _: cached)
    monkeypatch.setattr(news, "fetch_all_headlines", lambda _: [])
    assert news.get_news_context(force_refresh=True) == cached


def test_get_news_context_fetch_failure_old_cache_returns_none(monkeypatch) -> None:
    cached = NewsContext(fetched_at=(datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(), sources_used=["et"], headline_count=1, macro_trends=["old"])
    monkeypatch.setattr(news, "load_news_cache", lambda _: cached)
    monkeypatch.setattr(news, "fetch_all_headlines", lambda _: [])
    assert news.get_news_context(force_refresh=True) is None
