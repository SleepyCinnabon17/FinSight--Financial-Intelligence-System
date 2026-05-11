from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient

from backend import config
from backend import main


def _client_store(monkeypatch, tmp_path: Path) -> TestClient:
    store = tmp_path / "transactions.json"
    store.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "TRANSACTIONS_PATH", store)
    main.PENDING_UPLOADS.clear()
    return TestClient(main.app)


def _sample_image(index: int = 0) -> Path:
    return sorted(Path("synthetic/synthetic_bill_images").glob("BILL-*.png"))[index]


def test_upload_ocr_extraction_confirm_and_discard_flow(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "OCR_FIXTURE_METADATA_ENABLED", True)
    client = _client_store(monkeypatch, tmp_path)

    confirm_image = _sample_image(0)
    upload = client.post(
        "/api/v1/upload",
        files=[("files", (confirm_image.name, confirm_image.read_bytes(), "image/png"))],
    )
    assert upload.status_code == 200
    upload_result = upload.json()["data"][0]
    assert upload_result["upload_id"]
    assert upload_result["extraction"]["merchant"]["value"]
    assert upload_result["extraction"]["total"]["value"] is not None

    confirm = client.post(
        "/api/v1/transactions/confirm",
        json={
            "upload_id": upload_result["upload_id"],
            "extraction_result": upload_result["extraction"],
            "user_edits": {"merchant": "Confirmed Merchant"},
        },
    )
    assert confirm.status_code == 200
    confirmed_transaction = confirm.json()["data"]
    assert confirmed_transaction["merchant"] == "Confirmed Merchant"
    assert confirmed_transaction["user_confirmed"] is True

    persisted = client.get("/api/v1/transactions")
    assert persisted.status_code == 200
    assert [row["id"] for row in persisted.json()["data"]] == [confirmed_transaction["id"]]

    discard_image = _sample_image(1)
    second_upload = client.post(
        "/api/v1/upload",
        files=[("files", (discard_image.name, discard_image.read_bytes(), "image/png"))],
    )
    assert second_upload.status_code == 200
    discard_upload_id = second_upload.json()["data"][0]["upload_id"]

    discard = client.post("/api/v1/transactions/discard", json={"upload_id": discard_upload_id})
    assert discard.status_code == 200
    assert discard.json()["data"] == {"discarded": True}
    assert discard_upload_id not in main.PENDING_UPLOADS
    assert len(client.get("/api/v1/transactions").json()["data"]) == 1


def test_nova_sse_stream_connects_receives_tokens_and_closes_cleanly(monkeypatch, tmp_path: Path) -> None:
    client = _client_store(monkeypatch, tmp_path)

    async def fake_nova_chat(message: str, history: list[dict[str, str]], transactions: object) -> AsyncIterator[str]:
        assert message == "stream please"
        assert history == []
        del transactions
        yield "Hel"
        yield "lo"

    monkeypatch.setattr(main, "nova_chat", fake_nova_chat)

    with client.stream("POST", "/api/v1/chat", json={"message": "stream please", "conversation_history": []}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        chunks = list(response.iter_text())

    body = "".join(chunks)
    assert "data: Hel\n\n" in body
    assert "data: lo\n\n" in body
