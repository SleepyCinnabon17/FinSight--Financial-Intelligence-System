from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import feedparser
import requests

from backend import config
from backend.chatbot.market import format_market_snippet, get_market_data
from backend.chatbot.news import get_news_context
from backend.models.analysis import AnalysisResult
from backend.models.news import NewsContext
from backend.models.transaction import Transaction
from backend.pipeline.analyzer import generate_analysis


logger = logging.getLogger(__name__)

INVESTMENT_KEYWORDS = ["invest", "where should i", "portfolio", "fund", "nifty", "fd", "sip", "stock", "market", "rbi", "returns", "savings"]
SPENDING_KEYWORDS = ["spend", "spent", "how much", "category", "merchant", "bill"]
INJECTION_PATTERNS = ["ignore previous instructions", "you are now", "disregard", "forget your", "new persona"]
INVESTMENT_DISCLAIMER = "Nova does not provide certified financial advice."

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current finance or market context when cached market/news data is insufficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise finance search query, maximum 100 characters.",
                }
            },
            "required": ["query"],
        },
    },
}


def classify_intent(message: str) -> str:
    lowered = message.lower()
    if any(keyword in lowered for keyword in INVESTMENT_KEYWORDS):
        return "investment"
    if any(keyword in lowered for keyword in SPENDING_KEYWORDS):
        return "spending"
    return "general"


def sanitize_input(message: str) -> str:
    sanitized = message
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(re.escape(pattern), "", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()[: config.NOVA_MAX_INPUT_CHARS]


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_web_query(query: str) -> str:
    stripped = re.sub(r"[^A-Za-z0-9 .,\-?]", " ", query)
    return re.sub(r"\s+", " ", stripped).strip()[: config.WEB_SEARCH_MAX_QUERY_CHARS]


def execute_web_search(query: str) -> str:
    safe_query = _sanitize_web_query(query)
    if not safe_query:
        return ""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": safe_query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = [
            payload.get("AbstractText", ""),
            payload.get("Answer", ""),
            payload.get("Definition", ""),
        ]
        for candidate in candidates:
            text = _strip_html(str(candidate))
            if text:
                return text[:500]
    except Exception:
        pass

    try:
        url = f"https://news.google.com/rss/search?q={safe_query.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        snippets: list[str] = []
        for entry in feed.entries[:3]:
            title = _strip_html(getattr(entry, "title", ""))
            summary = _strip_html(getattr(entry, "summary", ""))
            combined = _strip_html(f"{title}. {summary}")
            if combined:
                snippets.append(combined)
        return " ".join(snippets)[:500]
    except Exception:
        return ""


def _analysis_lines(analysis: AnalysisResult) -> str:
    return "\n".join(
        [
            f"Total spend: {analysis.total_spend}",
            f"Transaction count: {analysis.transaction_count}",
            f"Category totals: {analysis.category_totals}",
            f"Top merchants: {analysis.top_merchants}",
            f"Daily trend: {analysis.daily_trend[-7:]}",
            f"Savings opportunity: {analysis.savings_opportunity}",
            f"Insights: {analysis.insights}",
        ]
    )


def _news_summary(news_context: NewsContext | None) -> str:
    if news_context is None:
        return "Current news unavailable."
    return "\n".join(
        [
            f"Macro trends: {news_context.macro_trends}",
            f"Sector signals: {news_context.sector_signals}",
            f"Fund developments: {news_context.fund_developments}",
        ]
    )


def build_system_prompt(analysis: AnalysisResult, market_data: dict[str, Any], news_context: NewsContext | None) -> str:
    market_data_snippet = format_market_snippet(market_data) if market_data else "Market data unavailable."
    news_summary = _news_summary(news_context)
    return (
        "You are Nova, FinSight's personal finance assistant. Use only the user's confirmed bill data for spending "
        "analysis, and use cached market/news context for investment education. Do not claim to be a certified advisor.\n\n"
        f"Spending analysis:\n{_analysis_lines(analysis)}\n\n"
        f"Market data:\n{market_data_snippet}\n\n"
        f"News summary:\n{news_summary}\n\n"
        f"When giving investment suggestions, always end with this exact disclaimer: {INVESTMENT_DISCLAIMER}"
    )


def should_use_web_search(provider: str) -> bool:
    return provider.lower() in {"groq", "openai", "anthropic"}


def _headers_for_provider(provider: str) -> dict[str, str]:
    if provider == "groq" and config.GROQ_API_KEY:
        return {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    if provider == "openai" and config.OPENAI_API_KEY:
        return {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    if provider == "anthropic" and config.ANTHROPIC_API_KEY:
        return {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"}
    return {}


def _provider_url(provider: str) -> str | None:
    if provider == "groq" and config.GROQ_API_KEY:
        return "https://api.groq.com/openai/v1/chat/completions"
    if provider == "openai" and config.OPENAI_API_KEY:
        return "https://api.openai.com/v1/chat/completions"
    if provider == "anthropic" and config.ANTHROPIC_API_KEY:
        return "https://api.anthropic.com/v1/messages"
    if provider == "ollama":
        return f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    return None


def _openai_like_body(provider: str, messages: list[dict[str, Any]], use_tools: bool) -> dict[str, Any]:
    model = "llama-3.1-8b-instant" if provider == "groq" else "gpt-4o-mini"
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
    if use_tools:
        body["tools"] = [WEB_SEARCH_TOOL]
        body["tool_choice"] = "auto"
    return body


def _anthropic_body(system_prompt: str, messages: list[dict[str, Any]], use_tools: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "claude-3-5-haiku-latest",
        "system": system_prompt,
        "messages": [message for message in messages if message.get("role") != "system"],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    if use_tools:
        body["tools"] = [
            {
                "name": "web_search",
                "description": WEB_SEARCH_TOOL["function"]["description"],
                "input_schema": WEB_SEARCH_TOOL["function"]["parameters"],
            }
        ]
    return body


def _fallback_llm_response(messages: list[dict[str, Any]], system_prompt: str) -> str:
    del system_prompt
    last = next((message.get("content", "") for message in reversed(messages) if message.get("role") == "user"), "")
    intent = classify_intent(str(last))
    if intent == "spending":
        return "Based on your confirmed bills, I can summarize spending by category, merchant, and recent trends."
    if intent == "investment":
        return f"Current market and news context can help frame options, but keep decisions diversified and risk-aware. {INVESTMENT_DISCLAIMER}"
    return "I can help analyze bills, explain spending patterns, and discuss market context for financial planning."


def _extract_tool_call(provider: str, response_json: dict[str, Any]) -> tuple[str, str] | None:
    if provider in {"groq", "openai"}:
        message = response_json.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return None
        call = tool_calls[0]
        args = call.get("function", {}).get("arguments", "{}")
        try:
            query = json.loads(args).get("query", "")
        except json.JSONDecodeError:
            query = ""
        return call.get("id", "web_search_call"), str(query)
    if provider == "anthropic":
        for block in response_json.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "web_search":
                return block.get("id", "web_search_call"), str(block.get("input", {}).get("query", ""))
    return None


def _extract_content(provider: str, response_json: dict[str, Any]) -> str:
    if provider in {"groq", "openai"}:
        return str(response_json.get("choices", [{}])[0].get("message", {}).get("content") or "")
    if provider == "anthropic":
        parts = [block.get("text", "") for block in response_json.get("content", []) if block.get("type") == "text"]
        return "\n".join(parts)
    if provider == "ollama":
        return str(response_json.get("message", {}).get("content") or "")
    return ""


def _call_provider_once(messages: list[dict[str, Any]], system_prompt: str, use_tools: bool) -> dict[str, Any] | None:
    provider = config.LLM_PROVIDER.lower()
    url = _provider_url(provider)
    if url is None:
        return None
    if provider in {"groq", "openai"}:
        body = _openai_like_body(provider, [{"role": "system", "content": system_prompt}, *messages], use_tools)
    elif provider == "anthropic":
        body = _anthropic_body(system_prompt, messages, use_tools)
    else:
        body = {"model": "llama3.1", "messages": [{"role": "system", "content": system_prompt}, *messages], "stream": False}
    response = requests.post(url, json=body, headers=_headers_for_provider(provider), timeout=45)
    response.raise_for_status()
    return response.json()


async def _stream_text(text: str) -> AsyncGenerator[str]:
    for token in re.findall(r"\S+\s*", text):
        yield token
        await asyncio.sleep(0)


async def call_llm(messages: list[dict[str, Any]], system_prompt: str, use_tools: bool) -> AsyncGenerator[str]:
    provider = config.LLM_PROVIDER.lower()
    try:
        response = await asyncio.to_thread(_call_provider_once, messages, system_prompt, use_tools)
        if response is None:
            async for token in _stream_text(_fallback_llm_response(messages, system_prompt)):
                yield token
            return
        tool_call = _extract_tool_call(provider, response) if use_tools else None
        if tool_call is not None:
            tool_call_id, query = tool_call
            search_result = execute_web_search(query)
            if provider in {"groq", "openai"}:
                messages = [
                    *messages,
                    response.get("choices", [{}])[0].get("message", {}),
                    {"role": "tool", "tool_call_id": tool_call_id, "content": search_result},
                ]
            else:
                messages = [*messages, {"role": "user", "content": f"Web search result for {query}: {search_result}"}]
            response = await asyncio.to_thread(_call_provider_once, messages, system_prompt, False)
            if response is None:
                async for token in _stream_text(search_result):
                    yield token
                return
        content = _extract_content(provider, response)
        async for token in _stream_text(content):
            yield token
    except requests.Timeout:
        yield "Nova is temporarily unavailable. Please try again."
    except Exception as exc:
        logger.warning("Nova LLM call failed: %s", exc)
        async for token in _stream_text(_fallback_llm_response(messages, system_prompt)):
            yield token


async def chat(message: str, history: list[dict[str, Any]], transactions: list[Transaction]) -> AsyncGenerator[str]:
    if not transactions:
        yield "I don't have any bills to analyze yet. Upload some bills to get started!"
        return
    sanitized = sanitize_input(message)
    intent = classify_intent(sanitized)
    analysis = generate_analysis(transactions)
    market_data = get_market_data()
    news_context = get_news_context() if intent == "investment" else None
    system_prompt = build_system_prompt(analysis, market_data, news_context)
    messages = [*history, {"role": "user", "content": sanitized}]
    use_tools = intent == "investment" and should_use_web_search(config.LLM_PROVIDER)

    chunks: list[str] = []
    async for token in call_llm(messages, system_prompt, use_tools):
        chunks.append(token)
        yield token
    if not "".join(chunks).strip():
        chunks.clear()
        async for token in call_llm(messages, system_prompt, use_tools):
            chunks.append(token)
            yield token
        if not "".join(chunks).strip():
            yield "Nova couldn't generate a response. Please try rephrasing."
    elif intent == "investment" and INVESTMENT_DISCLAIMER not in "".join(chunks):
        yield f" {INVESTMENT_DISCLAIMER}"
