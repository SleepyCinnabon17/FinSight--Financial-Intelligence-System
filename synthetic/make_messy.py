from __future__ import annotations

import os
import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
from PIL.PngImagePlugin import PngInfo


ROOT = Path(__file__).resolve().parent
IMAGE_DIR = ROOT / "synthetic_bill_images"


def _atomic_save_image(image: Image.Image, path: Path, ocr_text: str | None = None) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    pnginfo = None
    if ocr_text:
        pnginfo = PngInfo()
        pnginfo.add_text("finsight_ocr_text", ocr_text)
    image.save(tmp_path, format="PNG", pnginfo=pnginfo)
    os.replace(tmp_path, path)


def make_messy(count: int = 10) -> int:
    random.seed(42)
    source_images = sorted(path for path in IMAGE_DIR.glob("*.png") if not path.name.startswith("messy_"))
    selected = random.sample(source_images, min(count, len(source_images)))
    for image_path in selected:
        with Image.open(image_path) as image:
            ocr_text = image.info.get("finsight_ocr_text")
            rgb = image.convert("RGB")
            angle = random.uniform(-3, 3)
            contrast = random.uniform(0.6, 0.85)
            messy = rgb.rotate(angle, expand=True, fillcolor="white")
            messy = ImageEnhance.Contrast(messy).enhance(contrast)
            messy = messy.filter(ImageFilter.GaussianBlur(radius=0.8))
            _atomic_save_image(messy, IMAGE_DIR / f"messy_{image_path.name}", ocr_text)
    return len(selected)


if __name__ == "__main__":
    print(f"Created {make_messy()} messy images")
