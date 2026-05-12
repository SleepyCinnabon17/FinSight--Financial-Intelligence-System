param(
    [string]$ImageName = "finsight:benchmark",
    [string]$ExternalDataset = "all",
    [int]$Limit = 25,
    [string]$DatasetDir = ""
)

$ErrorActionPreference = "Stop"

docker build -t $ImageName .

$benchmarkPath = (Resolve-Path "backend/benchmarks").Path
$dockerArgs = @(
    "run",
    "--rm",
    "-e", "APP_ENV=development",
    "-v", "${benchmarkPath}:/app/backend/benchmarks"
)

$benchmarkArgs = @(
    "python",
    "backend/benchmarks/evaluate.py",
    "--external", $ExternalDataset,
    "--limit", "$Limit"
)

if ($DatasetDir -ne "") {
    $resolvedDatasetDir = (Resolve-Path $DatasetDir).Path
    $dockerArgs += @("-v", "${resolvedDatasetDir}:/datasets:ro")
    $benchmarkArgs += @("--dataset-dir", "/datasets")
}

docker @dockerArgs $ImageName @benchmarkArgs

Write-Host "Benchmark results saved to backend/benchmarks/results.json"
Write-Host "SROIE debug output saved to backend/benchmarks/debug/sroie_failures.json when SROIE runs."
