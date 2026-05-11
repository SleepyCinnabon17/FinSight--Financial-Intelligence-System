from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.models.extraction import LineItem


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Transaction(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    merchant: str | None = None
    date: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float
    category: str = "Uncategorized"
    payment_method: str | None = None
    bill_number: str | None = None
    upload_timestamp: str = Field(default_factory=_utc_now_iso)
    file_name: str | None = None
    file_hash: str | None = None
    is_anomaly: bool = False
    anomaly_score: float = 0.0
    anomaly_reason: str | None = None
    is_duplicate: bool = False
    duplicate_of: str | None = None
    user_confirmed: bool = False
    manually_edited: bool = False
    raw_ocr_text: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
