from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "synthetic_bills"
IMAGE_DIR = ROOT / "synthetic_bill_images"
GROUND_TRUTH_PATH = ROOT / "ground_truth.json"


def _atomic_save_image(image: Image.Image, path: Path, ocr_text: str | None = None) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    pnginfo = None
    if ocr_text:
        pnginfo = PngInfo()
        pnginfo.add_text("finsight_ocr_text", ocr_text)
    image.save(tmp_path, format="PNG", pnginfo=pnginfo)
    os.replace(tmp_path, path)


def _render_fallback_png(record: dict[str, object], path: Path) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    bold = ImageFont.load_default()
    lines = [
        str(record["merchant"]),
        f"Invoice: {record['bill_number']}",
        f"Date: {record['date']}",
        "Bill To: FinSight Demo User",
        f"{record['merchant']} Meal 1 {float(record['amount']) * 0.45:.2f}",
        f"{record['merchant']} Ride 1 {float(record['amount']) * 0.30:.2f}",
        f"{record['merchant']} Order 1 {float(record['amount']) * 0.25:.2f}",
        f"Subtotal {float(record['subtotal']):.2f}",
        f"GST 18% {float(record['tax']):.2f}",
        f"Grand Total {float(record['amount']):.2f}",
        f"Payment Method: {record['payment_method']}",
    ]
    y = 80
    for index, line in enumerate(lines):
        draw.text((80, y), line, fill="black", font=bold if index == 0 else font)
        y += 70 if index == 0 else 45
    _atomic_save_image(image, path, "\n".join(lines))


def convert_all() -> int:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for image in IMAGE_DIR.glob("*.png"):
        image.unlink()

    records_by_file: dict[str, dict[str, object]] = {}
    if GROUND_TRUTH_PATH.exists():
        records = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
        records_by_file = {str(record["file_name"]): record for record in records}

    converted = 0
    try:
        from pdf2image import convert_from_path
    except Exception:
        convert_from_path = None

    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        output = IMAGE_DIR / f"{pdf_path.stem}.png"
        if convert_from_path is not None:
            try:
                pages = convert_from_path(str(pdf_path), dpi=150, first_page=1, last_page=1)
                if pages:
                    _atomic_save_image(pages[0].convert("RGB"), output)
                    converted += 1
                    continue
            except Exception:
                # Poppler is an external runtime dependency. When it is absent,
                # render deterministic PNGs from ground truth so the local
                # benchmark and pipeline still have image fixtures.
                pass
        record = records_by_file.get(pdf_path.name)
        if record is None:
            continue
        _render_fallback_png(record, output)
        converted += 1
    return converted


if __name__ == "__main__":
    count = convert_all()
    print(f"Generated {count} PNG images")
