from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta
from pathlib import Path
from typing import TypedDict

from faker import Faker
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "synthetic_bills"
GROUND_TRUTH_PATH = ROOT / "ground_truth.json"

MERCHANTS = [
    "Zomato",
    "Swiggy",
    "Amazon",
    "Flipkart",
    "Netflix",
    "Spotify",
    "Uber",
    "Ola",
    "BigBasket",
    "Blinkit",
    "Myntra",
    "IRCTC",
]

CATEGORY_MAP = {
    "Zomato": "Food",
    "Swiggy": "Food",
    "Amazon": "Shopping",
    "Flipkart": "Shopping",
    "Netflix": "Subscription",
    "Spotify": "Subscription",
    "Uber": "Transport",
    "Ola": "Transport",
    "BigBasket": "Food",
    "Blinkit": "Food",
    "Myntra": "Shopping",
    "IRCTC": "Transport",
}

PAYMENT_METHODS = ["UPI", "Card", "Cash"]
ITEM_WORDS = ["Meal", "Ride", "Order", "Plan", "Ticket", "Cart", "Grocery", "Delivery"]


class BillRecord(TypedDict):
    file_name: str
    bill_id: str
    merchant: str
    date: str
    amount: float
    subtotal: float
    tax: float
    category: str
    payment_method: str
    bill_number: str
    is_anomaly: bool
    is_duplicate_of: str | None


def _atomic_write_json(path: Path, data: object) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp_path, path)


def _amount_parts(total: float) -> tuple[float, float]:
    subtotal = round(total / 1.18, 2)
    tax = round(total - subtotal, 2)
    return subtotal, tax


def _build_items(merchant: str, total: float) -> list[tuple[str, int, float, float]]:
    first = round(total * 0.45, 2)
    second = round(total * 0.30, 2)
    third = round(total - first - second, 2)
    return [
        (f"{merchant} {ITEM_WORDS[0]}", 1, first, first),
        (f"{merchant} {ITEM_WORDS[1]}", 1, second, second),
        (f"{merchant} {ITEM_WORDS[2]}", 1, third, third),
    ]


def _draw_pdf(path: Path, record: BillRecord, items: list[tuple[str, int, float, float]]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 72
    c.setFont("Helvetica-Bold", 20)
    c.drawString(72, y, record["merchant"])
    y -= 28
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Invoice: {record['bill_number']}")
    y -= 18
    c.drawString(72, y, f"Date: {record['date']}")
    y -= 18
    c.drawString(72, y, "Bill To: FinSight Demo User")
    y -= 32
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Item")
    c.drawString(290, y, "Qty")
    c.drawString(350, y, "Unit")
    c.drawString(430, y, "Price")
    y -= 18
    c.setFont("Helvetica", 11)
    for name, qty, unit_price, line_total in items:
        c.drawString(72, y, name[:32])
        c.drawRightString(315, y, str(qty))
        c.drawRightString(390, y, f"{unit_price:.2f}")
        c.drawRightString(480, y, f"{line_total:.2f}")
        y -= 18
    y -= 12
    c.drawRightString(390, y, "Subtotal")
    c.drawRightString(480, y, f"{record['subtotal']:.2f}")
    y -= 18
    c.drawRightString(390, y, "GST 18%")
    c.drawRightString(480, y, f"{record['tax']:.2f}")
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(390, y, "Grand Total")
    c.drawRightString(480, y, f"{record['amount']:.2f}")
    y -= 24
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Payment Method: {record['payment_method']}")
    c.save()


def _make_record(index: int, merchant: str, total: float, is_anomaly: bool, duplicate_of: str | None = None) -> BillRecord:
    subtotal, tax = _amount_parts(total)
    bill_id = f"BILL-{index:04d}"
    bill_date = date.today() - timedelta(days=random.randint(0, 30))
    return {
        "file_name": f"{bill_id}.pdf",
        "bill_id": bill_id,
        "merchant": merchant,
        "date": bill_date.isoformat(),
        "amount": round(total, 2),
        "subtotal": subtotal,
        "tax": tax,
        "category": CATEGORY_MAP[merchant],
        "payment_method": random.choice(PAYMENT_METHODS),
        "bill_number": f"INV-{random.randint(1000, 9999)}-{random.randint(10, 99)}",
        "is_anomaly": is_anomaly,
        "is_duplicate_of": duplicate_of,
    }


def generate() -> list[BillRecord]:
    random.seed(42)
    Faker.seed(42)
    Faker("en_IN")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for pdf in PDF_DIR.glob("*.pdf"):
        pdf.unlink()

    records: list[BillRecord] = []
    index = 1
    for _ in range(30):
        merchant = random.choice(MERCHANTS)
        total = random.uniform(50, 3000)
        record = _make_record(index, merchant, total, is_anomaly=False)
        _draw_pdf(PDF_DIR / record["file_name"], record, _build_items(merchant, record["amount"]))
        records.append(record)
        index += 1

    for _ in range(5):
        merchant = random.choice(MERCHANTS)
        total = random.uniform(8000, 15000)
        record = _make_record(index, merchant, total, is_anomaly=True)
        _draw_pdf(PDF_DIR / record["file_name"], record, _build_items(merchant, record["amount"]))
        records.append(record)
        index += 1

    base = _make_record(index, "Zomato", 742.50, is_anomaly=False)
    base["file_name"] = f"{base['bill_id']}.pdf"
    items = _build_items(base["merchant"], base["amount"])
    _draw_pdf(PDF_DIR / base["file_name"], base, items)
    records.append(base)
    index += 1

    duplicate: BillRecord = dict(base)  # type: ignore[assignment]
    duplicate["bill_id"] = f"BILL-{index:04d}"
    duplicate["file_name"] = f"{duplicate['bill_id']}.pdf"
    duplicate["is_duplicate_of"] = base["bill_id"]
    _draw_pdf(PDF_DIR / duplicate["file_name"], duplicate, items)
    records.append(duplicate)

    _atomic_write_json(GROUND_TRUTH_PATH, records)
    return records


if __name__ == "__main__":
    created = generate()
    print(f"Generated {len(created)} PDFs and {GROUND_TRUTH_PATH.name}")
