# FinSight Post-Implementation Audit

Date: 2026-05-11  
Scope: post-build gap analysis of the current repository only. No SRS-driven redesign was used for this audit.

## Executive Summary

FinSight is functional as a local or single-user demo, but it is not yet production-ready for multi-user deployment. The biggest risks are deployment packaging, local JSON persistence, synchronous OCR workloads, process-local pending upload state, and frontend DOM injection exposure from OCR/user-controlled values.

The system will work best today as a portfolio demo run from a developer machine. It will struggle on low-memory hosted environments, especially Railway free tier, because PaddleOCR, PDF conversion, image preprocessing, optional Transformers classification, and synchronous request handling all run inside the web process.

Effort scale:

| Effort | Meaning |
| --- | --- |
| S | Less than 1 day |
| M | 1 to 3 days |
| L | 3 to 7 days |
| XL | More than 1 week |

Severity scale:

| Severity | Meaning |
| --- | --- |
| Critical | Blocks real deployment or risks data loss/security exposure |
| High | Likely to fail under normal production use |
| Medium | Important for quality, maintainability, or scale |
| Low | Polish or hygiene issue |

## Priority Order

| Priority | Area | Finding | Severity | Effort | Agent-solvable | Deployment Impact |
| --- | --- | --- | --- | --- | --- | --- |
| P0-1 | Deployment | No production container/deployment assets are present | Critical | M | Yes | Blocks reliable hosted deployment |
| P0-2 | Persistence | Transactions and logs use local JSON files | Critical | L | Yes | Data loss on ephemeral hosts and poor concurrency |
| P0-3 | OCR | Upload OCR runs synchronously inside API requests | Critical | L | Yes | Timeouts, CPU saturation, poor concurrency |
| P0-4 | State | `PENDING_UPLOADS` is process-local and stores raw bytes in memory | Critical | M | Yes | Breaks multi-worker deployment and can leak memory |
| P0-5 | Security | Frontend renders OCR/API data with `innerHTML` | Critical | S | Yes | Stored/reflected XSS risk through uploaded bills or edits |
| P0-6 | Config | Production CORS and environment validation are incomplete | High | S | Yes | Hosted frontend/API may fail or silently run misconfigured |
| P1-1 | Storage scale | Duplicate detection, analysis, and transaction reads scan whole JSON datasets | High | L | Yes | Latency rises with every bill |
| P1-2 | Runtime deps | OCR/PDF/Transformers dependency footprint is too heavy for free-tier defaults | High | M | Yes | Build failures, cold starts, OOM kills |
| P1-3 | SSE | Nova SSE lacks heartbeat, cancellation handling, and durable session state | High | M | Yes | Long chats disconnect under proxies/load |
| P1-4 | Scheduler/cache | News scheduler and cache writes are per-process and not lock-protected | Medium | M | Yes | Duplicate refresh jobs and occasional cache races |
| P1-5 | Health/observability | Healthcheck is shallow and logging is not production-structured | Medium | M | Yes | Failures are hard to diagnose and health may be false-positive |
| P1-6 | Endpoint safety | Benchmark endpoint runs heavy work from the web API | Medium | S | Yes | Public deployments can trigger CPU-heavy workloads |
| P2-1 | UX | Frontend is functional but not portfolio-grade or fully responsive/accessibility-ready | Medium | L | Yes | Weak demo impression and lower usability |
| P2-2 | Docs | README lacks deployment, architecture, scaling, screenshots, and troubleshooting | Medium | M | Yes | Reviewers cannot quickly evaluate the system |
| P2-3 | Repo hygiene | Runtime data/cache/artifacts and generated Python caches are mixed with source | Low | S | Yes | Bloats project and obscures intended deliverables |
| P2-4 | Dependency hygiene | Requirements are mostly unpinned and include heavyweight optional packages | Medium | M | Yes | Reproducibility and hosted installs are fragile |

## What Fails Under 100 Concurrent Users

1. API worker responsiveness degrades first. `backend/main.py` exposes async endpoints, but upload processing calls preprocessing, OCR, structuring, duplicate detection, and JSON persistence synchronously in the request path. One CPU-bound OCR request can occupy a worker long enough for other requests to queue.

2. Upload memory grows sharply. Each upload reads full file bytes into memory, creates PIL/OpenCV/numpy copies, and then stores raw bytes again in `PENDING_UPLOADS` until confirm/discard. At 100 concurrent uploads near the 10 MB limit, raw bytes alone can approach 1 GB before image/OCR/model overhead.

3. `PENDING_UPLOADS` becomes unreliable. It is a module-level dictionary in `backend/main.py`. With multiple Uvicorn/Gunicorn workers, upload confirmation can hit a different process and return "Upload session expired." With a single process, abandoned uploads remain in memory until restart.

4. JSON writes serialize and slow down. `backend/pipeline/structurer.py` uses `FileLock` and rewrites the full transactions JSON file on each persist. At 100 users confirming transactions, writes become a single-file bottleneck.

5. Duplicate logging amplifies write load. `backend/pipeline/deduplicator.py` logs each duplicate decision into an append-style JSON file, but it still reads and rewrites the whole log. Under concurrent uploads this creates extra lock contention.

6. Nova chat connections consume web capacity. `backend/main.py` streams Server-Sent Events from `/api/v1/chat`; `backend/chatbot/nova.py` can perform external web and LLM calls. There is no heartbeat, cancellation cleanup, rate-limited provider pool, or backpressure strategy.

7. In-memory rate limiting is incomplete for real scale. SlowAPI protects some endpoints, but process-local limiter state does not coordinate across workers or instances. Multi-instance deployment requires Redis or another shared limiter backend.

8. Startup and background work duplicate across workers. `backend/chatbot/news.py` starts a scheduler per app process. Multi-worker deployment can run multiple news refresh jobs, increasing outbound requests and cache write races.

## What Fails Processing 1000 Bills

1. Transaction storage becomes latency-sensitive. `transactions.json` is loaded, parsed, filtered, scanned, and rewritten as a full document in multiple paths. At 1000 bills this may still work locally, but each additional bill increases request latency and file corruption blast radius.

2. Duplicate detection becomes progressively slower. Duplicate checks compare against existing transactions by hash, fingerprint, and fuzzy merchant/amount/date logic. That is O(n) per uploaded bill, so bulk ingestion becomes O(n squared) overall.

3. Duplicate log growth becomes a hidden bottleneck. Every duplicate check logs a decision. Since the log is stored as JSON and rewritten atomically, processing 1000 bills can create thousands of log entries and repeated full-file writes.

4. Analysis and chat recompute from the full dataset. `/api/v1/analysis` and Nova chat load all transactions and compute aggregates on demand. At 1000 bills this is not catastrophic, but it will become visible in latency and memory, especially during concurrent chat sessions.

5. Frontend transaction browsing is not designed for large datasets. `frontend/app.js` fetches `/api/v1/transactions` and renders table rows client-side. The API defaults to a limited page, but the UI does not expose server pagination, search, or virtualized browsing for larger history.

6. OCR benchmark/runtime artifacts grow in local directories. Benchmark results, duplicate logs, transaction stores, and generated files accumulate without documented retention policy.

7. Failure recovery is weak. If JSON storage is corrupted, `_read_json_list()` returns an empty list in `backend/pipeline/structurer.py`. That avoids crashing, but it can hide data loss until a user notices missing transactions.

## What Fails On Railway Free Tier

1. Build/runtime dependency pressure is the most likely blocker. `requirements.txt` includes PaddleOCR, PaddlePaddle, OpenCV, PDF conversion, Tesseract integration, Transformers, datasets, yfinance, and APScheduler. This is heavy for a free-tier container and may exceed memory or build time limits.

2. Missing system packages break real OCR/PDF behavior. PDF support depends on Poppler, and Tesseract requires the Tesseract binary. Without a Dockerfile or Railway-specific package setup, production uploads may fail or silently degrade.

3. PDF fallback can hide a broken deployment. `backend/pipeline/preprocess.py` returns a placeholder image when Poppler conversion fails. A hosted app could appear healthy while extracting placeholder text instead of real PDF bill content.

4. Local filesystem persistence is unsafe. Railway filesystems are ephemeral across restarts/redeploys. `backend/data/transactions.json`, duplicate logs, cache files, and generated benchmark artifacts are not durable storage.

5. Cold start and memory pressure are high. PaddleOCR model initialization, optional Transformers pipeline creation, image preprocessing, and PDF conversion can exceed free-tier memory. Runtime may be killed during first upload.

6. CORS blocks typical hosted frontend origins. `backend/main.py` allows `http://localhost` origins only. A deployed frontend domain will fail browser requests unless CORS is made configurable.

7. Long requests may hit proxy timeouts. OCR upload, benchmark execution, and LLM-backed SSE chat can exceed free-tier proxy/request timeout expectations.

8. No production healthcheck exists for platform restarts. `/api/v1/health` reports static OCR/KIE availability and cache freshness, but does not verify PaddleOCR model load, Poppler, Tesseract, disk writability, JSON readability, or outbound provider reachability.

## Agent-Doable Tasks

| Priority | Task | Concrete Implementation Approach | Severity | Effort | Deployment Impact |
| --- | --- | --- | --- | --- | --- |
| P0 | Add production deployment assets | Create `Dockerfile`, `.dockerignore`, and optional `docker-compose.yml`; install system OCR/PDF dependencies; run app with Uvicorn/Gunicorn settings from config | Critical | M | Enables reproducible deployment |
| P0 | Replace JSON storage with PostgreSQL | Add repository layer, migrations, transaction and duplicate indexes, and atomic DB writes; keep existing API schemas stable | Critical | L | Solves durability and concurrent write bottlenecks |
| P0 | Move OCR to background jobs | Add job table/queue, worker process, upload status API, and polling/SSE progress; keep confirm flow but avoid long request-bound OCR | Critical | L | Prevents API worker starvation |
| P0 | Externalize pending upload state | Store pending upload metadata and raw files in durable temp storage with TTL; use Redis/Postgres/object storage instead of process memory | Critical | M | Enables multi-worker and restart-safe confirmation |
| P0 | Fix frontend DOM injection | Replace API/OCR-driven `innerHTML` rendering with DOM text nodes or a sanitizer; validate user-edited fields before confirm | Critical | S | Removes XSS path |
| P0 | Make production config explicit | Add env validation in `config.py`, configurable CORS origins, provider key diagnostics, and fail-fast startup checks for required production settings | High | S | Prevents silent misconfiguration |
| P1 | Add shared rate limiting | Configure SlowAPI with Redis storage or equivalent shared backend for multi-worker deployments | High | M | Makes limits effective across instances |
| P1 | Add structured logging and request IDs | Configure JSON logs, request correlation IDs, OCR timing, provider latency, and exception redaction | Medium | M | Improves debugging and operations |
| P1 | Harden healthchecks | Add checks for filesystem writability, storage connectivity, JSON/DB readability, Poppler/Tesseract availability, OCR model load status, cache age, and outbound dependency mode | Medium | M | Lets platforms detect bad deploys |
| P1 | Stabilize Nova SSE | Add heartbeat events, cancellation handling, provider timeout reporting, retry-friendly client states, and chat request rate limits | High | M | Reduces disconnects and hanging streams |
| P1 | Lock cache writes and isolate scheduler | Add file locks or DB-backed cache records; run scheduler as one process only or external cron job | Medium | M | Avoids duplicate refreshes and cache races |
| P1 | Remove or guard benchmark endpoint | Restrict `/api/v1/benchmark` to development/admin mode, or move it to CLI/CI only | Medium | S | Avoids public CPU abuse |
| P2 | Redesign frontend | Add modern responsive layout, dark/light theme, accessible states, upload progress, batch upload handling, chart polish, chat controls, and server pagination | Medium | L | Improves portfolio/demo quality |
| P2 | Add CI | Add GitHub Actions for lint, tests, benchmark validation, and Docker build verification | Medium | M | Prevents regressions |
| P2 | Improve docs | Add `DEPLOYMENT.md`, `ARCHITECTURE.md`, `SCALING.md`, screenshots, API notes, env matrix, and troubleshooting | Medium | M | Makes project reviewable |

## Human / Manual Tasks

| Priority | Task | Why Human Input Is Needed | Severity | Effort | Recommended Next Step |
| --- | --- | --- | --- | --- | --- |
| P0 | Choose production hosting target and budget | OCR memory/CPU needs determine whether Railway, Render, Fly.io, or a VPS is realistic | Critical | S | Select target platform and minimum paid tier before implementation |
| P0 | Provision secrets | LLM provider keys, allowed origins, admin controls, and observability tokens must be created outside the repo | High | S | Create secrets in the platform dashboard, not in source |
| P0 | Decide durable storage provider | PostgreSQL/Redis/object storage selection affects deployment architecture and cost | Critical | S | Pick managed Postgres and optional Redis/object storage |
| P1 | Validate OCR on real Indian bill samples | Synthetic benchmark coverage does not prove field accuracy on noisy real bills | High | M | Collect representative anonymized samples and record expected outputs |
| P1 | Define privacy/data retention policy | Bills and transactions contain financial/PII-like data | High | M | Decide retention, deletion, anonymization, and demo-data policy |
| P1 | Confirm legal/financial disclaimer wording | Nova provides financial-style insights and needs explicit boundaries | Medium | S | Review disclaimer with intended audience and risk tolerance |
| P2 | Review UI brand direction | Portfolio-grade look depends on aesthetic preference and audience | Medium | S | Approve target visual direction before redesign |
| P2 | Configure domain/TLS/monitoring | Requires accounts, DNS, billing, and alert destinations | Medium | S | Create production project, domain, and alert contacts |

## Technical Debt And Scalability Bottlenecks

### Local JSON Storage

Evidence: `backend/pipeline/structurer.py` persists transactions with `FileLock`, reads the full JSON list, appends or rewrites, then atomically replaces the file. `backend/pipeline/deduplicator.py` uses a similar JSON-file pattern for duplicate logs.

Impact: Works for demos, but file-level locking serializes writes, full-file rewrites increase latency with data size, and ephemeral hosts lose data.

Recommended approach: Move transactions and duplicate decisions to PostgreSQL. Add indexes on transaction ID, date, merchant, amount, file hash, fingerprint hash, and user/session identifiers if users are added. Keep file-based storage only as a local development adapter.

### Request-Bound OCR

Evidence: `/api/v1/upload` in `backend/main.py` reads files and runs preprocess/OCR/structuring/duplicate detection before returning.

Impact: OCR is CPU and memory heavy. It blocks the API path, causes timeouts, and makes autoscaling inefficient.

Recommended approach: Store the upload, return a job ID, process OCR in a worker, and expose job status. A simple first step is a database-backed job table plus one worker process. A stronger production path is Redis Queue/Celery/Arq or platform-native queues.

### Process-Local Pending Upload State

Evidence: `PENDING_UPLOADS` is a module-level dictionary in `backend/main.py` and stores raw bytes plus extracted data.

Impact: Multi-worker confirmations fail, abandoned uploads retain memory, and restarts lose unconfirmed uploads.

Recommended approach: Store pending uploads in durable storage with TTL and explicit cleanup. Store raw files in object storage or a temp file table, not in Python memory.

### O(n) Duplicate And Analysis Paths

Evidence: Duplicate checks compare new records to all existing records. Analysis and chat load all transactions each time.

Impact: 1000 bills is likely acceptable for a demo but not for real users or multi-user deployments. Bulk ingestion becomes increasingly slow.

Recommended approach: Precompute fingerprints, index them, and query candidates by hash/date/amount/merchant windows. Cache analysis summaries and invalidate them on transaction writes.

### Runtime Model Loading

Evidence: `backend/pipeline/structurer.py` calls `pipeline("zero-shot-classification")` inside category inference for unknown merchants.

Impact: May download or initialize a large model during a user request, creating unpredictable latency and memory spikes.

Recommended approach: Cache the classifier behind a config flag, choose an explicit model, preload in diagnostics only when enabled, or replace with a small deterministic category model for production.

## UX / Design Issues

| Area | Issue | Impact | Severity | Recommended Approach |
| --- | --- | --- | --- | --- |
| Visual design | Current frontend uses basic CSS, plain cards, and limited hierarchy | Weak portfolio impression | Medium | Redesign as a fintech dashboard with polished spacing, typography, charts, and dark/light themes |
| Upload flow | Multi-file upload stores only the first extraction in active UI state | Users can lose track of batch results | High | Render a review queue with one confirm/discard action per upload |
| PDF preview | Frontend previews images only | PDF uploads feel opaque | Medium | Add PDF filename/status preview and server extraction progress |
| Transactions | No visible pagination/search/filter controls | Hard to browse larger history | Medium | Add server-driven pagination, filters, and empty/error states |
| Chat | No cancel/retry/heartbeat status | Long Nova calls feel stuck | Medium | Add stop button, retry, connection status, partial error state |
| Accessibility | Status/confidence relies heavily on color and generic markup | Lower accessibility and polish | Medium | Add semantic labels, focus states, contrast checks, ARIA where needed |
| Mobile | Layout is basic and table-oriented | Reduced usability on phones | Medium | Add responsive transaction cards or compact table mode |

## Security Hardening Gaps

| Priority | Gap | Evidence | Impact | Recommended Approach |
| --- | --- | --- | --- | --- |
| P0 | XSS through OCR/API data | `frontend/app.js` renders rows/details/extraction fields with `innerHTML` | Malicious bill text or edited merchant/category can execute script | Use safe text rendering or sanitization; add CSP |
| P0 | No production auth/admin boundary | API endpoints expose upload, delete, benchmark, news refresh, and transaction operations | Public deployment would allow arbitrary users to mutate or exhaust resources | Add auth or keep API private/demo-gated |
| P1 | Stack traces avoided in most API paths, but logs/structured errors are limited | Exceptions are caught in some paths but not centrally normalized for observability | Hard to distinguish user errors from server faults | Add exception middleware with redacted structured logs |
| P1 | Uploaded financial documents lack retention policy | Confirmed/unconfirmed uploads and OCR text can contain sensitive data | Privacy and compliance risk | Add retention/deletion policy and secure storage controls |
| P1 | Rate limits are not shared across workers | SlowAPI default in-memory state | Attackers can bypass limits across instances | Use Redis-backed limiter |
| P2 | Security headers are not configured | Static frontend/API responses do not set CSP/HSTS/etc. | Browser attack surface remains wider | Add security middleware/proxy headers in production |

## Deployment Blockers

| Blocker | Severity | Why It Blocks | Concrete Fix |
| --- | --- | --- | --- |
| Missing Dockerfile/system dependency setup | Critical | PaddleOCR, Tesseract, Poppler, OpenCV, and PDF conversion need reproducible OS-level setup | Add Dockerfile with pinned Python base, system packages, healthcheck, and non-root runtime |
| Local JSON persistence | Critical | Hosted filesystems are ephemeral and unsafe for concurrent production writes | Move to Postgres or explicitly mount durable volume for demo-only deployments |
| Localhost-only CORS | High | Browser frontend on hosted domain cannot call API | Configure allowed origins from env |
| Process-local pending uploads | Critical | Multi-worker and restart behavior breaks confirm/discard flow | Move pending state to shared durable store |
| Heavy cold start | High | Free tier memory/time limits may kill first OCR request | Preload selectively, separate worker, and document minimum resources |
| Shallow healthcheck | Medium | Platform can mark a broken OCR deployment healthy | Add deep diagnostics and startup checks |
| No CI/build verification | Medium | Deployment can fail after merge without early signal | Add GitHub Actions for tests, lint, benchmark smoke, and Docker build |

## Production-Readiness Gap Details

### P0-1: No Production Container Or Deployment Assets

Impact: The repo does not define how to install system dependencies or run the API consistently in production.

Deployment implications: Railway/Render/Fly.io may build Python packages but still miss Poppler/Tesseract. Different platforms will behave differently.

Scalability implications: Without a worker topology, all CPU-heavy work stays in the web process.

Recommended next step: Add Dockerfile, `.dockerignore`, optional `docker-compose.yml`, and platform-specific deployment docs. Include a healthcheck command and non-root runtime user.

### P0-2: Local JSON Persistence

Impact: Transactions, duplicate logs, and caches are local files under `backend/data`.

Deployment implications: Railway-style ephemeral filesystems can lose data on restart/redeploy. Horizontal scaling creates divergent data per instance.

Scalability implications: File locks serialize writes and full JSON rewrites grow with data size.

Recommended next step: Introduce a storage abstraction and PostgreSQL implementation. Migrate transaction and duplicate log writes first, then market/news cache if needed.

### P0-3: OCR Runs In API Request Path

Impact: Upload latency is dominated by preprocessing/OCR and can exceed proxy timeouts.

Deployment implications: A small web dyno can become unavailable while handling OCR.

Scalability implications: More users require more web workers, but each worker carries heavy OCR memory.

Recommended next step: Move OCR to background workers and return job status. Keep the current synchronous path only for local development if needed.

### P0-4: `PENDING_UPLOADS` Is Process-Local

Impact: Upload confirmation depends on hitting the same process that handled extraction.

Deployment implications: Multi-worker or multi-instance deployments will intermittently fail confirmations.

Scalability implications: Raw bytes retained in memory limit concurrent uploads.

Recommended next step: Store pending upload sessions in Redis/Postgres with TTL and keep raw files in durable temporary storage.

### P0-5: Frontend DOM Injection Risk

Impact: OCR text and user-edited transaction fields can flow into `innerHTML`.

Deployment implications: Public demos can be attacked with crafted uploads.

Scalability implications: Security incident risk grows with public usage, not raw traffic volume.

Recommended next step: Replace dynamic `innerHTML` usage with safe element creation and `textContent`, or sanitize with a vetted library plus CSP.

### P0-6: Production Config Is Not Fail-Fast

Impact: Missing LLM keys, missing OCR binaries, bad CORS origins, or unavailable storage can remain hidden until runtime.

Deployment implications: A deployment can pass startup but fail during user flows.

Scalability implications: Misconfigured caches/providers can create retry storms or degraded UX.

Recommended next step: Add explicit configuration validation in `config.py` and startup diagnostics that report required, optional, and degraded capabilities without exposing secrets.

## Portfolio Readiness Gaps

| Gap | Impact | Recommended Next Step |
| --- | --- | --- |
| README is too brief | Reviewers do not see the architecture, OCR pipeline, Nova chat, benchmark rigor, or deployment story | Rewrite README with feature overview, screenshots, setup, architecture, benchmarks, and limitations |
| No screenshots or diagrams | The project is harder to evaluate quickly | Add `/docs/ui/` screenshots and architecture/data-flow diagrams |
| No scaling narrative | Reviewers may assume the JSON and synchronous OCR design is naive rather than intentionally scoped | Add `SCALING.md` explaining current limits and migration path |
| No production deployment guide | The app cannot be easily evaluated on hosted infrastructure | Add `DEPLOYMENT.md` for Railway, Render, and Fly.io |
| Benchmark results are not presented | OCR/KIE effort is hidden | Add benchmark summary and how to reproduce it |

## Recommended Implementation Sequence

1. Fix security and deployment blockers first: frontend safe rendering, configurable CORS, Dockerfile/system dependencies, and production env validation.
2. Make persistence durable: move transactions and duplicate logs to PostgreSQL while preserving API schemas.
3. Move OCR out of the web request path: add background jobs and pending upload durability.
4. Harden operations: structured logging, health diagnostics, shared rate limiting, scheduler isolation, and CI.
5. Improve frontend UX and portfolio presentation: responsive dashboard redesign, screenshots, README, architecture docs, and scaling docs.
6. Validate with real-world samples and load tests: 100 concurrent requests, 1000-bill ingestion, and hosted free-tier smoke tests.

## Final Classification

Agent-doable remaining work:

- Docker/deployment assets and CI.
- PostgreSQL-backed storage implementation.
- Background OCR worker and job status APIs.
- Shared pending upload state with TTL cleanup.
- Frontend XSS remediation.
- Frontend redesign and accessibility pass.
- Config validation, structured logging, healthcheck hardening.
- Documentation, screenshots, architecture diagrams, and scaling guide.

Human/manual remaining work:

- Select hosting platform and budget.
- Provision secrets and managed services.
- Provide real anonymized bill samples for OCR validation.
- Decide privacy, retention, and deletion policy.
- Approve branding/visual direction.
- Configure production domain, TLS, monitoring, and alert contacts.
- Review financial disclaimer wording for intended audience.

Deployment blockers:

- Missing container/system dependency definition.
- Local JSON persistence on ephemeral filesystem.
- Request-bound OCR workloads.
- Process-local upload confirmation state.
- Localhost-only CORS.
- Heavy cold start and memory footprint.
- Shallow healthcheck.

Highest-risk technical debt:

- JSON storage and duplicate logs.
- Synchronous OCR/PDF pipeline in API requests.
- Process-local pending upload state.
- O(n) duplicate, analysis, and transaction access patterns.
- Runtime Transformers classifier initialization.
- Cache/scheduler behavior under multi-worker deployment.

Highest-priority security issues:

- `innerHTML` rendering of untrusted data.
- No production authentication or demo gate.
- In-memory rate limiting only.
- No documented sensitive-data retention policy.
- No production security headers/CSP.
