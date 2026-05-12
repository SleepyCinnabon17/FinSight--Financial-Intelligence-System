from __future__ import annotations

import json
from pathlib import Path

from backend.benchmarks import evaluate
from backend.models.extraction import ExtractedField, ExtractionResult
from backend.models.transaction import Transaction


def _extraction() -> ExtractionResult:
    return ExtractionResult(
        merchant=ExtractedField("Demo Store", 0.95, "Demo Store"),
        date=ExtractedField("2026-05-12", 0.95, "2026-05-12"),
        items=ExtractedField([], 1.0, ""),
        subtotal=ExtractedField(9.0, 0.9, "9.00"),
        tax=ExtractedField(1.0, 0.9, "1.00"),
        total=ExtractedField(10.0, 0.95, "10.00"),
        payment_method=ExtractedField("UPI", 0.95, "UPI"),
        bill_number=ExtractedField("INV-1", 0.95, "INV-1"),
        extraction_model="test",
        ocr_engine="test",
        raw_ocr_text="Demo Store",
    )


def test_run_evaluation_writes_frontend_ready_kpi_shape(monkeypatch, tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "BILL-0001.png"
    image_path.write_bytes(b"not-a-real-image")
    results_path = tmp_path / "results.json"
    truth = {
        "BILL-0001": {
            "merchant": "Demo Store",
            "date": "2026-05-12",
            "amount": 10.0,
            "category": "Food",
            "is_anomaly": False,
            "is_duplicate_of": None,
        }
    }

    def fake_pipeline(path: Path, record_truth: dict[str, object]) -> evaluate.EvaluationRecord:
        extraction = _extraction()
        transaction = Transaction(
            merchant="Demo Store",
            date="2026-05-12",
            items=[],
            subtotal=9.0,
            tax=1.0,
            total=10.0,
            category="Food",
            payment_method="UPI",
            bill_number="INV-1",
            file_name=path.name,
            raw_ocr_text="Demo Store",
        )
        return evaluate.EvaluationRecord(
            image_name=path.name,
            bill_id="BILL-0001",
            transaction=transaction,
            extraction=extraction,
            truth=record_truth,
            ocr_text="Demo Store",
            reference_text="Demo Store",
            pipeline_seconds=0.25,
        )

    monkeypatch.setattr(evaluate, "IMAGE_DIR", image_dir)
    monkeypatch.setattr(evaluate, "RESULTS_PATH", results_path)
    monkeypatch.setattr(evaluate, "_load_ground_truth", lambda: truth)
    monkeypatch.setattr(evaluate, "_safe_pipeline", fake_pipeline)

    result = evaluate.run_evaluation()

    assert result["summary"] == {
        "headline_source": "external",
        "external_available": False,
        "synthetic_regression_available": True,
    }
    assert result["synthetic_regression"]["purpose"] == "Internal regression check only"
    synthetic_metrics = result["synthetic_regression"]["metrics"]
    assert synthetic_metrics["summary"]["ocr_accuracy"] == 1.0
    assert synthetic_metrics["summary"]["field_extraction_accuracy"] == 1.0
    assert synthetic_metrics["summary"]["categorization_f1"] == 1.0
    assert synthetic_metrics["ocr"]["cer"] == 0.0
    assert synthetic_metrics["extraction"]["amount_accuracy_within_1_inr"] == 1.0
    assert result["external_benchmarks"]["sroie"]["available"] is False
    assert result["external_benchmarks"]["cord"]["available"] is False
    assert result["external_benchmarks"]["funsd"]["available"] is False
    assert result["deferred_metrics"]["correction_rate"] == "requires review-event logging"
    assert json.loads(results_path.read_text(encoding="utf-8"))["summary"] == result["summary"]


def test_sroie_row_maps_company_date_total_and_keeps_address_optional() -> None:
    row = {
        "key": "X0001",
        "entities": {
            "company": "OJC MARKETING SDN BHD",
            "date": "15/01/2019",
            "address": "NO 2 JALAN BAYU",
            "total": "193.00",
        },
        "words": ["OJC", "MARKETING", "TOTAL", "193.00"],
    }

    sample = evaluate._sample_from_sroie_row(row)

    assert sample.sample_id == "X0001"
    assert sample.truth["merchant"] == "OJC MARKETING SDN BHD"
    assert sample.truth["date"] == "2019-01-15"
    assert sample.truth["total"] == 193.0
    assert sample.truth["address"] == "NO 2 JALAN BAYU"
    assert sample.truth["fields"] == ["merchant", "date", "total"]
    assert sample.reference_text == "OJC MARKETING TOTAL 193.00"


def test_sroie_debug_report_records_field_failures(monkeypatch, tmp_path: Path) -> None:
    sample = evaluate.ExternalSample(
        dataset_key="sroie",
        sample_id="SROIE-1",
        image_bytes=b"image-bytes",
        truth={
            "merchant": "CROSS CHANNEL NETWORK SDN. BHD.",
            "date": "2017-12-31",
            "total": 7.95,
            "fields": ["merchant", "date", "total"],
        },
        reference_text="CROSS CHANNEL NETWORK SDN. BHD. TOTAL 7.95",
    )
    extraction = ExtractionResult(
        merchant=ExtractedField("CROSS CHANNEL NETWORK SDN BHD", 0.95, "CROSS CHANNEL NETWORK SDN BHD"),
        date=ExtractedField(None, 0.0, ""),
        items=ExtractedField([], 0.0, ""),
        subtotal=ExtractedField(None, 0.0, ""),
        tax=ExtractedField(None, 0.0, ""),
        total=ExtractedField(0.0, 0.65, ""),
        payment_method=ExtractedField(None, 0.0, ""),
        bill_number=ExtractedField(None, 0.0, ""),
        extraction_model="test",
        ocr_engine="test",
        raw_ocr_text="CROSS CHANNEL NETWORK SDN BHD",
    )
    transaction = Transaction(
        merchant="CROSS CHANNEL NETWORK SDN BHD",
        date=None,
        items=[],
        subtotal=None,
        tax=None,
        total=0.0,
        category="Uncategorized",
        file_name="sroie-1.png",
        raw_ocr_text="CROSS CHANNEL NETWORK SDN BHD",
    )

    def fake_pipeline(external_sample: evaluate.ExternalSample) -> evaluate.EvaluationRecord:
        return evaluate.EvaluationRecord(
            image_name="sroie-1.png",
            bill_id=external_sample.sample_id,
            transaction=transaction,
            extraction=extraction,
            truth=external_sample.truth,
            ocr_text="CROSS CHANNEL NETWORK SDN BHD",
            reference_text=external_sample.reference_text,
            pipeline_seconds=0.25,
        )

    debug_path = tmp_path / "sroie_failures.json"
    monkeypatch.setattr(evaluate, "_load_external_samples", lambda *_args, **_kwargs: [sample])
    monkeypatch.setattr(evaluate, "_safe_external_pipeline", fake_pipeline)
    monkeypatch.setattr(evaluate, "RESULTS_PATH", tmp_path / "results.json")
    monkeypatch.setattr(evaluate, "SROIE_DEBUG_PATH", debug_path)

    evaluate.run_evaluation(include_synthetic=False, external="sroie", limit=1)

    report = json.loads(debug_path.read_text(encoding="utf-8"))
    assert report["dataset"] == "sroie"
    assert report["samples"][0]["sample_id"] == "SROIE-1"
    assert report["samples"][0]["ground_truth"]["company"] == "CROSS CHANNEL NETWORK SDN. BHD."
    assert report["samples"][0]["predicted"]["merchant"] == "CROSS CHANNEL NETWORK SDN BHD"
    assert report["samples"][0]["field_results"]["merchant"]["passed"] is True
    assert report["samples"][0]["field_results"]["date"]["failure_reason"] == "missing_prediction"
    assert report["samples"][0]["diagnosis"] == ["date_missing_prediction", "total_missing_or_zero_prediction"]


def test_external_sroie_metrics_are_separate_from_synthetic(monkeypatch, tmp_path: Path) -> None:
    sample = evaluate.ExternalSample(
        dataset_key="sroie",
        sample_id="S1",
        image_bytes=b"image-bytes",
        truth={
            "merchant": "Demo Store",
            "date": "2026-05-12",
            "total": 10.0,
            "fields": ["merchant", "date", "total"],
        },
        reference_text="Demo Store Total 10.00",
    )
    extraction = _extraction()
    transaction = Transaction(
        merchant="Demo Store",
        date="2026-05-12",
        items=[],
        subtotal=9.0,
        tax=1.0,
        total=10.0,
        category="Uncategorized",
        file_name="s1.png",
        raw_ocr_text="Demo Store Total 10.00",
    )

    def fake_pipeline(external_sample: evaluate.ExternalSample) -> evaluate.EvaluationRecord:
        return evaluate.EvaluationRecord(
            image_name="s1.png",
            bill_id=external_sample.sample_id,
            transaction=transaction,
            extraction=extraction,
            truth=external_sample.truth,
            ocr_text="Demo Store Total 10.00",
            reference_text=external_sample.reference_text,
            pipeline_seconds=0.5,
        )

    monkeypatch.setattr(evaluate, "_load_external_samples", lambda *_args, **_kwargs: [sample])
    monkeypatch.setattr(evaluate, "_safe_external_pipeline", fake_pipeline)
    monkeypatch.setattr(evaluate, "RESULTS_PATH", tmp_path / "external-results.json")
    monkeypatch.setattr(evaluate, "SROIE_DEBUG_PATH", tmp_path / "sroie-debug.json")

    result = evaluate.run_evaluation(include_synthetic=False, external="sroie", limit=1)

    assert result["summary"]["external_available"] is True
    assert result["synthetic_regression"]["available"] is False
    sroie = result["external_benchmarks"]["sroie"]
    assert sroie["available"] is True
    assert sroie["purpose"] == "Real receipt field extraction benchmark"
    assert sroie["metrics"]["merchant_accuracy"] == 1.0
    assert sroie["metrics"]["total_amount_accuracy_within_1"] == 1.0
    assert "synthetic" not in sroie["purpose"].lower()


def test_merchant_matching_ignores_punctuation_for_company_names() -> None:
    assert evaluate._text_matches("CROSS CHANNEL NETWORK SDN BHD", "CROSS CHANNEL NETWORK SDN. BHD.")


def test_external_total_detection_uses_extracted_field_not_default_transaction_zero() -> None:
    extraction = ExtractionResult(
        merchant=ExtractedField(None, 0.0, ""),
        date=ExtractedField(None, 0.0, ""),
        items=ExtractedField([], 0.0, ""),
        subtotal=ExtractedField(None, 0.0, ""),
        tax=ExtractedField(None, 0.0, ""),
        total=ExtractedField(None, 0.0, ""),
        payment_method=ExtractedField(None, 0.0, ""),
        bill_number=ExtractedField(None, 0.0, ""),
        extraction_model="test",
        ocr_engine="test",
    )
    transaction = Transaction(
        merchant=None,
        date=None,
        items=[],
        subtotal=None,
        tax=None,
        total=0.0,
        category="Uncategorized",
        file_name="sroie-empty.png",
    )
    record = evaluate.EvaluationRecord(
        image_name="sroie-empty.png",
        bill_id="SROIE-EMPTY",
        transaction=transaction,
        extraction=extraction,
        truth={"total": 7.95, "fields": ["total"]},
        ocr_text="",
        reference_text="",
        pipeline_seconds=0.1,
    )

    assert evaluate._external_field_detected(record, "total") is False
