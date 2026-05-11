from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def _run_isolated(code: str, tmp_path: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "FINSIGHT_DATA_DIR": str(tmp_path),
            "GROQ_API_KEY": "super-secret-test-key",
            "OPENAI_API_KEY": "another-secret-test-key",
            "ANTHROPIC_API_KEY": "third-secret-test-key",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )


def test_production_disables_benchmark_by_default(tmp_path: Path) -> None:
    _run_isolated(
        """
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)
        response = client.get('/api/v1/benchmark')
        assert response.status_code == 404, response.text
        assert response.json()['error']['code'] == 'benchmark_disabled'
        """,
        tmp_path,
    )


def test_production_cors_blocks_localhost_and_allows_configured_origin(tmp_path: Path) -> None:
    _run_isolated(
        """
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)
        blocked = client.options(
            '/api/v1/transactions',
            headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'GET'},
        )
        assert blocked.headers.get('access-control-allow-origin') is None
        allowed = client.options(
            '/api/v1/transactions',
            headers={'Origin': 'https://finsight.example.com', 'Access-Control-Request-Method': 'GET'},
        )
        assert allowed.headers.get('access-control-allow-origin') == 'https://finsight.example.com'
        """,
        tmp_path,
        {"CORS_ALLOWED_ORIGINS": "https://finsight.example.com"},
    )


def test_production_data_dir_and_secret_safe_health(tmp_path: Path) -> None:
    _run_isolated(
        """
        from fastapi.testclient import TestClient
        from backend import config
        from backend.main import app

        client = TestClient(app)
        payload = {
            'merchant': {'value': 'Railway Store', 'confidence': 1.0, 'raw_text': 'Railway Store'},
            'date': {'value': '2026-05-01', 'confidence': 1.0, 'raw_text': '2026-05-01'},
            'items': {'value': [], 'confidence': 1.0, 'raw_text': ''},
            'subtotal': {'value': 10.0, 'confidence': 1.0, 'raw_text': '10'},
            'tax': {'value': 0.0, 'confidence': 1.0, 'raw_text': '0'},
            'total': {'value': 10.0, 'confidence': 1.0, 'raw_text': '10'},
            'payment_method': {'value': 'UPI', 'confidence': 1.0, 'raw_text': 'UPI'},
            'bill_number': {'value': 'INV-1', 'confidence': 1.0, 'raw_text': 'INV-1'},
            'raw_ocr_text': 'Railway Store',
            'metadata': {'file_name': 'railway.txt'},
        }
        response = client.post('/api/v1/transactions/confirm', json={'extraction_result': payload})
        assert response.status_code == 200, response.text
        assert config.TRANSACTIONS_PATH.exists()
        assert str(config.TRANSACTIONS_PATH).startswith(str(config.DATA_DIR))

        for endpoint in ['/api/v1/health', '/health/live', '/health/ready']:
            health = client.get(endpoint)
            assert health.status_code in {200, 503}
            text = health.text
            assert 'super-secret-test-key' not in text
            assert 'another-secret-test-key' not in text
            assert 'third-secret-test-key' not in text
        """,
        tmp_path,
    )
