from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import feedparser
import requests
from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import (
    ANTHROPIC_API_KEY,
    GROQ_API_KEY,
    LLM_PROVIDER,
    NEWS_CACHE_PATH,
    NEWS_CACHE_TTL_HOURS,
    NEWS_RSS_URLS,
    NEWS_SOURCES,
    OLLAMA_BASE_URL,
    OPENAI_API_KEY,
)
from backend.models.news import NewsContext


logger = logging.getLogger(__name__)

RSS_SOURCES: dict[str, str] = dict(NEWS_RSS_URLS)

SYSTEM_PROMPT = (
    "You are a financial analyst summarizing Indian financial news. Given these headlines, return ONLY a valid JSON "
    "object with keys: macro_trends (list of 3 strings), sector_signals (dict mapping sector to one-line signal), "
    "fund_developments (list of strings). No preamble, no markdown, just JSON."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_entry_datetime(entry: Any) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or entry.get("published_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    published = getattr(entry, "published", None) or entry.get("published")
    if not published:
        return None
    try:
        value = parsedate_to_datetime(str(published))
    except Exception:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def fetch_rss(url: str, max_items: int = 10) -> list[dict[str, str]]:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", url, exc)
            return []

    cutoff = _now() - timedelta(hours=48)
    items: list[dict[str, str]] = []
    for entry in feed.entries[:max_items]:
        published_at = _parse_entry_datetime(entry)
        if published_at is None or published_at < cutoff:
            continue
        title = _strip_html(getattr(entry, "title", "") or entry.get("title", ""))
        summary = _strip_html(getattr(entry, "summary", "") or entry.get("summary", ""))
        published = getattr(entry, "published", "") or entry.get("published", "")
        if title:
            items.append({"title": title, "summary": summary, "published": str(published)})
    return items


def fetch_all_headlines(sources: list[str]) -> list[str]:
    seen_titles: set[str] = set()
    headlines: list[str] = []
    for source in sources:
        url = RSS_SOURCES.get(source)
        if not url:
            continue
        for item in fetch_rss(url):
            title = item["title"]
            if title in seen_titles:
                continue
            seen_titles.add(title)
            combined = _strip_html(f"{title}. {item.get('summary', '')}")
            if combined:
                headlines.append(combined)
            if len(headlines) >= 30:
                return headlines
    return headlines[:30]


def _numbered_headlines(headlines: list[str]) -> str:
    return "\n".join(f"{index + 1}. {_strip_html(headline)}" for index, headline in enumerate(headlines))


def _provider_payload(system_prompt: str, user_message: str) -> tuple[str, dict[str, Any], dict[str, str]] | None:
    provider = LLM_PROVIDER.lower()
    if provider == "groq" and GROQ_API_KEY:
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                "temperature": 0.1,
            },
            {"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
    if provider == "openai" and OPENAI_API_KEY:
        return (
            "https://api.openai.com/v1/chat/completions",
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                "temperature": 0.1,
            },
            {"Authorization": f"Bearer {OPENAI_API_KEY}"},
        )
    if provider == "anthropic" and ANTHROPIC_API_KEY:
        return (
            "https://api.anthropic.com/v1/messages",
            {
                "model": "claude-3-5-haiku-latest",
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": 500,
                "temperature": 0.1,
            },
            {
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
    if provider == "ollama":
        return (
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            {
                "model": "llama3.1",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                "stream": False,
            },
            {},
        )
    return None


def _extract_provider_content(provider: str, data: dict[str, Any]) -> str | None:
    if provider in {"groq", "openai"}:
        return data.get("choices", [{}])[0].get("message", {}).get("content")
    if provider == "anthropic":
        content = data.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text")
    if provider == "ollama":
        return data.get("message", {}).get("content")
    return None


def _call_llm_summary(headlines: list[str]) -> str | None:
    payload = _provider_payload(SYSTEM_PROMPT, _numbered_headlines(headlines))
    if payload is None:
        return None
    url, body, headers = payload
    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return _extract_provider_content(LLM_PROVIDER.lower(), response.json())
    except Exception as exc:
        logger.warning("News LLM summary failed: %s", exc)
        return None


def _fallback_summary(headlines: list[str]) -> dict[str, Any]:
    clean = [_strip_html(headline) for headline in headlines if _strip_html(headline)]
    macro = clean[:3] if clean else []
    return {
        "macro_trends": macro,
        "sector_signals": {"Markets": clean[0][:160]} if clean else {},
        "fund_developments": clean[3:6],
    }


def summarize_headlines(headlines: list[str]) -> NewsContext:
    raw_response = _call_llm_summary(headlines)
    summary_model = LLM_PROVIDER
    if raw_response is None:
        parsed = _fallback_summary(headlines)
        summary_model = "fallback-extractive"
    else:
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("News LLM returned invalid JSON")
            parsed = {"macro_trends": [], "sector_signals": {}, "fund_developments": []}
    return NewsContext(
        fetched_at=_now().isoformat(),
        sources_used=list(NEWS_SOURCES),
        headline_count=len(headlines),
        macro_trends=[str(item) for item in parsed.get("macro_trends", [])][:3],
        sector_signals={str(key): str(value) for key, value in parsed.get("sector_signals", {}).items()},
        fund_developments=[str(item) for item in parsed.get("fund_developments", [])],
        raw_headlines=[_strip_html(headline) for headline in headlines],
        summary_model=summary_model,
    )


def save_news_cache(context: NewsContext, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(target) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(context), handle, indent=2)
    os.replace(tmp_path, target)


def load_news_cache(path: str) -> NewsContext | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return NewsContext(**data)
    except Exception:
        return None


def cache_is_fresh(context: NewsContext, ttl_hours: float) -> bool:
    try:
        fetched = datetime.fromisoformat(context.fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return _now() - fetched <= timedelta(hours=ttl_hours)


def _context_has_summary(context: NewsContext) -> bool:
    return bool(context.macro_trends or context.sector_signals or context.fund_developments)


def get_news_context(force_refresh: bool = False) -> NewsContext | None:
    try:
        cache = load_news_cache(str(NEWS_CACHE_PATH))
        if cache is not None and not force_refresh and cache_is_fresh(cache, NEWS_CACHE_TTL_HOURS):
            return cache
        headlines = fetch_all_headlines(list(NEWS_SOURCES))
        if not headlines:
            return cache if cache is not None and cache_is_fresh(cache, 24.0) else None
        context = summarize_headlines(headlines)
        if not _context_has_summary(context):
            return cache if cache is not None and cache_is_fresh(cache, 24.0) else None
        save_news_cache(context, str(NEWS_CACHE_PATH))
        return context
    except Exception as exc:
        logger.warning("News context refresh failed: %s", exc)
        cache = load_news_cache(str(NEWS_CACHE_PATH))
        return cache if cache is not None and cache_is_fresh(cache, 24.0) else None


def start_news_scheduler(app: Any) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(get_news_context, "interval", hours=NEWS_CACHE_TTL_HOURS)
    scheduler.start()
    app.state.news_scheduler = scheduler
    return scheduler
