from __future__ import annotations

from backend.models.transaction import Transaction
from backend.pipeline import deduplicator
from backend.pipeline.deduplicator import check_duplicate, compute_file_hash, compute_transaction_fingerprint


def test_same_file_bytes_same_hash() -> None:
    assert compute_file_hash(b"abc") == compute_file_hash(b"abc")


def test_same_merchant_date_total_same_fingerprint() -> None:
    left = Transaction(merchant="Zomato", date="2026-05-01", total=100.0)
    right = Transaction(merchant="zomato", date="2026-05-01", total=100.0)
    assert compute_transaction_fingerprint(left) == compute_transaction_fingerprint(right)


def test_check_duplicate_exact_match(monkeypatch) -> None:
    monkeypatch.setattr(deduplicator, "log_duplicate_decision", lambda *args, **kwargs: None)
    existing = Transaction(merchant="Zomato", date="2026-05-01", total=100.0)
    current = Transaction(merchant="Zomato", date="2026-05-01", total=100.0)
    result = check_duplicate(current, [existing])
    assert result.is_duplicate is True
    assert result.confidence == 1.0


def test_check_duplicate_fuzzy_match(monkeypatch) -> None:
    monkeypatch.setattr(deduplicator, "log_duplicate_decision", lambda *args, **kwargs: None)
    existing = Transaction(merchant="Zomato", date="2026-05-01", total=100.0)
    current = Transaction(merchant="Zomato", date="2026-05-01", total=100.5)
    result = check_duplicate(current, [existing])
    assert result.is_duplicate is True
    assert result.confidence == 0.85


def test_check_duplicate_different_transaction(monkeypatch) -> None:
    monkeypatch.setattr(deduplicator, "log_duplicate_decision", lambda *args, **kwargs: None)
    existing = Transaction(merchant="Zomato", date="2026-05-01", total=100.0)
    current = Transaction(merchant="Swiggy", date="2026-05-03", total=200.0)
    result = check_duplicate(current, [existing])
    assert result.is_duplicate is False
