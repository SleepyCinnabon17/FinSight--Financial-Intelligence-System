# FinSight

FinSight ingests bill images/PDFs, extracts transactions, detects anomalies and duplicates, summarizes spending, and streams Nova chatbot responses with market and news context.

## System Dependencies

Install these OS packages where applicable:

- `poppler-utils`
- `tesseract-ocr`
- `libgl1`

The code falls back gracefully when optional OCR/PDF system tools are unavailable, but production OCR quality is best with them installed.

## Setup

```bash
pip install -r requirements.txt
```

Populate `.env` with provider keys as needed:

```bash
GROQ_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LLM_PROVIDER=groq
```

## Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/`.

## Generate Synthetic Data

```bash
python synthetic/generate_bills.py
python synthetic/pdf_to_images.py
python synthetic/make_messy.py
```

## Run Benchmarks

```bash
python backend/benchmarks/evaluate.py
```

Results are written to `backend/benchmarks/results.json`.

## Run Tests

```bash
pytest tests/
```
