# FinSight v2 — Agent Execution Plan
**Based on:** SRS v2.0  
**Execution order:** Phases 0 → 9 in sequence. Each phase must be complete and verified before the next begins.

---

## PHASE 0: Project Scaffold
**Goal:** Full directory tree and all placeholder/config files created before any logic is written.

1. Create root `finsight/` with all subdirectories:
   `backend/pipeline/`, `backend/models/`, `backend/chatbot/`, `backend/data/`, `backend/benchmarks/`, `synthetic/synthetic_bills/`, `synthetic/synthetic_bill_images/`, `frontend/`, `tests/`

2. Create `__init__.py` in: `backend/pipeline/`, `backend/models/`, `backend/chatbot/`

3. Create `.env` with all variables from SRS §17.2:
   - `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_PROVIDER=groq`
   - `OLLAMA_BASE_URL=http://localhost:11434`
   - `MARKET_DATA_CACHE_TTL_HOURS=1`
   - `NEWS_CACHE_TTL_HOURS=2`
   - `NEWS_SOURCES=et,moneycontrol,googlenews`
   - `UPLOAD_MAX_SIZE_MB=10`, `ANOMALY_STDDEV_THRESHOLD=2.0`
   - `BUDGET_FOOD=5000`, `BUDGET_TRANSPORT=3000`, `BUDGET_SHOPPING=4000`, `BUDGET_SUBSCRIPTION=1000`

4. Create `.gitignore` per SRS §18 — include `.env`, `transactions.json`, `market_cache.json`, `news_cache.json`, synthetic bill directories, `__pycache__/`, `*.pyc`, `.venv/`

5. Create `requirements.txt` per SRS §17.3 — include ALL packages: fastapi, uvicorn[standard], python-multipart, paddleocr, paddlepaddle, pytesseract, Pillow, pillow-heif, pdf2image, deskew, opencv-python-headless, transformers, datasets, yfinance, requests, filelock, slowapi, faker, reportlab, pydantic, python-dotenv, feedparser, apscheduler

6. Create `backend/config.py` — load ALL env vars with typed defaults. Expose: `LLM_PROVIDER`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, `MARKET_DATA_CACHE_TTL_HOURS`, `NEWS_CACHE_TTL_HOURS`, `NEWS_SOURCES` (parsed to list), `UPLOAD_MAX_SIZE_MB`, `ANOMALY_STDDEV_THRESHOLD`, `BUDGET_*` dict, `NEWS_RSS_URLS` (map from source key to URL)

7. Create empty `backend/data/transactions.json` (`[]`), `backend/data/duplicate_log.json` (`[]`), `backend/data/market_cache.json` (`{}`), `backend/data/news_cache.json` (`{}`)

**Verification:** All directories exist, all files importable, `config.py` loads without error.

---

## PHASE 1: Pydantic Data Models
**Goal:** All shared schemas defined before any logic. Every other module imports from these.

### `backend/models/extraction.py`
- `OCRBlock` dataclass: `text: str`, `bbox: tuple` (x1,y1,x2,y2), `confidence: float`
- `ExtractedField(Generic[T])` dataclass: `value: T`, `confidence: float`, `raw_text: str`
- `LineItem` dataclass: `name: str`, `quantity: float | None`, `unit_price: float | None`, `total_price: float`
- `ExtractionResult` dataclass: all fields from SRS §12.3 — merchant, date, items, subtotal, tax, total, payment_method, bill_number (all as `ExtractedField`), `extraction_model: str`, `ocr_engine: str`

### `backend/models/transaction.py`
- `Transaction` Pydantic model: all fields from SRS §12.1 — id (UUID4 default), merchant, date, items, subtotal, tax, total (required float), category, payment_method, bill_number, upload_timestamp, file_name, file_hash, is_anomaly (bool, default False), anomaly_score (float, default 0.0), anomaly_reason, is_duplicate (bool, default False), duplicate_of, user_confirmed (bool, default False), manually_edited (bool, default False), raw_ocr_text

### `backend/models/analysis.py`
- `AnalysisResult` dataclass: all fields from SRS §12.4

### `backend/models/news.py` (NEW)
- `NewsContext` dataclass: all fields from SRS §12.5 — fetched_at, sources_used (list[str]), headline_count (int), macro_trends (list[str], max 3), sector_signals (dict[str, str]), fund_developments (list[str]), raw_headlines (list[str]), summary_model (str)

**Verification:** All models instantiate without error with dummy data. Run `python -c "from backend.models import *"`.

---

## PHASE 2: Synthetic Data Generation
**Goal:** Test data exists before the pipeline is built so each stage can be tested immediately.

### `synthetic/generate_bills.py`
- Use `Faker` + `ReportLab` to generate PDFs
- Merchants: Zomato, Swiggy, Amazon, Flipkart, Netflix, Spotify, Uber, Ola, BigBasket, Blinkit, Myntra, IRCTC
- Normal bills (30): amounts 50–3,000 INR, GST 18%, payment UPI/Card/Cash, bill number `INV-XXXX-XX`, date within last 30 days
- Anomaly bills (5): amounts 8,000–15,000 INR, flagged in ground truth
- Duplicate pair (2): identical content, different filenames
- Output: `synthetic/synthetic_bills/` (37 PDFs) + `synthetic/ground_truth.json` (one entry per bill per SRS §5.2 schema)
- ground_truth.json fields: `bill_id`, `merchant`, `date`, `amount`, `subtotal`, `tax`, `category`, `payment_method`, `bill_number`, `is_anomaly`, `is_duplicate_of`

### `synthetic/pdf_to_images.py`
- Convert all PDFs in `synthetic_bills/` to PNG at 150 DPI using `pdf2image`
- Output to `synthetic/synthetic_bill_images/`

### `synthetic/make_messy.py`
- Apply to 10 randomly selected bills: rotation ±3°, contrast 0.6–0.85, Gaussian blur radius 0.8
- Save as `messy_{original}.png` in `synthetic_bill_images/`

**Verification:** 37 PDFs in `synthetic_bills/`, 37+ PNGs in `synthetic_bill_images/`, `ground_truth.json` has 37 entries, `is_anomaly: true` on 5 entries, `is_duplicate_of` non-null on 1 entry.

---

## PHASE 3: Pipeline Modules (implement in order — each depends on the previous)

### Stage 1 — `backend/pipeline/preprocess.py`

Implement all 7 functions from SRS §8.1 in this exact order:

1. `detect_format(file_bytes: bytes) -> str`
   - Check magic bytes: PDF (`%PDF`), JPEG (`\xff\xd8`), PNG (`\x89PNG`), WEBP (`RIFF...WEBP`), HEIC (ftyp box)
   - Return string: `"pdf" | "jpeg" | "png" | "webp" | "heic"`

2. `pdf_to_image(file_bytes: bytes, dpi: int = 200) -> Image`
   - Use `pdf2image.convert_from_bytes`, take first page only
   - Raise `PreprocessingError("PDF appears to be empty.")` if no pages returned

3. `deskew(image: Image) -> Image`
   - Use `deskew` library or `cv2.HoughLines`
   - Target: correct within ±1°; include 180° flip detection

4. `normalize_contrast(image: Image) -> Image`
   - Apply CLAHE (`cv2.createCLAHE`) only if mean pixel brightness < 80 or > 200

5. `sharpen_if_blurry(image: Image) -> Image`
   - Compute Laplacian variance; apply unsharp mask if variance < 100

6. `resize_to_max(image: Image, max_dim: int = 2048) -> Image`
   - Preserve aspect ratio

7. `preprocess(file_bytes: bytes, mime_type: str) -> Image`
   - Orchestrates: detect_format → (pdf_to_image if PDF) → (HEIC convert if HEIC) → deskew → normalize_contrast → sharpen_if_blurry → resize_to_max
   - Raise structured `PreprocessingError` with human-readable message on any failure

**Verification:** `preprocess()` runs on 3 synthetic PNG bills and 1 PDF bill without error.

---

### Stage 2 — `backend/pipeline/ocr.py`

1. `run_paddleocr(image: Image) -> list[OCRBlock]`
   - Init `PaddleOCR(use_angle_cls=True, lang="en", show_log=False)`
   - Filter confidence < 0.5
   - Sort by (y1, x1) reading order

2. `run_tesseract(image: Image) -> list[OCRBlock]`
   - Use `pytesseract.image_to_data()` with `--psm 6`
   - Return same `OCRBlock` format

3. `merge_line_blocks(blocks: list[OCRBlock], y_tolerance: int = 10) -> list[OCRBlock]`
   - Merge blocks whose y1 values are within `y_tolerance` px of each other
   - Merge text left-to-right, combine bboxes, average confidence

4. `run_ocr(image: Image) -> list[OCRBlock]`
   - Try PaddleOCR first
   - Fall back to tesseract if result is empty OR raises exception

**Verification:** `run_ocr()` returns non-empty list on 3 synthetic bill images. Tesseract fallback tested with a mock that raises exception.

---

### Stage 3 — `backend/pipeline/kie.py`

1. Format detection function:
   - Receipt (CORD path): `>= 3 lines` each containing a price pattern `\d+\.\d{2}`
   - Invoice (SROIE path): any block contains "invoice" or "bill to" (case-insensitive)
   - Unknown (FUNSD path): neither condition met

2. CORD path:
   - Regex pattern: `(item_name)\s+(qty)?\s+(price)`
   - Group into `LineItem` objects
   - Sum line items to derive subtotal if not explicitly found

3. SROIE path (keyword proximity):
   - Company: largest/topmost text block
   - Date: block matching `(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{1,2}\s+\w{3}\s+\d{4})`
   - Total: block immediately following keyword `total|grand total|amount due` (case-insensitive)
   - Address: block following company block

4. FUNSD path:
   - Q-block: ends with ":", < 4 words, OR followed by ":"
   - A-block: contains digit, currency symbol, or is spatially to the right of a Q
   - Pair Q→A; map Q text to ExtractionResult fields by keyword matching

5. Date normalization — handle all formats, default DD/MM/YYYY for ambiguous Indian dates

6. Amount normalization:
   - Strip `₹ $ £ € Rs.`
   - Remove comma thousand separators: `"1,250.00"` → `1250.00`

7. GST/tax detection: keyword list `["gst", "tax", "vat", "cgst", "sgst", "igst"]`

8. Return `ExtractionResult` with per-field confidence and `extraction_model` string

9. Mark field as `"unextracted"` (confidence = 0.0, value = None) when confidence < 0.4

**Verification:** CORD path returns LineItems on an itemized synthetic bill. SROIE path returns merchant+date+total on a Zomato-style bill. Date normalization unit test covers 5 formats.

---

### Stage 4 — `backend/pipeline/structurer.py`

1. `MERCHANT_CATEGORY_MAP` dict — all 12 merchants from SRS §8.4

2. `infer_category(merchant: str, items: list[str]) -> str`
   - Lowercase normalize merchant
   - Lookup in map
   - If not found: zero-shot classify using `transformers.pipeline("zero-shot-classification")`
   - Candidate labels: Food, Transport, Groceries, Subscription, Shopping, Utilities, Healthcare, Education, Entertainment, Other
   - If classifier confidence < 0.5: return "Uncategorized"

3. `extraction_to_transaction(extraction: ExtractionResult, file_bytes: bytes, file_name: str) -> Transaction`
   - Assign UUID4 id
   - Set `upload_timestamp` to current UTC datetime (ISO 8601)
   - Set `transaction date` from extraction
   - Compute `file_hash` = SHA-256 of file_bytes
   - Set `raw_ocr_text` from extraction
   - Set `is_anomaly=False`, `anomaly_score=0.0` (anomaly detection runs in a later step)

4. `persist_transaction(transaction: Transaction, path: str) -> None`
   - Load existing JSON list with filelock
   - Append new transaction
   - Atomic write: write to `{path}.tmp`, then `os.replace()` to `path`

**Verification:** `infer_category("zomato", [])` returns "Food". Unknown merchant goes through classifier. Transaction persisted to file and re-readable.

---

### Stage 5 — `backend/pipeline/deduplicator.py`

Implement exactly per SRS §8.5:

1. `compute_file_hash(file_bytes: bytes) -> str` — SHA-256 hex digest

2. `compute_transaction_fingerprint(transaction: Transaction) -> str`
   - SHA-256 of `f"{transaction.merchant.lower()}|{transaction.date}|{round(transaction.total, 2)}"`

3. `check_duplicate(transaction: Transaction, existing: list[Transaction]) -> DuplicateResult`
   - Step 1: exact fingerprint match → `is_duplicate=True, confidence=1.0`
   - Step 2: fuzzy — same merchant (lowercase), amount within 1% (`abs(a-b)/max(a,b) <= 0.01`), date within 1 day → `is_duplicate=True, confidence=0.85`
   - Return `DuplicateResult(is_duplicate: bool, confidence: float, matching_transaction_id: str | None)`

4. Never auto-discard — mark and surface for user

5. Log all decisions to `data/duplicate_log.json` (append-only, same atomic write pattern)

**Verification:** Upload same synthetic bill twice → second flagged as duplicate. Different bill with same merchant on different date → not flagged.

---

### Stage 6 — `backend/pipeline/analyzer.py`

Implement all functions from SRS §8.6:

1. `compute_category_totals(transactions, start_date, end_date) -> dict[str, float]`
   - Filter by date range, sum total per category

2. `compute_merchant_totals(transactions, days=30) -> list[tuple[str, float]]`
   - Filter to last 30 days, sum per merchant, return top 5 sorted descending

3. `compute_daily_trend(transactions, days=30) -> list[tuple[str, float]]`
   - Fill all 30 days (include days with 0 spend)

4. `detect_anomalies(transaction, history) -> AnomalyResult`
   - Rule 1: amount > category_mean + 2σ (using non-anomaly historical transactions)
   - Rule 2: merchant not seen in last 90 days AND amount > 5000
   - Rule 3: same merchant appears > 3x on same date
   - Return `AnomalyResult(is_anomaly: bool, score: float, reason: str | None)`
   - Score: 1.0 if Rule 1 fires, 0.7 if Rule 2, 0.6 if Rule 3

5. `compute_savings_opportunity(transactions, budget_config) -> float`
   - Sum Food + Shopping + Subscription spend for current month
   - Subtract sum of corresponding budget targets
   - Return max(0, result) — savings opportunity cannot be negative

6. `generate_analysis(transactions) -> AnalysisResult`
   - Orchestrate all above; populate all AnalysisResult fields
   - Insights: auto-generate strings for categories > 20% MoM increase

**Verification:** Category totals correct on 5 synthetic bills. Anomaly bill correctly flagged. Savings opportunity > 0 when spend exceeds budget.

---

## PHASE 4: News Module (`backend/chatbot/news.py`)

**This is the new module. Implement completely before touching Nova.**

### `backend/chatbot/news.py`

1. `RSS_SOURCES` dict — map keys to URLs per SRS §14.2:
   - `et` → Economic Times Markets RSS
   - `moneycontrol` → Moneycontrol Latest News RSS
   - `googlenews` → Google News India Finance RSS

2. `fetch_rss(url: str, max_items: int = 10) -> list[dict]`
   - Use `feedparser.parse(url)` with 10s timeout
   - Return list of `{title, summary, published}` dicts
   - Filter to last 48 hours only (parse `published` field; skip if unparseable)
   - On exception: log and return empty list

3. `fetch_all_headlines(sources: list[str]) -> list[str]`
   - Fetch from all configured sources
   - Combine titles + summaries into plain strings
   - Deduplicate by exact title match
   - Return list of strings, max 30 total

4. `summarize_headlines(headlines: list[str]) -> NewsContext`
   - Call LLM (use same provider as Nova, configured in config.py)
   - System prompt: "You are a financial analyst summarizing Indian financial news. Given these headlines, return ONLY a valid JSON object with keys: macro_trends (list of 3 strings), sector_signals (dict mapping sector to one-line signal), fund_developments (list of strings). No preamble, no markdown, just JSON."
   - User message: numbered list of headlines
   - Parse JSON response
   - If parsing fails: return `NewsContext` with empty fields and log warning
   - Set `fetched_at`, `sources_used`, `headline_count`, `raw_headlines`, `summary_model`

5. `save_news_cache(context: NewsContext, path: str) -> None`
   - Write as JSON to `data/news_cache.json` (atomic write)

6. `load_news_cache(path: str) -> NewsContext | None`
   - Load from `data/news_cache.json`
   - Return None if file missing or corrupted

7. `cache_is_fresh(context: NewsContext, ttl_hours: float) -> bool`
   - Compare `context.fetched_at` to current UTC time

8. `get_news_context(force_refresh: bool = False) -> NewsContext | None`
   - If cache exists and fresh (< `NEWS_CACHE_TTL_HOURS`): return cache
   - Else: fetch → summarize → save → return
   - If fetch or summarize fails: use stale cache if < 24h; else return None
   - Never raise — always return NewsContext or None

9. APScheduler job setup (called from `main.py` on startup):
   ```python
   def start_news_scheduler(app):
       scheduler = BackgroundScheduler()
       scheduler.add_job(get_news_context, 'interval', hours=NEWS_CACHE_TTL_HOURS)
       scheduler.start()
   ```

**Verification:** `get_news_context()` returns a valid `NewsContext` with at least 1 macro trend when internet is available. With mocked RSS returning empty, function returns None gracefully. Cache read/write round-trips correctly.

---

## PHASE 5: Market Data Module (`backend/chatbot/market.py`)

Implement per SRS §10.4 and §14.1:

1. `fetch_nifty() -> dict`
   - `yf.Ticker("^NSEI").history(period="1d")` — return `{value, change_pct}`

2. `fetch_usdinr() -> float`
   - `yf.Ticker("USDINR=X").history(period="1d")["Close"].iloc[-1]`

3. `fetch_amfi_navs(scheme_codes: list[str]) -> dict[str, float]`
   - GET `https://www.amfiindia.com/spages/NAVAll.txt`
   - Parse pipe-delimited text; match scheme codes
   - Return `{scheme_name: nav_value}`

4. `format_market_snippet(data: dict) -> str`
   - Format all fetched data as a human-readable multi-line string for Nova's system prompt

5. `get_market_data(force_refresh: bool = False) -> dict`
   - Check `data/market_cache.json` freshness (TTL = `MARKET_DATA_CACHE_TTL_HOURS`)
   - If fresh: return cache
   - Else: fetch all, save cache, return
   - On any failure: return stale cache if available, else `{}`

**Verification:** `get_market_data()` returns a dict with `nifty` key when internet is available. Returns stale cache on network failure.

---

## PHASE 6: Nova Chatbot (`backend/chatbot/nova.py`)

**Depends on:** Phases 4 and 5 complete. `NewsContext` and market data available.

1. **Intent classifier** — `classify_intent(message: str) -> str`
   - Returns: `"spending"` | `"investment"` | `"general"`
   - Simple keyword matching: investment keywords = ["invest", "where should I", "portfolio", "fund", "nifty", "fd", "sip", "stock", "market", "rbi", "returns", "savings"]
   - If any investment keyword in message (case-insensitive): return "investment"
   - Elif spending keywords ["spend", "spent", "how much", "category", "merchant", "bill"]: return "spending"
   - Else: return "general"

2. **Web search tool definition** — `WEB_SEARCH_TOOL` dict per SRS §10.6

3. **`execute_web_search(query: str) -> str`** — per SRS §14.3
   - DuckDuckGo Instant Answer API primary
   - Google News RSS fallback
   - Max 500 chars returned
   - Strip HTML before returning
   - On failure: return empty string (never raise)

4. **`build_system_prompt(analysis, market_data, news_context) -> str`** — per SRS §10.3 template
   - Format all fields
   - If `news_context` is None: replace `{news_summary}` with "Current news unavailable."
   - If `market_data` is empty: replace `{market_data_snippet}` with "Market data unavailable."

5. **`should_use_web_search(provider: str) -> bool`**
   - Return True only for: `"groq"`, `"openai"`, `"anthropic"`
   - Return False for `"ollama"` (no tool calling support)

6. **`call_llm(messages, system_prompt, use_tools: bool) -> AsyncGenerator[str]`**
   - Dispatch to correct provider based on `config.LLM_PROVIDER`
   - If `use_tools=True` and provider supports it: include `WEB_SEARCH_TOOL` in tools list
   - Handle tool use response: if LLM returns a tool call, execute `execute_web_search()`, inject result as tool result, re-call LLM
   - Stream response token-by-token

7. **`chat(message: str, history: list[dict], transactions: list[Transaction]) -> AsyncGenerator[str]`**
   - Classify intent
   - Generate analysis from transactions
   - Fetch market data
   - If intent == "investment": fetch news context
   - Else: news_context = None
   - Build system prompt
   - Determine if web search should be enabled
   - Call LLM and stream response
   - Sanitize input: strip prompt injection patterns before sending

8. **Input sanitization** — strip: "ignore previous instructions", "you are now", "disregard", "forget your", "new persona" (case-insensitive). Truncate to 2000 chars.

9. **Output guardrails:**
   - If no transactions: return fixed string "I don't have any bills to analyze yet. Upload some bills to get started!"
   - On LLM timeout: return "Nova is temporarily unavailable. Please try again."
   - On empty response: retry once, then return "Nova couldn't generate a response. Please try rephrasing."

**Verification:** Spending query → no news fetch. Investment query → news context injected. Ollama provider → no web search tool. Web search tool invoked → `execute_web_search` called → result injected.

---

## PHASE 7: FastAPI Backend (`backend/main.py`)

**Depends on:** All pipeline and chatbot modules complete.

1. **App setup:**
   - Create `FastAPI()` app
   - Mount CORS: allow `http://localhost:*` only
   - Mount `frontend/` as static files at `/`
   - On startup: call `start_news_scheduler(app)` and run first `get_news_context()` fetch

2. **Rate limiters (slowapi):**
   - Upload: 10/minute per IP
   - Chat: 20/minute per IP
   - News refresh: 2/hour per IP

3. **File validation helper:**
   - Check magic bytes (not Content-Type header) for JPEG, PNG, WEBP, PDF, HEIC
   - Check file size ≤ `UPLOAD_MAX_SIZE_MB`
   - Save to temp dir with UUID filename; schedule deletion after processing

4. **Implement all endpoints from SRS §11.2:**

   **`POST /api/v1/upload`**
   - Accept `multipart/form-data`, field `files`, max 10 files
   - For each file: validate format + size → preprocess → OCR → KIE → structure → check_duplicate (against full transaction store) → detect_anomalies
   - Return array of `{file_name, extraction, duplicate_check, anomaly_check}` per SRS §11.3
   - Do NOT persist to store yet — wait for user confirmation

   **`POST /api/v1/transactions/confirm`**
   - Accept: `{extraction_result, user_edits: dict | null}`
   - Apply edits to extraction result if provided
   - Convert to Transaction, set `user_confirmed=True`, `manually_edited=True` if edits applied
   - Persist via `persist_transaction()`

   **`POST /api/v1/transactions/discard`**
   - No-op (temp file already deleted); return success

   **`GET /api/v1/transactions`**
   - Query params: `start_date`, `end_date`, `category`, `limit` (default 50), `offset` (default 0)
   - Load from JSON store, filter, paginate, return

   **`GET /api/v1/transactions/{id}`** — filter by ID, 404 if not found

   **`DELETE /api/v1/transactions/{id}`** — remove from JSON store (atomic write)

   **`POST /api/v1/transactions/{id}/dismiss-anomaly`** — set `is_anomaly=False`, `anomaly_score=0.0`, `anomaly_reason="dismissed"` for given ID

   **`GET /api/v1/analysis`** — call `generate_analysis(all_transactions)`, return result

   **`POST /api/v1/chat`**
   - Body: `{message: str, conversation_history: list[dict]}`
   - Sanitize input (max 2000 chars, strip injection patterns)
   - Call `nova.chat()` — return `StreamingResponse` with `text/event-stream`
   - Each streamed token: `data: {token}\n\n`

   **`GET /api/v1/market`** — return `get_market_data()`

   **`GET /api/v1/news`** — return `get_news_context()` or error if None

   **`POST /api/v1/news/refresh`** — force `get_news_context(force_refresh=True)`; rate-limited 2/hour

   **`GET /api/v1/benchmark`** — run `evaluate.py` logic inline, return metrics JSON

   **`GET /api/v1/health`** — return status of all components: OCR, KIE, LLM connection, news cache freshness, market cache freshness

5. **Error handling middleware:**
   - All unhandled exceptions → `{success: false, data: null, error: {code, message, details}}`
   - Never expose stack traces in response body

6. **Duplicate confirmation endpoint:**
   - `POST /api/v1/duplicate/confirm` — body: `{transaction_id, confirmed: bool}`
   - If confirmed: remove duplicate flag, persist
   - Log decision to `duplicate_log.json`

**Verification:** All 14 endpoints return 200 on happy path. Upload rejects file > 10 MB with 413. Unsupported format returns 415. Chat streams response.

---

## PHASE 8: Frontend (`frontend/`)

**Note:** This implementation is functional/data-binding focused. Visual redesign will be done in a separate pass. Keep CSS minimal and structural — no time spent on polish here.

### `frontend/index.html`
- Two-column layout: left 60% (dashboard), right 40% (upload + Nova)
- Header: "FinSight" + tagline + subheadline (from SRS §9.1)
- All sections as semantic HTML: `<section id="upload">`, `<section id="transactions">`, `<section id="charts">`, `<section id="nova">`
- Canvas elements for 3 Chart.js charts
- Chat bubble container + input row

### `frontend/style.css`
- Minimal structural CSS only
- Responsive breakpoints: ≥1024px (two-col), 768–1023px (two-col reduced), <768px (single-col)
- Color-coded confidence: `.confidence-high {color: green}`, `.confidence-mid {color: orange}`, `.confidence-low {color: red}`
- Anomaly rows: `.anomaly-row {border-left: 3px solid red}`
- Duplicate rows: `.duplicate-row {border-left: 3px solid blue}`
- **No decorative styling — defer to design pass**

### `frontend/app.js`

1. **State object:**
   ```javascript
   const state = {
     transactions: [],
     currentExtraction: null,
     novaHistory: [],
     analysis: null,
     charts: { donut: null, line: null, bar: null }
   };
   ```

2. **On page load:** `GET /api/v1/transactions` + `GET /api/v1/analysis` → populate state + render table + render charts

3. **Upload section:**
   - Drag-and-drop zone labeled "Come see where you lost money"
   - File picker button + supported formats label
   - On drop/select: show thumbnail preview (use `URL.createObjectURL`)
   - Show spinner during upload
   - `POST /api/v1/upload` (multipart)
   - On response: show extraction preview panel

4. **Extraction preview panel:**
   - Render each field: label, value, confidence badge (color-coded)
   - Each value is an `<input>` (editable inline)
   - "Confirm" → `POST /api/v1/transactions/confirm` with user edits → refresh transactions + charts
   - "Discard" → `POST /api/v1/transactions/discard` → hide panel

5. **Transaction table:**
   - Columns: Date, Merchant, Category, Amount, Status
   - Sortable: click header toggles asc/desc
   - Row click: expand to show full extraction details
   - Status badge: "anomaly" (red), "duplicate" (blue), "normal" (gray)
   - Duplicate row: show "Confirm duplicate" / "Keep both" buttons
   - Anomaly row: show "Dismiss" button → `POST /api/v1/transactions/{id}/dismiss-anomaly`

6. **Charts (Chart.js CDN):**
   - Chart 1: Doughnut — `analysis.category_totals`
   - Chart 2: Line — `analysis.daily_trend`
   - Chart 3: Bar — `analysis.top_merchants`
   - `updateCharts(analysis)` function called after every confirm/delete

7. **Nova chat panel:**
   - Chat bubble render: Nova left, user right
   - Input at bottom, send on Enter or button click
   - Pre-fill input with "Where do I invest?" as placeholder
   - On send: append user bubble → `POST /api/v1/chat` with SSE → append Nova bubble, stream tokens in
   - Disclaimer footer: "Nova does not provide certified financial advice."
   - Handle SSE: `const es = new EventSource(...)` with `onmessage` appending tokens

**Verification:** Upload a synthetic bill → extraction panel appears → confirm → transaction in table → charts update. Ask Nova a question → streaming response appears.

---

## PHASE 9: Tests

One file per module. Each test independently runnable with mock inputs (no live network, no real files required unless specifically an integration test).

### `tests/test_preprocess.py`
- `detect_format` on magic bytes for all 5 formats
- `pdf_to_image` on synthetic PDF → returns PIL Image
- `deskew` on a 5° rotated test image → rotation reduced
- `normalize_contrast` on dark image (mean < 80) → contrast improves
- `sharpen_if_blurry` on blurry test image (Laplacian < 100) → sharpens
- `preprocess` on empty file → raises PreprocessingError

### `tests/test_ocr.py`
- `run_paddleocr` on clean synthetic bill → returns non-empty list of OCRBlocks
- `run_tesseract` on clean synthetic bill → same format
- `merge_line_blocks` with mock blocks on same line → merged correctly
- `run_ocr` with mocked PaddleOCR raising exception → tesseract fallback triggered

### `tests/test_kie.py`
- CORD path: itemized bill → returns LineItems with prices
- SROIE path: invoice-format bill → merchant, date, total correctly extracted
- FUNSD path: unknown format → Q→A pairs mapped correctly
- Date normalization: `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`, `DD Mon YYYY`, `DD-MM-YYYY` → all return `YYYY-MM-DD`
- Amount parsing: `"₹1,250.00"` → `1250.0`, `"Rs. 500"` → `500.0`
- Low-confidence field → marked as "unextracted"

### `tests/test_structurer.py`
- `infer_category("zomato", [])` → "Food"
- `infer_category("swiggy", [])` → "Food"
- All 12 merchants in lookup → correct category
- Unknown merchant → zero-shot classifier called (mock classifier)
- UUID assigned → unique per call
- `persist_transaction` → file readable after write; append of second transaction keeps first

### `tests/test_deduplicator.py`
- Same file bytes → same hash
- Same merchant/date/total → same fingerprint
- `check_duplicate` on exact match → `is_duplicate=True, confidence=1.0`
- `check_duplicate` on fuzzy match (amount within 0.5%, date same day) → `is_duplicate=True, confidence=0.85`
- `check_duplicate` on genuinely different transaction → `is_duplicate=False`

### `tests/test_analyzer.py`
- `compute_category_totals` on 5 transactions → correct per-category sums
- `compute_daily_trend` → 30 entries returned, 0-spend days included
- `detect_anomalies` on anomaly bill (amount >> mean+2σ) → `is_anomaly=True`
- `detect_anomalies` on normal bill → `is_anomaly=False`
- `compute_savings_opportunity` → correct when spend > budget; 0 when spend < budget

### `tests/test_news.py` (NEW)
- `fetch_rss` with mock feedparser response → returns list of dicts
- `fetch_rss` with network error → returns empty list (no exception)
- Headline deduplication → same headline twice → appears once
- Age filter → headline older than 48h → excluded
- `summarize_headlines` with mock LLM returning valid JSON → returns populated NewsContext
- `summarize_headlines` with mock LLM returning invalid JSON → returns NewsContext with empty fields, no exception
- `get_news_context` with fresh cache → returns cached, no fetch
- `get_news_context` with stale cache → fetches and updates
- `get_news_context` with fetch failure and cache < 24h → returns stale cache
- `get_news_context` with fetch failure and cache > 24h → returns None

### `tests/test_api.py`
- `POST /api/v1/upload` with valid PNG → 200, returns extraction
- `POST /api/v1/upload` with file > 10MB → 413
- `POST /api/v1/upload` with .txt file → 415
- `POST /api/v1/transactions/confirm` → transaction in store
- `GET /api/v1/transactions` → returns list
- `DELETE /api/v1/transactions/{id}` → removed from store
- `GET /api/v1/analysis` → returns AnalysisResult
- `POST /api/v1/chat` → streaming response (check Content-Type: text/event-stream)
- `GET /api/v1/news` → returns NewsContext or descriptive error
- `GET /api/v1/health` → 200 with component status dict

---

## PHASE 10: Benchmarking

### `backend/benchmarks/evaluate.py`
- Load `synthetic/ground_truth.json`
- For each bill in `synthetic/synthetic_bill_images/`:
  - Run full pipeline (preprocess → OCR → KIE → structurer)
  - Compare extracted fields to ground truth entry
- Compute and print:
  - Per-field accuracy: merchant, date, total, category (target: ≥70%)
  - Anomaly detection recall (target: ≥80%)
  - Duplicate detection precision (target: ≥95%)
  - Overall extraction F1
- Save to `backend/benchmarks/results.json`

---

## PHASE 11: README + Final Wiring Checklist

### `README.md`
- System dependencies: `poppler-utils`, `tesseract-ocr`, `libgl1`
- Setup: `pip install -r requirements.txt`, populate `.env`
- Run: `uvicorn backend.main:app --reload --port 8000`
- Generate synthetic data: `python synthetic/generate_bills.py && python synthetic/pdf_to_images.py && python synthetic/make_messy.py`
- Run benchmarks: `python backend/benchmarks/evaluate.py`
- Run tests: `pytest tests/`

### Final wiring checklist (agent must verify each):
- [ ] `config.py` is the single source of all thresholds — no hardcoded values in any pipeline file
- [ ] `NEWS_CACHE_TTL_HOURS` and `MARKET_DATA_CACHE_TTL_HOURS` read from config, not hardcoded
- [ ] All exceptions in pipeline return structured `{success: false, error: {...}}` JSON — no stack traces exposed
- [ ] All writes to `transactions.json`, `news_cache.json`, `market_cache.json`, `duplicate_log.json` use atomic write (temp file + `os.replace()`)
- [ ] `filelock` used around all reads AND writes to `transactions.json`
- [ ] CORS allows `localhost` only
- [ ] `.env` is in `.gitignore` and not committed
- [ ] Temp uploaded files are deleted after processing (success or failure)
- [ ] Web search disabled when `LLM_PROVIDER=ollama`
- [ ] News scheduler starts on FastAPI startup and runs first fetch immediately
- [ ] Nova input sanitized before LLM call (injection patterns stripped, 2000 char limit)
- [ ] Web search query validated (max 100 chars, special chars stripped)
- [ ] RSS HTML stripped before LLM injection
- [ ] Investment suggestions always end with disclaimer
- [ ] `GET /api/v1/health` reports news cache freshness and market cache freshness

---

## Execution Order Summary

| Phase | What | Depends On |
|-------|------|-----------|
| 0 | Scaffold | Nothing |
| 1 | Data models | Phase 0 |
| 2 | Synthetic data | Phase 1 |
| 3 | Pipeline (6 stages) | Phases 1, 2 |
| 4 | News module | Phases 0, 1 |
| 5 | Market module | Phase 0 |
| 6 | Nova chatbot | Phases 3, 4, 5 |
| 7 | FastAPI backend | Phases 3, 4, 5, 6 |
| 8 | Frontend | Phase 7 (API must be running) |
| 9 | Tests | All phases |
| 10 | Benchmarks | Phases 2, 3 |
| 11 | README + checklist | All phases |
