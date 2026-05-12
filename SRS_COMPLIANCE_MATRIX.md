# SRS Compliance Matrix

Status values: `Implemented`, `Partial`, `Missing`, `Out of scope for v1`.

| Area | Status | Evidence | Notes |
| --- | --- | --- | --- |
| FR-1 Upload | Implemented | `/api/v1/upload`, multi-file handling, size/type validation, frontend upload UX | HEIC depends on Pillow support in the runtime. Multi-page PDF processes the first page. |
| FR-2 Preprocessing | Implemented | `backend/pipeline/preprocess.py` | Deskew, resize, contrast, blur handling, and PDF conversion are implemented with graceful fallback. |
| FR-3 OCR | Implemented | `backend/pipeline/ocr.py` | PaddleOCR primary, Tesseract fallback, confidence filtering, ordering, line merge, and timeout fallback are covered. |
| FR-4 KIE | Implemented | `backend/pipeline/kie.py` | Extracts merchant, date, items, subtotal, tax, total, payment method, bill number, confidence, and normalized values. |
| FR-5 Transaction Structuring | Implemented | `backend/pipeline/structurer.py` | UUIDs, timestamps, category inference, atomic JSON persistence, and safe repair are implemented. |
| FR-6 Duplicate Detection | Implemented | `backend/pipeline/deduplicator.py` | SHA-256 file hash, transaction fingerprint, fuzzy checks, user resolution logging. |
| FR-7 Anomaly Detection | Implemented | `backend/pipeline/analyzer.py`, API dismiss route, frontend table | Baseline/rule flags and dismiss flow exist. |
| FR-8 Spending Analysis | Implemented | `/api/v1/analysis`, `backend/pipeline/analyzer.py` | Category, merchant, daily trend, MoM insights, and savings opportunity are exposed. |
| FR-9 Dashboard | Implemented | `frontend/*` | Responsive dashboard, charts, transaction table, upload review, manual edits, anomalies, and empty/loading states. |
| FR-10 Nova | Partial | `/api/v1/chat`, `backend/chatbot/nova.py` | SSE streaming, transaction context, market/news context, and disclaimer exist. Provider-native web search/tool calling remains limited by provider support and is documented. |
| FR-11 Financial News | Implemented | `/api/v1/news`, scheduler, `backend/chatbot/news.py` | RSS fetch, LLM/fallback summary, cache, endpoint, and graceful failure. |
| Security requirements | Partial | Upload validation, rate limits, error envelope, sanitization, production CORS | No auth, no tenant isolation, no CSP/security headers yet. |
| Testing requirements | Implemented | `tests/*`, Playwright tests, benchmark script | Unit/integration/frontend/production-mode tests and synthetic benchmark exist. Benchmark output now includes OCR CER/WER, extraction accuracy, category F1, anomaly/duplicate metrics, confidence calibration buckets, and pipeline timing. |
| Deployment requirements | Partial | Dockerfile, Railway config/docs, health probes, smoke script, CI | Railway deployment still requires manual project, secrets, domain, and volume setup. |
| Known limitations | Implemented | README, `DEPLOYMENT.md`, `SCALING.md`, audit | Auth, PostgreSQL, Redis, background workers, and banking integrations are out of scope for v1. |

## KPI Metrics Status

| KPI Area | Status | Evidence | Notes |
| --- | --- | --- | --- |
| OCR CER/WER/accuracy | Implemented | `backend/benchmarks/metrics.py`, `backend/benchmarks/evaluate.py`, `backend/benchmarks/results.json` | Computed from synthetic fixture reference text when available. |
| Field detection and extraction accuracy | Implemented | benchmark evaluator and metric tests | Covers merchant, date, amount/total, and category, plus amount tolerance within INR 1 and date parse rate. |
| Categorization precision/recall/F1 | Implemented | `classification_metrics` helper | Macro and weighted F1 plus per-category metrics are generated without heavy dependencies. |
| Duplicate/anomaly benchmark metrics | Implemented | evaluator duplicate/anomaly section | Includes duplicate precision, duplicate detection rate, anomaly recall, and false positive rate when denominator exists. |
| Confidence calibration | Partial | confidence buckets in benchmark output | Uses extraction confidence versus field correctness; full calibration needs larger labeled datasets. |
| Self-correction rate | Deferred | benchmark output status | Requires persisted review/edit event logging. |
| Nova/RAG groundedness and retrieval precision | Deferred | benchmark output status | No live LLM calls in CI; full metrics require source logging or labeled mock chat cases. |
| Product KPIs | Partial | pipeline timing, anomalies detected, savings opportunity | End-to-end benchmark timing and analysis-derived savings are present; real savings validation requires longitudinal/user data. |
| Frontend evaluator panel | Implemented | `#benchmark-metrics` in `frontend/index.html` | Collapsible panel reads saved benchmark results without running production benchmark. |
