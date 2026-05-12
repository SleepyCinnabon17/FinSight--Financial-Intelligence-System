from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend import config
from backend.main import app


def _client_store(monkeypatch, tmp_path: Path) -> TestClient:
    store = tmp_path / "transactions.json"
    store.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "TRANSACTIONS_PATH", store)
    return TestClient(app)


def test_upload_valid_png_returns_extraction(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    image = sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[0]
    response = client.post("/api/v1/upload", files=[("files", (image.name, image.read_bytes(), "image/png"))])
    assert response.status_code == 200
    assert response.json()["data"][0]["extraction"]


def test_upload_large_file_returns_413(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * (config.UPLOAD_MAX_SIZE_MB * 1024 * 1024 + 1)
    response = client.post("/api/v1/upload", files=[("files", ("big.png", payload, "image/png"))])
    assert response.status_code == 413


def test_upload_txt_returns_415(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    response = client.post("/api/v1/upload", files=[("files", ("bad.txt", b"text", "text/plain"))])
    assert response.status_code == 415


def test_confirm_get_delete_transaction(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    image = sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[0]
    upload = client.post("/api/v1/upload", files=[("files", (image.name, image.read_bytes(), "image/png"))]).json()["data"][0]
    confirm = client.post("/api/v1/transactions/confirm", json={"upload_id": upload["upload_id"], "extraction_result": upload["extraction"], "user_edits": None})
    assert confirm.status_code == 200
    transaction_id = confirm.json()["data"]["id"]
    assert client.get("/api/v1/transactions").status_code == 200
    assert client.delete(f"/api/v1/transactions/{transaction_id}").status_code == 200
    assert client.get("/api/v1/transactions").json()["data"] == []


def test_confirm_accepts_blank_optional_ui_numeric_edits(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    extraction = {
        "merchant": {"value": "UI Store", "confidence": 1.0, "raw_text": "UI Store"},
        "date": {"value": "2026-05-01", "confidence": 1.0, "raw_text": "2026-05-01"},
        "items": {"value": [], "confidence": 1.0, "raw_text": ""},
        "subtotal": {"value": None, "confidence": 0.0, "raw_text": ""},
        "tax": {"value": None, "confidence": 0.0, "raw_text": ""},
        "total": {"value": 25.0, "confidence": 1.0, "raw_text": "25"},
        "payment_method": {"value": None, "confidence": 0.0, "raw_text": ""},
        "bill_number": {"value": None, "confidence": 0.0, "raw_text": ""},
        "raw_ocr_text": "UI Store",
        "metadata": {"file_name": "ui-confirm.txt"},
    }
    response = client.post(
        "/api/v1/transactions/confirm",
        json={
            "extraction_result": extraction,
            "user_edits": {
                "merchant": "UI Store",
                "date": "2026-05-01",
                "subtotal": "",
                "tax": "",
                "total": "25.0",
                "payment_method": "",
                "bill_number": "",
            },
        },
    )
    assert response.status_code == 200, response.text
    transaction = response.json()["data"]
    assert transaction["subtotal"] is None
    assert transaction["tax"] is None
    assert transaction["total"] == 25.0


def test_expired_pending_upload_cannot_be_confirmed(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    image = sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[0]
    upload = client.post("/api/v1/upload", files=[("files", (image.name, image.read_bytes(), "image/png"))]).json()["data"][0]
    monkeypatch.setattr(config, "PENDING_UPLOAD_TTL_SECONDS", -1)
    confirm = client.post("/api/v1/transactions/confirm", json={"upload_id": upload["upload_id"], "extraction_result": upload["extraction"], "user_edits": None})
    assert confirm.status_code == 404
    assert confirm.json()["error"]["message"] == "Upload session expired or not found."


def test_confirm_sanitizes_user_edits_before_persistence(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    extraction = {
        "merchant": {"value": "Original Store", "confidence": 1.0, "raw_text": "Original Store"},
        "date": {"value": "2026-05-01", "confidence": 1.0, "raw_text": "2026-05-01"},
        "items": {"value": [], "confidence": 1.0, "raw_text": ""},
        "subtotal": {"value": 100.0, "confidence": 1.0, "raw_text": "100"},
        "tax": {"value": 0.0, "confidence": 1.0, "raw_text": "0"},
        "total": {"value": 100.0, "confidence": 1.0, "raw_text": "100"},
        "payment_method": {"value": "Card", "confidence": 1.0, "raw_text": "Card"},
        "bill_number": {"value": "INV-123/45", "confidence": 1.0, "raw_text": "INV-123/45"},
        "raw_ocr_text": "Original Store",
        "metadata": {"file_name": "manual.txt"},
    }
    response = client.post(
        "/api/v1/transactions/confirm",
        json={
            "extraction_result": extraction,
            "user_edits": {
                "merchant": "<script>alert(1)</script>   Valid     Store",
                "category": "  Food   <b>Priority</b> ",
                "payment_method": "<img src=x> UPI",
                "bill_number": "INV-123/45",
                "total": "123.45",
            },
        },
    )
    assert response.status_code == 200
    transaction = response.json()["data"]
    assert "<" not in transaction["merchant"]
    assert transaction["merchant"] == "alert(1) Valid Store"
    assert transaction["category"] == "Food Priority"
    assert transaction["payment_method"] == "UPI"
    assert transaction["bill_number"] == "INV-123/45"
    assert transaction["total"] == 123.45


def test_analysis_chat_news_health(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)
    assert client.get("/api/v1/analysis").status_code == 200
    chat = client.post("/api/v1/chat", json={"message": "Hello", "conversation_history": []})
    assert chat.status_code == 200
    assert "text/event-stream" in chat.headers["content-type"]
    news = client.get("/api/v1/news")
    assert news.status_code in {200, 503}
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/v1/health/live").status_code == 200


def test_benchmark_results_endpoint_reads_generated_json(monkeypatch, tmp_path: Path) -> None:
    results_path = tmp_path / "results.json"
    results_path.write_text('{"summary": {"ocr_accuracy": 0.95}}', encoding="utf-8")
    monkeypatch.setattr(config, "BENCHMARK_RESULTS_PATH", results_path)
    client = TestClient(app)

    response = client.get("/api/v1/benchmark/results")

    assert response.status_code == 200
    assert response.json()["data"]["summary"]["ocr_accuracy"] == 0.95


def test_benchmark_results_endpoint_handles_missing_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "BENCHMARK_RESULTS_PATH", tmp_path / "missing-results.json")
    client = TestClient(app)

    response = client.get("/api/v1/benchmark/results")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "benchmark_results_unavailable"
