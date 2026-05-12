from __future__ import annotations

from pathlib import Path

from PIL import Image

from backend import config
from backend.models.extraction import OCRBlock
from backend.pipeline.kie import extract_fields, normalize_amount, normalize_date
from backend.pipeline.ocr import run_ocr


def test_cord_path_itemized_bill_returns_line_items(monkeypatch) -> None:
    monkeypatch.setattr(config, "OCR_FIXTURE_METADATA_ENABLED", True)
    with Image.open(sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[0]) as image:
        result = extract_fields(run_ocr(image))
    assert result.extraction_model == "cord_regex"
    assert len(result.items.value) >= 3


def test_sroie_path_extracts_merchant_date_total() -> None:
    blocks = [
        OCRBlock("Zomato", (0, 0, 200, 20), 0.95),
        OCRBlock("Invoice", (0, 30, 100, 50), 0.9),
        OCRBlock("Date: 01/05/2026", (0, 60, 200, 80), 0.9),
        OCRBlock("Grand Total", (0, 120, 120, 140), 0.9),
        OCRBlock("742.50", (150, 120, 220, 140), 0.9),
    ]
    result = extract_fields(blocks)
    assert result.extraction_model == "sroie_keyword_proximity"
    assert result.merchant.value == "Zomato"
    assert result.date.value == "2026-05-01"
    assert result.total.value == 742.50


def test_sroie_merchant_prefers_company_suffix_near_top() -> None:
    blocks = [
        OCRBlock("TAN CHAY YEE", (0, 0, 200, 20), 0.95),
        OCRBlock("*** COPY ***", (0, 25, 200, 45), 0.95),
        OCRBlock("OJC MARKETING SDN BHD", (0, 50, 240, 70), 0.95),
        OCRBlock("TAX INVOICE", (0, 90, 150, 110), 0.95),
        OCRBlock("DATE : 15/01/2019", (0, 120, 180, 140), 0.95),
        OCRBlock("TOTAL: 193.00", (0, 180, 160, 200), 0.95),
    ]
    result = extract_fields(blocks)
    assert result.merchant.value == "OJC MARKETING SDN BHD"


def test_total_prefers_final_payable_total_over_intermediate_total_lines() -> None:
    blocks = [
        OCRBlock("Receipt", (0, 0, 100, 20), 0.95),
        OCRBlock("TOTAL EXCLUDE GST: 100.00", (0, 100, 220, 120), 0.95),
        OCRBlock("TOTAL GST @6%: 6.00", (0, 130, 220, 150), 0.95),
        OCRBlock("TOTAL INCLUSIVE GST: 106.00", (0, 160, 240, 180), 0.95),
        OCRBlock("ROUND AMT: 0.00", (0, 190, 180, 210), 0.95),
        OCRBlock("TOTAL: 106.00", (0, 220, 180, 240), 0.95),
    ]
    result = extract_fields(blocks)
    assert result.total.value == 106.0


def test_funsd_path_maps_question_answer_pairs() -> None:
    blocks = [
        OCRBlock("Merchant:", (0, 0, 80, 20), 0.9),
        OCRBlock("Zomato", (120, 0, 200, 20), 0.9),
        OCRBlock("Date:", (0, 40, 80, 60), 0.9),
        OCRBlock("01/05/2026", (120, 40, 220, 60), 0.9),
        OCRBlock("Total:", (0, 80, 80, 100), 0.9),
        OCRBlock("500.00", (120, 80, 220, 100), 0.9),
    ]
    result = extract_fields(blocks)
    assert result.extraction_model == "funsd_question_answer"
    assert result.merchant.value == "Zomato"
    assert result.date.value == "2026-05-01"
    assert result.total.value == 500.0


def test_date_normalization_formats() -> None:
    cases = ["01/05/2026", "12/31/2026", "2026-05-01", "01 May 2026", "01-05-2026", "31.12.2017"]
    assert [normalize_date(value) for value in cases] == [
        "2026-05-01",
        "2026-12-31",
        "2026-05-01",
        "2026-05-01",
        "2026-05-01",
        "2017-12-31",
    ]


def test_amount_parsing() -> None:
    assert normalize_amount("\u20b91,250.00") == 1250.0
    assert normalize_amount("Rs. 500") == 500.0


def test_low_confidence_field_marked_unextracted() -> None:
    blocks = [
        OCRBlock("Unknown Merchant", (0, 0, 200, 20), 0.2),
        OCRBlock("Invoice", (0, 30, 100, 50), 0.9),
        OCRBlock("Date: 01/05/2026", (0, 60, 200, 80), 0.9),
        OCRBlock("Grand Total", (0, 120, 120, 140), 0.9),
        OCRBlock("742.50", (150, 120, 220, 140), 0.9),
    ]
    result = extract_fields(blocks)
    assert result.merchant.value is None
    assert result.merchant.confidence == 0.0
