from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yfinance as yf

from backend.config import AMFI_LARGE_CAP_NAV_LIMIT, MARKET_CACHE_PATH, MARKET_DATA_CACHE_TTL_HOURS, SBI_FD_1Y_RATE


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_nifty() -> dict[str, float]:
    history = yf.Ticker("^NSEI").history(period="1d")
    if history.empty:
        raise RuntimeError("Nifty history unavailable")
    row = history.iloc[-1]
    close = float(row["Close"])
    open_value = float(row.get("Open", close))
    change_pct = 0.0 if open_value == 0 else ((close - open_value) / open_value) * 100
    return {"value": round(close, 2), "change_pct": round(change_pct, 2)}


def fetch_usdinr() -> float:
    history = yf.Ticker("USDINR=X").history(period="1d")
    if history.empty:
        raise RuntimeError("USD/INR history unavailable")
    return round(float(history["Close"].iloc[-1]), 4)


def fetch_amfi_navs(scheme_codes: list[str]) -> dict[str, float]:
    if not scheme_codes:
        return {}
    response = requests.get("https://www.amfiindia.com/spages/NAVAll.txt", timeout=15)
    response.raise_for_status()
    wanted = set(scheme_codes)
    navs: dict[str, float] = {}
    for line in response.text.splitlines():
        parts = line.split(";")
        if len(parts) < 5:
            continue
        scheme_code, _, _, scheme_name, nav_value = parts[:5]
        if scheme_code in wanted:
            try:
                navs[scheme_name] = float(nav_value)
            except ValueError:
                continue
    return navs


def fetch_top_large_cap_navs(limit: int = AMFI_LARGE_CAP_NAV_LIMIT) -> dict[str, float]:
    response = requests.get("https://www.amfiindia.com/spages/NAVAll.txt", timeout=15)
    response.raise_for_status()
    navs: dict[str, float] = {}
    for line in response.text.splitlines():
        parts = line.split(";")
        if len(parts) < 5:
            continue
        _, _, _, scheme_name, nav_value = parts[:5]
        normalized = scheme_name.lower()
        if "large cap" not in normalized or "growth" not in normalized:
            continue
        try:
            navs[scheme_name] = float(nav_value)
        except ValueError:
            continue
        if len(navs) >= limit:
            break
    return navs


def format_market_snippet(data: dict[str, Any]) -> str:
    if not data:
        return "Market data unavailable."
    lines: list[str] = []
    nifty = data.get("nifty")
    if isinstance(nifty, dict):
        lines.append(f"Nifty 50: {nifty.get('value')} ({nifty.get('change_pct')}% intraday)")
    if "usdinr" in data:
        lines.append(f"USD/INR: {data['usdinr']}")
    if "sbi_fd_1y" in data:
        lines.append(f"SBI 1-year FD rate: {data['sbi_fd_1y']}%")
    amfi_navs = data.get("amfi_navs")
    if isinstance(amfi_navs, dict) and amfi_navs:
        for scheme, nav in amfi_navs.items():
            lines.append(f"{scheme}: NAV {nav}")
    return "\n".join(lines) if lines else "Market data unavailable."


def _load_cache() -> dict[str, Any] | None:
    if not MARKET_CACHE_PATH.exists():
        return None
    try:
        data = json.loads(MARKET_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _cache_is_fresh(cache: dict[str, Any]) -> bool:
    fetched_at = cache.get("fetched_at")
    if not isinstance(fetched_at, str):
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return _now() - fetched <= timedelta(hours=MARKET_DATA_CACHE_TTL_HOURS)


def _save_cache(data: dict[str, Any]) -> None:
    MARKET_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": _now().isoformat(), "data": data}
    tmp_path = Path(str(MARKET_CACHE_PATH) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(tmp_path, MARKET_CACHE_PATH)


def get_market_data(force_refresh: bool = False) -> dict[str, Any]:
    cache = _load_cache()
    if cache and not force_refresh and _cache_is_fresh(cache):
        data = cache.get("data", {})
        return data if isinstance(data, dict) else {}
    try:
        data = {
            "nifty": fetch_nifty(),
            "usdinr": fetch_usdinr(),
            "sbi_fd_1y": SBI_FD_1Y_RATE,
            "amfi_navs": fetch_top_large_cap_navs(),
        }
        _save_cache(data)
        return data
    except Exception as exc:
        logger.warning("Market data fetch failed: %s", exc)
        if cache and isinstance(cache.get("data"), dict):
            return cache["data"]
        return {}


def market_cache_is_fresh() -> bool:
    cache = _load_cache()
    return bool(cache and _cache_is_fresh(cache))
