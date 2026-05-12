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

    assert result["summary"]["ocr_accuracy"] == 1.0
    assert result["summary"]["field_extraction_accuracy"] == 1.0
    assert result["summary"]["categorization_f1"] == 1.0
    assert result["ocr"]["cer"] == 0.0
    assert result["extraction"]["amount_accuracy_within_1_inr"] == 1.0
    assert result["self_correction"]["correction_rate"] is None
    assert result["chatbot"]["response_latency_target_seconds"] == 5
    assert json.loads(results_path.read_text(encoding="utf-8"))["summary"] == result["summary"]
