from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from backend.config import ZERO_SHOT_CONFIDENCE_THRESHOLD
from backend.models.extraction import ExtractionResult, LineItem
from backend.models.transaction import Transaction

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional dependency fallback
    pipeline = None  # type: ignore[assignment]


MERCHANT_CATEGORY_MAP: dict[str, str] = {
    "zomato": "Food",
    "swiggy": "Food",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "netflix": "Subscription",
    "spotify": "Subscription",
    "uber": "Transport",
    "ola": "Transport",
    "bigbasket": "Food",
    "blinkit": "Food",
    "myntra": "Shopping",
    "irctc": "Transport",
}

CANDIDATE_LABELS = [
    "Food",
    "Transport",
    "Groceries",
    "Subscription",
    "Shopping",
    "Utilities",
    "Healthcare",
    "Education",
    "Entertainment",
    "Other",
]


def infer_category(merchant: str, items: list[str]) -> str:
    normalized = (merchant or "").strip().lower()
    if normalized in MERCHANT_CATEGORY_MAP:
        return MERCHANT_CATEGORY_MAP[normalized]
    text = " ".join([merchant, *items]).strip() or "unknown purchase"
    if pipeline is None:
        # Transformers is optional at runtime. Unknown merchants remain explicit
        # instead of silently receiving a low-confidence category.
        return "Uncategorized"
    try:
        classifier = pipeline("zero-shot-classification")
        result = classifier(text, CANDIDATE_LABELS)
        labels = result.get("labels", [])
        scores = result.get("scores", [])
        if labels and scores and float(scores[0]) >= ZERO_SHOT_CONFIDENCE_THRESHOLD:
            return str(labels[0])
    except Exception:
        return "Uncategorized"
    return "Uncategorized"


def _hash_file(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _field_value(extraction: ExtractionResult, name: str) -> Any:
    return getattr(extraction, name).value


def extraction_to_transaction(extraction: ExtractionResult, file_bytes: bytes, file_name: str) -> Transaction:
    items: list[LineItem] = extraction.items.value or []
    merchant = _field_value(extraction, "merchant")
    item_names = [item.name for item in items]
    category = infer_category(str(merchant or ""), item_names)
    total = _field_value(extraction, "total")
    return Transaction(
        merchant=merchant,
        date=_field_value(extraction, "date"),
        items=items,
        subtotal=_field_value(extraction, "subtotal"),
        tax=_field_value(extraction, "tax"),
        total=float(total) if total is not None else 0.0,
        category=category,
        payment_method=_field_value(extraction, "payment_method"),
        bill_number=_field_value(extraction, "bill_number"),
        upload_timestamp=datetime.now(timezone.utc).isoformat(),
        file_name=file_name,
        file_hash=_hash_file(file_bytes),
        is_anomaly=False,
        anomaly_score=0.0,
        raw_ocr_text=extraction.raw_ocr_text,
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def persist_transaction(transaction: Transaction, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(target) + ".lock")
    with lock:
        data = _read_json_list(target)
        data.append(transaction.to_json_dict())
        tmp_path = Path(str(target) + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp_path, target)


def load_transactions(path: str) -> list[Transaction]:
    target = Path(path)
    lock = FileLock(str(target) + ".lock")
    with lock:
        records = _read_json_list(target)
    transactions: list[Transaction] = []
    for record in records:
        try:
            transactions.append(Transaction.model_validate(record))
        except Exception:
            continue
    return transactions


def write_transactions(transactions: list[Transaction], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(target) + ".lock")
    with lock:
        tmp_path = Path(str(target) + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump([transaction.to_json_dict() for transaction in transactions], handle, indent=2)
        os.replace(tmp_path, target)
