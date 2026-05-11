from __future__ import annotations

from io import BytesIO
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from backend.config import (
    BLUR_VARIANCE_THRESHOLD,
    CLAHE_CLIP_LIMIT,
    CLAHE_TILE_GRID_SIZE,
    DESKEW_CANNY_HIGH_THRESHOLD,
    DESKEW_CANNY_LOW_THRESHOLD,
    DESKEW_FLIP_INK_RATIO,
    DESKEW_FLIP_MIN_INK,
    DESKEW_HOUGH_THRESHOLD,
    DESKEW_HOUGH_MAX_LINES,
    DESKEW_INK_PIXEL_THRESHOLD,
    DESKEW_MAX_ANGLE,
    DESKEW_MIN_ANGLE,
    HIGH_BRIGHTNESS_THRESHOLD,
    LOW_BRIGHTNESS_THRESHOLD,
    PREPROCESS_MAX_DIM,
    PREPROCESS_PDF_DPI,
    UNSHARP_PERCENT,
    UNSHARP_RADIUS,
    UNSHARP_THRESHOLD,
)


ImageFormat = Literal["pdf", "jpeg", "png", "webp", "heic"]


class PreprocessingError(Exception):
    """Human-readable preprocessing failure surfaced to API clients."""


def detect_format(file_bytes: bytes) -> str:
    if not file_bytes:
        raise PreprocessingError("Uploaded file is empty.")
    if file_bytes.startswith(b"%PDF"):
        return "pdf"
    if file_bytes.startswith(b"\xff\xd8"):
        return "jpeg"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "webp"
    if len(file_bytes) >= 12 and file_bytes[4:8] == b"ftyp" and file_bytes[8:12] in {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }:
        return "heic"
    raise PreprocessingError("Unsupported file format. Please upload PDF, JPEG, PNG, WEBP, or HEIC.")


def _fallback_pdf_image() -> Image.Image:
    # Poppler is an external dependency for pdf2image. If it is missing,
    # continue with a deterministic placeholder so uploads fail gracefully in
    # later extraction instead of crashing the preprocessing layer.
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    draw.text((72, 72), "PDF preview unavailable: Poppler is not installed.", fill="black")
    return image


def pdf_to_image(file_bytes: bytes, dpi: int = 200) -> Image.Image:
    try:
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(file_bytes, dpi=dpi, first_page=1, last_page=1)
    except Exception:
        return _fallback_pdf_image()
    if not pages:
        raise PreprocessingError("PDF appears to be empty.")
    return pages[0].convert("RGB")


def _pil_to_gray_array(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("L"))


def _rotate_bound(image: Image.Image, angle: float) -> Image.Image:
    return image.rotate(angle, expand=True, fillcolor="white", resample=Image.Resampling.BICUBIC)


def _needs_180_flip(gray: np.ndarray) -> bool:
    height = gray.shape[0]
    if height < 4:
        return False
    top = gray[: height // 4, :]
    bottom = gray[-height // 4 :, :]
    top_ink = float(np.mean(top < DESKEW_INK_PIXEL_THRESHOLD))
    bottom_ink = float(np.mean(bottom < DESKEW_INK_PIXEL_THRESHOLD))
    return bottom_ink > top_ink * DESKEW_FLIP_INK_RATIO and bottom_ink > DESKEW_FLIP_MIN_INK


def deskew(image: Image.Image) -> Image.Image:
    normalized = ImageOps.exif_transpose(image).convert("RGB")
    gray = _pil_to_gray_array(normalized)
    if _needs_180_flip(gray):
        normalized = normalized.rotate(180, expand=True, fillcolor="white")
        gray = _pil_to_gray_array(normalized)

    angle = 0.0
    try:
        from deskew import determine_skew

        detected = determine_skew(gray)
        if detected is not None:
            angle = float(detected)
    except Exception:
        edges = cv2.Canny(gray, DESKEW_CANNY_LOW_THRESHOLD, DESKEW_CANNY_HIGH_THRESHOLD, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, DESKEW_HOUGH_THRESHOLD)
        if lines is not None:
            angles: list[float] = []
            for line in lines[:DESKEW_HOUGH_MAX_LINES]:
                theta = float(line[0][1])
                line_angle = (theta * 180 / np.pi) - 90
                if -DESKEW_MAX_ANGLE <= line_angle <= DESKEW_MAX_ANGLE:
                    angles.append(line_angle)
            if angles:
                angle = float(np.median(angles))

    if abs(angle) < DESKEW_MIN_ANGLE or abs(angle) > DESKEW_MAX_ANGLE:
        return normalized
    return _rotate_bound(normalized, -angle)


def normalize_contrast(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    gray = _pil_to_gray_array(rgb)
    mean_brightness = float(np.mean(gray))
    if LOW_BRIGHTNESS_THRESHOLD <= mean_brightness <= HIGH_BRIGHTNESS_THRESHOLD:
        return rgb

    lab = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_TILE_GRID_SIZE, CLAHE_TILE_GRID_SIZE))
    enhanced_l = clahe.apply(l_channel)
    merged = cv2.merge((enhanced_l, a_channel, b_channel))
    enhanced = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    return Image.fromarray(enhanced)


def sharpen_if_blurry(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    gray = _pil_to_gray_array(rgb)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if variance >= BLUR_VARIANCE_THRESHOLD:
        return rgb
    return rgb.filter(ImageFilter.UnsharpMask(radius=UNSHARP_RADIUS, percent=UNSHARP_PERCENT, threshold=UNSHARP_THRESHOLD))


def resize_to_max(image: Image.Image, max_dim: int = PREPROCESS_MAX_DIM) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    largest = max(width, height)
    if largest <= max_dim:
        return rgb
    scale = max_dim / largest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return rgb.resize(new_size, Image.Resampling.LANCZOS)


def _load_raster(file_bytes: bytes, file_format: str) -> Image.Image:
    if file_format == "heic":
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except Exception as exc:
            raise PreprocessingError("HEIC support is unavailable in this environment.") from exc
    try:
        return Image.open(BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        raise PreprocessingError("Could not read uploaded image.") from exc


def preprocess(file_bytes: bytes, mime_type: str) -> Image.Image:
    del mime_type
    try:
        file_format = detect_format(file_bytes)
        image = pdf_to_image(file_bytes, dpi=PREPROCESS_PDF_DPI) if file_format == "pdf" else _load_raster(file_bytes, file_format)
        source_info = dict(getattr(image, "info", {}))
        image = deskew(image)
        image = normalize_contrast(image)
        image = sharpen_if_blurry(image)
        processed = resize_to_max(image)
        processed.info.update(source_info)
        return processed
    except PreprocessingError:
        raise
    except Exception as exc:
        raise PreprocessingError("Could not preprocess uploaded file.") from exc
