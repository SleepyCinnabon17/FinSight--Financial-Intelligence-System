# Architecture

## Runtime Components

- `backend/main.py`: FastAPI app, API routes, upload session state, health probes, benchmark gate, and frontend static mount.
- `backend/pipeline/*`: preprocessing, OCR, KIE, transaction structuring, duplicate detection, and anomaly/spending analysis.
- `backend/chatbot/*`: Nova chat, market data cache, and financial news cache.
- `frontend/*`: vanilla JavaScript dashboard modules for API calls, state, upload, transactions, charts, and Nova chat.
- `synthetic/*` and `backend/benchmarks/evaluate.py`: generated-bill regression checks plus optional external SROIE/CORD/FUNSD benchmark evaluation.

## Request/Data Flow

```text
upload
  -> format validation and bounded read
  -> preprocessing
  -> PaddleOCR with timeout
  -> Tesseract fallback if needed
  -> KIE extraction
  -> transaction draft
  -> duplicate/anomaly preview
  -> pending upload session
  -> confirm/discard
  -> JSON transaction store
  -> analysis/dashboard/Nova context
```

## Persistence

Runtime JSON files live under `FINSIGHT_DATA_DIR`:

- `transactions.json`
- `duplicate_log.json`
- `market_cache.json`
- `news_cache.json`

Transaction writes use file locks and atomic temp-file replacement. Empty/corrupt/non-list transaction files are repaired safely; corrupt files are quarantined before reset.

## Nova

Nova receives sanitized user input, current transactions, generated analysis, market data when available, and summarized financial news when relevant. Responses stream over Server-Sent Events from `POST /api/v1/chat`.

## Deployment Topology

V1 topology is one web process plus a persistent volume:

```text
Browser -> FastAPI/Uvicorn container -> /data JSON files
                                  -> external LLM/RSS/market providers
```

The next production topology should split OCR into a worker and move storage to PostgreSQL:

```text
Browser -> API container -> PostgreSQL
                  |       -> Redis/job queue
                  v
              OCR worker -> object storage/temp upload storage
```
