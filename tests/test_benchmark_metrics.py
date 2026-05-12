from __future__ import annotations

from backend.benchmarks.metrics import (
    amount_accuracy_within_tolerance,
    character_error_rate,
    classification_metrics,
    confidence_calibration_buckets,
    date_parse_rate,
    duplicate_detection_rate,
    field_accuracy,
    word_error_rate,
)


def test_text_error_rates_use_edit_distance() -> None:
    assert character_error_rate("kitten", "sitten") == 0.1667
    assert word_error_rate("hello world", "hello brave world") == 0.5


def test_field_and_amount_accuracy() -> None:
    comparisons = [
        {"merchant": True, "date": False, "total": True},
        {"merchant": True, "date": True, "total": False},
    ]
    result = field_accuracy(comparisons, ["merchant", "date", "total"])

    assert result["overall"] == 0.6667
    assert result["by_field"] == {"merchant": 1.0, "date": 0.5, "total": 0.5}
    assert amount_accuracy_within_tolerance([100.75, 101.5, None], [100.0, 100.0, 10.0]) == 0.3333


def test_date_parse_rate() -> None:
    assert date_parse_rate(["2026-05-12", "bad-date", None]) == 0.3333


def test_classification_metrics() -> None:
    result = classification_metrics(
        ["Food", "Food", "Shopping", "Transport"],
        ["Food", "Shopping", "Shopping", "Food"],
    )

    assert result["accuracy"] == 0.5
    assert result["macro_f1"] == 0.3889
    assert result["weighted_f1"] == 0.4167
    assert result["per_category"]["Food"] == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "support": 2,
    }


def test_duplicate_detection_rate() -> None:
    assert duplicate_detection_rate(2, 4) == 0.5
    assert duplicate_detection_rate(0, 0) is None


def test_confidence_calibration_buckets() -> None:
    buckets = confidence_calibration_buckets(
        [(0.95, True), (0.85, False), (0.65, True), (0.25, False)],
        bucket_size=0.5,
    )

    assert buckets == [
        {"range": "0.00-0.50", "count": 1, "avg_confidence": 0.25, "accuracy": 0.0, "calibration_gap": 0.25},
        {"range": "0.50-1.00", "count": 3, "avg_confidence": 0.8167, "accuracy": 0.6667, "calibration_gap": 0.15},
    ]
