from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.benchmarks.metrics import (
    amount_accuracy_within_tolerance,
    character_error_rate,
    classification_metrics,
    confidence_calibration_buckets,
    date_parse_rate,
    duplicate_detection_rate,
    false_positive_rate,
    field_accuracy as compute_field_accuracy,
    word_error_rate,
)
from backend.models.extraction import ExtractionResult
from backend.models.transaction import Transaction
from backend.pipeline.analyzer import detect_anomalies, generate_analysis
from backend.pipeline.deduplicator import check_duplicate
from backend.pipeline.kie import extract_fields
from backend.pipeline.ocr import run_ocr
from backend.pipeline.preprocess import preprocess
from backend.pipeline.structurer import extraction_to_transaction


GROUND_TRUTH_PATH = PROJECT_ROOT / "synthetic" / "ground_truth.json"
IMAGE_DIR = PROJECT_ROOT / "synthetic" / "synthetic_bill_images"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
EVALUATED_FIELDS = ["merchant", "date", "total", "category"]
DETECTION_FIELDS = ["merchant", "date", "total", "category"]


@dataclass(slots=True)
class EvaluationRecord:
    image_name: str
    bill_id: str
    transaction: Transaction
    extraction: ExtractionResult
    truth: dict[str, Any]
    ocr_text: str
    reference_text: str
    pipeline_seconds: float


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp_path = Path(str(path) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
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
    return abs(float(left) - float(right)) <= 1.0


def _field_scores(predicted: Transaction, truth: dict[str, Any]) -> dict[str, bool]:
    return {
        "merchant": (predicted.merchant or "").lower() == str(truth["merchant"]).lower(),
        "date": predicted.date == truth["date"],
        "total": _amount_matches(predicted.total, float(truth["amount"])),
        "category": predicted.category == truth["category"],
    }


def _ocr_text(blocks: list[Any]) -> str:
    return "\n".join(str(block.text) for block in blocks)


def _safe_pipeline(image_path: Path, truth: dict[str, Any]) -> EvaluationRecord | None:
    started = time.perf_counter()
    try:
        file_bytes = image_path.read_bytes()
        image = preprocess(file_bytes, "image/png")
        reference_text = str(image.info.get("finsight_ocr_text", ""))
        blocks = run_ocr(image)
        ocr_text = _ocr_text(blocks)
        extraction = extract_fields(blocks)
        transaction = extraction_to_transaction(extraction, file_bytes, image_path.name)
        return EvaluationRecord(
            image_name=image_path.name,
            bill_id=_bill_id_from_image(image_path),
            transaction=transaction,
            extraction=extraction,
            truth=truth,
            ocr_text=ocr_text,
            reference_text=reference_text,
            pipeline_seconds=time.perf_counter() - started,
        )
    except Exception:
        return None


def _field_detection(record: EvaluationRecord, field_name: str) -> bool:
    if field_name == "category":
        return bool(record.transaction.category)
    field = getattr(record.extraction, field_name)
    value = field.value
    return value is not None and str(value).strip() != ""


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _confidence_samples(records: list[EvaluationRecord]) -> list[tuple[float | None, bool]]:
    samples: list[tuple[float | None, bool]] = []
    for record in records:
        scores = _field_scores(record.transaction, record.truth)
        for field_name in ["merchant", "date", "total"]:
            field = getattr(record.extraction, field_name)
            samples.append((field.confidence, scores[field_name]))
    return samples


def _legacy_target_pass(field_accuracy: dict[str, float], anomaly_recall: float, duplicate_precision: float) -> dict[str, bool]:
    return {
        "merchant": field_accuracy.get("merchant", 0.0) >= 0.70,
        "date": field_accuracy.get("date", 0.0) >= 0.70,
        "total": field_accuracy.get("total", 0.0) >= 0.70,
        "category": field_accuracy.get("category", 0.0) >= 0.70,
        "anomaly_detection_recall": anomaly_recall >= 0.80,
        "duplicate_detection_precision": duplicate_precision >= 0.95,
    }


def run_evaluation() -> dict[str, Any]:
    truth_by_id = _load_ground_truth()
    errors: list[str] = []
    records: list[EvaluationRecord] = []
    canonical_records: list[EvaluationRecord] = []

    for image_path in sorted(IMAGE_DIR.glob("*.png")):
        bill_id = _bill_id_from_image(image_path)
        truth = truth_by_id.get(bill_id)
        if truth is None:
            continue
        record = _safe_pipeline(image_path, truth)
        if record is None:
            errors.append(image_path.name)
            continue
        records.append(record)
        if not image_path.name.startswith("messy_"):
            canonical_records.append(record)

    comparisons = [_field_scores(record.transaction, record.truth) for record in records]
    field_accuracy_result = compute_field_accuracy(comparisons, EVALUATED_FIELDS)
    field_accuracy = field_accuracy_result["by_field"]
    field_accuracy_overall = field_accuracy_result["overall"]

    amount_accuracy = amount_accuracy_within_tolerance(
        [record.transaction.total for record in records],
        [float(record.truth["amount"]) for record in records],
        tolerance=1.0,
    )
    parsed_date_rate = date_parse_rate([record.transaction.date for record in records])
    detection_checks = [
        {field_name: _field_detection(record, field_name) for field_name in DETECTION_FIELDS}
        for record in records
    ]
    detection_result = compute_field_accuracy(detection_checks, DETECTION_FIELDS)
    field_detection_rate = detection_result["overall"]

    text_records = [record for record in records if record.reference_text]
    combined_reference = "\n".join(record.reference_text for record in text_records)
    combined_ocr = "\n".join(record.ocr_text for record in text_records)
    cer = character_error_rate(combined_reference, combined_ocr) if text_records else None
    wer = word_error_rate(combined_reference, combined_ocr) if text_records else None
    ocr_accuracy = round(max(0.0, 1.0 - cer), 4) if cer is not None else None

    category_metrics = classification_metrics(
        [str(record.truth["category"]) for record in records],
        [str(record.transaction.category) for record in records],
    )

    history: list[Transaction] = []
    anomaly_truth_total = 0
    anomaly_truth_found = 0
    anomaly_false_positives = 0
    anomaly_true_negatives = 0
    anomalies_detected = 0
    duplicate_seeded = 0
    duplicate_seeded_caught = 0
    duplicate_predictions = 0
    duplicate_true_predictions = 0

    for record in canonical_records:
        transaction = record.transaction
        truth = record.truth
        anomaly = detect_anomalies(transaction, history)
        duplicate = check_duplicate(transaction, history)
        if truth["is_anomaly"]:
            anomaly_truth_total += 1
            if anomaly.is_anomaly:
                anomaly_truth_found += 1
        elif anomaly.is_anomaly:
            anomaly_false_positives += 1
        else:
            anomaly_true_negatives += 1
        if anomaly.is_anomaly:
            anomalies_detected += 1
        if truth["is_duplicate_of"] is not None:
            duplicate_seeded += 1
            if duplicate.is_duplicate:
                duplicate_seeded_caught += 1
        if duplicate.is_duplicate:
            duplicate_predictions += 1
            if truth["is_duplicate_of"] is not None:
                duplicate_true_predictions += 1
        history.append(transaction)

    anomaly_recall = round(anomaly_truth_found / anomaly_truth_total, 4) if anomaly_truth_total else 0.0
    duplicate_precision = round(duplicate_true_predictions / duplicate_predictions, 4) if duplicate_predictions else 1.0
    duplicate_rate = duplicate_detection_rate(duplicate_seeded_caught, duplicate_seeded)
    anomaly_fpr = false_positive_rate(anomaly_false_positives, anomaly_true_negatives)
    overall_extraction_f1 = round(sum(field_accuracy.values()) / len(field_accuracy), 4) if field_accuracy else 0.0
    canonical_transactions = [record.transaction for record in canonical_records]
    analysis = generate_analysis(canonical_transactions)
    pipeline_times = [record.pipeline_seconds for record in records]

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "synthetic",
        "summary": {
            "ocr_accuracy": ocr_accuracy,
            "field_extraction_accuracy": field_accuracy_overall,
            "categorization_f1": category_metrics["macro_f1"],
            "duplicate_detection_rate": duplicate_rate,
            "anomaly_recall": anomaly_recall,
            "avg_pipeline_time_seconds": _mean(pipeline_times),
            "bills_processed": len(records),
        },
        "ocr": {
            "cer": cer,
            "wer": wer,
            "field_detection_rate": field_detection_rate,
            "ocr_accuracy": ocr_accuracy,
        },
        "extraction": {
            "field_accuracy_overall": field_accuracy_overall,
            "field_accuracy_by_field": {
                "merchant": field_accuracy.get("merchant", 0.0),
                "date": field_accuracy.get("date", 0.0),
                "amount": field_accuracy.get("total", 0.0),
                "category": field_accuracy.get("category", 0.0),
            },
            "amount_accuracy_within_1_inr": amount_accuracy,
            "date_parse_rate": parsed_date_rate,
            "extraction_f1": overall_extraction_f1,
        },
        "categorization": {
            **category_metrics,
            "headline_f1": category_metrics["macro_f1"],
            "target_f1_min": 0.85,
            "target_pass": float(category_metrics["macro_f1"]) >= 0.85,
        },
        "duplicates_anomalies": {
            "duplicate_precision": duplicate_precision,
            "duplicate_detection_rate": duplicate_rate,
            "duplicates_seeded": duplicate_seeded,
            "duplicates_caught": duplicate_seeded_caught,
            "anomaly_recall": anomaly_recall,
            "anomalies_seeded": anomaly_truth_total,
            "anomalies_detected": anomalies_detected,
            "false_positive_rate": anomaly_fpr,
        },
        "self_correction": {
            "correction_rate": None,
            "false_positive_rate": anomaly_fpr,
            "duplicate_detection_rate": duplicate_rate,
            "confidence_calibration": confidence_calibration_buckets(_confidence_samples(records)),
            "status": "correction_rate requires review-event logging",
        },
        "pipeline": {
            "avg_pipeline_time_seconds": _mean(pipeline_times),
            "max_pipeline_time_seconds": round(max(pipeline_times), 4) if pipeline_times else None,
            "bills_processed": len(records),
            "pipeline_errors": len(errors),
        },
        "product": {
            "savings_identified": analysis.savings_opportunity,
            "anomalies_detected": anomalies_detected,
            "chatbot_relevance": None,
            "status": "chatbot relevance requires human review or persisted chat evaluation labels",
        },
        "chatbot": {
            "mode": "offline/documented",
            "retrieval_precision": None,
            "groundedness": None,
            "response_latency_target_seconds": 5,
            "user_query_success_rate": None,
            "status": "requires source logging or mocked chat evaluation cases; no live LLM calls in CI",
        },
        "field_accuracy": field_accuracy,
        "anomaly_detection_recall": anomaly_recall,
        "duplicate_detection_precision": duplicate_precision,
        "overall_extraction_f1": overall_extraction_f1,
        "counts": {
            "evaluated_images": len(records),
            "canonical_bills": len(canonical_records),
            "pipeline_errors": len(errors),
        },
        "targets": {
            "field_accuracy_min": 0.70,
            "anomaly_recall_min": 0.80,
            "duplicate_precision_min": 0.95,
        },
        "target_pass": _legacy_target_pass(field_accuracy, anomaly_recall, duplicate_precision),
        "errors": errors,
    }
    _atomic_write_json(RESULTS_PATH, results)
    return results


def main() -> None:
    results = run_evaluation()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
