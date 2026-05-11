from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from backend.config import (
    FUNSD_MAX_LOOKAHEAD_BLOCKS,
    FUNSD_QUESTION_MAX_WORDS,
    KIE_BILL_CONFIDENCE,
    KIE_DERIVED_SUBTOTAL_CONFIDENCE,
    KIE_FALLBACK_TOTAL_CONFIDENCE,
    KIE_FUNSD_CONFIDENCE,
    KIE_HIGH_CONFIDENCE,
    KIE_MEDIUM_CONFIDENCE,
    KIE_MIN_FIELD_CONFIDENCE,
    KIE_PAYMENT_CONFIDENCE,
    RECEIPT_PRICE_LINE_THRESHOLD,
)
from backend.models.extraction import ExtractedField, ExtractionResult, LineItem, OCRBlock


PRICE_RE = re.compile(r"(?<!\d)(?:rs\.?\s*)?[\d,]+(?:\.\d{1,2})?(?!\d)", re.IGNORECASE)
DATE_RE = re.compile(
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s+\w{3,9}\s+\d{4})",
    re.IGNORECASE,
)
TOTAL_KEYWORDS = re.compile(r"\b(total|grand total|amount due)\b", re.IGNORECASE)
TAX_KEYWORDS = ["gst", "tax", "vat", "cgst", "sgst", "igst"]
PAYMENT_RE = re.compile(r"\b(upi|card|cash|netbanking|wallet)\b", re.IGNORECASE)
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _field(value: object, confidence: float, raw_text: str) -> ExtractedField:
    if confidence < KIE_MIN_FIELD_CONFIDENCE:
        return ExtractedField(value=None, confidence=0.0, raw_text=raw_text)
    return ExtractedField(value=value, confidence=confidence, raw_text=raw_text)


def normalize_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = re.sub(r"(?i)\brs\.?", "", raw)
    cleaned = cleaned.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _last_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = re.sub(r"(?i)\brs\.?", "", raw).replace(",", "")
    matches = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def normalize_date(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    match = DATE_RE.search(text)
    if not match:
        return None
    token = match.group(1)
    month_match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", token)
    if month_match:
        day = int(month_match.group(1))
        month = MONTHS.get(month_match.group(2).lower())
        year = int(month_match.group(3))
        if month:
            return _safe_iso_date(year, month, day)

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", token):
        year_s, month_s, day_s = token.split("-")
        return _safe_iso_date(int(year_s), int(month_s), int(day_s))

    parts = re.split(r"[/\-]", token)
    if len(parts) != 3:
        return None
    first, second, year = (int(part) for part in parts)
    if year < 100:
        year += 2000
    if first > 12:
        day, month = first, second
    elif second > 12:
        month, day = first, second
    else:
        day, month = first, second
    return _safe_iso_date(year, month, day)


def _safe_iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def detect_document_format(blocks: list[OCRBlock]) -> str:
    price_lines = sum(1 for block in blocks if PRICE_RE.search(block.text))
    if price_lines >= RECEIPT_PRICE_LINE_THRESHOLD:
        return "receipt"
    if any(re.search(r"\b(invoice|bill to)\b", block.text, re.IGNORECASE) for block in blocks):
        return "invoice"
    return "unknown"


def _raw_text(blocks: Iterable[OCRBlock]) -> str:
    return "\n".join(block.text for block in blocks)


def _top_merchant(blocks: list[OCRBlock]) -> tuple[str | None, float, str]:
    candidates = [
        block
        for block in sorted(blocks, key=lambda item: (item.bbox[1], item.bbox[0]))
        if not re.search(r"\b(invoice|date|bill to|subtotal|total|gst|payment)\b", block.text, re.IGNORECASE)
    ]
    if not candidates:
        return None, 0.0, ""
    block = candidates[0]
    return block.text.strip(), min(KIE_HIGH_CONFIDENCE, block.confidence), block.text


def _extract_date(blocks: list[OCRBlock]) -> tuple[str | None, float, str]:
    for block in blocks:
        normalized = normalize_date(block.text)
        if normalized:
            return normalized, min(KIE_HIGH_CONFIDENCE, block.confidence), block.text
    return None, 0.0, ""


def _amount_after_keyword(blocks: list[OCRBlock], keyword_re: re.Pattern[str]) -> tuple[float | None, float, str]:
    for index, block in enumerate(blocks):
        if not keyword_re.search(block.text):
            continue
        amount = _last_amount(block.text)
        if amount is not None and re.search(r"\d", block.text):
            return amount, min(KIE_HIGH_CONFIDENCE, block.confidence), block.text
        if index + 1 < len(blocks):
            amount = normalize_amount(blocks[index + 1].text)
            if amount is not None:
                return amount, min(KIE_MEDIUM_CONFIDENCE, blocks[index + 1].confidence), blocks[index + 1].text
    return None, 0.0, ""


def _extract_payment(blocks: list[OCRBlock]) -> tuple[str | None, float, str]:
    for block in blocks:
        match = PAYMENT_RE.search(block.text)
        if match:
            return match.group(1).upper() if match.group(1).lower() == "upi" else match.group(1).title(), min(KIE_PAYMENT_CONFIDENCE, block.confidence), block.text
    return None, 0.0, ""


def _extract_bill_number(blocks: list[OCRBlock]) -> tuple[str | None, float, str]:
    for block in blocks:
        match = re.search(r"\b(?:inv|invoice|bill)[\s:#-]*([A-Z0-9-]{4,})\b", block.text, re.IGNORECASE)
        if match:
            value = match.group(1).upper()
            if value.startswith("OICE"):
                continue
            return value, min(KIE_BILL_CONFIDENCE, block.confidence), block.text
    return None, 0.0, ""


def _extract_tax(blocks: list[OCRBlock]) -> tuple[float | None, float, str]:
    tax_re = re.compile("|".join(re.escape(keyword) for keyword in TAX_KEYWORDS), re.IGNORECASE)
    return _amount_after_keyword(blocks, tax_re)


def _extract_subtotal(blocks: list[OCRBlock]) -> tuple[float | None, float, str]:
    return _amount_after_keyword(blocks, re.compile(r"\bsubtotal\b", re.IGNORECASE))


def _extract_total(blocks: list[OCRBlock]) -> tuple[float | None, float, str]:
    total, confidence, raw = _amount_after_keyword(blocks, TOTAL_KEYWORDS)
    if total is not None:
        return total, confidence, raw
    amounts = [(normalize_amount(block.text), block) for block in blocks if PRICE_RE.search(block.text)]
    parsed = [(amount, block) for amount, block in amounts if amount is not None]
    if not parsed:
        return None, 0.0, ""
    amount, block = max(parsed, key=lambda item: item[0])
    return amount, min(KIE_FALLBACK_TOTAL_CONFIDENCE, block.confidence), block.text


def _extract_line_items(blocks: list[OCRBlock]) -> list[LineItem]:
    items: list[LineItem] = []
    skip_re = re.compile(r"\b(subtotal|gst|tax|vat|total|payment|invoice|date|bill to)\b", re.IGNORECASE)
    item_re = re.compile(r"^(.+?)\s+(?:(\d+(?:\.\d+)?)\s+)?((?:rs\.?\s*)?[\d,]+(?:\.\d{1,2})?)$", re.IGNORECASE)
    for block in blocks:
        text = block.text.strip()
        if skip_re.search(text):
            continue
        match = item_re.match(text)
        if not match:
            continue
        name = match.group(1).strip()
        quantity = float(match.group(2)) if match.group(2) is not None else None
        total_price = normalize_amount(match.group(3))
        if not name or total_price is None:
            continue
        unit_price = round(total_price / quantity, 2) if quantity else None
        items.append(LineItem(name=name, quantity=quantity, unit_price=unit_price, total_price=total_price))
    return items


def _cord_path(blocks: list[OCRBlock]) -> ExtractionResult:
    merchant, merchant_conf, merchant_raw = _top_merchant(blocks)
    normalized_date, date_conf, date_raw = _extract_date(blocks)
    items = _extract_line_items(blocks)
    subtotal, subtotal_conf, subtotal_raw = _extract_subtotal(blocks)
    if subtotal is None and items:
        subtotal = round(sum(item.total_price for item in items), 2)
        subtotal_conf = KIE_DERIVED_SUBTOTAL_CONFIDENCE
        subtotal_raw = "derived from line items"
    tax, tax_conf, tax_raw = _extract_tax(blocks)
    total, total_conf, total_raw = _extract_total(blocks)
    payment, payment_conf, payment_raw = _extract_payment(blocks)
    bill_number, bill_conf, bill_raw = _extract_bill_number(blocks)
    return _build_result(
        blocks,
        "cord_regex",
        merchant,
        merchant_conf,
        merchant_raw,
        normalized_date,
        date_conf,
        date_raw,
        items,
        0.85 if items else 0.0,
        subtotal,
        subtotal_conf,
        subtotal_raw,
        tax,
        tax_conf,
        tax_raw,
        total,
        total_conf,
        total_raw,
        payment,
        payment_conf,
        payment_raw,
        bill_number,
        bill_conf,
        bill_raw,
    )


def _sroie_path(blocks: list[OCRBlock]) -> ExtractionResult:
    merchant, merchant_conf, merchant_raw = _top_merchant(blocks)
    normalized_date, date_conf, date_raw = _extract_date(blocks)
    total, total_conf, total_raw = _extract_total(blocks)
    subtotal, subtotal_conf, subtotal_raw = _extract_subtotal(blocks)
    tax, tax_conf, tax_raw = _extract_tax(blocks)
    payment, payment_conf, payment_raw = _extract_payment(blocks)
    bill_number, bill_conf, bill_raw = _extract_bill_number(blocks)
    return _build_result(
        blocks,
        "sroie_keyword_proximity",
        merchant,
        merchant_conf,
        merchant_raw,
        normalized_date,
        date_conf,
        date_raw,
        [],
        0.0,
        subtotal,
        subtotal_conf,
        subtotal_raw,
        tax,
        tax_conf,
        tax_raw,
        total,
        total_conf,
        total_raw,
        payment,
        payment_conf,
        payment_raw,
        bill_number,
        bill_conf,
        bill_raw,
    )


def _is_q_block(block: OCRBlock, next_block: OCRBlock | None) -> bool:
    text = block.text.strip()
    return text.endswith(":") or len(text.split()) < FUNSD_QUESTION_MAX_WORDS and (next_block is not None and next_block.text.strip() == ":")


def _is_a_block(block: OCRBlock, q_block: OCRBlock) -> bool:
    text = block.text
    return bool(re.search(r"[\d$]", text)) or block.bbox[0] > q_block.bbox[2]


def _funsd_path(blocks: list[OCRBlock]) -> ExtractionResult:
    pairs: dict[str, OCRBlock] = {}
    ordered = sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
    for index, block in enumerate(ordered):
        next_block = ordered[index + 1] if index + 1 < len(ordered) else None
        if not _is_q_block(block, next_block):
            continue
        q_text = block.text.strip().rstrip(":").lower()
        candidates = [candidate for candidate in ordered[index + 1 : index + FUNSD_MAX_LOOKAHEAD_BLOCKS] if _is_a_block(candidate, block)]
        if candidates:
            pairs[q_text] = candidates[0]

    def value_for(*keywords: str) -> tuple[str | None, float, str]:
        for key, block in pairs.items():
            if any(keyword in key for keyword in keywords):
                return block.text, min(KIE_FUNSD_CONFIDENCE, block.confidence), block.text
        return None, 0.0, ""

    merchant, merchant_conf, merchant_raw = value_for("merchant", "company", "vendor")
    raw_date, date_conf, date_raw = value_for("date")
    total_raw_value, total_conf, total_raw = value_for("total", "amount due", "amount")
    subtotal_raw_value, subtotal_conf, subtotal_raw = value_for("subtotal")
    tax_raw_value, tax_conf, tax_raw = value_for("tax", "gst", "vat")
    payment, payment_conf, payment_raw = value_for("payment", "method")
    bill_number, bill_conf, bill_raw = value_for("invoice", "bill")
    return _build_result(
        blocks,
        "funsd_question_answer",
        merchant,
        merchant_conf,
        merchant_raw,
        normalize_date(raw_date),
        date_conf if normalize_date(raw_date) else 0.0,
        date_raw,
        [],
        0.0,
        normalize_amount(subtotal_raw_value),
        subtotal_conf,
        subtotal_raw,
        normalize_amount(tax_raw_value),
        tax_conf,
        tax_raw,
        normalize_amount(total_raw_value),
        total_conf,
        total_raw,
        payment,
        payment_conf,
        payment_raw,
        bill_number,
        bill_conf,
        bill_raw,
    )


def _build_result(
    blocks: list[OCRBlock],
    extraction_model: str,
    merchant: str | None,
    merchant_conf: float,
    merchant_raw: str,
    normalized_date: str | None,
    date_conf: float,
    date_raw: str,
    items: list[LineItem],
    items_conf: float,
    subtotal: float | None,
    subtotal_conf: float,
    subtotal_raw: str,
    tax: float | None,
    tax_conf: float,
    tax_raw: str,
    total: float | None,
    total_conf: float,
    total_raw: str,
    payment: str | None,
    payment_conf: float,
    payment_raw: str,
    bill_number: str | None,
    bill_conf: float,
    bill_raw: str,
) -> ExtractionResult:
    return ExtractionResult(
        merchant=_field(merchant, merchant_conf, merchant_raw),
        date=_field(normalized_date, date_conf, date_raw),
        items=ExtractedField(value=items, confidence=items_conf, raw_text="\n".join(item.name for item in items)),
        subtotal=_field(subtotal, subtotal_conf, subtotal_raw),
        tax=_field(tax, tax_conf, tax_raw),
        total=_field(total, total_conf, total_raw),
        payment_method=_field(payment, payment_conf, payment_raw),
        bill_number=_field(bill_number, bill_conf, bill_raw),
        extraction_model=extraction_model,
        ocr_engine="paddleocr_or_tesseract",
        raw_ocr_text=_raw_text(blocks),
    )


def extract_fields(blocks: list[OCRBlock]) -> ExtractionResult:
    document_format = detect_document_format(blocks)
    if document_format == "receipt":
        return _cord_path(blocks)
    if document_format == "invoice":
        return _sroie_path(blocks)
    return _funsd_path(blocks)


def run_kie(blocks: list[OCRBlock]) -> ExtractionResult:
    return extract_fields(blocks)
