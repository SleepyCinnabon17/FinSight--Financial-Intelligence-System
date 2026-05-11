from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.models.extraction import OCRBlock
from backend.pipeline.ocr import merge_line_blocks, run_ocr, run_paddleocr, run_tesseract


def _synthetic_image() -> Image.Image:
    return Image.open(sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[0])


def test_run_paddleocr_on_clean_synthetic_bill_returns_blocks() -> None:
    with _synthetic_image() as image:
        assert run_paddleocr(image)


def test_run_tesseract_on_clean_synthetic_bill_returns_blocks() -> None:
    with _synthetic_image() as image:
        assert run_tesseract(image)


def test_merge_line_blocks_merges_same_line_left_to_right() -> None:
    blocks = [
        OCRBlock("World", (50, 10, 90, 20), 0.8),
        OCRBlock("Hello", (0, 12, 40, 20), 1.0),
    ]
    merged = merge_line_blocks(blocks, y_tolerance=5)
    assert len(merged) == 1
    assert merged[0].text == "Hello World"
    assert merged[0].confidence == 0.9


def test_run_ocr_falls_back_when_paddle_raises() -> None:
    with _synthetic_image() as image:
        with patch("backend.pipeline.ocr.run_paddleocr", side_effect=RuntimeError("paddle failure")):
            assert run_ocr(image)


def test_run_ocr_falls_back_when_paddle_returns_empty() -> None:
    with _synthetic_image() as image:
        with patch("backend.pipeline.ocr.run_paddleocr", return_value=[]), patch("backend.pipeline.ocr.run_tesseract", return_value=[OCRBlock("fallback", (0, 0, 10, 10), 0.9)]) as tesseract:
            blocks = run_ocr(image)
    assert tesseract.called
    assert blocks[0].text == "fallback"


def test_run_ocr_falls_back_when_paddle_times_out() -> None:
    def _slow_paddle(image: Image.Image) -> list[OCRBlock]:
        import time

        del image
        time.sleep(0.1)
        return [OCRBlock("late", (0, 0, 10, 10), 0.9)]

    with _synthetic_image() as image:
        with patch("backend.pipeline.ocr.OCR_PRIMARY_TIMEOUT_SECONDS", 0.01), patch("backend.pipeline.ocr.run_paddleocr", side_effect=_slow_paddle), patch("backend.pipeline.ocr.run_tesseract", return_value=[OCRBlock("fallback", (0, 0, 10, 10), 0.9)]) as tesseract:
            blocks = run_ocr(image)
    assert tesseract.called
    assert blocks[0].text == "fallback"
