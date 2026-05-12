from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend import config
from backend.chatbot.market import get_market_data, market_cache_is_fresh
from backend.chatbot.news import cache_is_fresh, get_news_context, load_news_cache, start_news_scheduler
from backend.chatbot.nova import chat as nova_chat
from backend.chatbot.nova import sanitize_input
from backend.models.analysis import AnalysisResult
from backend.models.extraction import ExtractedField, ExtractionResult, LineItem
from backend.models.transaction import Transaction
from backend.pipeline.analyzer import detect_anomalies, generate_analysis
from backend.pipeline.deduplicator import DuplicateResult, append_duplicate_resolution, check_duplicate
from backend.pipeline.kie import extract_fields
from backend.pipeline.ocr import run_ocr
from backend.pipeline.preprocess import PreprocessingError, detect_format, preprocess
from backend.pipeline.structurer import extraction_to_transaction, load_transactions, persist_transaction, sanitize_text_field, write_transactions


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> Any:
    scheduler = getattr(fastapi_app.state, "news_scheduler", None)
    if scheduler is None or not getattr(scheduler, "running", False):
        start_news_scheduler(fastapi_app)
    fastapi_app.state.news_warmup_task = asyncio.create_task(asyncio.to_thread(get_news_context))
    try:
        yield
    finally:
        warmup_task = getattr(fastapi_app.state, "news_warmup_task", None)
        if warmup_task is not None and not warmup_task.done():
            warmup_task.cancel()
        scheduler = getattr(fastapi_app.state, "news_scheduler", None)
        if scheduler is not None and getattr(scheduler, "running", False):
            scheduler.shutdown(wait=False)


app = FastAPI(title="FinSight API", version="2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_origin_regex=None if config.IS_PRODUCTION else r"^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PENDING_UPLOADS: dict[str, dict[str, Any]] = {}
SANITIZED_EDIT_FIELDS = {"merchant", "category", "payment_method", "bill_number"}


class ConfirmTransactionRequest(BaseModel):
    extraction_result: dict[str, Any] = Field(default_factory=dict)
    user_edits: dict[str, Any] | None = None
    upload_id: str | None = None


class DiscardRequest(BaseModel):
    upload_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


class DuplicateConfirmRequest(BaseModel):
    transaction_id: str
    confirmed: bool


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": _to_jsonable(data), "error": None}


def _error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"success": False, "data": None, "error": {"code": code, "message": message, "details": details}}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Transaction):
        return value.to_json_dict()
    if isinstance(value, AnalysisResult):
        payload = asdict(value)
        payload["top_merchants"] = value.top_merchants
        return payload
    if isinstance(value, DuplicateResult):
        return asdict(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    del request
    return JSONResponse(status_code=429, content=_error("rate_limit_exceeded", "Too many requests.", str(exc.detail)))


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    del request
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(status_code=exc.status_code, content=_error(f"http_{exc.status_code}", detail, None))


@app.middleware("http")
async def _unhandled_exception_middleware(request: Request, call_next: Any) -> Any:
    try:
        return await call_next(request)
    except HTTPException as exc:
        return await _http_exception_handler(request, exc)
    except Exception:
        return JSONResponse(
            status_code=500,
            content=_error("internal_error", "An unexpected error occurred.", None),
        )


def _load_all_transactions() -> list[Transaction]:
    return load_transactions(str(config.TRANSACTIONS_PATH))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_expired_pending_uploads() -> None:
    cutoff = _now() - timedelta(seconds=config.PENDING_UPLOAD_TTL_SECONDS)
    expired = [
        upload_id
        for upload_id, payload in PENDING_UPLOADS.items()
        if payload.get("created_at") is None or payload["created_at"] < cutoff
    ]
    for upload_id in expired:
        PENDING_UPLOADS.pop(upload_id, None)


def _pop_pending_upload(upload_id: str | None) -> dict[str, Any] | None:
    _cleanup_expired_pending_uploads()
    if not upload_id:
        return None
    pending = PENDING_UPLOADS.pop(upload_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="Upload session expired or not found.")
    return pending


def _validate_file_bytes(file_bytes: bytes) -> str:
    max_size = config.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=f"File too large. Maximum size is {config.UPLOAD_MAX_SIZE_MB}MB.")
    try:
        return detect_format(file_bytes)
    except PreprocessingError as exc:
        if "empty" in str(exc).lower():
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc


async def _read_bounded_upload(upload_file: UploadFile) -> bytes:
    max_size = config.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    payload = await upload_file.read(max_size + 1)
    if len(payload) > max_size:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=f"File too large. Maximum size is {config.UPLOAD_MAX_SIZE_MB}MB.")
    return payload


def _stage_temp_file(file_bytes: bytes, suffix: str) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "finsight_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / f"{uuid.uuid4()}.{suffix}"
    tmp_path = Path(str(target) + ".tmp")
    with tmp_path.open("wb") as handle:
        handle.write(file_bytes)
    os.replace(tmp_path, target)
    return target


def _cleanup_path(path: Path | None) -> None:
    if path and path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _apply_duplicate_and_anomaly(transaction: Transaction, existing: list[Transaction]) -> tuple[DuplicateResult, Any]:
    duplicate = check_duplicate(transaction, existing)
    transaction.is_duplicate = duplicate.is_duplicate
    transaction.duplicate_of = duplicate.matching_transaction_id
    anomaly = detect_anomalies(transaction, existing)
    transaction.is_anomaly = anomaly.is_anomaly
    transaction.anomaly_score = anomaly.score
    transaction.anomaly_reason = anomaly.reason
    return duplicate, anomaly


def _field_from_payload(payload: Any, default: Any = None) -> ExtractedField:
    if isinstance(payload, dict):
        return ExtractedField(
            value=payload.get("value", default),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            raw_text=str(payload.get("raw_text", "")),
        )
    return ExtractedField(value=payload if payload is not None else default, confidence=1.0 if payload is not None else 0.0, raw_text=str(payload or ""))


def _items_from_payload(payload: Any) -> ExtractedField[list[LineItem]]:
    field = _field_from_payload(payload, [])
    items: list[LineItem] = []
    for item in field.value or []:
        if isinstance(item, LineItem):
            items.append(item)
        elif isinstance(item, dict):
            items.append(
                LineItem(
                    name=str(item.get("name", "")),
                    quantity=float(item["quantity"]) if item.get("quantity") is not None else None,
                    unit_price=float(item["unit_price"]) if item.get("unit_price") is not None else None,
                    total_price=float(item.get("total_price", 0.0)),
                )
            )
    return ExtractedField(value=items, confidence=field.confidence, raw_text=field.raw_text)


def _extraction_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        merchant=_field_from_payload(payload.get("merchant")),
        date=_field_from_payload(payload.get("date")),
        items=_items_from_payload(payload.get("items")),
        subtotal=_field_from_payload(payload.get("subtotal")),
        tax=_field_from_payload(payload.get("tax")),
        total=_field_from_payload(payload.get("total")),
        payment_method=_field_from_payload(payload.get("payment_method")),
        bill_number=_field_from_payload(payload.get("bill_number")),
        extraction_model=str(payload.get("extraction_model", "api_payload")),
        ocr_engine=str(payload.get("ocr_engine", "api_payload")),
        raw_ocr_text=str(payload.get("raw_ocr_text", "")),
        metadata=dict(payload.get("metadata", {}) or {}),
    )


def _coerce_numeric_edit(field_name: str, value: Any) -> Any:
    if field_name in {"subtotal", "tax", "total"}:
        if value in {None, ""}:
            return None
        return float(value)
    if field_name in SANITIZED_EDIT_FIELDS:
        return sanitize_text_field(value, field_name)
    return value


def _apply_edits(extraction: ExtractionResult, edits: dict[str, Any] | None) -> bool:
    if not edits:
        return False
    editable = {"merchant", "date", "subtotal", "tax", "total", "payment_method", "bill_number"}
    changed = False
    for field_name, value in edits.items():
        if field_name == "category":
            extraction.metadata["category_override"] = sanitize_text_field(value, "category")
            changed = True
            continue
        if field_name not in editable:
            continue
        coerced = _coerce_numeric_edit(field_name, value)
        setattr(extraction, field_name, ExtractedField(value=coerced, confidence=1.0, raw_text=str(value)))
        changed = True
    return changed


@app.post("/api/v1/upload")
@limiter.limit("10/minute")
async def upload(request: Request, background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)) -> JSONResponse:
    del request, background_tasks
    if len(files) > config.MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {config.MAX_UPLOAD_FILES} files are allowed per upload.")
    _cleanup_expired_pending_uploads()
    results: list[dict[str, Any]] = []
    for upload_file in files:
        file_bytes = await _read_bounded_upload(upload_file)
        file_format = _validate_file_bytes(file_bytes)
        temp_path: Path | None = None
        try:
            temp_path = _stage_temp_file(file_bytes, file_format)
            try:
                image = preprocess(file_bytes, upload_file.content_type or "")
            except PreprocessingError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            blocks = run_ocr(image)
            extraction = extract_fields(blocks)
            upload_id = str(uuid.uuid4())
            extraction.metadata.update({"upload_id": upload_id, "file_name": upload_file.filename or temp_path.name})
            transaction = extraction_to_transaction(extraction, file_bytes, upload_file.filename or temp_path.name)
            existing = _load_all_transactions()
            duplicate, anomaly = _apply_duplicate_and_anomaly(transaction, existing)
            PENDING_UPLOADS[upload_id] = {
                "file_bytes": file_bytes,
                "file_name": upload_file.filename or temp_path.name,
                "extraction": extraction,
                "created_at": _now(),
            }
            results.append(
                {
                    "file_name": upload_file.filename,
                    "upload_id": upload_id,
                    "extraction": extraction,
                    "duplicate_check": duplicate,
                    "anomaly_check": anomaly,
                }
            )
        finally:
            _cleanup_path(temp_path)
    return JSONResponse(_success(results))


@app.post("/api/v1/transactions/confirm")
async def confirm_transaction(body: ConfirmTransactionRequest) -> JSONResponse:
    pending = _pop_pending_upload(body.upload_id)
    extraction = pending["extraction"] if pending else _extraction_from_payload(body.extraction_result)
    edited = _apply_edits(extraction, body.user_edits)
    file_bytes = pending["file_bytes"] if pending else extraction.raw_ocr_text.encode("utf-8")
    file_name = pending["file_name"] if pending else extraction.metadata.get("file_name", "confirmed_upload")
    transaction = extraction_to_transaction(extraction, file_bytes, str(file_name))
    if "category_override" in extraction.metadata:
        transaction.category = sanitize_text_field(extraction.metadata["category_override"], "category")
    transaction.user_confirmed = True
    transaction.manually_edited = edited
    existing = _load_all_transactions()
    _apply_duplicate_and_anomaly(transaction, existing)
    persist_transaction(transaction, str(config.TRANSACTIONS_PATH))
    return JSONResponse(_success(transaction))


@app.post("/api/v1/transactions/discard")
async def discard_transaction(body: DiscardRequest | None = None) -> JSONResponse:
    if body and body.upload_id:
        _pop_pending_upload(body.upload_id)
    return JSONResponse(_success({"discarded": True}))


@app.get("/api/v1/transactions")
async def list_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    transactions = _load_all_transactions()
    filtered = []
    for transaction in transactions:
        if start_date and (transaction.date or "") < start_date:
            continue
        if end_date and (transaction.date or "") > end_date:
            continue
        if category and transaction.category != category:
            continue
        filtered.append(transaction)
    return JSONResponse(_success(filtered[offset : offset + limit]))


@app.get("/api/v1/transactions/{transaction_id}")
async def get_transaction(transaction_id: str) -> JSONResponse:
    for transaction in _load_all_transactions():
        if str(transaction.id) == transaction_id:
            return JSONResponse(_success(transaction))
    raise HTTPException(status_code=404, detail="Transaction not found.")


@app.delete("/api/v1/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str) -> JSONResponse:
    transactions = _load_all_transactions()
    remaining = [transaction for transaction in transactions if str(transaction.id) != transaction_id]
    if len(remaining) == len(transactions):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    write_transactions(remaining, str(config.TRANSACTIONS_PATH))
    return JSONResponse(_success({"deleted": True}))


@app.post("/api/v1/transactions/{transaction_id}/dismiss-anomaly")
async def dismiss_anomaly(transaction_id: str) -> JSONResponse:
    transactions = _load_all_transactions()
    for transaction in transactions:
        if str(transaction.id) == transaction_id:
            transaction.is_anomaly = False
            transaction.anomaly_score = 0.0
            transaction.anomaly_reason = "dismissed"
            write_transactions(transactions, str(config.TRANSACTIONS_PATH))
            return JSONResponse(_success(transaction))
    raise HTTPException(status_code=404, detail="Transaction not found.")


@app.get("/api/v1/analysis")
async def analysis() -> JSONResponse:
    return JSONResponse(_success(generate_analysis(_load_all_transactions())))


@app.post("/api/v1/chat")
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    del request
    message = sanitize_input(body.message)
    transactions = _load_all_transactions()

    async def event_stream() -> Any:
        async for token in nova_chat(message, body.conversation_history, transactions):
            yield f"data: {token}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/v1/market")
async def market() -> JSONResponse:
    return JSONResponse(_success(get_market_data()))


@app.get("/api/v1/news")
async def news() -> JSONResponse:
    context = get_news_context()
    if context is None:
        return JSONResponse(status_code=503, content=_error("news_unavailable", "Current news context is unavailable.", None))
    return JSONResponse(_success(context))


@app.post("/api/v1/news/refresh")
@limiter.limit("2/hour")
async def refresh_news(request: Request) -> JSONResponse:
    del request
    context = get_news_context(force_refresh=True)
    if context is None:
        return JSONResponse(status_code=503, content=_error("news_unavailable", "Current news context is unavailable.", None))
    return JSONResponse(_success(context))


def _run_benchmark_inline() -> dict[str, Any]:
    try:
        from backend.benchmarks.evaluate import run_evaluation

        return run_evaluation()
    except Exception:
        return {"available": False, "message": "Benchmark module is not available yet."}


@app.get("/api/v1/benchmark")
async def benchmark() -> JSONResponse:
    if not config.ENABLE_BENCHMARK_ENDPOINT:
        return JSONResponse(status_code=404, content=_error("benchmark_disabled", "Benchmark endpoint is disabled in this environment.", None))
    return JSONResponse(_success(_run_benchmark_inline()))


@app.get("/api/v1/benchmark/results")
async def benchmark_results() -> JSONResponse:
    if not config.BENCHMARK_RESULTS_PATH.exists():
        return JSONResponse(
            status_code=404,
            content=_error("benchmark_results_unavailable", "Run the benchmark to populate system metrics.", None),
        )
    try:
        results = json.loads(config.BENCHMARK_RESULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content=_error("benchmark_results_unavailable", "Benchmark results are unavailable or invalid.", None),
        )
    return JSONResponse(_success(results))


def _llm_status() -> dict[str, Any]:
    provider = config.LLM_PROVIDER.lower()
    llm_configured = provider == "ollama" or bool(
        (provider == "groq" and config.GROQ_API_KEY)
        or (provider == "openai" and config.OPENAI_API_KEY)
        or (provider == "anthropic" and config.ANTHROPIC_API_KEY)
    )
    return {"provider": provider, "configured": llm_configured}


def _dependency_status() -> dict[str, bool]:
    return {
        "tesseract": shutil.which("tesseract") is not None,
        "poppler_pdfinfo": shutil.which("pdfinfo") is not None,
    }


def _json_file_readable(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


def _readiness_payload() -> dict[str, Any]:
    data_dir_ready = False
    transaction_store_ready = False
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = config.DATA_DIR / ".finsight-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        data_dir_ready = True
        load_transactions(str(config.TRANSACTIONS_PATH))
        transaction_store_ready = True
    except Exception:
        data_dir_ready = False
        transaction_store_ready = False

    frontend_root = config.PROJECT_ROOT / "frontend"
    cache_status = {
        "news_cache_readable": _json_file_readable(config.NEWS_CACHE_PATH),
        "market_cache_readable": _json_file_readable(config.MARKET_CACHE_PATH),
    }
    dependencies = _dependency_status()
    checks = {
        "data_dir_writable": data_dir_ready,
        "transaction_store_ready": transaction_store_ready,
        "frontend_static_root": frontend_root.exists(),
        **dependencies,
        **cache_status,
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "benchmark_endpoint_enabled": config.ENABLE_BENCHMARK_ENDPOINT,
        "app_env": config.APP_ENV,
        "llm": _llm_status(),
    }


@app.get("/api/v1/health")
async def health() -> JSONResponse:
    news_cache = load_news_cache(str(config.NEWS_CACHE_PATH))
    data = {
        "ocr": {"available": True},
        "kie": {"available": True},
        "dependencies": _dependency_status(),
        "llm": _llm_status(),
        "app_env": config.APP_ENV,
        "benchmark_endpoint_enabled": config.ENABLE_BENCHMARK_ENDPOINT,
        "news_cache_fresh": bool(news_cache and cache_is_fresh(news_cache, config.NEWS_CACHE_TTL_HOURS)),
        "market_cache_fresh": market_cache_is_fresh(),
    }
    return JSONResponse(_success(data))


async def _health_live() -> JSONResponse:
    return JSONResponse(_success({"status": "alive"}))


async def _health_ready() -> JSONResponse:
    payload = _readiness_payload()
    return JSONResponse(_success(payload), status_code=200 if payload["ready"] else 503)


app.add_api_route("/health/live", _health_live, methods=["GET"])
app.add_api_route("/api/v1/health/live", _health_live, methods=["GET"])
app.add_api_route("/health/ready", _health_ready, methods=["GET"])
app.add_api_route("/api/v1/health/ready", _health_ready, methods=["GET"])


@app.post("/api/v1/duplicate/confirm")
async def duplicate_confirm(body: DuplicateConfirmRequest) -> JSONResponse:
    transactions = _load_all_transactions()
    for transaction in transactions:
        if str(transaction.id) == body.transaction_id:
            if body.confirmed:
                transaction.is_duplicate = False
                transaction.duplicate_of = None
            append_duplicate_resolution(body.transaction_id, body.confirmed)
            write_transactions(transactions, str(config.TRANSACTIONS_PATH))
            return JSONResponse(_success(transaction))
    raise HTTPException(status_code=404, detail="Transaction not found.")


if config.PROJECT_ROOT.joinpath("frontend").exists():
    app.mount("/", StaticFiles(directory=str(config.PROJECT_ROOT / "frontend"), html=True), name="frontend")
