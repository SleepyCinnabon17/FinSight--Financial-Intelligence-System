from __future__ import annotations

import os
from pathlib import Path
from typing import Final

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


BASE_DIR: Final[Path] = Path(__file__).resolve().parent
PROJECT_ROOT: Final[Path] = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")


def _get_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in _get_str(name, default).split(",") if item.strip()]


def _get_path(name: str, default: Path) -> Path:
    raw = Path(_get_str(name, str(default))).expanduser()
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


APP_ENV: Final[str] = _get_str("APP_ENV", "development").strip().lower() or "development"
IS_PRODUCTION: Final[bool] = APP_ENV == "production"
CORS_ALLOWED_ORIGINS: Final[list[str]] = _get_csv("CORS_ALLOWED_ORIGINS")
DATA_DIR: Final[Path] = _get_path("FINSIGHT_DATA_DIR", BASE_DIR / "data")
TRANSACTIONS_PATH: Final[Path] = DATA_DIR / "transactions.json"
DUPLICATE_LOG_PATH: Final[Path] = DATA_DIR / "duplicate_log.json"
MARKET_CACHE_PATH: Final[Path] = DATA_DIR / "market_cache.json"
NEWS_CACHE_PATH: Final[Path] = DATA_DIR / "news_cache.json"
BENCHMARK_RESULTS_PATH: Final[Path] = PROJECT_ROOT / "backend" / "benchmarks" / "results.json"
ENABLE_BENCHMARK_ENDPOINT: Final[bool] = _get_bool("ENABLE_BENCHMARK_ENDPOINT", not IS_PRODUCTION)
OCR_PRIMARY_TIMEOUT_SECONDS: Final[float] = _get_float("OCR_PRIMARY_TIMEOUT_SECONDS", 5.0)
PENDING_UPLOAD_TTL_SECONDS: Final[int] = _get_int("PENDING_UPLOAD_TTL_SECONDS", 1800)
OCR_FIXTURE_METADATA_ENABLED: Final[bool] = _get_bool("FINSIGHT_ENABLE_OCR_FIXTURE_METADATA", False)


LLM_PROVIDER: Final[str] = _get_str("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY: Final[str] = _get_str("GROQ_API_KEY")
OPENAI_API_KEY: Final[str] = _get_str("OPENAI_API_KEY")
ANTHROPIC_API_KEY: Final[str] = _get_str("ANTHROPIC_API_KEY")
OLLAMA_BASE_URL: Final[str] = _get_str("OLLAMA_BASE_URL", "http://localhost:11434")

MARKET_DATA_CACHE_TTL_HOURS: Final[float] = _get_float("MARKET_DATA_CACHE_TTL_HOURS", 1.0)
NEWS_CACHE_TTL_HOURS: Final[float] = _get_float("NEWS_CACHE_TTL_HOURS", 2.0)
NEWS_SOURCES: Final[list[str]] = [
    item.strip()
    for item in _get_str("NEWS_SOURCES", "et,moneycontrol,googlenews").split(",")
    if item.strip()
]

UPLOAD_MAX_SIZE_MB: Final[int] = _get_int("UPLOAD_MAX_SIZE_MB", 10)
ANOMALY_STDDEV_THRESHOLD: Final[float] = _get_float("ANOMALY_STDDEV_THRESHOLD", 2.0)

BUDGET_CONFIG: Final[dict[str, float]] = {
    "Food": _get_float("BUDGET_FOOD", 5000.0),
    "Transport": _get_float("BUDGET_TRANSPORT", 3000.0),
    "Shopping": _get_float("BUDGET_SHOPPING", 4000.0),
    "Subscription": _get_float("BUDGET_SUBSCRIPTION", 1000.0),
}
SBI_FD_1Y_RATE: Final[float] = _get_float("SBI_FD_1Y_RATE", 6.55)
AMFI_LARGE_CAP_NAV_LIMIT: Final[int] = 3

NEWS_RSS_URLS: Final[dict[str, str]] = {
    "et": "https://economictimes.indiatimes.com/markets/rss.cms",
    "moneycontrol": "https://www.moneycontrol.com/rss/latestnews.xml",
    "googlenews": (
        "https://news.google.com/rss/search?q=india+stock+market+investment&hl=en-IN&gl=IN&ceid=IN:en"
    ),
}

OCR_CONFIDENCE_THRESHOLD: Final[float] = 0.5
KIE_MIN_FIELD_CONFIDENCE: Final[float] = 0.4
BLUR_VARIANCE_THRESHOLD: Final[float] = 100.0
LOW_BRIGHTNESS_THRESHOLD: Final[float] = 80.0
HIGH_BRIGHTNESS_THRESHOLD: Final[float] = 200.0
PREPROCESS_PDF_DPI: Final[int] = 200
PREPROCESS_MAX_DIM: Final[int] = 2048
DESKEW_MIN_ANGLE: Final[float] = 0.2
DESKEW_MAX_ANGLE: Final[float] = 15.0
DESKEW_CANNY_LOW_THRESHOLD: Final[int] = 50
DESKEW_CANNY_HIGH_THRESHOLD: Final[int] = 150
DESKEW_HOUGH_THRESHOLD: Final[int] = 160
DESKEW_FLIP_INK_RATIO: Final[float] = 1.8
DESKEW_FLIP_MIN_INK: Final[float] = 0.02
DESKEW_INK_PIXEL_THRESHOLD: Final[int] = 200
DESKEW_HOUGH_MAX_LINES: Final[int] = 50
CLAHE_CLIP_LIMIT: Final[float] = 2.0
CLAHE_TILE_GRID_SIZE: Final[int] = 8
UNSHARP_RADIUS: Final[float] = 2.0
UNSHARP_PERCENT: Final[int] = 160
UNSHARP_THRESHOLD: Final[int] = 3
OCR_LINE_MERGE_Y_TOLERANCE: Final[int] = 10
RECEIPT_PRICE_LINE_THRESHOLD: Final[int] = 3
ZERO_SHOT_CONFIDENCE_THRESHOLD: Final[float] = 0.5
DUPLICATE_AMOUNT_TOLERANCE: Final[float] = 0.01
DUPLICATE_DATE_TOLERANCE_DAYS: Final[int] = 1
DUPLICATE_EXACT_CONFIDENCE: Final[float] = 1.0
DUPLICATE_FUZZY_CONFIDENCE: Final[float] = 0.85
KIE_HIGH_CONFIDENCE: Final[float] = 0.95
KIE_MEDIUM_CONFIDENCE: Final[float] = 0.85
KIE_PAYMENT_CONFIDENCE: Final[float] = 0.90
KIE_BILL_CONFIDENCE: Final[float] = 0.90
KIE_DERIVED_SUBTOTAL_CONFIDENCE: Final[float] = 0.75
KIE_FUNSD_CONFIDENCE: Final[float] = 0.75
KIE_FALLBACK_TOTAL_CONFIDENCE: Final[float] = 0.65
FUNSD_QUESTION_MAX_WORDS: Final[int] = 4
FUNSD_MAX_LOOKAHEAD_BLOCKS: Final[int] = 4
ANOMALY_RULE1_SCORE: Final[float] = 1.0
ANOMALY_RULE2_SCORE: Final[float] = 0.7
ANOMALY_RULE3_SCORE: Final[float] = 0.6
MOM_INCREASE_THRESHOLD: Final[float] = 0.20
ATOMIC_REPLACE_RETRIES: Final[int] = 5
ATOMIC_REPLACE_RETRY_DELAY_SECONDS: Final[float] = 0.1
MAX_UPLOAD_FILES: Final[int] = 10
WEB_SEARCH_MAX_QUERY_CHARS: Final[int] = 100
NOVA_MAX_INPUT_CHARS: Final[int] = 2000
ANALYSIS_WINDOW_DAYS: Final[int] = 30
NEW_MERCHANT_LOOKBACK_DAYS: Final[int] = 90
HIGH_VALUE_NEW_MERCHANT_AMOUNT: Final[float] = 5000.0
MERCHANT_REPEAT_THRESHOLD: Final[int] = 3
