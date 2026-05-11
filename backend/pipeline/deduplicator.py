from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from backend.config import (
    DUPLICATE_AMOUNT_TOLERANCE,
    DUPLICATE_DATE_TOLERANCE_DAYS,
    DUPLICATE_EXACT_CONFIDENCE,
    DUPLICATE_FUZZY_CONFIDENCE,
    DUPLICATE_LOG_PATH,
    ATOMIC_REPLACE_RETRIES,
    ATOMIC_REPLACE_RETRY_DELAY_SECONDS,
)
from backend.models.transaction import Transaction


@dataclass(slots=True)
class DuplicateResult:
    is_duplicate: bool
    confidence: float
    matching_transaction_id: str | None


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def compute_transaction_fingerprint(transaction: Transaction) -> str:
    merchant = (transaction.merchant or "").lower()
    payload = f"{merchant}|{transaction.date}|{round(transaction.total, 2)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value[:10])
        except ValueError:
            return None


def _within_one_percent(left: float, right: float) -> bool:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return left == right
    return abs(left - right) / denominator <= DUPLICATE_AMOUNT_TOLERANCE


def _within_one_day(left: str | None, right: str | None) -> bool:
    left_date = _parse_date(left)
    right_date = _parse_date(right)
    if left_date is None or right_date is None:
        return False
    return abs((left_date.date() - right_date.date()).days) <= DUPLICATE_DATE_TOLERANCE_DAYS


def _read_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _atomic_write_log(path: Path, data: list[dict[str, object]]) -> None:
    tmp_path = Path(str(path) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    for attempt in range(ATOMIC_REPLACE_RETRIES):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == ATOMIC_REPLACE_RETRIES - 1:
                raise
            time.sleep(ATOMIC_REPLACE_RETRY_DELAY_SECONDS)


def log_duplicate_decision(
    transaction: Transaction,
    result: DuplicateResult,
    reason: str,
    path: Path = DUPLICATE_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        data = _read_log(path)
        data.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "transaction_id": str(transaction.id),
                "is_duplicate": result.is_duplicate,
                "confidence": result.confidence,
                "matching_transaction_id": result.matching_transaction_id,
                "reason": reason,
            }
        )
        _atomic_write_log(path, data)


def append_duplicate_resolution(transaction_id: str, confirmed: bool, path: Path = DUPLICATE_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        data = _read_log(path)
        data.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "transaction_id": transaction_id,
                "confirmed": confirmed,
                "reason": "user_confirmation",
            }
        )
        _atomic_write_log(path, data)


def check_duplicate(transaction: Transaction, existing: list[Transaction]) -> DuplicateResult:
    if transaction.file_hash:
        for candidate in existing:
            if candidate.file_hash and candidate.file_hash == transaction.file_hash:
                result = DuplicateResult(True, DUPLICATE_EXACT_CONFIDENCE, str(candidate.id))
                log_duplicate_decision(transaction, result, "exact_file_hash")
                return result

    current_fingerprint = compute_transaction_fingerprint(transaction)
    for candidate in existing:
        if compute_transaction_fingerprint(candidate) == current_fingerprint:
            result = DuplicateResult(True, DUPLICATE_EXACT_CONFIDENCE, str(candidate.id))
            log_duplicate_decision(transaction, result, "exact_fingerprint")
            return result

    for candidate in existing:
        same_merchant = (transaction.merchant or "").lower() == (candidate.merchant or "").lower()
        if (
            same_merchant
            and _within_one_percent(transaction.total, candidate.total)
            and _within_one_day(transaction.date, candidate.date)
        ):
            result = DuplicateResult(True, DUPLICATE_FUZZY_CONFIDENCE, str(candidate.id))
            log_duplicate_decision(transaction, result, "fuzzy_merchant_amount_date")
            return result

    result = DuplicateResult(False, 0.0, None)
    log_duplicate_decision(transaction, result, "no_match")
    return result
