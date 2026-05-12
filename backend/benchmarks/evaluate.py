from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

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
from backend.benchmarks.ocr_deps import external_ocr_dependency_status, format_dependency_report
from backend.models.extraction import ExtractionResult
from backend.models.transaction import Transaction
from backend.pipeline.analyzer import detect_anomalies, generate_analysis
from backend.pipeline.deduplicator import check_duplicate
from backend.pipeline.kie import extract_fields, normalize_amount, normalize_date
from backend.pipeline.ocr import run_ocr
from backend.pipeline.preprocess import preprocess
from backend.pipeline.structurer import extraction_to_transaction


GROUND_TRUTH_PATH = PROJECT_ROOT / "synthetic" / "ground_truth.json"
IMAGE_DIR = PROJECT_ROOT / "synthetic" / "synthetic_bill_images"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
SROIE_DEBUG_PATH = Path(__file__).resolve().parent / "debug" / "sroie_failures.json"
SROIE_DEBUG_SAMPLE_LIMIT = 10
EVALUATED_FIELDS = ["merchant", "date", "total", "category"]
DETECTION_FIELDS = ["merchant", "date", "total", "category"]
HF_DATASET_ROWS_URL = "https://datasets-server.huggingface.co/rows"
REQUEST_TIMEOUT_SECONDS = 30

EXTERNAL_DATASETS: dict[str, dict[str, str]] = {
    "sroie": {
        "repo": "jsdnrs/ICDAR2019-SROIE",
        "dataset": "ICDAR2019-SROIE",
        "split": "test",
        "purpose": "Real receipt field extraction benchmark",
    },
    "cord": {
        "repo": "naver-clova-ix/cord-v2",
        "dataset": "CORD v2",
        "split": "test",
        "purpose": "Receipt OCR/layout robustness benchmark",
    },
    "funsd": {
        "repo": "nielsr/funsd",
        "dataset": "FUNSD",
        "split": "test",
        "purpose": "Document key-value structure stress test; not a receipt benchmark",
    },
}

DEFERRED_METRICS = {
    "correction_rate": "requires review-event logging",
    "nova_groundedness": "requires source/retrieval logging or human-labeled chat eval",
    "nova_retrieval_precision": "requires retrieval/source evaluation",
    "real_savings_validation": "requires longitudinal user data",
}


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


@dataclass(slots=True)
class ExternalSample:
    dataset_key: str
    sample_id: str
    image_bytes: bytes | None
    truth: dict[str, Any]
    reference_text: str


class ExternalDatasetUnavailable(RuntimeError):
    """Raised when an optional external benchmark cannot be loaded."""


def _external_ocr_dependency_status() -> dict[str, Any]:
    return external_ocr_dependency_status()


def _ensure_external_ocr_dependencies(allow_missing_ocr: bool) -> None:
    if allow_missing_ocr:
        return
    report = _external_ocr_dependency_status()
    if report.get("ready"):
        return
    raise ExternalDatasetUnavailable(
        "External OCR benchmark cannot run reliably because OCR dependencies are missing. "
        "Use Docker benchmark command or install Tesseract/Poppler locally.\n"
        f"{format_dependency_report(report)}"
    )


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _amount_matches(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= 1.0


def _text_matches(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return _normalize_text(left) == _normalize_text(right)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).lower().replace("\n", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _field_scores(predicted: Transaction, truth: dict[str, Any]) -> dict[str, bool]:
    return {
        "merchant": _text_matches(predicted.merchant, str(truth["merchant"])),
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


def _confidence_samples(records: list[EvaluationRecord], fields: Iterable[str] = ("merchant", "date", "total")) -> list[tuple[float | None, bool]]:
    samples: list[tuple[float | None, bool]] = []
    for record in records:
        scores = _external_field_scores(record, list(fields)) if "fields" in record.truth else _field_scores(record.transaction, record.truth)
        for field_name in fields:
            if not hasattr(record.extraction, field_name):
                continue
            field = getattr(record.extraction, field_name)
            samples.append((field.confidence, scores.get(field_name, False)))
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


def _run_synthetic_regression() -> dict[str, Any]:
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

    cer, wer, ocr_accuracy = _ocr_quality(records)

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

    return {
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
            "confidence_calibration": confidence_calibration_buckets(_confidence_samples(records, ("merchant", "date", "total"))),
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


def _ocr_quality(records: list[EvaluationRecord]) -> tuple[float | None, float | None, float | None]:
    text_records = [record for record in records if record.reference_text]
    if not text_records:
        return None, None, None
    combined_reference = "\n".join(record.reference_text for record in text_records)
    combined_ocr = "\n".join(record.ocr_text for record in text_records)
    cer = character_error_rate(combined_reference, combined_ocr)
    wer = word_error_rate(combined_reference, combined_ocr)
    ocr_accuracy = round(max(0.0, 1.0 - cer), 4)
    return cer, wer, ocr_accuracy


def _empty_external_result(dataset_key: str, limit: int, status: str = "not generated", message: str | None = None) -> dict[str, Any]:
    dataset = EXTERNAL_DATASETS[dataset_key]
    result: dict[str, Any] = {
        "available": False,
        "dataset": dataset["dataset"],
        "purpose": dataset["purpose"],
        "limit": limit,
        "metrics": {},
        "status": status,
    }
    if message:
        result["message"] = message
    return result


def _external_results_template(limit: int) -> dict[str, dict[str, Any]]:
    return {dataset_key: _empty_external_result(dataset_key, limit) for dataset_key in EXTERNAL_DATASETS}


def _sample_from_sroie_row(row: dict[str, Any], image_bytes: bytes | None = None) -> ExternalSample:
    entities = row.get("entities") or {}
    company = _clean_string(entities.get("company"))
    normalized = normalize_date(_clean_string(entities.get("date")))
    amount = normalize_amount(_clean_string(entities.get("total")))
    truth: dict[str, Any] = {
        "merchant": company,
        "date": normalized,
        "total": amount,
        "address": _clean_string(entities.get("address")),
        "fields": ["merchant", "date", "total"],
    }
    return ExternalSample(
        dataset_key="sroie",
        sample_id=str(row.get("key") or row.get("id") or "sroie-sample"),
        image_bytes=image_bytes,
        truth=truth,
        reference_text=_reference_text_from_words(row.get("words")),
    )


def _sample_from_cord_row(row: dict[str, Any], image_bytes: bytes | None = None) -> ExternalSample:
    ground_truth = row.get("ground_truth") or {}
    if isinstance(ground_truth, str):
        try:
            ground_truth = json.loads(ground_truth)
        except json.JSONDecodeError:
            ground_truth = {}
    parse = ground_truth.get("gt_parse") if isinstance(ground_truth, dict) else {}
    parse = parse if isinstance(parse, dict) else {}
    total = parse.get("total") if isinstance(parse.get("total"), dict) else {}
    subtotal = parse.get("sub_total") if isinstance(parse.get("sub_total"), dict) else {}
    fields: list[str] = []
    truth: dict[str, Any] = {"fields": fields}
    total_amount = normalize_amount(_clean_string(total.get("total_price")))
    subtotal_amount = normalize_amount(_clean_string(subtotal.get("subtotal_price")))
    tax_amount = normalize_amount(_clean_string(subtotal.get("tax_price") or total.get("tax_price")))
    if total_amount is not None:
        truth["total"] = total_amount
        fields.append("total")
    if subtotal_amount is not None:
        truth["subtotal"] = subtotal_amount
        fields.append("subtotal")
    if tax_amount is not None:
        truth["tax"] = tax_amount
        fields.append("tax")
    reference_text = _cord_reference_text(ground_truth)
    return ExternalSample(
        dataset_key="cord",
        sample_id=str(row.get("key") or row.get("id") or "cord-sample"),
        image_bytes=image_bytes,
        truth=truth,
        reference_text=reference_text,
    )


def _sample_from_funsd_row(row: dict[str, Any], image_bytes: bytes | None = None) -> ExternalSample:
    words = row.get("words") or []
    return ExternalSample(
        dataset_key="funsd",
        sample_id=str(row.get("id") or row.get("key") or "funsd-sample"),
        image_bytes=image_bytes,
        truth={"fields": []},
        reference_text=_reference_text_from_words(words),
    )


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def _reference_text_from_words(words: Any) -> str:
    if not isinstance(words, list):
        return ""
    return " ".join(str(word) for word in words if str(word).strip())


def _cord_reference_text(ground_truth: Any) -> str:
    if not isinstance(ground_truth, dict):
        return ""
    valid_lines = ground_truth.get("valid_line")
    tokens: list[str] = []
    if isinstance(valid_lines, list):
        for line in valid_lines:
            if not isinstance(line, dict):
                continue
            words = line.get("words")
            if isinstance(words, list):
                tokens.extend(str(word.get("text", "")) for word in words if isinstance(word, dict))
    if tokens:
        return " ".join(token for token in tokens if token.strip())
    return json.dumps(ground_truth.get("gt_parse", {}), sort_keys=True)


def _load_external_samples(
    dataset_key: str,
    limit: int,
    dataset_dir: Path | None = None,
    allow_download: bool = True,
) -> list[ExternalSample]:
    if dataset_key not in EXTERNAL_DATASETS:
        raise ExternalDatasetUnavailable(f"Unknown external dataset: {dataset_key}")
    if dataset_dir is not None:
        local_samples = _load_local_external_samples(dataset_key, dataset_dir, limit)
        if local_samples:
            return local_samples
        if not allow_download:
            raise ExternalDatasetUnavailable(
                f"{EXTERNAL_DATASETS[dataset_key]['dataset']} dataset not found. Provide dataset path or enable HuggingFace loading."
            )
    if not allow_download:
        raise ExternalDatasetUnavailable(
            f"{EXTERNAL_DATASETS[dataset_key]['dataset']} dataset not found. Provide dataset path or enable HuggingFace loading."
        )
    rows = _fetch_hf_rows(dataset_key, limit)
    samples: list[ExternalSample] = []
    for row in rows:
        image_bytes = _download_image_bytes(row)
        if dataset_key == "sroie":
            samples.append(_sample_from_sroie_row(row, image_bytes=image_bytes))
        elif dataset_key == "cord":
            samples.append(_sample_from_cord_row(row, image_bytes=image_bytes))
        else:
            samples.append(_sample_from_funsd_row(row, image_bytes=image_bytes))
    return samples


def _load_local_external_samples(dataset_key: str, dataset_dir: Path, limit: int) -> list[ExternalSample]:
    json_path = dataset_dir / f"{dataset_key}.json"
    jsonl_path = dataset_dir / f"{dataset_key}.jsonl"
    rows: list[dict[str, Any]] = []
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
    elif jsonl_path.exists():
        rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        return []
    samples: list[ExternalSample] = []
    for row in rows[:limit]:
        image_bytes = _local_image_bytes(row, dataset_dir)
        if dataset_key == "sroie":
            samples.append(_sample_from_sroie_row(row, image_bytes=image_bytes))
        elif dataset_key == "cord":
            samples.append(_sample_from_cord_row(row, image_bytes=image_bytes))
        else:
            samples.append(_sample_from_funsd_row(row, image_bytes=image_bytes))
    return samples


def _local_image_bytes(row: dict[str, Any], dataset_dir: Path) -> bytes | None:
    image_path = row.get("image_path") or row.get("image")
    if isinstance(image_path, dict):
        image_path = image_path.get("path")
    if not image_path:
        return None
    path = Path(str(image_path))
    if not path.is_absolute():
        path = dataset_dir / path
    try:
        return path.read_bytes()
    except OSError:
        return None


def _fetch_hf_rows(dataset_key: str, limit: int) -> list[dict[str, Any]]:
    meta = EXTERNAL_DATASETS[dataset_key]
    response = requests.get(
        HF_DATASET_ROWS_URL,
        params={
            "dataset": meta["repo"],
            "config": "default",
            "split": meta["split"],
            "offset": 0,
            "length": max(1, min(limit, 100)),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return [item.get("row", {}) for item in payload.get("rows", [])]


def _download_image_bytes(row: dict[str, Any]) -> bytes | None:
    image = row.get("image")
    if not isinstance(image, dict):
        return None
    src = image.get("src")
    if not src:
        return None
    try:
        response = requests.get(str(src), timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return None
    return response.content


def _safe_external_pipeline(sample: ExternalSample) -> EvaluationRecord | None:
    if not sample.image_bytes:
        return None
    started = time.perf_counter()
    try:
        image = preprocess(sample.image_bytes, "image/png")
        blocks = run_ocr(image)
        ocr_text = _ocr_text(blocks)
        extraction = extract_fields(blocks)
        transaction = _transaction_from_external_extraction(extraction, sample)
        return EvaluationRecord(
            image_name=f"{sample.dataset_key}-{sample.sample_id}",
            bill_id=sample.sample_id,
            transaction=transaction,
            extraction=extraction,
            truth=sample.truth,
            ocr_text=ocr_text,
            reference_text=sample.reference_text,
            pipeline_seconds=time.perf_counter() - started,
        )
    except Exception:
        return None


def _transaction_from_external_extraction(extraction: ExtractionResult, sample: ExternalSample) -> Transaction:
    total = extraction.total.value if extraction.total.value is not None else 0.0
    return Transaction(
        merchant=extraction.merchant.value,
        date=extraction.date.value,
        items=extraction.items.value or [],
        subtotal=extraction.subtotal.value,
        tax=extraction.tax.value,
        total=float(total),
        category="Uncategorized",
        payment_method=extraction.payment_method.value,
        bill_number=extraction.bill_number.value,
        file_name=f"{sample.dataset_key}-{sample.sample_id}",
        raw_ocr_text=extraction.raw_ocr_text,
    )


def _evaluate_external_dataset(dataset_key: str, samples: list[ExternalSample], limit: int) -> dict[str, Any]:
    records: list[EvaluationRecord] = []
    debug_entries: list[dict[str, Any]] = []
    skipped = 0
    failed = 0
    for sample in samples[:limit]:
        if not sample.image_bytes:
            skipped += 1
            if dataset_key == "sroie" and len(debug_entries) < SROIE_DEBUG_SAMPLE_LIMIT:
                debug_entries.append(_sroie_debug_entry(sample, None, "missing_image_bytes"))
            continue
        record = _safe_external_pipeline(sample)
        if record is None:
            failed += 1
            if dataset_key == "sroie" and len(debug_entries) < SROIE_DEBUG_SAMPLE_LIMIT:
                debug_entries.append(_sroie_debug_entry(sample, None, "pipeline_failed"))
            continue
        records.append(record)
        if dataset_key == "sroie" and len(debug_entries) < SROIE_DEBUG_SAMPLE_LIMIT:
            debug_entries.append(_sroie_debug_entry(sample, record))
    if dataset_key == "sroie":
        _write_sroie_debug_report(debug_entries, limit=limit, processed=len(records), skipped=skipped, failed=failed)
    if not records:
        return _empty_external_result(
            dataset_key,
            limit,
            status="no evaluable samples",
            message="External samples were unavailable, skipped, or failed during OCR/KIE.",
        )

    metrics = _external_metrics(dataset_key, records, skipped=skipped, failed=failed)
    return {
        "available": True,
        "dataset": EXTERNAL_DATASETS[dataset_key]["dataset"],
        "purpose": EXTERNAL_DATASETS[dataset_key]["purpose"],
        "limit": limit,
        "metrics": metrics,
        "status": "generated",
    }


def _write_sroie_debug_report(
    samples: list[dict[str, Any]],
    *,
    limit: int,
    processed: int,
    skipped: int,
    failed: int,
) -> None:
    report = {
        "dataset": "sroie",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "debug_sample_limit": SROIE_DEBUG_SAMPLE_LIMIT,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "samples": samples,
    }
    _atomic_write_json(SROIE_DEBUG_PATH, report)


def _sroie_debug_entry(sample: ExternalSample, record: EvaluationRecord | None, failure_reason: str | None = None) -> dict[str, Any]:
    field_results = _sroie_field_debug_results(record) if record is not None else _sroie_missing_field_results(failure_reason)
    diagnosis = _sroie_diagnosis(record, field_results, failure_reason)
    return {
        "sample_id": sample.sample_id,
        "ground_truth": {
            "company": sample.truth.get("merchant"),
            "date": sample.truth.get("date"),
            "total": sample.truth.get("total"),
        },
        "raw_ocr_text": record.ocr_text if record is not None else "",
        "ocr_lines": record.ocr_text.splitlines() if record is not None else [],
        "predicted": {
            "merchant": record.transaction.merchant if record is not None else None,
            "date": record.transaction.date if record is not None else None,
            "total": record.transaction.total if record is not None else None,
        },
        "normalized_ground_truth": _sroie_normalized_values(sample.truth),
        "normalized_prediction": _sroie_normalized_prediction(record),
        "field_results": field_results,
        "diagnosis": diagnosis,
    }


def _sroie_normalized_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "merchant": _normalize_text(values.get("merchant")),
        "date": normalize_date(str(values.get("date"))) if values.get("date") else None,
        "total": normalize_amount(str(values.get("total"))) if values.get("total") is not None else None,
    }


def _sroie_normalized_prediction(record: EvaluationRecord | None) -> dict[str, Any]:
    if record is None:
        return {"merchant": "", "date": None, "total": None}
    return {
        "merchant": _normalize_text(record.transaction.merchant),
        "date": normalize_date(str(record.transaction.date)) if record.transaction.date else None,
        "total": normalize_amount(str(record.transaction.total)) if record.transaction.total is not None else None,
    }


def _sroie_missing_field_results(reason: str | None) -> dict[str, dict[str, Any]]:
    return {
        field: {
            "passed": False,
            "failure_reason": reason or "pipeline_failed",
        }
        for field in ("merchant", "date", "total")
    }


def _sroie_field_debug_results(record: EvaluationRecord) -> dict[str, dict[str, Any]]:
    scores = _external_field_scores(record, ["merchant", "date", "total"])
    reasons = {
        "merchant": _field_failure_reason(record.transaction.merchant, record.truth.get("merchant"), "merchant", scores["merchant"]),
        "date": _field_failure_reason(record.transaction.date, record.truth.get("date"), "date", scores["date"]),
        "total": _field_failure_reason(record.transaction.total, record.truth.get("total"), "total", scores["total"]),
    }
    return {
        field: {
            "passed": bool(scores[field]),
            "failure_reason": None if scores[field] else reasons[field],
        }
        for field in ("merchant", "date", "total")
    }


def _field_failure_reason(prediction: Any, truth: Any, field_name: str, passed: bool) -> str | None:
    if passed:
        return None
    if prediction is None or str(prediction).strip() == "":
        return "missing_prediction"
    if field_name == "total" and float(prediction or 0.0) == 0.0:
        return "missing_or_zero_prediction"
    if truth is None or str(truth).strip() == "":
        return "missing_ground_truth"
    return "value_mismatch"


def _sroie_diagnosis(
    record: EvaluationRecord | None,
    field_results: dict[str, dict[str, Any]],
    failure_reason: str | None,
) -> list[str]:
    if record is None:
        return [failure_reason or "pipeline_failed"]
    reasons: list[str] = []
    if not record.ocr_text.strip():
        reasons.append("ocr_empty")
    for field_name, result in field_results.items():
        if result["passed"]:
            continue
        reason = str(result.get("failure_reason") or "value_mismatch")
        if field_name == "total" and reason == "missing_or_zero_prediction":
            reasons.append("total_missing_or_zero_prediction")
        else:
            reasons.append(f"{field_name}_{reason}")
    return reasons


def _external_metrics(dataset_key: str, records: list[EvaluationRecord], skipped: int, failed: int) -> dict[str, Any]:
    field_names = _external_fields(records, dataset_key)
    comparisons = [_external_field_scores(record, field_names) for record in records]
    field_accuracy_result = compute_field_accuracy(comparisons, field_names) if field_names else {"overall": None, "by_field": {}}
    detection_checks = [{field_name: _external_field_detected(record, field_name) for field_name in field_names} for record in records]
    detection_result = compute_field_accuracy(detection_checks, field_names) if field_names else {"overall": None, "by_field": {}}
    cer, wer, ocr_accuracy = _ocr_quality(records)
    pipeline_times = [record.pipeline_seconds for record in records]
    metrics: dict[str, Any] = {
        "field_extraction_accuracy": field_accuracy_result["overall"],
        "field_accuracy_by_field": field_accuracy_result["by_field"],
        "field_detection_rate": detection_result["overall"],
        "field_detection_by_field": detection_result["by_field"],
        "cer": cer,
        "wer": wer,
        "ocr_accuracy": ocr_accuracy,
        "avg_pipeline_time_seconds": _mean(pipeline_times),
        "max_pipeline_time_seconds": round(max(pipeline_times), 4) if pipeline_times else None,
        "samples_processed": len(records),
        "samples_failed": failed,
        "samples_skipped": skipped,
        "confidence_calibration": confidence_calibration_buckets(_confidence_samples(records, tuple(field_names))),
    }
    if "merchant" in field_names:
        metrics["merchant_accuracy"] = field_accuracy_result["by_field"].get("merchant")
    if "date" in field_names:
        metrics["date_accuracy"] = field_accuracy_result["by_field"].get("date")
        metrics["date_parse_rate"] = date_parse_rate([record.transaction.date for record in records])
    if "total" in field_names:
        metrics["total_amount_accuracy_within_1"] = amount_accuracy_within_tolerance(
            [record.transaction.total for record in records],
            [record.truth.get("total") for record in records],
            tolerance=1.0,
        )
    if dataset_key == "cord":
        metrics["scope_note"] = "CORD metrics focus on receipt OCR/layout and totals where labels map cleanly to FinSight fields."
    if dataset_key == "funsd":
        metrics["scope_note"] = "FUNSD is a document-structure stress test, not a receipt accuracy benchmark."
        metrics["key_value_pairing_rate"] = None
        metrics["key_value_pairing_status"] = "requires a dedicated form-understanding evaluator"
    return metrics


def _external_fields(records: list[EvaluationRecord], dataset_key: str) -> list[str]:
    if dataset_key == "funsd":
        return []
    ordered_fields = ["merchant", "date", "total", "subtotal", "tax"]
    present = {field for record in records for field in record.truth.get("fields", [])}
    return [field for field in ordered_fields if field in present]


def _external_field_scores(record: EvaluationRecord, fields: list[str]) -> dict[str, bool]:
    scores: dict[str, bool] = {}
    for field_name in fields:
        truth_value = record.truth.get(field_name)
        if field_name == "merchant":
            scores[field_name] = _text_matches(record.transaction.merchant, truth_value)
        elif field_name == "date":
            scores[field_name] = record.transaction.date == truth_value
        elif field_name in {"total", "subtotal", "tax"}:
            prediction = getattr(record.transaction, field_name)
            scores[field_name] = _amount_matches(prediction, truth_value)
        else:
            scores[field_name] = False
    return scores


def _external_field_detected(record: EvaluationRecord, field_name: str) -> bool:
    if not hasattr(record.extraction, field_name):
        return False
    field = getattr(record.extraction, field_name)
    value = field.value
    if field_name in {"total", "subtotal", "tax"} and float(value or 0.0) == 0.0:
        return False
    return value is not None


def _run_external_benchmarks(
    external: str | None,
    limit: int,
    dataset_dir: Path | None,
    allow_download: bool,
    allow_missing_ocr: bool,
) -> dict[str, dict[str, Any]]:
    external_results = _external_results_template(limit)
    if external is None:
        return external_results
    _ensure_external_ocr_dependencies(allow_missing_ocr)
    dataset_keys = list(EXTERNAL_DATASETS) if external == "all" else [external]
    for dataset_key in dataset_keys:
        try:
            samples = _load_external_samples(dataset_key, limit=limit, dataset_dir=dataset_dir, allow_download=allow_download)
            external_results[dataset_key] = _evaluate_external_dataset(dataset_key, samples, limit)
        except Exception as exc:
            external_results[dataset_key] = _empty_external_result(
                dataset_key,
                limit,
                status="unavailable",
                message=str(exc),
            )
    return external_results


def _synthetic_section(include_synthetic: bool) -> dict[str, Any]:
    if not include_synthetic:
        return {
            "available": False,
            "dataset": "FinSight generated synthetic bills",
            "purpose": "Internal regression check only",
            "metrics": {},
            "status": "not generated",
        }
    return {
        "available": True,
        "dataset": "FinSight generated synthetic bills",
        "purpose": "Internal regression check only",
        "notice": "Synthetic regression check with generated bills. These scores validate controlled pipeline consistency, not real-world accuracy.",
        "metrics": _run_synthetic_regression(),
    }


def run_evaluation(
    *,
    include_synthetic: bool = True,
    external: str | None = None,
    limit: int = 25,
    dataset_dir: Path | None = None,
    allow_download: bool = True,
    allow_missing_ocr: bool = False,
) -> dict[str, Any]:
    if external not in {None, "sroie", "cord", "funsd", "all"}:
        raise ValueError("external must be one of: sroie, cord, funsd, all")
    synthetic_regression = _synthetic_section(include_synthetic)
    external_benchmarks = _run_external_benchmarks(external, limit, dataset_dir, allow_download, allow_missing_ocr)
    external_available = any(result.get("available") is True for result in external_benchmarks.values())
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "headline_source": "external",
            "external_available": external_available,
            "synthetic_regression_available": synthetic_regression["available"],
        },
        "synthetic_regression": synthetic_regression,
        "external_benchmarks": external_benchmarks,
        "deferred_metrics": DEFERRED_METRICS,
    }
    _atomic_write_json(RESULTS_PATH, results)
    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FinSight synthetic and optional external benchmark evaluation.")
    parser.add_argument("--synthetic", action="store_true", help="Run the FinSight generated-bill regression benchmark.")
    parser.add_argument("--skip-synthetic", action="store_true", help="Skip the generated-bill regression benchmark.")
    parser.add_argument("--external", choices=["sroie", "cord", "funsd", "all"], default=None, help="Run an optional external dataset benchmark.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum external samples to evaluate.")
    parser.add_argument("--dataset-dir", type=Path, default=None, help="Optional local directory containing <dataset>.json or <dataset>.jsonl rows.")
    parser.add_argument("--no-download", action="store_true", help="Do not call Hugging Face Dataset Viewer or download images.")
    parser.add_argument(
        "--allow-missing-ocr",
        action="store_true",
        help="Debug only: run external benchmarks even if local OCR system dependencies are missing.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    include_synthetic = not args.skip_synthetic
    if args.synthetic:
        include_synthetic = True
    try:
        results = run_evaluation(
            include_synthetic=include_synthetic,
            external=args.external,
            limit=max(1, args.limit),
            dataset_dir=args.dataset_dir,
            allow_download=not args.no_download,
            allow_missing_ocr=args.allow_missing_ocr,
        )
    except ExternalDatasetUnavailable as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
