# FinSight — Software Requirements Specification
**Version:** 2.0  
**Project:** FinSight — Financial Intelligence System  
**Type:** GenAI Document Understanding + Financial Analytics Web Application  
**Date:** May 2026  
**Changes from v1.0:** Added financial news ingestion module (§10.5), Nova web search tool (§10.6), NewsContext data model (§12.5), updated Nova system prompt (§10.3), updated API endpoint (§11.2), updated requirements.txt (§17.3), updated directory structure (§18), updated tech stack (§19).

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [System Architecture](#3-system-architecture)
4. [Dataset Specifications](#4-dataset-specifications)
5. [Synthetic Data Generation](#5-synthetic-data-generation)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Pipeline Stage Specifications](#8-pipeline-stage-specifications)
9. [Frontend Requirements](#9-frontend-requirements)
10. [Chatbot — Nova](#10-chatbot--nova)
11. [API Design](#11-api-design)
12. [Data Models](#12-data-models)
13. [Error Handling & Edge Cases](#13-error-handling--edge-cases)
14. [External Integrations](#14-external-integrations)
15. [Security Requirements](#15-security-requirements)
16. [Testing Requirements](#16-testing-requirements)
17. [Deployment Requirements](#17-deployment-requirements)
18. [File & Directory Structure](#18-file--directory-structure)
19. [Dependencies & Tech Stack](#19-dependencies--tech-stack)
20. [Known Limitations & Assumptions](#20-known-limitations--assumptions)

---

## 1. Introduction

### 1.1 Purpose
This document specifies all functional, non-functional, technical, and design requirements for FinSight — a multi-stage AI pipeline that processes uploaded bill images, extracts structured financial data, detects anomalies, analyzes spending patterns, and provides real-time investment suggestions through a chatbot interface named Nova. Nova's investment suggestions are grounded in both live market data and current financial news.

### 1.2 Scope
FinSight is a web application. The user uploads a bill image or PDF. The system runs it through an OCR → key-value extraction → transaction structuring → analysis → chatbot pipeline and presents insights on a dashboard. The system must work end-to-end in a browser with a Python/FastAPI backend.

### 1.3 Definitions

| Term | Definition |
|------|------------|
| Bill | Any scanned or photographed receipt, invoice, utility bill, or payment confirmation |
| Transaction | A single extracted financial event with merchant, amount, date, category, and metadata |
| Soft label | Probabilistic annotation (used in FUNSD-style training context) |
| OCR | Optical Character Recognition — converting image pixels to text |
| KIE | Key Information Extraction — identifying specific fields from OCR output |
| Nova | The FinSight chatbot agent that provides financial advice |
| Ground truth | The known-correct extraction used for benchmarking |
| Anomaly | A transaction whose amount, frequency, or pattern deviates significantly from baseline |
| Duplicate | Two bill uploads that correspond to the same real-world transaction |
| NewsContext | A structured object containing summarized financial headlines and their relevance to investment decisions |
| Web search tool | A tool available to Nova's LLM to fetch live search results when answering investment queries |

### 1.4 Overview of Document
Section 3 defines overall architecture. Sections 6–10 define detailed requirements per component. Sections 13–16 define edge cases, integrations, security, and testing.

---

## 2. Overall Description

### 2.1 Product Perspective
FinSight is a standalone web application with a Python backend and a browser-based frontend. It does not integrate with banking APIs or require user authentication in v1. All uploaded files are processed locally. Nova's investment suggestions combine user spending analysis, live market prices, and live financial news context.

### 2.2 User Classes

| User | Description | Primary Actions |
|------|-------------|-----------------|
| End User | A person managing personal finances | Upload bills, view dashboard, ask Nova questions |
| Demo Evaluator | Instructor or reviewer assessing the project | Upload synthetic bills, inspect extraction accuracy, test edge cases |

### 2.3 Operating Environment
- Backend: Python 3.10+, FastAPI, runs locally or on any Linux server
- Frontend: Single-page application served by FastAPI static files or a separate dev server
- Browser: Chrome 120+, Firefox 120+, Safari 17+ (mobile Safari included)
- GPU: Optional. All models must have CPU fallback paths.
- OS: macOS, Ubuntu 22.04+, Windows 11 (WSL2 recommended)
- Internet: Required for news fetching and market data. Graceful offline fallback required for both.

### 2.4 Constraints
- No paid external APIs are mandatory. All AI models must have a free/open-source option.
- News fetching uses free RSS/public APIs only (no NewsAPI paid tier required).
- The system must work fully offline except for market data and news features (both have graceful offline fallbacks).
- Maximum upload file size: 10 MB per file.
- The system is not HIPAA/GDPR compliant in v1 — no PII storage guarantees.

---

## 3. System Architecture

### 3.1 High-Level Pipeline

```
User Upload (image/PDF)
        │
        ▼
[Stage 1] Preprocessing
  - Format detection (PDF vs image)
  - PDF → image conversion (pdf2image)
  - Image normalization (deskew, contrast, resize)
  - Messy bill detection → enhancement path
        │
        ▼
[Stage 2] OCR
  - PaddleOCR (primary)
  - Fallback: pytesseract
  - Output: list of (text, bounding_box, confidence) tuples
        │
        ▼
[Stage 3] Key Information Extraction (KIE)
  - CORD model for receipts (item-level)
  - SROIE model for invoices (header-level: total, date, vendor, address)
  - FUNSD-style field labeling for unknown formats
  - Output: structured dict {merchant, date, items[], subtotal, tax, total, payment_method}
        │
        ▼
[Stage 4] Transaction Structuring
  - Map extracted fields to Transaction schema
  - Category inference (rule-based + ML)
  - Duplicate detection (hash + fuzzy match)
  - Anomaly scoring
  - Output: Transaction object saved to local JSON store
        │
        ▼
[Stage 5] Analysis Engine
  - Spending trends (by category, by merchant, by time period)
  - Monthly budget comparison
  - Anomaly flagging with explanation
  - Savings opportunity detection
  - Output: AnalysisResult object
        │
        ▼
[Stage 6] Nova Chatbot
  - Context: full transaction history + current analysis
  - News context: summarized financial headlines (fetched + cached)
  - Market data: NIFTY 50, mutual fund NAVs, FD rates
  - Web search tool: Nova can trigger live search for specific investment queries
  - Capabilities: Q&A on spending, investment suggestions grounded in current affairs, savings tips
  - Output: streamed text response
        │
        ▼
[Frontend Dashboard]
  - Upload interface
  - Extraction result preview (with edit capability)
  - Transaction history table
  - Charts (category breakdown, trend line, anomaly markers)
  - Nova chat panel
```

### 3.2 Component Map

```
finsight/
├── backend/
│   ├── main.py                  ← FastAPI app, all routes
│   ├── config.py                ← All configuration and env vars
│   ├── pipeline/
│   │   ├── preprocess.py        ← image normalization
│   │   ├── ocr.py               ← PaddleOCR + fallback
│   │   ├── kie.py               ← CORD/SROIE/FUNSD extraction
│   │   ├── structurer.py        ← Transaction schema mapping
│   │   ├── analyzer.py          ← spending analysis
│   │   └── deduplicator.py      ← duplicate detection
│   ├── models/
│   │   ├── transaction.py       ← Pydantic Transaction model
│   │   ├── analysis.py          ← Pydantic AnalysisResult model
│   │   ├── extraction.py        ← Pydantic ExtractionResult model
│   │   └── news.py              ← Pydantic NewsContext model
│   ├── chatbot/
│   │   ├── nova.py              ← Nova chatbot logic + web search tool
│   │   ├── market.py            ← Market data fetcher + cache
│   │   └── news.py              ← Financial news fetcher + summarizer + cache
│   ├── data/
│   │   ├── transactions.json    ← persisted transaction store
│   │   ├── duplicate_log.json   ← duplicate decisions
│   │   ├── market_cache.json    ← cached market data
│   │   └── news_cache.json      ← cached news summaries
│   └── benchmarks/
│       └── evaluate.py          ← extraction accuracy metrics
├── synthetic/
│   ├── generate_bills.py        ← PDF bill generator
│   ├── pdf_to_images.py         ← PDF → PNG converter
│   └── make_messy.py            ← image degradation
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── tests/
    ├── test_ocr.py
    ├── test_kie.py
    ├── test_structurer.py
    ├── test_deduplicator.py
    ├── test_analyzer.py
    ├── test_news.py
    └── test_api.py
```

---

## 4. Dataset Specifications

### 4.1 CORD (naver-clova-ix/cord-v2)

**Source:** HuggingFace — `naver-clova-ix/cord-v2`  
**Purpose:** Train/fine-tune receipt OCR and item-level key-value extraction  
**Contents:** 800 train / 100 validation / 100 test Indonesian receipt images with full bounding box annotations at token, line, and field level  
**Fields annotated:** menu.nm (item name), menu.unitprice, menu.cnt, menu.price, subtotal.subtotal_price, total.total_price, total.tax_price, total.cashprice  
**Usage in FinSight:**
- Use as reference for receipt format understanding
- Fine-tune or prompt-engineer the KIE model to extract equivalent fields from Indian merchant bills (Zomato, Swiggy, Amazon, etc.)
- Use CORD's field taxonomy as the canonical schema for item-level extraction

**Loading:**
```python
from datasets import load_dataset
cord = load_dataset("naver-clova-ix/cord-v2")
```

**Edge cases in CORD:**
- Some receipts have no tax field — handle None gracefully
- Item counts can be fractional (e.g. 0.5 kg) — store as float not int
- Currency is IDR — normalize to INR for FinSight or treat amounts as unitless floats

### 4.2 FUNSD (nielsr/funsd)

**Source:** HuggingFace — `nielsr/funsd`  
**Purpose:** Document structure understanding — learning which text regions are questions vs answers vs headers vs other  
**Contents:** 199 noisy scanned documents with word-level bounding boxes and semantic labels: header, question, answer, other  
**Usage in FinSight:**
- Use FUNSD-style labeling logic for unknown bill formats where CORD/SROIE models do not match
- When a bill does not match known receipt/invoice patterns, apply the FUNSD label taxonomy to identify which OCR text blocks are field labels (questions) and which are values (answers)
- Key/value pairing: "Total" (question) → "₹2,500" (answer)

**Loading:**
```python
from datasets import load_dataset
funsd = load_dataset("nielsr/funsd")
```

**Edge cases in FUNSD:**
- Documents are heavily degraded — OCR confidence will be low; apply confidence threshold filtering (minimum 0.6)
- Multi-word field labels span multiple bounding boxes — merge adjacent "question" tokens before pairing

### 4.3 SROIE (jsdnrs/ICDAR2019-SROIE)

**Source:** HuggingFace — `jsdnrs/ICDAR2019-SROIE`  
**Purpose:** Receipt key information extraction — company name, date, address, total  
**Contents:** 626 train / 347 test scanned receipts with character-level bounding boxes and field-level annotations for exactly 4 fields: company, date, address, total  
**Usage in FinSight:**
- Primary model for header-level extraction (merchant name, date, grand total)
- Use as evaluation benchmark: run FinSight's KIE on SROIE test set and report character-level F1

**Loading:**
```python
from datasets import load_dataset
sroie = load_dataset("jsdnrs/ICDAR2019-SROIE")
```

**Edge cases in SROIE:**
- Date formats vary widely: "01/05/2019", "1 MAY 2019", "05-01-2019" — normalize all dates to ISO 8601 (YYYY-MM-DD)
- Total field sometimes includes currency symbol, sometimes not — strip symbols before float conversion
- Address field is multiline — join with comma or newline, store as single string
- Some SROIE images are rotated — apply deskew before OCR

---

## 5. Synthetic Data Generation

### 5.1 Purpose
Synthetic bills are used to benchmark the pipeline with known ground truth, demonstrate messy-input handling, and populate the dashboard for demo purposes.

### 5.2 Approach 1 — Programmatic PDF Bills

Generate 30 normal bills + 5 anomaly bills + 2 duplicates = 37 bills minimum.

**Merchants:** Zomato, Swiggy, Amazon, Flipkart, Netflix, Spotify, Uber, Ola, BigBasket, Blinkit, Myntra, IRCTC

**Categories:**
```
Food: Zomato, Swiggy, BigBasket, Blinkit
Transport: Uber, Ola, IRCTC
Subscription: Netflix, Spotify
Shopping: Amazon, Flipkart, Myntra
```

**Normal bill fields:** Bill number (INV-XXXX-XX format), merchant name, date (last 30 days), category, subtotal, GST 18%, total, payment method (UPI/Card/Cash)

**Anomaly bills:** Amount 8,000–15,000 INR (well above normal range of 50–3,000)

**Duplicate bills:** Identical content, different filenames — tests deduplication

**Ground truth JSON schema:**
```json
{
  "bill_id": "bill_0",
  "merchant": "Zomato",
  "date": "2026-04-15",
  "amount": 354.00,
  "subtotal": 300.00,
  "tax": 54.00,
  "category": "Food",
  "payment_method": "UPI",
  "bill_number": "INV-4521-ZA",
  "is_anomaly": false,
  "is_duplicate_of": null
}
```

### 5.3 Approach 2 — Image Bills (OCR Test)

Convert PDFs to PNG at 150 DPI using pdf2image. Lower DPI creates harder OCR challenge.

### 5.4 Approach 3 — Messy Bills

Apply to 10 bills:
- Random rotation ±3 degrees (simulates bad phone scan)
- Contrast reduction to 0.6–0.85 (simulates bad lighting)
- Gaussian blur radius 0.8 (simulates camera shake)

Save as `messy_{original_filename}.png` in same directory.

### 5.5 Benchmarking Against Ground Truth

After running synthetic bills through the pipeline, compute:
- **Field-level accuracy:** % of bills where each field (merchant, date, total, category) matches ground truth exactly
- **Anomaly detection recall:** % of anomaly bills correctly flagged
- **Duplicate detection precision:** % of detected duplicates that are true duplicates
- **Total extraction F1:** harmonic mean of precision and recall across all fields

Report these metrics in a `benchmarks/results.json` file.

---

## 6. Functional Requirements

### FR-1 Bill Upload
- FR-1.1: System shall accept file uploads in formats: JPEG, PNG, WEBP, PDF, HEIC
- FR-1.2: System shall reject files larger than 10 MB with a clear error message
- FR-1.3: System shall accept multiple files in a single upload (batch processing, max 10 files)
- FR-1.4: System shall display an upload progress indicator during processing
- FR-1.5: System shall show a preview thumbnail of the uploaded image before processing begins
- FR-1.6: System shall convert HEIC to JPEG before processing (using pillow-heif)
- FR-1.7: System shall convert multi-page PDFs — process only page 1 unless user requests all pages

### FR-2 Preprocessing
- FR-2.1: System shall detect and correct image rotation using deskew (target: within ±1 degree of horizontal)
- FR-2.2: System shall resize images to a maximum of 2048px on the longer dimension while preserving aspect ratio
- FR-2.3: System shall apply adaptive contrast normalization if mean pixel brightness < 80 or > 200
- FR-2.4: System shall detect if the image is blurry (Laplacian variance < 100) and apply sharpening
- FR-2.5: System shall detect if the image is a PDF and convert to PNG at 200 DPI before OCR

### FR-3 OCR
- FR-3.1: System shall extract all text from the preprocessed image using PaddleOCR
- FR-3.2: System shall return bounding boxes, text strings, and confidence scores for each detected text block
- FR-3.3: System shall filter out text blocks with confidence < 0.5
- FR-3.4: System shall fall back to pytesseract if PaddleOCR fails or returns 0 text blocks
- FR-3.5: System shall sort text blocks by reading order (top-to-bottom, left-to-right)
- FR-3.6: System shall merge text blocks on the same horizontal line within 10px vertical tolerance into a single line

### FR-4 Key Information Extraction
- FR-4.1: System shall extract the following fields from OCR output: merchant name, transaction date, line items (name + price), subtotal, tax amount, grand total, payment method
- FR-4.2: System shall use CORD-trained extraction logic for receipt-format bills (itemized purchases)
- FR-4.3: System shall use SROIE-trained extraction logic for invoice-format bills (single total with header info)
- FR-4.4: System shall apply FUNSD-style key-value pairing for unrecognized formats
- FR-4.5: System shall normalize all dates to YYYY-MM-DD ISO 8601 format
- FR-4.6: System shall strip currency symbols (₹, $, £, €, Rs.) from amount fields before conversion to float
- FR-4.7: System shall handle amounts with comma thousand separators (e.g., "1,250.00" → 1250.00)
- FR-4.8: System shall detect GST/tax fields by keyword matching: ["gst", "tax", "vat", "cgst", "sgst", "igst"]
- FR-4.9: System shall return a confidence score per extracted field (0.0–1.0)
- FR-4.10: System shall mark fields as "unextracted" (not null) when extraction confidence < 0.4

### FR-5 Transaction Structuring
- FR-5.1: System shall map extracted fields to the canonical Transaction schema (see Section 12.1)
- FR-5.2: System shall infer category from merchant name using a lookup table (see Section 5.2)
- FR-5.3: System shall apply ML-based category classification as fallback if merchant not in lookup table, using merchant name + item names as input
- FR-5.4: System shall assign a unique transaction ID (UUID4) to each new transaction
- FR-5.5: System shall record the upload timestamp separately from the transaction date
- FR-5.6: System shall persist transactions to `data/transactions.json` (append-only)

### FR-6 Duplicate Detection
- FR-6.1: System shall compute a content hash (SHA-256) of the raw image bytes to detect exact duplicate file uploads
- FR-6.2: System shall compute a transaction fingerprint: hash of (merchant + date + total) normalized to detect semantic duplicates
- FR-6.3: System shall flag a transaction as a probable duplicate if its fingerprint matches an existing transaction within a 1-day date window and amount within 1%
- FR-6.4: System shall not automatically discard duplicates — it shall mark them and present a confirmation dialog to the user
- FR-6.5: System shall log all duplicate decisions (confirmed/rejected by user) to `data/duplicate_log.json`

### FR-7 Anomaly Detection
- FR-7.1: System shall compute a per-category spending baseline from all non-anomaly transactions in the store
- FR-7.2: System shall flag a transaction as anomalous if its amount exceeds the category mean by more than 2 standard deviations
- FR-7.3: System shall flag a transaction as anomalous if it is from a merchant not seen in the last 90 days and its amount > ₹5,000
- FR-7.4: System shall flag a transaction as anomalous if the same merchant appears more than 3 times in a single day
- FR-7.5: System shall assign an anomaly score (0.0–1.0) and an anomaly reason string to each flagged transaction
- FR-7.6: System shall display anomaly flags visually on the dashboard (red border, warning icon)
- FR-7.7: System shall allow users to dismiss anomaly flags (mark as "known/expected")

### FR-8 Spending Analysis
- FR-8.1: System shall compute total spending per category for the current month and previous month
- FR-8.2: System shall compute total spending per merchant (top 5) for the last 30 days
- FR-8.3: System shall compute a daily spending trend line for the last 30 days
- FR-8.4: System shall detect spending categories that increased >20% month-over-month and surface them as insights
- FR-8.5: System shall compute a "savings opportunity" estimate: sum of discretionary category (Food, Shopping, Subscription) spending minus a configurable budget target
- FR-8.6: System shall output analysis results as a structured AnalysisResult object (see Section 12.2)

### FR-9 Dashboard
- FR-9.1: System shall display a category breakdown as a donut/pie chart
- FR-9.2: System shall display a daily spending trend line chart for the last 30 days
- FR-9.3: System shall display a transaction history table (sortable by date, amount, category)
- FR-9.4: System shall display extraction result for the most recently uploaded bill (field-by-field with confidence indicators)
- FR-9.5: System shall allow users to manually edit extracted fields before committing to the transaction store
- FR-9.6: System shall display anomaly-flagged transactions with visual distinction
- FR-9.7: System shall display the "where you lost money" view: a breakdown of spending by category with percentage of total spend
- FR-9.8: System shall be fully responsive (mobile + desktop)

### FR-10 Nova Chatbot
- FR-10.1: System shall provide a chat interface named "Nova" accessible from the main page
- FR-10.2: Nova shall have full context of all stored transactions and current analysis results
- FR-10.3: Nova shall respond to natural language questions about spending ("How much did I spend on food last month?")
- FR-10.4: Nova shall suggest investment options based on computed savings opportunity
- FR-10.5: Nova shall inject real-time market data (equity prices, FD rates, mutual fund NAVs) into its context when available
- FR-10.6: Nova shall have a graceful fallback when market data is unavailable (use cached data < 24 hours old, or decline to quote specific prices)
- FR-10.7: Nova shall stream its responses token-by-token to the frontend
- FR-10.8: Nova shall not hallucinate specific financial figures — all amounts cited must come from the transaction store or verified market data or news context
- FR-10.9: Nova shall include a disclaimer on investment suggestions: "This is not certified financial advice."
- **FR-10.10: Nova shall fetch and inject summarized financial news headlines into its context for every investment-related query**
- **FR-10.11: Nova shall use a web search tool to retrieve live, specific information when the user asks about a named investment instrument, sector, or recent financial event**
- **FR-10.12: Nova shall clearly attribute any news-based claim to its source (e.g., "According to recent reports...")**
- **FR-10.13: Nova shall not use news context to recommend individual stocks — it may use it to discuss sectors, macro trends, and general asset classes only**

### FR-11 Financial News Integration
- **FR-11.1: System shall fetch financial news headlines from at least two free sources on a configurable schedule (default: every 2 hours)**
- **FR-11.2: System shall summarize fetched headlines into a NewsContext object (see Section 12.5) using an LLM summarization call**
- **FR-11.3: System shall cache the NewsContext in `data/news_cache.json` with a timestamp**
- **FR-11.4: System shall provide a graceful fallback when news cannot be fetched: use cached NewsContext if < 24 hours old; otherwise Nova acknowledges it has no current news**
- **FR-11.5: System shall expose a `/api/v1/news` endpoint returning the current cached NewsContext**

---

## 7. Non-Functional Requirements

### NFR-1 Performance
- NFR-1.1: End-to-end processing time from upload to extraction result display: ≤ 10 seconds on CPU for a standard receipt image
- NFR-1.2: Nova response first token latency: ≤ 3 seconds
- NFR-1.3: Dashboard load time (all charts rendered): ≤ 2 seconds after page load
- NFR-1.4: Batch upload of 10 bills: ≤ 90 seconds total
- **NFR-1.5: News fetch + summarization: ≤ 15 seconds; runs as a background task, never on the critical path of a user request**

### NFR-2 Accuracy
- NFR-2.1: Field-level extraction accuracy on SROIE test set: ≥ 70% for total, date, company fields
- NFR-2.2: Duplicate detection precision on synthetic dataset: ≥ 95%
- NFR-2.3: Anomaly detection recall on synthetic anomaly bills: ≥ 80%
- NFR-2.4: Category classification accuracy on synthetic bills: ≥ 90% (merchant in lookup table)

### NFR-3 Reliability
- NFR-3.1: The system must not crash on any valid image upload — all exceptions must be caught and returned as structured error responses
- NFR-3.2: The system must not lose transaction data on backend restart — all writes to transactions.json must be atomic (write to temp file, then rename)
- NFR-3.3: OCR fallback must activate within 5 seconds of primary OCR timeout
- **NFR-3.4: News fetch failure must not affect any other system function — failure is silent and logged only**

### NFR-4 Usability
- NFR-4.1: Error messages must be human-readable and actionable (not stack traces)
- NFR-4.2: All loading states must have visible indicators (spinner or progress bar)
- NFR-4.3: The upload interface must support drag-and-drop in addition to file picker
- NFR-4.4: Extracted fields must be editable inline before final submission

### NFR-5 Maintainability
- NFR-5.1: Each pipeline stage must be independently testable with mock inputs
- NFR-5.2: All configuration values (thresholds, budget targets, model paths, news sources, news refresh interval) must be in a single `config.py` file, not hardcoded
- NFR-5.3: All API responses must follow a consistent envelope schema (see Section 11)

---

## 8. Pipeline Stage Specifications

### 8.1 Preprocessing Module (`pipeline/preprocess.py`)

**Inputs:** Raw file bytes + MIME type  
**Outputs:** Normalized PIL Image object

**Functions required:**
```python
def detect_format(file_bytes: bytes) -> str:
    # Returns: "pdf", "jpeg", "png", "webp", "heic"

def pdf_to_image(file_bytes: bytes, dpi: int = 200) -> Image:
    # Converts first page of PDF to PIL Image
    # Uses pdf2image.convert_from_bytes
    # Raises: PreprocessingError if conversion fails

def deskew(image: Image) -> Image:
    # Detects skew angle using Hough transform
    # Rotates to correct within ±1 degree
    # Uses: deskew library or cv2.HoughLines

def normalize_contrast(image: Image) -> Image:
    # Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # Only if mean brightness < 80 or > 200
    # Uses: cv2.createCLAHE

def sharpen_if_blurry(image: Image) -> Image:
    # Computes Laplacian variance
    # Applies unsharp mask if variance < 100

def resize_to_max(image: Image, max_dim: int = 2048) -> Image:
    # Preserves aspect ratio

def preprocess(file_bytes: bytes, mime_type: str) -> Image:
    # Orchestrates all above steps in order
```

### 8.2 OCR Module (`pipeline/ocr.py`)

**Inputs:** PIL Image  
**Outputs:** List of `OCRBlock(text, bbox, confidence)`

**Functions required:**
```python
@dataclass
class OCRBlock:
    text: str
    bbox: tuple  # (x1, y1, x2, y2)
    confidence: float

def run_paddleocr(image: Image) -> list[OCRBlock]:
    # PaddleOCR with lang="en"
    # Filters confidence < 0.5
    # Returns sorted by (y1, x1) reading order

def run_tesseract(image: Image) -> list[OCRBlock]:
    # Fallback using pytesseract
    # --psm 6 (uniform block of text)
    # Returns same OCRBlock format

def merge_line_blocks(blocks: list[OCRBlock], y_tolerance: int = 10) -> list[OCRBlock]:
    # Merges horizontally adjacent blocks on same line

def run_ocr(image: Image) -> list[OCRBlock]:
    # Tries PaddleOCR first
    # Falls back to tesseract if result is empty or raises exception
```

### 8.3 KIE Module (`pipeline/kie.py`)

**Inputs:** List of OCRBlock  
**Outputs:** `ExtractionResult` (see Section 12.3)

**Format detection logic:**
```
IF blocks contain item-price pattern (multiple lines with amounts) → receipt format → CORD path
ELSE IF blocks contain "invoice" or "bill to" keyword → invoice format → SROIE path
ELSE → unknown format → FUNSD path
```

**CORD path:** Look for sequences of (item_name, quantity, unit_price, line_total) patterns using regex + positional logic

**SROIE path:** Use regex + keyword proximity to extract:
- Company: first bold/large text block OR block nearest to top-center
- Date: block matching date regex patterns
- Total: block following "total" / "grand total" / "amount due" keyword
- Address: block following company name

**FUNSD path:**
- Label each block as Q (question/label) or A (answer/value) based on:
  - Q indicators: ends with ":", is short (< 4 words), is followed by a colon
  - A indicators: contains digits, currency symbols, or is to the right of a Q
- Pair adjacent Q→A blocks
- Map pairs to ExtractionResult fields by keyword matching Q text

**Date normalization:** handle formats:
- DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD
- DD Mon YYYY (e.g., "15 Apr 2026")
- DD-MM-YYYY
- Ambiguous cases (e.g., 01/05/2026): default to DD/MM/YYYY for Indian bills

### 8.4 Structurer Module (`pipeline/structurer.py`)

**Inputs:** ExtractionResult  
**Outputs:** Transaction (see Section 12.1)

**Category inference:**
```python
MERCHANT_CATEGORY_MAP = {
    "zomato": "Food", "swiggy": "Food", "bigbasket": "Groceries",
    "blinkit": "Groceries", "uber": "Transport", "ola": "Transport",
    "irctc": "Transport", "netflix": "Subscription", "spotify": "Subscription",
    "amazon": "Shopping", "flipkart": "Shopping", "myntra": "Shopping",
}

def infer_category(merchant: str, items: list[str]) -> str:
    # 1. Normalize merchant to lowercase
    # 2. Check MERCHANT_CATEGORY_MAP
    # 3. If not found, use zero-shot text classifier on merchant + item names
    # 4. If classifier confidence < 0.5, return "Uncategorized"
```

**Zero-shot classifier candidate labels:**
```
["Food", "Transport", "Groceries", "Subscription", "Shopping",
 "Utilities", "Healthcare", "Education", "Entertainment", "Other"]
```

### 8.5 Deduplicator Module (`pipeline/deduplicator.py`)

```python
def compute_file_hash(file_bytes: bytes) -> str:
    # SHA-256 hex digest

def compute_transaction_fingerprint(transaction: Transaction) -> str:
    # SHA-256 of f"{merchant.lower()}|{date}|{round(total, 2)}"

def check_duplicate(transaction: Transaction, existing: list[Transaction]) -> DuplicateResult:
    # Check exact fingerprint match
    # Check fuzzy match: same merchant, amount within 1%, date within 1 day
    # Returns DuplicateResult(is_duplicate, confidence, matching_transaction_id)
```

### 8.6 Analyzer Module (`pipeline/analyzer.py`)

```python
def compute_category_totals(transactions: list[Transaction],
                             start_date: date, end_date: date) -> dict[str, float]:

def compute_merchant_totals(transactions: list[Transaction],
                             days: int = 30) -> list[tuple[str, float]]:

def compute_daily_trend(transactions: list[Transaction], days: int = 30) -> list[tuple[date, float]]:

def detect_anomalies(transaction: Transaction,
                     history: list[Transaction]) -> AnomalyResult:

def compute_savings_opportunity(transactions: list[Transaction],
                                 budget_config: dict) -> float:

def generate_analysis(transactions: list[Transaction]) -> AnalysisResult:
    # Orchestrates all above functions
```

---

## 9. Frontend Requirements

### 9.1 Page Layout

The frontend is a single page with the following sections:

**Header:**
- Logo: "FinSight" wordmark
- Tagline: "Financial Intelligence System"
- Subheadline: "99% of gamblers give up before making it big. Be the 1%."

**Main content area — two columns on desktop, stacked on mobile:**
- Left column (60%): Dashboard (charts + transaction table)
- Right column (40%): Upload panel + Nova chat

**Upload Section:**
- Drag-and-drop zone with label: "Come see where you lost money"
- File picker button
- Supported formats listed below the drop zone
- Processing status indicator

**Transaction Table:**
- Columns: Date, Merchant, Category, Amount, Status (normal/anomaly/duplicate)
- Sortable by clicking column headers
- Row click expands to show full extraction detail
- Anomaly rows highlighted in amber/red
- Duplicate rows highlighted in blue with merge/dismiss action

**Charts:**
- Chart 1: Donut chart — spending by category (current month)
- Chart 2: Line chart — daily spending trend (last 30 days)
- Chart 3: Bar chart — top 5 merchants by spend (last 30 days)
- Charts update in real time when new bills are processed

**Extraction Preview Panel:**
- Shown after upload completes
- Lists each extracted field with its value and confidence indicator (color-coded: green ≥ 0.8, amber 0.5–0.8, red < 0.5)
- Each field is editable inline
- "Confirm" and "Discard" buttons

**Nova Chat Panel:**
- Chat bubble interface
- Input box at bottom
- Nova messages on left, user messages on right
- "Where do I invest?" pre-filled as example prompt
- Streaming text rendering (characters appear progressively)
- Disclaimer footer: "Nova does not provide certified financial advice."

> **Note:** UI visual design (colors, typography, spacing, component styling) will be revisited in a dedicated design pass. Functional layout and data binding are the priority for v1 implementation.

### 9.2 Frontend Tech Stack
- Vanilla HTML + CSS + JavaScript (no framework required, but React is acceptable)
- Chart library: Chart.js (free, CDN-available)
- No jQuery

### 9.3 Responsive Breakpoints
- Desktop: ≥ 1024px — two-column layout
- Tablet: 768–1023px — two-column with reduced padding
- Mobile: < 768px — single-column, charts stacked, Nova chat collapsible

### 9.4 State Management
All frontend state (transactions, current extraction, Nova conversation history) stored in a single JavaScript state object. On page reload, state is re-fetched from the backend API.

---

## 10. Chatbot — Nova

### 10.1 Architecture

Nova is implemented as a context-augmented LLM call with an optional web search tool. On each user message:
1. Classify the intent: spending query vs investment/market query vs general
2. Fetch current transaction summary from analyzer
3. Fetch real-time market data (if available)
4. **If intent is investment/market: fetch current NewsContext from news cache**
5. **If intent requires specific live data (named instrument, recent event): trigger web search tool**
6. Build system prompt with all available context
7. Call LLM API with conversation history and (conditionally) web search tool enabled
8. Stream response to frontend

### 10.2 LLM Options (in preference order)
1. **Groq API** (free tier, fast inference) — `llama-3.3-70b-versatile` or `mixtral-8x7b`
2. **Ollama local** — `llama3.2:3b` or `phi3:mini` for fully offline operation
3. **OpenAI API** — `gpt-4o-mini` (paid but high quality)
4. **Anthropic API** — `claude-haiku-4-5` (paid)

The system must be configurable via `config.py` to switch between providers without code changes.

### 10.3 System Prompt Template

```
You are Nova, a financial intelligence assistant for the FinSight app.
You help users understand their spending and make informed investment decisions
grounded in their actual financial data AND current financial news.

Current date: {current_date}

USER'S FINANCIAL SUMMARY:
- Total transactions: {n_transactions}
- Current month spend: ₹{current_month_total}
- Previous month spend: ₹{prev_month_total}
- Top spending category: {top_category} (₹{top_category_amount})
- Anomalies detected: {n_anomalies}
- Estimated monthly savings opportunity: ₹{savings_opportunity}

CATEGORY BREAKDOWN (current month):
{category_breakdown_table}

TOP MERCHANTS (last 30 days):
{top_merchants_table}

MARKET DATA (as of {market_data_timestamp}):
{market_data_snippet}

CURRENT FINANCIAL NEWS CONTEXT (as of {news_timestamp}):
{news_summary}

RULES:
1. Only cite specific amounts that appear in the data above. Do not invent figures.
2. For investment suggestions, ground your advice in the news context AND the user's savings amount.
3. Always end investment suggestions with: "This is not certified financial advice."
4. If market data is unavailable, say so explicitly and give general advice instead.
5. If news context is unavailable, say so and base advice on market data only.
6. Use the web search tool when the user asks about a specific named instrument, recent RBI policy, budget announcement, or sector event — do not guess from training data.
7. Do NOT recommend individual stocks. Discuss sectors, index funds, mutual fund categories, and FDs only.
8. Attribute news-based claims: say "According to recent reports..." or "Recent news suggests...".
9. Be concise. Bullet points preferred for lists. Max 300 words per response.
```

### 10.4 Market Data Integration

**Primary source:** Yahoo Finance via `yfinance` Python library (free, no API key)  
**Data fetched:** NIFTY 50 index, top 5 mutual fund NAVs (Parag Parikh Flexi Cap, Axis Bluechip, etc.), SBI FD rate, 10-year G-Sec yield  
**Cache TTL:** 1 hour — store in `data/market_cache.json` with timestamp  
**Fallback:** If fetch fails or cache > 24 hours old, Nova acknowledges unavailability and gives general advice

**Fetching logic:**
```python
def get_market_data(force_refresh: bool = False) -> dict:
    cache = load_cache()
    if not force_refresh and cache_is_fresh(cache, ttl_hours=1):
        return cache["data"]
    try:
        data = fetch_from_yfinance()
        save_cache(data)
        return data
    except Exception:
        if cache:
            return cache["data"]  # Use stale cache
        return {}  # Empty — Nova will handle gracefully
```

### 10.5 Financial News Integration (`chatbot/news.py`)

**Purpose:** Fetch current Indian financial headlines from free public sources and summarize them into a structured NewsContext object that Nova uses to ground investment suggestions in current affairs.

**News Sources (free, no API key required):**
- Economic Times Markets RSS: `https://economictimes.indiatimes.com/markets/rss.cms`
- Moneycontrol Top News RSS: `https://www.moneycontrol.com/rss/latestnews.xml`
- RBI Press Releases (scraped): `https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx`
- Fallback: Google News RSS for query "India stock market": `https://news.google.com/rss/search?q=india+stock+market+investment&hl=en-IN&gl=IN&ceid=IN:en`

**Fetch and summarize flow:**
```python
def fetch_news_headlines(sources: list[str], max_per_source: int = 10) -> list[str]:
    # Parse RSS feeds using feedparser
    # Return list of headline strings (title + brief description)
    # Deduplicate by title similarity
    # Filter to last 48 hours only

def summarize_headlines(headlines: list[str]) -> NewsContext:
    # Call LLM with headlines list
    # System prompt: "Summarize these Indian financial headlines into:
    #   1. Three macro trends (RBI policy, inflation, GDP, market direction)
    #   2. Sector-level signals (IT, banking, FMCG, pharma, energy)
    #   3. Any specific mutual fund / index / FD relevant developments
    #   Return JSON only."
    # Parse response into NewsContext model

def get_news_context(force_refresh: bool = False) -> NewsContext | None:
    # Check news_cache.json — use if < NEWS_CACHE_TTL_HOURS old (default 2)
    # If stale or missing: fetch + summarize + cache
    # On any failure: return cached version if < 24h, else return None
```

**Scheduling:** News is refreshed as a background task triggered either:
- On FastAPI startup (first fetch)
- Every `NEWS_CACHE_TTL_HOURS` via APScheduler background job
- On demand via `/api/v1/news/refresh` endpoint (admin use)

**Dependencies to add:** `feedparser`, `apscheduler`

### 10.6 Nova Web Search Tool

**Purpose:** Allow Nova to retrieve live, specific information for investment queries that require more granularity than the cached news summary provides (e.g., "What happened to HDFC Bank this week?", "What is the current RBI repo rate?").

**Implementation:** Use the LLM provider's native tool/function calling feature to define a `web_search` tool. Nova decides autonomously whether to invoke it.

**Tool definition (provider-agnostic schema):**
```python
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for current Indian financial information. "
        "Use this when the user asks about a specific named stock, mutual fund, "
        "sector event, RBI policy change, budget announcement, or any financial "
        "news from the last 7 days that may not be in your training data. "
        "Do NOT use for general investment concepts you already know."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Concise search query, 3–8 words. Always include 'India' or INR context."
            }
        },
        "required": ["query"]
    }
}
```

**Search execution:**
```python
def execute_web_search(query: str) -> str:
    # Primary: DuckDuckGo Instant Answer API (free, no key)
    #   GET https://api.duckduckgo.com/?q={query}&format=json&no_html=1
    # Fallback: Google News RSS search
    #   GET https://news.google.com/rss/search?q={query}&hl=en-IN
    # Returns: top 3 results as formatted string: "Title | Snippet | Source"
    # Max response length: 500 chars total — truncate if needed
```

**Guardrails on web search results:**
- Strip all HTML before injecting into prompt
- Do not inject raw URLs into Nova's response — Nova summarizes findings in its own words
- If search returns no results or errors, Nova acknowledges and falls back to news cache
- Web search is only enabled when `LLM_PROVIDER` supports tool/function calling (Groq with tool support, OpenAI, Anthropic). For Ollama, web search is disabled and Nova uses news cache only.

### 10.7 Investment Suggestion Logic

Based on `savings_opportunity` value, combined with news context:
- < ₹1,000: "Consider a recurring deposit or liquid mutual fund for short-term parking"
- ₹1,000–₹5,000: "SIP in an index fund (NIFTY 50 ETF) or liquid fund"
- ₹5,000–₹20,000: "Consider splitting: 50% equity index fund, 30% debt fund, 20% emergency liquid fund"
- > ₹20,000: "Consider consulting a SEBI-registered investment advisor for personalized portfolio construction"

These are base templates. Nova uses news context and web search results to add a current-affairs layer — e.g., if news indicates RBI rate hike, Nova may note that FD rates are attractive right now. Nova must not contradict these templates with news context; it only supplements them.

---

## 11. API Design

All API routes are prefixed with `/api/v1/`.

### 11.1 Response Envelope

All responses follow:
```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

On error:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "EXTRACTION_FAILED",
    "message": "Could not extract total amount from bill",
    "details": { ... }
  }
}
```

### 11.2 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/upload` | Upload bill file(s). Returns extraction results. |
| POST | `/api/v1/transactions/confirm` | Confirm extracted transaction (with optional edits). Saves to store. |
| POST | `/api/v1/transactions/discard` | Discard extraction result without saving. |
| GET | `/api/v1/transactions` | List all transactions. Query params: `start_date`, `end_date`, `category`, `limit`, `offset` |
| GET | `/api/v1/transactions/{id}` | Get single transaction by ID. |
| DELETE | `/api/v1/transactions/{id}` | Delete transaction from store. |
| POST | `/api/v1/transactions/{id}/dismiss-anomaly` | Mark anomaly as known/expected. |
| GET | `/api/v1/analysis` | Get current AnalysisResult for all transactions. |
| POST | `/api/v1/chat` | Send message to Nova. Body: `{message, conversation_history}`. Returns streaming response. |
| GET | `/api/v1/market` | Get current cached market data. |
| GET | `/api/v1/news` | Get current cached NewsContext. |
| POST | `/api/v1/news/refresh` | Force-refresh news fetch and summarization (admin). |
| GET | `/api/v1/benchmark` | Run pipeline on synthetic dataset and return accuracy metrics. |
| GET | `/api/v1/health` | Health check. Returns pipeline component status including news module. |

### 11.3 Upload Endpoint Detail

**Request:** `multipart/form-data` with field `files` (multiple files accepted)  
**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "file_name": "bill_0.png",
        "extraction": { ... ExtractionResult ... },
        "duplicate_check": {
          "is_duplicate": false,
          "confidence": 0.0,
          "matching_id": null
        },
        "anomaly_check": {
          "is_anomaly": false,
          "score": 0.12,
          "reason": null
        }
      }
    ]
  }
}
```

---

## 12. Data Models

### 12.1 Transaction

```python
@dataclass
class Transaction:
    id: str                    # UUID4
    merchant: str              # Normalized merchant name
    date: str                  # ISO 8601: YYYY-MM-DD
    items: list[LineItem]      # May be empty for non-itemized bills
    subtotal: float | None
    tax: float | None
    total: float               # Required — cannot be None
    category: str              # From lookup or classifier
    payment_method: str | None # "UPI", "Card", "Cash", "Unknown"
    bill_number: str | None
    upload_timestamp: str      # ISO 8601 datetime of upload
    file_name: str             # Original filename
    file_hash: str             # SHA-256 of original file
    is_anomaly: bool
    anomaly_score: float       # 0.0–1.0
    anomaly_reason: str | None
    is_duplicate: bool
    duplicate_of: str | None   # ID of original transaction
    user_confirmed: bool       # True if user confirmed extraction
    manually_edited: bool      # True if user edited any field
    raw_ocr_text: str          # Full OCR output for debugging
```

### 12.2 LineItem

```python
@dataclass
class LineItem:
    name: str
    quantity: float | None
    unit_price: float | None
    total_price: float
```

### 12.3 ExtractionResult

```python
@dataclass
class ExtractionResult:
    merchant: ExtractedField[str]
    date: ExtractedField[str]
    items: list[LineItem]
    subtotal: ExtractedField[float | None]
    tax: ExtractedField[float | None]
    total: ExtractedField[float]
    payment_method: ExtractedField[str | None]
    bill_number: ExtractedField[str | None]
    extraction_model: str      # "cord", "sroie", "funsd"
    ocr_engine: str            # "paddleocr", "tesseract"

@dataclass
class ExtractedField(Generic[T]):
    value: T
    confidence: float          # 0.0–1.0
    raw_text: str              # Original OCR text before normalization
```

### 12.4 AnalysisResult

```python
@dataclass
class AnalysisResult:
    generated_at: str                          # ISO 8601 timestamp
    total_transactions: int
    date_range: tuple[str, str]                # (start_date, end_date)
    current_month_total: float
    previous_month_total: float
    month_over_month_change: float             # Percentage change
    category_totals: dict[str, float]          # {category: total_spend}
    category_previous_month: dict[str, float]
    top_merchants: list[tuple[str, float]]     # [(merchant, total), ...]
    daily_trend: list[tuple[str, float]]       # [(date_str, total), ...]
    anomaly_count: int
    anomalies: list[str]                       # Transaction IDs
    savings_opportunity: float
    insights: list[str]                        # Human-readable insight strings
```

### 12.5 NewsContext (NEW)

```python
@dataclass
class NewsContext:
    fetched_at: str                      # ISO 8601 timestamp
    sources_used: list[str]              # Which RSS feeds were successfully fetched
    headline_count: int                  # Number of raw headlines processed
    macro_trends: list[str]              # 3 macro trend strings (RBI, inflation, market direction)
    sector_signals: dict[str, str]       # {"IT": "positive — strong Q4 earnings", ...}
    fund_developments: list[str]         # Mutual fund / index / FD specific news
    raw_headlines: list[str]             # Original headlines before summarization (for debugging)
    summary_model: str                   # Which LLM was used for summarization
```

---

## 13. Error Handling & Edge Cases

### 13.1 Upload Errors

| Scenario | System Response |
|----------|-----------------|
| File > 10MB | HTTP 413, error message: "File too large. Maximum size is 10MB." |
| Unsupported format | HTTP 415, list supported formats |
| Corrupted file / unreadable | HTTP 422, "Could not read file. Please check the file is not corrupted." |
| Empty PDF (no pages) | HTTP 422, "PDF appears to be empty." |
| Password-protected PDF | HTTP 422, "PDF is password protected. Please remove the password and re-upload." |
| Image is completely black | Preprocessing detects zero variance, returns warning but continues |

### 13.2 OCR Edge Cases

| Scenario | Handling |
|----------|----------|
| Handwritten bill | OCR will have low confidence; all fields marked "unextracted"; user prompted to enter manually |
| Bill in non-English language | PaddleOCR supports multi-language; if language detection returns non-English, attempt OCR with detected language |
| Bill with only QR code | No text extracted; return "No readable text found" error |
| Very small image (< 100px) | Reject with message: "Image resolution too low for processing." |
| Image with watermark | Watermark text may be extracted; KIE confidence will be lower but should still extract key fields |
| Rotated 180 degrees | Deskew handles ±180; include 180-degree flip detection |

### 13.3 Extraction Edge Cases

| Scenario | Handling |
|----------|----------|
| No total found | Attempt to compute total = subtotal + tax; if both missing, mark total as "unextracted" and require user input |
| Multiple totals on page | Take the largest amount labeled "total" or "grand total"; log ambiguity |
| Date in the future | Accept but log warning; flag for user review |
| Date before 2000 | Likely OCR error; flag for user review |
| Amount with no currency symbol | Treat as INR by default; log assumption |
| Negative amounts | Flag as potential refund/credit; mark category as "Refund" |
| Item prices that don't sum to subtotal | Log discrepancy; use extracted subtotal as authoritative |

### 13.4 Duplicate Detection Edge Cases

| Scenario | Handling |
|----------|----------|
| Same bill uploaded twice in same session | Detected by file hash before OCR runs |
| Slightly different scans of same bill | Detected by transaction fingerprint |
| Two different bills for same amount on same day from same merchant | Both kept; user asked to confirm |
| Split payment (two bills, same merchant, amounts sum to expected total) | Not detected as duplicate; both kept |

### 13.5 Nova Edge Cases

| Scenario | Handling |
|----------|----------|
| No transactions in store | Nova responds: "I don't have any bills to analyze yet. Upload some bills to get started!" |
| User asks about specific stock | Nova cites sector-level news context and NIFTY data; declines to recommend individual stocks |
| User asks how to avoid taxes | Nova declines and suggests consulting a CA |
| LLM API timeout | Return error message in chat: "Nova is temporarily unavailable. Please try again." |
| User message > 2000 characters | Truncate to 2000 chars before sending to LLM |
| LLM returns empty response | Retry once; if still empty, return "Nova couldn't generate a response. Please try rephrasing." |
| Web search returns no results | Nova acknowledges and falls back to news cache; does not fabricate search results |
| Web search tool not supported by provider | Disable tool; Nova uses news cache only and acknowledges it cannot do live lookups |
| News fetch fails completely and no cache | Nova says: "I don't have current market news available. My suggestions are based on general guidelines." |

### 13.6 Data Persistence Edge Cases

| Scenario | Handling |
|----------|----------|
| transactions.json corrupted | On load failure, rename to `transactions.json.bak`, start fresh, log error |
| Disk full during write | Catch OSError, return 500 error, do not partially write |
| Concurrent uploads (two users simultaneously) | Use file lock (filelock library) around all writes to transactions.json |
| news_cache.json corrupted | Delete and re-fetch on next news refresh cycle; log error |

---

## 14. External Integrations

### 14.1 yfinance (Market Data)

```python
import yfinance as yf

def fetch_nifty():
    ticker = yf.Ticker("^NSEI")
    return ticker.history(period="1d")["Close"].iloc[-1]
```

**Required data points:**
- NIFTY 50 current value and 1-day change
- USD/INR exchange rate
- SBI 1-year FD rate (hardcoded or scraped from SBI website — yfinance does not provide this)
- Top 3 large-cap mutual fund NAVs (fetched from AMFI India open data API: `https://www.amfiindia.com/spages/NAVAll.txt`)

**AMFI India NAV fetch:**
```python
import requests

def fetch_amfi_navs(scheme_codes: list[str]) -> dict:
    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    response = requests.get(url, timeout=10)
    # Parse pipe-delimited text file
    # Format: SchemeCode|ISIN|SchemeNameGrowth|SchemeNameDividend|NAV|Date
```

### 14.2 Financial News RSS Feeds

```python
import feedparser

def fetch_rss(url: str, max_items: int = 10) -> list[dict]:
    feed = feedparser.parse(url)
    return [
        {"title": entry.title, "summary": entry.get("summary", ""), "published": entry.get("published", "")}
        for entry in feed.entries[:max_items]
    ]
```

**Sources:**
- Economic Times Markets: `https://economictimes.indiatimes.com/markets/rss.cms`
- Moneycontrol: `https://www.moneycontrol.com/rss/latestnews.xml`
- Google News India Finance: `https://news.google.com/rss/search?q=india+stock+market+investment&hl=en-IN&gl=IN&ceid=IN:en`

**Timeout:** 10 seconds per source. If a source times out, skip it and continue with others.

### 14.3 DuckDuckGo Instant Answer API (Web Search)

```python
import requests

def duckduckgo_search(query: str) -> str:
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    response = requests.get(url, params=params, timeout=5)
    data = response.json()
    results = []
    if data.get("AbstractText"):
        results.append(data["AbstractText"])
    for topic in data.get("RelatedTopics", [])[:2]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append(topic["Text"])
    return " | ".join(results)[:500]
```

### 14.4 pdf2image

```python
from pdf2image import convert_from_bytes
images = convert_from_bytes(pdf_bytes, dpi=200, fmt="PNG")
```

Requires Poppler installed on system:
- Ubuntu: `apt-get install poppler-utils`
- macOS: `brew install poppler`
- Windows: download Poppler binaries and add to PATH

### 14.5 PaddleOCR

```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
result = ocr.ocr(image_path, cls=True)
```

First run downloads model weights (~50 MB). Must be handled gracefully in first-time setup.

### 14.6 HuggingFace Datasets

All three datasets loaded via `datasets` library:
```python
pip install datasets
```

Datasets are cached locally after first download in `~/.cache/huggingface/datasets/`.

---

## 15. Security Requirements

### 15.1 File Upload Security
- SR-1: Validate MIME type server-side (do not trust Content-Type header alone — verify magic bytes)
- SR-2: Save uploaded files to a temporary directory with a random UUID filename, not the original filename
- SR-3: Delete temporary files after processing completes or fails
- SR-4: Do not execute uploaded files under any circumstances
- SR-5: Limit file read to 10 MB even if OS allows more

### 15.2 Data Security
- SR-6: Do not log bill images or extracted text to console in production
- SR-7: transactions.json must not be served as a static file — it must only be accessible through the API
- SR-8: API keys (Groq, OpenAI, etc.) must be stored in environment variables, never in source code

### 15.3 Input Validation
- SR-9: Sanitize all user-edited field values before saving (strip HTML, limit length)
- SR-10: Nova chat input must be sanitized before inclusion in LLM prompt (strip prompt injection patterns: "ignore previous instructions", "you are now", etc.)
- **SR-11: Web search query constructed by Nova must be validated — max 100 chars, strip special characters that could manipulate the search API**
- **SR-12: News content fetched from RSS must be stripped of HTML tags before injection into any LLM prompt**

### 15.4 Rate Limiting
- SR-13: Limit upload endpoint to 10 requests per minute per IP (use slowapi)
- SR-14: Limit Nova chat endpoint to 20 requests per minute per IP
- **SR-15: Limit `/api/v1/news/refresh` to 2 requests per hour per IP to prevent abuse of LLM summarization calls**

---

## 16. Testing Requirements

### 16.1 Unit Tests

| Module | What to Test |
|--------|-------------|
| `preprocess.py` | Deskew on rotated test images, contrast normalization on dark/bright images, PDF conversion |
| `ocr.py` | PaddleOCR on clean synthetic bill, tesseract fallback trigger, line merging |
| `kie.py` | CORD path on itemized receipt, SROIE path on invoice, date normalization for 5 formats, amount parsing with commas and symbols |
| `structurer.py` | Category lookup for all 12 merchants, fallback classifier for unknown merchant, UUID generation |
| `deduplicator.py` | Exact file hash match, fuzzy transaction fingerprint match, non-duplicate pair |
| `analyzer.py` | Category totals, daily trend computation, anomaly detection with synthetic data |
| `chatbot/news.py` | RSS fetch with mock responses, headline deduplication, summarization with mock LLM response, cache read/write, staleness logic |
| `chatbot/nova.py` | Intent classification (spending vs investment), web search tool trigger condition, fallback when news unavailable, web search disabled for Ollama |

### 16.2 Integration Tests

| Test | Description |
|------|-------------|
| Full pipeline on clean synthetic bill | Upload → extract → structure → analyze. All fields extracted correctly. |
| Full pipeline on messy synthetic bill | OCR fallback may trigger. Fields extracted with lower confidence. |
| Duplicate detection end-to-end | Upload same bill twice, verify duplicate flag on second upload |
| Anomaly detection end-to-end | Upload anomaly bill, verify anomaly flag with correct reason |
| Nova responds with transaction context | Upload 5 bills, ask Nova "How much did I spend?", verify answer matches analyzer output |
| **Nova investment query with news context** | Mock news cache populated, ask Nova "Where should I invest?", verify response references news context |
| **Nova web search trigger** | Ask Nova "What happened to NIFTY this week?", verify web search tool is called, response attributes source |
| **News fetch end-to-end** | Mock RSS feeds, run fetch + summarize, verify NewsContext fields populated correctly |
| **News fallback** | RSS unreachable, cache < 24h old, verify stale cache is used; cache > 24h old, verify Nova acknowledges no news |

### 16.3 Benchmark Tests

Run `python backend/benchmarks/evaluate.py` to:
- Process all 37 synthetic bills
- Compute field-level accuracy against ground_truth.json
- Report per-field accuracy table
- Report anomaly detection recall
- Report duplicate detection precision
- Save results to `benchmarks/results.json`

### 16.4 Test Data

- 5 clean synthetic PDF bills (normal)
- 5 clean synthetic PNG bills (normal)
- 3 messy PNG bills
- 2 anomaly bills
- 1 duplicate pair
- 1 empty PDF
- 1 image with no text
- 1 handwritten bill image (can be a real photo of handwriting on paper)
- **Mock news cache JSON with populated NewsContext (for offline Nova tests)**
- **Mock RSS feed XML files (for news fetch unit tests)**

---

## 17. Deployment Requirements

### 17.1 Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (served by FastAPI)
# Static files mounted at /
```

### 17.2 Environment Variables

```bash
# .env file (never commit to git)
GROQ_API_KEY=...
OPENAI_API_KEY=...          # Optional
ANTHROPIC_API_KEY=...       # Optional
LLM_PROVIDER=groq           # groq | openai | anthropic | ollama
OLLAMA_BASE_URL=http://localhost:11434
MARKET_DATA_CACHE_TTL_HOURS=1
NEWS_CACHE_TTL_HOURS=2
NEWS_SOURCES=et,moneycontrol,googlenews   # Comma-separated source keys
UPLOAD_MAX_SIZE_MB=10
ANOMALY_STDDEV_THRESHOLD=2.0
BUDGET_FOOD=5000
BUDGET_TRANSPORT=3000
BUDGET_SHOPPING=4000
BUDGET_SUBSCRIPTION=1000
```

### 17.3 requirements.txt

```
fastapi
uvicorn[standard]
python-multipart
paddleocr
paddlepaddle
pytesseract
Pillow
pillow-heif
pdf2image
deskew
opencv-python-headless
transformers
datasets
yfinance
requests
filelock
slowapi
faker
reportlab
pydantic
python-dotenv
feedparser
apscheduler
```

### 17.4 System Dependencies (install separately)

```
poppler-utils      # PDF to image conversion
tesseract-ocr      # OCR fallback
libgl1             # Required by OpenCV on headless servers
```

---

## 18. File & Directory Structure

```
finsight/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── preprocess.py
│   │   ├── ocr.py
│   │   ├── kie.py
│   │   ├── structurer.py
│   │   ├── analyzer.py
│   │   └── deduplicator.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── transaction.py
│   │   ├── analysis.py
│   │   ├── extraction.py
│   │   └── news.py
│   ├── chatbot/
│   │   ├── __init__.py
│   │   ├── nova.py
│   │   ├── market.py
│   │   └── news.py
│   ├── data/
│   │   ├── transactions.json
│   │   ├── duplicate_log.json
│   │   ├── market_cache.json
│   │   └── news_cache.json
│   └── benchmarks/
│       ├── evaluate.py
│       └── results.json
├── synthetic/
│   ├── generate_bills.py
│   ├── pdf_to_images.py
│   ├── make_messy.py
│   ├── synthetic_bills/
│   ├── synthetic_bill_images/
│   └── ground_truth.json
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_preprocess.py
│   ├── test_ocr.py
│   ├── test_kie.py
│   ├── test_structurer.py
│   ├── test_deduplicator.py
│   ├── test_analyzer.py
│   ├── test_news.py
│   └── test_api.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

**.gitignore must include:**
```
.env
backend/data/transactions.json
backend/data/market_cache.json
backend/data/news_cache.json
synthetic/synthetic_bills/
synthetic/synthetic_bill_images/
__pycache__/
*.pyc
.venv/
```

---

## 19. Dependencies & Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web framework | FastAPI | REST API + static file serving |
| ASGI server | Uvicorn | Production server |
| OCR (primary) | PaddleOCR | Text extraction from images |
| OCR (fallback) | pytesseract | Backup OCR engine |
| Image processing | Pillow, OpenCV, deskew | Preprocessing |
| PDF conversion | pdf2image + Poppler | PDF → image |
| HEIC support | pillow-heif | iPhone photo format |
| ML / KIE | HuggingFace Transformers | CORD/SROIE/FUNSD model inference |
| Datasets | HuggingFace datasets | Loading CORD, FUNSD, SROIE |
| Zero-shot classification | HuggingFace pipeline | Category inference |
| LLM (Nova) | Groq / Ollama / OpenAI / Anthropic | Chatbot responses + news summarization |
| Market data | yfinance + AMFI API | Investment context |
| **News fetching** | **feedparser** | **RSS feed parsing for financial headlines** |
| **News summarization** | **Same LLM as Nova** | **Headline → NewsContext summarization** |
| **Web search** | **DuckDuckGo Instant Answer API** | **Live financial query resolution** |
| **Background scheduler** | **APScheduler** | **Periodic news refresh** |
| Data validation | Pydantic | Request/response models |
| Concurrency safety | filelock | Safe JSON writes |
| Rate limiting | slowapi | Upload / chat / news rate limits |
| Synthetic data | Faker + ReportLab | Bill generation |
| Charts | Chart.js | Frontend visualizations |
| Testing | pytest | Unit + integration tests |

---

## 20. Known Limitations & Assumptions

### 20.1 Limitations

- The system only supports INR-denominated bills in v1. Multi-currency support is out of scope.
- PaddleOCR performs poorly on handwritten text. Handwritten bills will require manual entry.
- The CORD and SROIE models are trained on Southeast Asian and general receipts respectively — performance on Indian merchant bills may be lower than benchmark numbers.
- The system does not handle multi-page bills — only page 1 is processed.
- The duplicate detection fuzzy match may produce false positives for regular subscriptions. The user confirmation dialog is the safety valve.
- Investment suggestions are sector-level and macro-level, not personalized to risk profile. This is by design in v1.
- **Web search via DuckDuckGo Instant Answer API returns limited results for niche queries — it is best-effort, not a comprehensive search engine.**
- **News summarization quality depends on the LLM provider — Ollama local models may produce lower-quality summaries than Groq/OpenAI.**
- **Web search tool is unavailable when using Ollama (no native tool calling support in small local models). Nova falls back to news cache.**
- RSS feeds may go down or change format — the system is designed to degrade gracefully, never hard-fail on news unavailability.

### 20.2 Assumptions

- The user uploads one bill per transaction. Bundle bills are treated as a single transaction.
- All bills are in English. Non-English OCR is supported by PaddleOCR but KIE logic is English-keyword-based.
- The backend and frontend run on the same machine in v1. CORS is configured to allow localhost only.
- Market data and news represent Indian markets. The system is designed for Indian users.
- The user's device has at least 4 GB RAM available — PaddleOCR and transformer models require significant memory.
- Internet access is available for model download, market data, and news. After initial model download, only market data and news require connectivity.
- News refresh runs as a background task and does not block any user-facing request.

### 20.3 Out of Scope for v1

- User authentication and multi-user support
- Bank statement import (PDF or CSV)
- Automatic bill email parsing
- Mobile app (iOS/Android)
- GDPR compliance and data export
- Recurring transaction detection
- Bill OCR for non-bill documents (ID cards, forms)
- Currency conversion
- Tax computation or ITR filing assistance
- Personalized risk-profile-based investment recommendations
- Real-time stock price streaming
