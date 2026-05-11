#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${RAILWAY_URL:-${BASE_URL:-}}}"

if [[ -z "${BASE_URL}" ]]; then
  echo "Usage: bash scripts/smoke_railway.sh https://your-app.up.railway.app"
  echo "       or set RAILWAY_URL / BASE_URL"
  exit 2
fi

BASE_URL="${BASE_URL%/}"

echo "Testing FinSight deployment: ${BASE_URL}"

check_json() {
  local path="$1"
  local body
  echo "-> GET ${path}"
  body="$(curl -fsS "${BASE_URL}${path}")"
  if ! grep -q '"success"[[:space:]]*:[[:space:]]*true' <<<"${body}"; then
    echo "Probe failed: ${path}"
    echo "${body}"
    exit 1
  fi
}

check_frontend() {
  local body
  echo "-> GET /"
  body="$(curl -fsS "${BASE_URL}/")"
  if ! grep -qi 'FinSight' <<<"${body}"; then
    echo "Frontend probe failed: root HTML did not contain FinSight"
    exit 1
  fi
}

check_json "/health/live"
check_json "/health/ready"
check_json "/api/v1/transactions"
check_frontend

echo "FinSight smoke test passed."
