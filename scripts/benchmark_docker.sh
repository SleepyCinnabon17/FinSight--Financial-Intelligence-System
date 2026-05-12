#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-finsight:benchmark}"
EXTERNAL_DATASET="${EXTERNAL_DATASET:-all}"
LIMIT="${LIMIT:-25}"
DATASET_DIR="${DATASET_DIR:-}"

docker build -t "$IMAGE_NAME" .

docker_args=(
  run
  --rm
  -e APP_ENV=development
  -v "$PWD/backend/benchmarks:/app/backend/benchmarks"
)

benchmark_args=(
  python
  backend/benchmarks/evaluate.py
  --external "$EXTERNAL_DATASET"
  --limit "$LIMIT"
)

if [[ -n "$DATASET_DIR" ]]; then
  docker_args+=(-v "$DATASET_DIR:/datasets:ro")
  benchmark_args+=(--dataset-dir /datasets)
fi

docker "${docker_args[@]}" "$IMAGE_NAME" "${benchmark_args[@]}"

echo "Benchmark results saved to backend/benchmarks/results.json"
echo "SROIE debug output saved to backend/benchmarks/debug/sroie_failures.json when SROIE runs."
