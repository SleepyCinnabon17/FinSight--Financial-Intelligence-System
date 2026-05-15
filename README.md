# FinSight

FinSight is a FastAPI and vanilla JavaScript financial intelligence dashboard. It ingests bill images/PDFs, preprocesses them, runs OCR and key information extraction, persists confirmed transactions, detects duplicates and anomalies, summarizes spending, and streams Nova chatbot responses with market/news context.

> **Latest**: Fixed navigation button state helper for consistent module interaction.

## Features

- Multi-file bill upload with OCR extraction and confirm/discard review.
- PaddleOCR primary OCR with Tesseract fallback.
- Transaction structuring, duplicate detection, anomaly detection, and monthly spending analysis.
- Responsive fintech dashboard with charts, transaction browsing, upload review, and Nova SSE chat.
- Financial news and market cache support for Nova investment-context answers.
- External benchmark support for SROIE, CORD v2, and FUNSD, plus a separate synthetic regression check and collapsible dashboard metrics panel.
- Railway-ready Docker deployment, health probes, and smoke test tooling.

## System Dependencies

Install these OS packages for production-quality OCR/PDF behavior:

- `poppler-utils`
- `tesseract-ocr`
- `libgl1`

The app degrades gracefully when optional tools are unavailable, but real OCR quality is best with these installed.

### Windows OCR Setup

External receipt benchmarks require OCR tools on PATH. On Windows, install and verify:

```powershell
winget install UB-Mannheim.TesseractOCR
winget install oschwartz10612.Poppler
tesseract --version
pdfinfo -v
python scripts/check_ocr_deps.py
```

If either `winget` package name fails, install Tesseract from the UB Mannheim installer, install Poppler for Windows, add `tesseract.exe` and the Poppler `bin` folder to PATH, then restart VS Code or your terminal.

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
The frontend reads those generated results through `GET /api/v1/benchmark/results` for the collapsed **Benchmark Metrics** panel. This endpoint only serves the saved JSON file; it does not run the benchmark and remains safe when `GET /api/v1/benchmark` is disabled in production.

Synthetic benchmark output is an internal regression check only. It uses FinSight-generated bills to confirm the controlled pipeline did not break, so those scores are not presented as the public real-world accuracy headline.

Evaluator-facing external benchmarks are optional and run offline from Hugging Face Dataset Viewer or local dataset rows:

```bash
python backend/benchmarks/evaluate.py --external sroie --limit 25
python backend/benchmarks/evaluate.py --external cord --limit 25
python backend/benchmarks/evaluate.py --external funsd --limit 25
python backend/benchmarks/evaluate.py --external all --limit 25
```

Use `--no-download` to verify missing-dataset behavior without network calls, or `--dataset-dir <path>` for local JSON/JSONL rows. SROIE is the primary receipt field extraction benchmark; CORD v2 is treated as receipt OCR/layout robustness; FUNSD is treated as a document-structure stress test, not a receipt accuracy score. Full external datasets are not run in CI or Railway production.

Raw local external benchmark runs are valid only when OCR dependencies are present. The CLI fails early if required OCR tools are missing instead of writing misleading empty-OCR metrics. `--allow-missing-ocr` exists only for diagnostic debugging and should not be used for evaluator-facing results.

The official reproducible external benchmark path is Docker or CI. Docker uses the repo `Dockerfile`, which installs Tesseract and Poppler:

```bash
bash scripts/benchmark_docker.sh
```

PowerShell:

```powershell
.\scripts\benchmark_docker.ps1
```

To benchmark local dataset rows without committing datasets:

```bash
DATASET_DIR=/path/to/datasets bash scripts/benchmark_docker.sh
```

PowerShell:

```powershell
.\scripts\benchmark_docker.ps1 -DatasetDir "C:\path\to\datasets"
```

Both Docker scripts mount `backend/benchmarks`, so `results.json` and `debug/sroie_failures.json` persist back into the host repo.

For deterministic synthetic fixture validation in CI only, set:

```bash
FINSIGHT_ENABLE_OCR_FIXTURE_METADATA=1 python backend/benchmarks/evaluate.py
```

Do not set `FINSIGHT_ENABLE_OCR_FIXTURE_METADATA` in Railway or production.

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

## KPI Metrics Coverage

Automated KPI metrics now separate external evaluator results from synthetic regression results. Implemented calculations include OCR CER/WER/accuracy, field detection rate, field accuracy by field, amount accuracy within INR 1, date parse rate, category precision/recall/F1 where labels exist, duplicate detection rate, anomaly recall, confidence calibration buckets, and pipeline timing. Review-event correction rate, Nova groundedness/retrieval precision, chatbot relevance, and real savings validation are documented as deferred until review/chat logging or human labels exist.
