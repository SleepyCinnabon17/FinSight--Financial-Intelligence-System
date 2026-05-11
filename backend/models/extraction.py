from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")
BBox = tuple[float, float, float, float]


@dataclass(slots=True)
class OCRBlock:
    text: str
    bbox: BBox
    confidence: float


@dataclass(slots=True)
class ExtractedField(Generic[T]):
    value: T
    confidence: float
    raw_text: str


@dataclass(slots=True)
class LineItem:
    name: str
    quantity: float | None
    unit_price: float | None
    total_price: float


@dataclass(slots=True)
class ExtractionResult:
    merchant: ExtractedField[str | None]
    date: ExtractedField[str | None]
    items: ExtractedField[list[LineItem]]
    subtotal: ExtractedField[float | None]
    tax: ExtractedField[float | None]
    total: ExtractedField[float | None]
    payment_method: ExtractedField[str | None]
    bill_number: ExtractedField[str | None]
    extraction_model: str
    ocr_engine: str
    raw_ocr_text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


def unextracted_field(raw_text: str = "") -> ExtractedField[None]:
    return ExtractedField(value=None, confidence=0.0, raw_text=raw_text)
