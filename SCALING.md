# Scaling Notes

## Current V1 Limits

- JSON storage only. File locks serialize writes and each append rewrites the full JSON list.
- No authentication or multi-user isolation.
- Upload OCR runs synchronously inside the web request.
- Pending upload sessions are process-local and expire by TTL.
- Rate limiting is process-local.
- No real banking integration.
- No background OCR worker queue.

## What Fails First

At 100 concurrent users, OCR requests and pending upload memory are the first risks. Uploads are bounded by size, but preprocessing, OCR, PIL/OpenCV copies, and pending session storage still consume CPU and memory in the web process.

At 1000 bills, duplicate detection and JSON persistence become the dominant bottlenecks. Duplicate detection scans existing transactions, and analysis/Nova load the transaction list for each request.

On Railway free tier, the likely failure modes are memory pressure during OCR/model initialization, missing system OCR/PDF dependencies if Docker is bypassed, slow cold starts, and data loss without a mounted `/data` volume.

## Recommended Scaling Path

1. Add authentication and tenant/user IDs before accepting real users.
2. Replace JSON persistence with PostgreSQL tables for transactions, duplicate decisions, jobs, and caches.
3. Move OCR into a background worker with durable job state and retry limits.
4. Store raw uploads in object storage or a short-lived encrypted temp store.
5. Add Redis-backed rate limiting and shared pending-session state.
6. Add structured logs, request IDs, metrics, and provider latency tracking.
7. Use separate web and worker containers with CPU/memory sized for OCR.

## Free-Tier Guidance

Railway free or very small tiers are suitable for demos with a few uploads. Keep benchmark endpoint disabled in production, attach `/data`, avoid large PDFs, and expect cold OCR requests to be slow. A paid tier or separate worker host is recommended for reliable OCR demos.

## KPI Metrics Limits

The Benchmark Metrics panel is evaluator-facing and uses the saved synthetic benchmark result file. It is not a live production observability system. Real user correction rate, Nova groundedness, retrieval precision, chatbot relevance, and validated savings require persisted review/chat events plus labeled evaluation data before they can be automated. External datasets such as SROIE or CORD can be added later without changing the v1 Railway topology.
