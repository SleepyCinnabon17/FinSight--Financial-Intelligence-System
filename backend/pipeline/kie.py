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


PRICE_RE = re.compile(
    r"(?<!\w)(?:rs\.?|rm|rp|inr|myr)?\s*[$\u20b9]?\s*-?\d[\d,]*(?:[\.,:]\d{1,3})?(?!\w)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s+\w{3,9}\s+\d{4})",
    re.IGNORECASE,
)
TOTAL_KEYWORDS = re.compile(r"\b(total|tot|grand total|amount due|amount|amt)\b|\*amt\b", re.IGNORECASE)
TOTAL_PENALTY_KEYWORDS = re.compile(
    r"\b("
    r"subtotal|sub total|sub-total|exclude|excluding|gst|tax|vat|round|rounding|discount|disc|"
    r"qty|quantity|change|tender|paid|payment|cashier|sales|tel|fax|phone|gst id"
    r")\b",
    re.IGNORECASE,
)
TOTAL_STRONG_KEYWORDS = re.compile(
    r"\b(grand total|amount due|balance due|total payable|net total|total amount|total amt|amt rm|nett total)\b|\*amt\b",
    re.IGNORECASE,
)
MERCHANT_NOISE_RE = re.compile(
    r"\b("
    r"invoice|receipt|tax invoice|date|bill to|subtotal|sub total|total|gst|tax|vat|payment|"
    r"cashier|sales|copy|customer|address|description|qty|quantity|price|amount|tel|fax|"
    r"email|website|www|roc|reg|no\.?|page|time|jalan|jln|bandar|taman|selangor|johor|"
    r"kuala|bahru|ba(h)?ru|store no|id no|gst id|co no"
    r")\b",
    re.IGNORECASE,
)
MERCHANT_SUFFIX_RE = re.compile(
    r"\b("
    r"sdn|bhd|ltd|limited|llc|inc|corp|company|co\.?|store|stores|market|marketing|"
    r"restaurant|cafe|pharmacy|supermarket|mart|trading|enterprise|enterprises|corporation|s/?b|sb"
    r")\b",
    re.IGNORECASE,
)
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
    amounts = _amount_candidates(raw, infer_cents=False)
    return amounts[0] if amounts else None


def _amount_candidates(raw: str | None, *, infer_cents: bool = False) -> list[float]:
    if raw is None:
        return []
    text = re.sub(r"(?<=\d)\s+([,\.:])\s*(?=\d)", r"\1", str(raw))
    currency_context = bool(re.search(r"(?i)\b(rs\.?|rm|rp|inr|myr)\b|[$\u20b9]", text))
    values: list[float] = []
    for match in PRICE_RE.finditer(text):
        token = match.group(0).strip()
        token_end = match.end()
        if token_end < len(text) and text[token_end : token_end + 1] == "%":
            continue
        amount = _parse_amount_token(token, infer_cents=infer_cents, currency_context=currency_context)
        if amount is not None:
            values.append(amount)
    return values


def _parse_amount_token(token: str, *, infer_cents: bool, currency_context: bool) -> float | None:
    cleaned = re.sub(r"(?i)\b(rs\.?|rm|rp|inr|myr)\b", "", token)
    cleaned = cleaned.replace("\u20b9", "").replace("$", "").strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"(?<=\d):(?=\d{1,2}\b)", ".", cleaned)
    cleaned = cleaned.rstrip("/-")
    if not re.search(r"\d", cleaned):
        return None

    has_decimal_marker = bool(re.search(r"[\.,:]\d{1,2}$", cleaned))
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        integer, fraction = cleaned.rsplit(",", 1)
        if len(fraction) in {1, 2}:
            cleaned = f"{integer}.{fraction}"
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        integer, fraction = cleaned.rsplit(".", 1)
        if len(fraction) == 3 and integer.lstrip("-").isdigit() and len(integer.lstrip("-")) <= 3:
            cleaned = f"{integer}{fraction}"

    digits_only = re.sub(r"\D", "", cleaned)
    if not digits_only:
        return None
    if len(digits_only) > 7 and not has_decimal_marker and not currency_context:
        return None
    if infer_cents and not has_decimal_marker and not currency_context and 3 <= len(digits_only) <= 4:
        try:
            return round(float(digits_only) / 100.0, 2)
        except ValueError:
            return None

    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _last_amount(raw: str | None, *, infer_cents: bool = False) -> float | None:
    amounts = _amount_candidates(raw, infer_cents=infer_cents)
    if not amounts:
        return None
    return amounts[-1]


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

    parts = re.split(r"[/\-.]", token)
    if len(parts) != 3:
        return None
    first, second, year = (int(part) for part in parts)
    if year < 100:
        year += 2000
    elif 2060 <= year <= 2079:
        year -= 60
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
    ordered = sorted(blocks, key=lambda item: (item.bbox[1], item.bbox[0]))
    candidates: list[tuple[float, OCRBlock]] = []
    for index, block in enumerate(ordered):
        text = _clean_merchant_candidate(block.text)
        if not text or MERCHANT_NOISE_RE.search(text):
            continue
        if PRICE_RE.fullmatch(text) or _looks_like_identifier_or_phone(text):
            continue
        score = max(0.0, 10.0 - index * 0.35)
        if MERCHANT_SUFFIX_RE.search(text):
            score += 4.0
        if re.search(r"[A-Za-z]{3}", text):
            score += 1.0
        candidates.append((score, block))
    if not candidates:
        return None, 0.0, ""
    top_window = candidates[:15]
    _, block = max(top_window, key=lambda item: item[0])
    merchant_text = _clean_merchant_candidate(block.text)
    block_index = ordered.index(block)
    merchant_words = re.findall(r"[A-Za-z0-9/&']+", merchant_text)
    if block_index > 0 and MERCHANT_SUFFIX_RE.search(merchant_text) and len(merchant_words) <= 2:
        previous_text = _clean_merchant_candidate(ordered[block_index - 1].text)
        if previous_text and not MERCHANT_NOISE_RE.search(previous_text) and not _looks_like_identifier_or_phone(previous_text):
            merchant_text = f"{previous_text} {merchant_text}".strip()
    if block_index + 1 < len(ordered):
        next_text = _clean_merchant_candidate(ordered[block_index + 1].text)
        if next_text and MERCHANT_SUFFIX_RE.search(next_text) and not MERCHANT_NOISE_RE.search(next_text):
            merchant_text = f"{merchant_text} {next_text}".strip()
    return merchant_text, min(KIE_HIGH_CONFIDENCE, block.confidence), block.text


def _clean_merchant_candidate(raw: str | None) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^[^\w&]+|[^\w&./' -]+$", "", text)
    return " ".join(text.split())


def _looks_like_identifier_or_phone(text: str) -> bool:
    stripped = text.strip()
    if re.search(r"\d[\.,:]\d{1,2}\b", stripped):
        return False
    digits = re.sub(r"\D", "", stripped)
    letters = re.sub(r"[^A-Za-z]", "", stripped)
    if len(digits) >= 6 and len(letters) <= 4:
        return True
    if len(digits) == 5 and len(letters) <= 4:
        return True
    if len(digits) >= 4 and re.search(r"\b(tel|fax|phone|id|no|gst|roc|co)\b", stripped, re.IGNORECASE):
        return True
    if digits and len(letters) == 0:
        return True
    return False


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
    total_candidates: list[tuple[float, float, OCRBlock]] = []
    for index, block in enumerate(blocks):
        if not TOTAL_KEYWORDS.search(block.text):
            continue
        text = block.text
        sources: list[tuple[float, OCRBlock, int, int]] = []
        same_line_amounts = _amount_candidates(text, infer_cents=True)
        for amount in same_line_amounts:
            sources.append((amount, block, 0, len(same_line_amounts)))
        for lookahead, next_block in enumerate(blocks[index + 1 : index + 7], start=1):
            if _skip_total_lookahead_line(next_block.text):
                continue
            next_amounts = _amount_candidates(next_block.text, infer_cents=True)
            for amount in next_amounts:
                sources.append((amount, next_block, lookahead, len(next_amounts)))
        for amount, source_block, lookahead, amount_count in sources:
            if amount <= 0:
                continue
            payment_confirmed = _has_nearby_payment_confirmation(blocks, source_block, amount)
            score = _total_candidate_score(text, amount, source_block, lookahead, amount_count, payment_confirmed)
            total_candidates.append((score, amount, source_block))
    if total_candidates:
        _, amount, block = max(total_candidates, key=lambda item: (item[0], item[1]))
        return amount, min(KIE_HIGH_CONFIDENCE, block.confidence), block.text
    amounts = [(_last_amount(block.text), block) for block in blocks if PRICE_RE.search(block.text) and not _skip_total_fallback_line(block.text)]
    parsed = [(amount, block) for amount, block in amounts if amount is not None and 0 < amount < 100000]
    if not parsed:
        return None, 0.0, ""
    amount, block = max(parsed, key=lambda item: (item[1].bbox[1], item[0]))
    return amount, min(KIE_FALLBACK_TOTAL_CONFIDENCE, block.confidence), block.text


def _skip_total_lookahead_line(text: str) -> bool:
    if re.search(r"\b(gst|tax|vat|discount|rounding|round|change|tender|paid|cashier|tel|fax|phone|id)\b", text, re.IGNORECASE):
        return True
    if _looks_like_identifier_or_phone(text):
        return True
    return False


def _skip_total_fallback_line(text: str) -> bool:
    if re.search(r"\b(tel|fax|phone|gst id|roc|co no|invoice|receipt|date|time|approval|code)\b", text, re.IGNORECASE):
        return True
    if re.search(r"\b(jalan|jln|bandar|taman|selangor|johor|km)\b", text, re.IGNORECASE):
        return True
    if DATE_RE.search(text) or re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", text):
        return True
    return _looks_like_identifier_or_phone(text)


def _has_nearby_payment_confirmation(blocks: list[OCRBlock], source_block: OCRBlock, amount: float) -> bool:
    try:
        index = blocks.index(source_block)
    except ValueError:
        return False
    for neighbor in blocks[index + 1 : index + 4]:
        if not re.search(r"\b(cash|card|visa|mastercard|payment|paid)\b", neighbor.text, re.IGNORECASE):
            continue
        if any(abs(candidate - amount) <= 0.01 for candidate in _amount_candidates(neighbor.text, infer_cents=True)):
            return True
    return False


def _total_candidate_score(
    keyword_text: str,
    amount: float,
    source_block: OCRBlock,
    lookahead: int,
    amount_count: int,
    payment_confirmed: bool,
) -> float:
    score = 10.0
    if TOTAL_STRONG_KEYWORDS.search(keyword_text):
        score += 8.0
    if re.search(r"^\s*(?:\*?amt|total|tot|nett total|net total)\b\s*[:\-]?", keyword_text, re.IGNORECASE):
        score += 6.0
    if re.search(r"\binclusive\b", keyword_text, re.IGNORECASE):
        score += 5.0
    if TOTAL_PENALTY_KEYWORDS.search(keyword_text):
        score -= 9.0
    if amount_count > 1:
        score -= 10.0
    if re.search(r"\b\d{2,}:\d{1,2}\b", source_block.text):
        score -= 8.0
    if payment_confirmed:
        score += 4.0
    if re.search(r"\b(payment mode|cash|change|tender|paid)\b", keyword_text, re.IGNORECASE):
        score -= 7.0
    if amount >= 100000:
        score -= 20.0
    if lookahead:
        score -= lookahead * 0.75
    score += min(source_block.bbox[1] / 1000.0, 5.0)
    return score


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
