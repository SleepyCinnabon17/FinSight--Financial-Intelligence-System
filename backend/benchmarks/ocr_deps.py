from __future__ import annotations

import importlib.util
import shutil
import subprocess
from typing import Any


COMMAND_CHECKS: tuple[tuple[str, str, bool, str], ...] = (
    ("tesseract", "Tesseract", True, "Install Tesseract OCR and ensure tesseract is on PATH."),
    ("pdfinfo", "Poppler pdfinfo", True, "Install Poppler and ensure its bin directory is on PATH."),
)

PACKAGE_CHECKS: tuple[tuple[str, str, bool, str], ...] = (
    ("pytesseract", "pytesseract", True, "Install Python dependencies with pip install -r requirements.txt."),
    ("pdf2image", "pdf2image", True, "Install Python dependencies with pip install -r requirements.txt."),
    ("PIL", "Pillow", True, "Install Python dependencies with pip install -r requirements.txt."),
    ("paddleocr", "PaddleOCR", False, "Optional primary OCR package. Tesseract fallback remains supported."),
)


def _command_status(command: str, label: str, required: bool, install_hint: str) -> dict[str, Any]:
    executable = shutil.which(command)
    status: dict[str, Any] = {
        "ok": executable is not None,
        "label": label,
        "required": required,
        "path": executable,
        "install_hint": install_hint,
    }
    if executable is None:
        return status
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (completed.stdout or completed.stderr or "").strip().splitlines()
        status["version"] = output[0] if output else "available"
    except Exception:
        status["version"] = "available"
    return status


def _package_status(module_name: str, label: str, required: bool, install_hint: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    return {
        "ok": spec is not None,
        "label": label,
        "required": required,
        "path": spec.origin if spec and spec.origin else None,
        "install_hint": install_hint,
    }


def external_ocr_dependency_status() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for command, label, required, install_hint in COMMAND_CHECKS:
        checks[command] = _command_status(command, label, required, install_hint)
    for module_name, label, required, install_hint in PACKAGE_CHECKS:
        checks[module_name] = _package_status(module_name, label, required, install_hint)

    missing_required = [
        key
        for key, status in checks.items()
        if bool(status["required"]) and not bool(status["ok"])
    ]
    return {
        "ready": not missing_required,
        "missing_required": missing_required,
        "checks": checks,
    }


def format_dependency_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    checks = report.get("checks", {})
    for key in ("tesseract", "pdfinfo", "pytesseract", "pdf2image", "PIL", "paddleocr"):
        status = checks.get(key, {})
        label = status.get("label", key)
        state = "OK" if status.get("ok") else "MISSING"
        required = "required" if status.get("required") else "optional"
        detail = status.get("version") or status.get("path") or status.get("install_hint") or ""
        lines.append(f"{label}: {state} ({required}) {detail}".rstrip())
    if report.get("ready"):
        lines.append("External OCR benchmark environment: OK")
    else:
        missing = ", ".join(str(item) for item in report.get("missing_required", []))
        lines.append(f"External OCR benchmark environment: MISSING required dependencies: {missing}")
    return "\n".join(lines)
