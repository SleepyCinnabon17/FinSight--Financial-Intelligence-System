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
| Testing requirements | Implemented | `tests/*`, Playwright tests, benchmark script | Unit/integration/frontend/production-mode tests and synthetic benchmark exist. |
| Deployment requirements | Partial | Dockerfile, Railway config/docs, health probes, smoke script, CI | Railway deployment still requires manual project, secrets, domain, and volume setup. |
| Known limitations | Implemented | README, `DEPLOYMENT.md`, `SCALING.md`, audit | Auth, PostgreSQL, Redis, background workers, and banking integrations are out of scope for v1. |
