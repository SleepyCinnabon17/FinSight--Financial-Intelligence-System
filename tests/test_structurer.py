from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from backend.models.extraction import ExtractedField, ExtractionResult, LineItem
from backend.pipeline import structurer
from backend.pipeline.structurer import MERCHANT_CATEGORY_MAP, extraction_to_transaction, infer_category, load_transactions, persist_transaction


def _extraction(total: float = 100.0, merchant: str = "Zomato") -> ExtractionResult:
    item = LineItem(name="Meal", quantity=1, unit_price=total, total_price=total)
    return ExtractionResult(
        merchant=ExtractedField(merchant, 1.0, merchant),
        date=ExtractedField("2026-05-01", 1.0, "01/05/2026"),
        items=ExtractedField([item], 1.0, "Meal"),
        subtotal=ExtractedField(total, 1.0, str(total)),
        tax=ExtractedField(0.0, 1.0, "0"),
        total=ExtractedField(total, 1.0, str(total)),
        payment_method=ExtractedField("UPI", 1.0, "UPI"),
        bill_number=ExtractedField("INV-1234-56", 1.0, "INV-1234-56"),
        extraction_model="test",
        ocr_engine="test",
        raw_ocr_text="raw",
    )


def test_known_categories() -> None:
    assert infer_category("zomato", []) == "Food"
    assert infer_category("swiggy", []) == "Food"
    for merchant, category in MERCHANT_CATEGORY_MAP.items():
        assert infer_category(merchant, []) == category


def test_unknown_merchant_calls_zero_shot_classifier() -> None:
    original = structurer.pipeline
    structurer.pipeline = Mock(return_value=Mock(return_value={"labels": ["Utilities"], "scores": [0.91]}))
    try:
        assert infer_category("Unknown Power", ["meter"]) == "Utilities"
        structurer.pipeline.assert_called_once_with("zero-shot-classification")
    finally:
        structurer.pipeline = original


def test_uuid_assigned_unique_per_call() -> None:
    first = extraction_to_transaction(_extraction(), b"one", "one.png")
    second = extraction_to_transaction(_extraction(), b"two", "two.png")
    assert first.id != second.id


def test_persist_transaction_appends_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "transactions.json"
    first = extraction_to_transaction(_extraction(100), b"one", "one.png")
    second = extraction_to_transaction(_extraction(200), b"two", "two.png")
    persist_transaction(first, str(path))
    persist_transaction(second, str(path))
    loaded = load_transactions(str(path))
    assert [transaction.total for transaction in loaded] == [100.0, 200.0]


def test_missing_transactions_file_loads_empty(tmp_path: Path) -> None:
    assert load_transactions(str(tmp_path / "transactions.json")) == []


def test_empty_transactions_file_repairs_to_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "transactions.json"
    path.write_text("   ", encoding="utf-8")
    assert load_transactions(str(path)) == []
    assert path.read_text(encoding="utf-8").strip() == "[]"


def test_corrupt_transactions_file_is_quarantined_and_repaired(tmp_path: Path) -> None:
    path = tmp_path / "transactions.json"
    path.write_text("{broken json", encoding="utf-8")
    assert load_transactions(str(path)) == []
    assert path.read_text(encoding="utf-8").strip() == "[]"
    backups = list(tmp_path.glob("transactions.json.corrupt.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{broken json"


def test_non_list_transactions_file_is_quarantined_and_repaired(tmp_path: Path) -> None:
    path = tmp_path / "transactions.json"
    path.write_text('{"id": "not-a-list"}', encoding="utf-8")
    assert load_transactions(str(path)) == []
    assert path.read_text(encoding="utf-8").strip() == "[]"
    assert list(tmp_path.glob("transactions.json.corrupt.*.bak"))


def test_sanitizes_user_visible_text_fields_before_persistence(tmp_path: Path) -> None:
    transaction = extraction_to_transaction(_extraction(100, "<script>x</script>  Zomato   Store"), b"one", "one.png")
    assert "<script>" not in transaction.merchant
    assert transaction.merchant == "x Zomato Store"
