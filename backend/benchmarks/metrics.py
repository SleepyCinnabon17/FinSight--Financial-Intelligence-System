from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import ceil
from typing import Any, Iterable, Sequence


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _edit_distance(left: Sequence[Any], right: Sequence[Any]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            substitution = previous[j - 1] + (0 if left_item == right_item else 1)
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, prediction: str) -> float:
    if not reference:
        return 0.0 if not prediction else 1.0
    return _rate(_edit_distance(reference, prediction), len(reference))


def word_error_rate(reference: str, prediction: str) -> float:
    reference_words = reference.split()
    prediction_words = prediction.split()
    if not reference_words:
        return 0.0 if not prediction_words else 1.0
    return _rate(_edit_distance(reference_words, prediction_words), len(reference_words))


def field_accuracy(comparisons: Iterable[dict[str, bool]], fields: Sequence[str]) -> dict[str, Any]:
    rows = list(comparisons)
    by_field = {
        field: _rate(sum(1 for row in rows if row.get(field) is True), len(rows))
        for field in fields
    }
    total_checks = len(rows) * len(fields)
    total_correct = sum(1 for row in rows for field in fields if row.get(field) is True)
    return {"overall": _rate(total_correct, total_checks), "by_field": by_field}


def amount_accuracy_within_tolerance(
    predictions: Sequence[float | int | None],
    references: Sequence[float | int | None],
    tolerance: float = 1.0,
) -> float:
    pairs = list(zip(predictions, references))
    correct = 0
    for prediction, reference in pairs:
        if prediction is None or reference is None:
            continue
        if abs(float(prediction) - float(reference)) <= tolerance:
            correct += 1
    return _rate(correct, len(pairs))


def date_parse_rate(values: Sequence[str | None]) -> float:
    parsed = 0
    for value in values:
        if not value:
            continue
        try:
            datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        parsed += 1
    return _rate(parsed, len(values))


def classification_metrics(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, Any]:
    pairs = list(zip(y_true, y_pred))
    labels = sorted(set(y_true) | set(y_pred))
    true_counts = Counter(y_true)
    per_category: dict[str, dict[str, float | int]] = {}
    weighted_sum = 0.0
    for label in labels:
        tp = sum(1 for truth, prediction in pairs if truth == label and prediction == label)
        fp = sum(1 for truth, prediction in pairs if truth != label and prediction == label)
        fn = sum(1 for truth, prediction in pairs if truth == label and prediction != label)
        precision = _rate(tp, tp + fp)
        recall = _rate(tp, tp + fn)
        f1 = _rate(2 * precision * recall, precision + recall) if precision + recall > 0 else 0.0
        support = true_counts[label]
        per_category[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        weighted_sum += f1 * support
    accuracy = _rate(sum(1 for truth, prediction in pairs if truth == prediction), len(pairs))
    macro_f1 = _round(sum(float(item["f1"]) for item in per_category.values()) / len(labels)) if labels else 0.0
    weighted_f1 = _round(weighted_sum / len(y_true)) if y_true else 0.0
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_category": per_category,
    }


def duplicate_detection_rate(caught: int, seeded: int) -> float | None:
    if seeded <= 0:
        return None
    return _rate(caught, seeded)


def false_positive_rate(false_positives: int, true_negatives: int) -> float | None:
    denominator = false_positives + true_negatives
    if denominator <= 0:
        return None
    return _rate(false_positives, denominator)


def confidence_calibration_buckets(
    samples: Iterable[tuple[float | None, bool]],
    bucket_size: float = 0.2,
) -> list[dict[str, float | int | str]]:
    if bucket_size <= 0 or bucket_size > 1:
        raise ValueError("bucket_size must be in the range (0, 1].")
    bucket_count = ceil(1 / bucket_size)
    grouped: list[list[tuple[float, bool]]] = [[] for _ in range(bucket_count)]
    for confidence, correct in samples:
        if confidence is None:
            continue
        clamped = min(1.0, max(0.0, float(confidence)))
        index = min(bucket_count - 1, int(clamped / bucket_size))
        grouped[index].append((clamped, bool(correct)))

    buckets: list[dict[str, float | int | str]] = []
    for index, rows in enumerate(grouped):
        if not rows:
            continue
        start = index * bucket_size
        end = min(1.0, start + bucket_size)
        avg_confidence = sum(confidence for confidence, _ in rows) / len(rows)
        accuracy = sum(1 for _, correct in rows if correct) / len(rows)
        buckets.append(
            {
                "range": f"{start:.2f}-{end:.2f}",
                "count": len(rows),
                "avg_confidence": _round(avg_confidence),
                "accuracy": _round(accuracy),
                "calibration_gap": _round(abs(avg_confidence - accuracy)),
            }
        )
    return buckets
