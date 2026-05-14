from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Iterable

from backend.config import (
    ANALYSIS_WINDOW_DAYS,
    ANOMALY_RULE1_SCORE,
    ANOMALY_RULE2_SCORE,
    ANOMALY_RULE3_SCORE,
    ANOMALY_STDDEV_THRESHOLD,
    BUDGET_CONFIG,
    HIGH_VALUE_NEW_MERCHANT_AMOUNT,
    MERCHANT_REPEAT_THRESHOLD,
    MOM_INCREASE_THRESHOLD,
    NEW_MERCHANT_LOOKBACK_DAYS,
)
from backend.models.analysis import AnalysisResult
from backend.models.transaction import Transaction


@dataclass(slots=True)
class AnomalyResult:
    is_anomaly: bool
    score: float
    reason: str | None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None


def _transaction_date(transaction: Transaction, use_upload_fallback: bool) -> date | None:
    if use_upload_fallback:
        return _parse_date(transaction.upload_timestamp) or _parse_date(transaction.date)
    return _parse_date(transaction.date)


def _coerce_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _parse_date(value)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def compute_category_totals(
    transactions: Iterable[Transaction],
    start_date: str | date | datetime | None,
    end_date: str | date | datetime | None,
    use_upload_fallback: bool = False,
) -> dict[str, float]:
    start = _coerce_date(start_date)
    end = _coerce_date(end_date)
    totals: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        tx_date = _transaction_date(transaction, use_upload_fallback)
        if tx_date is None:
            continue
        if start and tx_date < start:
            continue
        if end and tx_date > end:
            continue
        totals[transaction.category or "Uncategorized"] += transaction.total
    return {category: round(total, 2) for category, total in totals.items()}


def compute_merchant_totals(
    transactions: Iterable[Transaction],
    days: int = ANALYSIS_WINDOW_DAYS,
    use_upload_fallback: bool = False,
) -> list[tuple[str, float]]:
    cutoff = _today() - timedelta(days=days)
    totals: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        tx_date = _transaction_date(transaction, use_upload_fallback)
        if tx_date is None or tx_date < cutoff:
            continue
        totals[transaction.merchant or "Unknown"] += transaction.total
    return sorted(((merchant, round(total, 2)) for merchant, total in totals.items()), key=lambda item: item[1], reverse=True)[:5]


def compute_daily_trend(
    transactions: Iterable[Transaction],
    days: int = ANALYSIS_WINDOW_DAYS,
    use_upload_fallback: bool = False,
) -> list[tuple[str, float]]:
    end = _today()
    start = end - timedelta(days=days - 1)
    totals: dict[date, float] = defaultdict(float)
    for transaction in transactions:
        tx_date = _transaction_date(transaction, use_upload_fallback)
        if tx_date is None or tx_date < start or tx_date > end:
            continue
        totals[tx_date] += transaction.total
    return [((start + timedelta(days=offset)).isoformat(), round(totals[start + timedelta(days=offset)], 2)) for offset in range(days)]


def detect_anomalies(transaction: Transaction, history: Iterable[Transaction]) -> AnomalyResult:
    history_list = list(history)
    category_history = [
        item.total
        for item in history_list
        if not item.is_anomaly and (item.category or "") == (transaction.category or "") and item.id != transaction.id
    ]
    if category_history:
        category_mean = mean(category_history)
        category_stddev = pstdev(category_history) if len(category_history) > 1 else 0.0
        if transaction.total > category_mean + ANOMALY_STDDEV_THRESHOLD * category_stddev:
            return AnomalyResult(True, ANOMALY_RULE1_SCORE, "amount exceeds category mean by configured standard deviation threshold")

    tx_date = _parse_date(transaction.date) or _today()
    merchant_seen = False
    for item in history_list:
        item_date = _parse_date(item.date)
        if item_date is None:
            continue
        if (item.merchant or "").lower() == (transaction.merchant or "").lower() and 0 <= (tx_date - item_date).days <= NEW_MERCHANT_LOOKBACK_DAYS:
            merchant_seen = True
            break
    if not merchant_seen and transaction.total > HIGH_VALUE_NEW_MERCHANT_AMOUNT:
        return AnomalyResult(True, ANOMALY_RULE2_SCORE, "high-value transaction from merchant not seen in lookback window")

    same_day_count = sum(
        1
        for item in history_list
        if (item.merchant or "").lower() == (transaction.merchant or "").lower()
        and _parse_date(item.date) == tx_date
    )
    if same_day_count + 1 > MERCHANT_REPEAT_THRESHOLD:
        return AnomalyResult(True, ANOMALY_RULE3_SCORE, "merchant appears more than configured repeat threshold on same date")

    return AnomalyResult(False, 0.0, None)


def compute_savings_opportunity(transactions: Iterable[Transaction], budget_config: dict[str, float]) -> float:
    today = _today()
    tracked = {"Food", "Shopping", "Subscription"}
    spend = 0.0
    for transaction in transactions:
        tx_date = _parse_date(transaction.date)
        if tx_date is None or tx_date.year != today.year or tx_date.month != today.month:
            continue
        if transaction.category in tracked:
            spend += transaction.total
    budget = sum(float(budget_config.get(category, 0.0)) for category in tracked)
    return round(max(0.0, spend - budget), 2)


def _month_range(month_offset: int) -> tuple[date, date]:
    today = _today()
    first_this_month = today.replace(day=1)
    if month_offset == 0:
        start = first_this_month
    else:
        previous_end = first_this_month - timedelta(days=1)
        start = previous_end.replace(day=1)
    if month_offset == 0:
        next_month = (first_this_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
    else:
        end = first_this_month - timedelta(days=1)
    return start, end


def _mom_insights(transactions: list[Transaction]) -> list[str]:
    current_start, current_end = _month_range(0)
    previous_start, previous_end = _month_range(-1)
    current = compute_category_totals(transactions, current_start, current_end)
    previous = compute_category_totals(transactions, previous_start, previous_end)
    insights: list[str] = []
    for category, current_total in current.items():
        previous_total = previous.get(category, 0.0)
        if previous_total <= 0:
            continue
        increase = (current_total - previous_total) / previous_total
        if increase > MOM_INCREASE_THRESHOLD:
            insights.append(f"{category} spend is up {increase * 100:.1f}% month over month.")
    return insights


def generate_analysis(transactions: Iterable[Transaction]) -> AnalysisResult:
    txs = list(transactions)
    end = _today()
    start = end - timedelta(days=ANALYSIS_WINDOW_DAYS - 1)
    category_totals = compute_category_totals(txs, start, end)
    merchant_totals = compute_merchant_totals(txs)
    daily_trend = compute_daily_trend(txs)
    has_trend_activity = any(amount for _, amount in daily_trend)
    if txs and (not category_totals or not merchant_totals or not has_trend_activity):
        if not category_totals:
            category_totals = compute_category_totals(txs, start, end, use_upload_fallback=True)
        if not merchant_totals:
            merchant_totals = compute_merchant_totals(txs, use_upload_fallback=True)
        if not has_trend_activity:
            daily_trend = compute_daily_trend(txs, use_upload_fallback=True)
    savings = compute_savings_opportunity(txs, BUDGET_CONFIG)
    anomalies = [
        {
            "id": str(transaction.id),
            "merchant": transaction.merchant,
            "total": transaction.total,
            "is_anomaly": transaction.is_anomaly,
            "anomaly_score": transaction.anomaly_score,
            "anomaly_reason": transaction.anomaly_reason,
        }
        for transaction in txs
        if transaction.is_anomaly
    ]
    budget_status = {
        category: round(category_totals.get(category, 0.0) - budget, 2)
        for category, budget in BUDGET_CONFIG.items()
    }
    return AnalysisResult(
        category_totals=category_totals,
        merchant_totals=merchant_totals,
        daily_trend=daily_trend,
        savings_opportunity=savings,
        insights=_mom_insights(txs),
        total_spend=round(sum(transaction.total for transaction in txs), 2),
        transaction_count=len(txs),
        anomalies=anomalies,
        budget_status=budget_status,
    )
