from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.transaction import Transaction
from backend.pipeline.analyzer import detect_anomalies
from backend.pipeline.deduplicator import check_duplicate
from backend.pipeline.kie import extract_fields
from backend.pipeline.ocr import run_ocr
from backend.pipeline.preprocess import preprocess
from backend.pipeline.structurer import extraction_to_transaction


GROUND_TRUTH_PATH = PROJECT_ROOT / "synthetic" / "ground_truth.json"
IMAGE_DIR = PROJECT_ROOT / "synthetic" / "synthetic_bill_images"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp_path = Path(str(path) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp_path, path)


def _load_ground_truth() -> dict[str, dict[str, Any]]:
    records = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    return {Path(record["file_name"]).stem: record for record in records}


def _bill_id_from_image(path: Path) -> str:
    stem = path.stem
    if stem.startswith("messy_"):
        stem = stem.removeprefix("messy_")
    return stem


def _amount_matches(left: float | None, right: float) -> bool:
    if left is None:
        return False
    return abs(float(left) - float(right)) <= max(1.0, abs(float(right)) * 0.01)


def _field_scores(predicted: Transaction, truth: dict[str, Any]) -> dict[str, bool]:
    return {
        "merchant": (predicted.merchant or "").lower() == str(truth["merchant"]).lower(),
        "date": predicted.date == truth["date"],
        "total": _amount_matches(predicted.total, float(truth["amount"])),
        "category": predicted.category == truth["category"],
    }


def _safe_pipeline(image_path: Path) -> Transaction | None:
    try:
        file_bytes = image_path.read_bytes()
        image = preprocess(file_bytes, "image/png")
        blocks = run_ocr(image)
        extraction = extract_fields(blocks)
        return extraction_to_transaction(extraction, file_bytes, image_path.name)
    except Exception:
        return None


def run_evaluation() -> dict[str, Any]:
    truth_by_id = _load_ground_truth()
    field_counts = {"merchant": 0, "date": 0, "total": 0, "category": 0}
    evaluated_fields = 0
    errors: list[str] = []
    canonical_transactions: list[tuple[Transaction, dict[str, Any]]] = []

    for image_path in sorted(IMAGE_DIR.glob("*.png")):
        bill_id = _bill_id_from_image(image_path)
        truth = truth_by_id.get(bill_id)
        if truth is None:
            continue
        transaction = _safe_pipeline(image_path)
        evaluated_fields += 1
        if transaction is None:
            errors.append(image_path.name)
            continue
        for field, matched in _field_scores(transaction, truth).items():
            if matched:
                field_counts[field] += 1
        if not image_path.name.startswith("messy_"):
            canonical_transactions.append((transaction, truth))

    field_accuracy = {
        field: round(count / evaluated_fields, 4) if evaluated_fields else 0.0
        for field, count in field_counts.items()
    }

    history: list[Transaction] = []
    anomaly_truth_total = 0
    anomaly_truth_found = 0
    duplicate_predictions = 0
    duplicate_true_predictions = 0

    for transaction, truth in canonical_transactions:
        anomaly = detect_anomalies(transaction, history)
        duplicate = check_duplicate(transaction, history)
        if truth["is_anomaly"]:
            anomaly_truth_total += 1
            if anomaly.is_anomaly:
                anomaly_truth_found += 1
        if duplicate.is_duplicate:
            duplicate_predictions += 1
            if truth["is_duplicate_of"] is not None:
                duplicate_true_predictions += 1
        history.append(transaction)

    anomaly_recall = round(anomaly_truth_found / anomaly_truth_total, 4) if anomaly_truth_total else 0.0
    duplicate_precision = round(duplicate_true_predictions / duplicate_predictions, 4) if duplicate_predictions else 1.0
    overall_extraction_f1 = round(sum(field_accuracy.values()) / len(field_accuracy), 4) if field_accuracy else 0.0

    results = {
        "field_accuracy": field_accuracy,
        "anomaly_detection_recall": anomaly_recall,
        "duplicate_detection_precision": duplicate_precision,
        "overall_extraction_f1": overall_extraction_f1,
        "counts": {
            "evaluated_images": evaluated_fields,
            "canonical_bills": len(canonical_transactions),
            "pipeline_errors": len(errors),
        },
        "targets": {
            "field_accuracy_min": 0.70,
            "anomaly_recall_min": 0.80,
            "duplicate_precision_min": 0.95,
        },
        "target_pass": {
            "merchant": field_accuracy.get("merchant", 0.0) >= 0.70,
            "date": field_accuracy.get("date", 0.0) >= 0.70,
            "total": field_accuracy.get("total", 0.0) >= 0.70,
            "category": field_accuracy.get("category", 0.0) >= 0.70,
            "anomaly_detection_recall": anomaly_recall >= 0.80,
            "duplicate_detection_precision": duplicate_precision >= 0.95,
        },
        "errors": errors,
    }
    _atomic_write_json(RESULTS_PATH, results)
    return results


def main() -> None:
    results = run_evaluation()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
