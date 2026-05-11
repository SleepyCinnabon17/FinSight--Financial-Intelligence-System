# Deployment Guide

## Local Production Mode

```bash
APP_ENV=production \
FINSIGHT_DATA_DIR=/tmp/finsight-data \
CORS_ALLOWED_ORIGINS=http://localhost:8000 \
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

PowerShell:

```powershell
$env:APP_ENV='production'
$env:FINSIGHT_DATA_DIR='/tmp/finsight-data'
$env:CORS_ALLOWED_ORIGINS='http://localhost:8000'
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t finsight:railway-smoke .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e APP_ENV=production \
  -e FINSIGHT_DATA_DIR=/tmp/finsight-data \
  -e CORS_ALLOWED_ORIGINS=http://localhost:8000 \
  finsight:railway-smoke
```

Smoke test from another terminal:

```bash
bash scripts/smoke_railway.sh http://localhost:8000
```

## Railway

1. Create a Railway project from the GitHub repository.
2. Let Railway build with the included `Dockerfile`.
3. Set the Railway healthcheck path to `/health/live`.
4. Add a Railway Volume mounted at `/data`.
5. Set required variables:

```bash
APP_ENV=production
FINSIGHT_DATA_DIR=/data
CORS_ALLOWED_ORIGINS=https://your-app.up.railway.app
LLM_PROVIDER=groq
GROQ_API_KEY=...
UPLOAD_MAX_SIZE_MB=10
MARKET_DATA_CACHE_TTL_HOURS=1
NEWS_CACHE_TTL_HOURS=2
```

Do not set `FINSIGHT_ENABLE_OCR_FIXTURE_METADATA` in Railway or any production environment. That flag is reserved for synthetic test fixtures only.

6. Deploy and run:

```bash
bash scripts/smoke_railway.sh https://your-app.up.railway.app
```

## Render

Use Docker deployment. Configure the same environment variables as Railway. Mount persistent disk storage and set `FINSIGHT_DATA_DIR` to that mount path. Use `/health/live` as a liveness probe and `/health/ready` as a readiness probe if the plan supports separate checks.

## Fly.io

Use Docker deployment. Allocate enough memory for OCR workloads, attach a volume for `FINSIGHT_DATA_DIR`, and expose the app on `${PORT:-8000}`. Start with one machine for the v1 JSON-storage deployment.

## Health Endpoints

- `/health/live`: minimal liveness probe. It confirms the process can respond.
- `/health/ready`: readiness probe. It checks data directory writability, transaction JSON repairability, frontend static files, OCR/PDF binaries, cache readability, app environment, benchmark status, and LLM provider configuration.
- `/api/v1/health`: API diagnostics for OCR/KIE/LLM/cache status. It returns booleans, labels, and provider names only.

Health responses must not expose API keys, raw environment values, stack traces, or secret paths.

## Benchmark Endpoint

`GET /api/v1/benchmark` is enabled by default in development and disabled by default when `APP_ENV=production`. Set `ENABLE_BENCHMARK_ENDPOINT=true` only for controlled environments.

## Smoke Test Commands

```bash
BASE_URL=https://your-app.up.railway.app
curl -fsS "$BASE_URL/health/live"
curl -fsS "$BASE_URL/health/ready"
curl -fsS "$BASE_URL/api/v1/transactions"
curl -fsS "$BASE_URL/"
```

Or:

```bash
bash scripts/smoke_railway.sh "$BASE_URL"
```

## Production Limitations

This v1 deployment is appropriate for a single-user portfolio/demo environment. It has no auth, no tenant isolation, JSON storage only, synchronous OCR inside the web process, and no real banking integration. Do not use it for real financial data without adding authentication, durable database storage, background workers, and privacy controls.
