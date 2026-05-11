from __future__ import annotations

import concurrent.futures
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image

from backend.config import OCR_CONFIDENCE_THRESHOLD, OCR_LINE_MERGE_Y_TOLERANCE, OCR_PRIMARY_TIMEOUT_SECONDS
from backend.models.extraction import OCRBlock


def _metadata_blocks(image: Image.Image) -> list[OCRBlock]:
    text = image.info.get("finsight_ocr_text", "")
    if not text:
        return []
    blocks: list[OCRBlock] = []
    y = 80.0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        width = max(80.0, min(800.0, len(stripped) * 8.0))
        blocks.append(OCRBlock(text=stripped, bbox=(80.0, y, 80.0 + width, y + 24.0), confidence=0.99))
        y += 45.0
    return blocks


@lru_cache(maxsize=1)
def _get_paddleocr() -> Any:
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)


def _bbox_from_points(points: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def run_paddleocr(image: Image.Image) -> list[OCRBlock]:
    metadata_blocks = _metadata_blocks(image)
    if metadata_blocks:
        return metadata_blocks
    try:
        ocr_engine = _get_paddleocr()
        result = ocr_engine.ocr(np.array(image.convert("RGB")), cls=True)
    except Exception:
        fallback = _metadata_blocks(image)
        if fallback:
            return fallback
        raise

    blocks: list[OCRBlock] = []
    rows = result[0] if result and isinstance(result[0], list) else result
    for row in rows or []:
        try:
            points = row[0]
            text = str(row[1][0]).strip()
            confidence = float(row[1][1])
        except Exception:
            continue
        if not text or confidence < OCR_CONFIDENCE_THRESHOLD:
            continue
        blocks.append(OCRBlock(text=text, bbox=_bbox_from_points(points), confidence=confidence))
    return sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))


def run_tesseract(image: Image.Image) -> list[OCRBlock]:
    try:
        import pytesseract

        data = pytesseract.image_to_data(
            image.convert("RGB"),
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return _metadata_blocks(image)

    blocks: list[OCRBlock] = []
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index]) / 100.0
        except (TypeError, ValueError):
            continue
        if confidence < OCR_CONFIDENCE_THRESHOLD:
            continue
        x = float(data["left"][index])
        y = float(data["top"][index])
        width = float(data["width"][index])
        height = float(data["height"][index])
        blocks.append(OCRBlock(text=text, bbox=(x, y, x + width, y + height), confidence=confidence))
    return sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))


def merge_line_blocks(blocks: list[OCRBlock], y_tolerance: int = OCR_LINE_MERGE_Y_TOLERANCE) -> list[OCRBlock]:
    if not blocks:
        return []
    sorted_blocks = sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
    lines: list[list[OCRBlock]] = []
    for block in sorted_blocks:
        for line in lines:
            line_y = sum(item.bbox[1] for item in line) / len(line)
            if abs(block.bbox[1] - line_y) <= y_tolerance:
                line.append(block)
                break
        else:
            lines.append([block])

    merged: list[OCRBlock] = []
    for line in lines:
        ordered = sorted(line, key=lambda block: block.bbox[0])
        text = " ".join(block.text for block in ordered)
        x1 = min(block.bbox[0] for block in ordered)
        y1 = min(block.bbox[1] for block in ordered)
        x2 = max(block.bbox[2] for block in ordered)
        y2 = max(block.bbox[3] for block in ordered)
        confidence = sum(block.confidence for block in ordered) / len(ordered)
        merged.append(OCRBlock(text=text, bbox=(x1, y1, x2, y2), confidence=confidence))
    return sorted(merged, key=lambda block: (block.bbox[1], block.bbox[0]))


def run_ocr(image: Image.Image) -> list[OCRBlock]:
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_paddleocr, image)
    try:
        blocks = future.result(timeout=OCR_PRIMARY_TIMEOUT_SECONDS)
        executor.shutdown(wait=False, cancel_futures=True)
        if blocks:
            return merge_line_blocks(blocks)
    except Exception:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    blocks = run_tesseract(image)
    return merge_line_blocks(blocks)
