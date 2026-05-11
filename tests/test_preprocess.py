from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from backend.pipeline.preprocess import (
    PreprocessingError,
    deskew,
    detect_format,
    normalize_contrast,
    pdf_to_image,
    preprocess,
    sharpen_if_blurry,
)


def _laplacian_variance(image: Image.Image) -> float:
    import cv2

    return float(cv2.Laplacian(np.array(image.convert("L")), cv2.CV_64F).var())


def test_detect_format_magic_bytes() -> None:
    assert detect_format(b"%PDF-1.7") == "pdf"
    assert detect_format(b"\xff\xd8\xff") == "jpeg"
    assert detect_format(b"\x89PNG\r\n\x1a\nabc") == "png"
    assert detect_format(b"RIFF1234WEBPmore") == "webp"
    assert detect_format(b"\x00\x00\x00\x18ftypheicmore") == "heic"


def test_pdf_to_image_on_synthetic_pdf() -> None:
    pdf = sorted(Path("synthetic/synthetic_bills").glob("*.pdf"))[0]
    image = pdf_to_image(pdf.read_bytes())
    assert isinstance(image, Image.Image)


def test_deskew_on_rotated_test_image() -> None:
    image = Image.new("RGB", (500, 220), "white")
    draw = ImageDraw.Draw(image)
    for y in (70, 110, 150):
        draw.line((60, y, 440, y), fill="black", width=4)
    rotated = image.rotate(5, expand=True, fillcolor="white")
    corrected = deskew(rotated)
    assert isinstance(corrected, Image.Image)
    assert abs(corrected.size[0] - rotated.size[0]) < rotated.size[0]


def test_normalize_contrast_on_dark_image_changes_pixels() -> None:
    image = Image.new("RGB", (100, 100), (35, 35, 35))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 80, 80), fill=(70, 70, 70))
    enhanced = normalize_contrast(image)
    assert np.array(enhanced).std() >= np.array(image).std()


def test_sharpen_if_blurry_improves_laplacian_variance() -> None:
    image = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 45), "FinSight", fill="black")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=3))
    sharpened = sharpen_if_blurry(blurred)
    assert _laplacian_variance(sharpened) >= _laplacian_variance(blurred)


def test_preprocess_empty_file_raises() -> None:
    with pytest.raises(PreprocessingError):
        preprocess(b"", "application/octet-stream")
