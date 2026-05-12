from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.benchmarks.ocr_deps import external_ocr_dependency_status, format_dependency_report


WINDOWS_INSTALL_HELP = """
Windows install commands:
  winget install UB-Mannheim.TesseractOCR
  winget install oschwartz10612.Poppler

Verify after restarting VS Code/terminal:
  tesseract --version
  pdfinfo -v

If winget package names fail, install Tesseract from the UB Mannheim installer,
install Poppler for Windows, add tesseract.exe and Poppler's bin folder to PATH,
then restart VS Code/terminal.
""".strip()


def main() -> int:
    report = external_ocr_dependency_status()
    print(format_dependency_report(report))
    if report["ready"]:
        return 0
    print()
    print(WINDOWS_INSTALL_HELP)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
