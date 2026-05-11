# FinSight

FinSight is a FastAPI and vanilla JavaScript financial intelligence dashboard. It ingests bill images/PDFs, preprocesses them, runs OCR and key information extraction, persists confirmed transactions, detects duplicates and anomalies, summarizes spending, and streams Nova chatbot responses with market/news context.

## Features

- Multi-file bill upload with OCR extraction and confirm/discard review.
- PaddleOCR primary OCR with Tesseract fallback.
- Transaction structuring, duplicate detection, anomaly detection, and monthly spending analysis.
- Responsive fintech dashboard with charts, transaction browsing, upload review, and Nova SSE chat.
- Financial news and market cache support for Nova investment-context answers.
- Synthetic benchmark pipeline with field accuracy, anomaly recall, duplicate precision, and extraction F1.
- Railway-ready Docker deployment, health probes, and smoke test tooling.

## System Dependencies

Install these OS packages for production-quality OCR/PDF behavior:

- `poppler-utils`
- `tesseract-ocr`
- `libgl1`

The app degrades gracefully when optional tools are unavailable, but real OCR quality is best with these installed.

## Local Setup

```bash
pip install -r requirements.txt
npm ci
```

Create `.env` as needed:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
APP_ENV=development
```

Run locally:

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/`.

## Tests And Benchmarks

```bash
python -m pytest
npm run test:frontend
npm test
python backend/benchmarks/evaluate.py
```

Production-mode check:

```bash
APP_ENV=production npm test
```

PowerShell:

```powershell
$env:APP_ENV='production'
npm test
Remove-Item Env:APP_ENV
```

Benchmark results are written to `backend/benchmarks/results.json`.

## Docker

```bash
docker build -t finsight .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e APP_ENV=production \
  -e FINSIGHT_DATA_DIR=/tmp/finsight-data \
  finsight
```

Smoke test:

```bash
bash scripts/smoke_railway.sh http://localhost:8000
```

## Railway

Use the Dockerfile deployment path and configure:

```bash
APP_ENV=production
FINSIGHT_DATA_DIR=/data
CORS_ALLOWED_ORIGINS=https://your-app.up.railway.app
LLM_PROVIDER=groq
GROQ_API_KEY=...
UPLOAD_MAX_SIZE_MB=10
```

Attach a Railway Volume at `/data` for demo persistence. See `DEPLOYMENT.md` for full steps.

## Known V1 Limitations

- No authentication or multi-user isolation.
- JSON file storage only; suitable for a single-user/demo deployment, not shared production finance data.
- OCR runs inside the web process and is CPU/memory intensive.
- Pending upload sessions are process-local and expire by TTL.
- No real banking integration.
- No PostgreSQL, Redis-backed rate limiting, or background OCR worker queue yet.

## Documentation

- `DEPLOYMENT.md` - Docker, Railway, production env, health probes, and smoke tests.
- `ARCHITECTURE.md` - pipeline, data flow, API surface, and runtime components.
- `SCALING.md` - bottlenecks, Railway free-tier constraints, and realistic scaling path.
- `SRS_COMPLIANCE_MATRIX.md` - implementation status against the SRS.
- `POST_IMPLEMENTATION_AUDIT.md` - remaining gaps and manual tasks.
