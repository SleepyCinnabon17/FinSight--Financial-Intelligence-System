from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.transaction import Transaction
from backend.pipeline.analyzer import (
    compute_category_totals,
    compute_daily_trend,
    compute_savings_opportunity,
    detect_anomalies,
)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def test_compute_category_totals() -> None:
    transactions = [
        Transaction(merchant="A", date=_today(), total=100, category="Food"),
        Transaction(merchant="B", date=_today(), total=200, category="Food"),
        Transaction(merchant="C", date=_today(), total=50, category="Transport"),
        Transaction(merchant="D", date=_today(), total=75, category="Shopping"),
        Transaction(merchant="E", date=_today(), total=25, category="Shopping"),
    ]
    assert compute_category_totals(transactions, _today(), _today()) == {"Food": 300.0, "Transport": 50.0, "Shopping": 100.0}


def test_compute_daily_trend_has_30_entries_and_zero_days() -> None:
    trend = compute_daily_trend([Transaction(merchant="A", date=_today(), total=100, category="Food")])
    assert len(trend) == 30
    assert any(total == 0 for _, total in trend)


def test_detect_anomalies_flags_large_category_outlier() -> None:
    today = datetime.now(timezone.utc).date()
    history = [
        Transaction(merchant="A", date=(today - timedelta(days=index + 1)).isoformat(), total=100, category="Food")
        for index in range(5)
    ]
    result = detect_anomalies(Transaction(merchant="A", date=today.isoformat(), total=1000, category="Food"), history)
    assert result.is_anomaly is True


def test_detect_anomalies_normal_bill_not_flagged() -> None:
    today = datetime.now(timezone.utc).date()
    history = [
        Transaction(merchant="A", date=(today - timedelta(days=index + 1)).isoformat(), total=100, category="Food")
        for index in range(5)
    ]
    result = detect_anomalies(Transaction(merchant="A", date=today.isoformat(), total=100, category="Food"), history)
    assert result.is_anomaly is False


def test_compute_savings_opportunity() -> None:
    transactions = [
        Transaction(merchant="A", date=_today(), total=6000, category="Food"),
        Transaction(merchant="B", date=_today(), total=5000, category="Shopping"),
        Transaction(merchant="C", date=_today(), total=2000, category="Subscription"),
    ]
    assert compute_savings_opportunity(transactions, {"Food": 5000, "Shopping": 4000, "Subscription": 1000}) == 3000.0
    assert compute_savings_opportunity([], {"Food": 5000, "Shopping": 4000, "Subscription": 1000}) == 0.0
