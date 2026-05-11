# FinSight Post-Implementation Audit

Date: 2026-05-11  
Scope: current repository after frontend modularization/redesign and production-hardening pass.

## Executive Summary

FinSight is now deployable as a single-user/demo Railway-style portfolio project. The repo includes frontend modularization, XSS-safe rendering, production config, Docker/Railway assets, health probes, a Railway smoke script, production-mode tests, JSON corruption repair, and deployment documentation.

It is not a real multi-user financial production system. The remaining serious gaps are authentication, durable database storage, background OCR workers, shared rate limiting/session state, and formal privacy/compliance controls.

## Priority Findings

| Priority | Area | Finding | Severity | Effort | Agent-solvable | Deployment Impact | Scalability Impact | Recommended Next Step |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | Auth/security | No authentication or tenant isolation | Critical | L | Yes | Public deployment can be mutated by anyone | Blocks real multi-user use | Add auth, user IDs, and authorization checks before real data use |
| P0 | Storage | JSON storage only | Critical | L | Yes | Requires mounted volume and remains demo-only | File locks/full rewrites bottleneck writes | Replace with PostgreSQL while keeping API schemas |
| P0 | OCR architecture | OCR runs in the web process | High | L | Yes | Uploads can time out or exhaust dyno memory | CPU-bound requests starve API workers | Move OCR to a background worker/job queue |
| P0 | Pending uploads | Pending sessions are process-local | High | M | Yes | Multi-worker confirms can fail; restart loses drafts | Memory rises with abandoned uploads | Store pending state in Redis/Postgres/object storage with TTL |
| P1 | Rate limiting | Limits are process-local | High | M | Yes | Multi-instance deployments bypass limits | Weak abuse protection | Add Redis-backed limiter |
| P1 | SSE robustness | Nova SSE lacks heartbeat/durable session resume | Medium | M | Yes | Proxy disconnects can interrupt chats | Long chats consume worker capacity | Add heartbeat, timeout, retry guidance, and cancellation telemetry |
| P1 | Security headers | No CSP/HSTS/security header middleware | Medium | S | Yes | Browser hardening incomplete | No scale effect | Add production security headers after checking frontend inline-script needs |
| P1 | Observability | Logs are not structured with request IDs/timings | Medium | M | Yes | Hosted debugging is harder | Bottlenecks harder to locate | Add JSON logs, request IDs, OCR/provider timing |
| P2 | UX scale | Transaction browsing is not server-paginated in the UI | Medium | M | Yes | Fine for demos, weak for large histories | 1000+ bills become harder to browse | Add filters/search/pagination controls |
| P2 | Dependency weight | OCR/ML dependencies are heavy | Medium | M | Yes | Free-tier builds/cold starts may be slow | Memory pressure under load | Split optional ML paths and document minimum memory |

## What Would Fail Under 100 Concurrent Users

- OCR uploads saturate CPU and memory because preprocessing/OCR/KIE run in the request path.
- Pending upload memory grows because extracted sessions keep raw bytes until confirm/discard/TTL.
- Multi-worker confirmation is unreliable because `PENDING_UPLOADS` is process-local.
- JSON writes serialize on file locks and rewrite the full transaction file.
- SlowAPI limits are process-local and do not coordinate across multiple instances.
- Nova SSE streams can tie up workers during long LLM/provider responses.

## What Would Fail Processing 1000 Bills

- Duplicate detection and analysis repeatedly scan the full transaction list.
- `transactions.json` and `duplicate_log.json` grow and are rewritten as full files.
- Frontend browsing lacks large-history pagination/search controls.
- Nova context loading becomes slower because all transactions are loaded for each chat request.

## What Would Fail On Railway Free Tier

- OCR/model initialization may exceed memory during cold starts or large uploads.
- Deployments without a `/data` volume lose JSON data on restart/redeploy.
- Long OCR uploads and benchmark calls can hit platform/proxy timeouts.
- A public URL without auth can be used by anyone unless kept private.
- Free-tier CPU is not suited for concurrent OCR workloads.

## Agent-Doable Remaining Tasks

| Task | Severity | Effort | Approach |
| --- | --- | --- | --- |
| Add auth | Critical | L | Add provider/session auth, user IDs on transactions, protected mutation routes |
| PostgreSQL migration | Critical | L | Add repository layer, migrations, indexes for date/merchant/hash/fingerprint |
| Background OCR jobs | High | L | Add job table/queue, worker process, status endpoint, retry/failure states |
| Shared pending uploads | High | M | Store pending metadata in Redis/Postgres and raw upload bytes in object/temp storage |
| Redis-backed limits | High | M | Configure SlowAPI shared backend or replace limiter |
| SSE heartbeat/cancellation telemetry | Medium | M | Emit heartbeat events and log client disconnects/provider timeouts |
| Security headers/CSP | Medium | S | Add production middleware and verify frontend still runs |
| Structured logging | Medium | M | Add request IDs, JSON log format, OCR/provider latency fields |

## Human/Manual Remaining Tasks

| Task | Severity | Effort | Reason |
| --- | --- | --- | --- |
| Deploy on Railway | High | S | Requires account/project access |
| Provision secrets | High | S | LLM keys must be created outside source control |
| Mount Railway volume | High | S | Required for demo persistence at `/data` |
| Choose production storage provider | Critical | S | PostgreSQL/Redis provider affects cost and architecture |
| Define privacy/data retention policy | High | M | Uploaded bills contain sensitive financial data |
| Validate with real anonymized bills | High | M | Synthetic benchmark does not prove real-world OCR quality |

## Deployment Blockers

For a portfolio demo, deployment blockers have been reduced to manual Railway setup: project creation, environment variables, domain/origin value, and volume mount.

For real production, blockers remain: no auth, no database, no background worker, no shared rate limiting, no formal retention policy, and no compliance review.

## Known Limitations To Keep Visible

- No authentication.
- JSON storage only.
- Single-user/demo deployment only.
- OCR is CPU and memory intensive.
- No real banking integration.
- No PostgreSQL/Redis/background worker yet.
- Nova is informational and not certified financial advice.
