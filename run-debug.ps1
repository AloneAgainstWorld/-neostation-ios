#!/usr/bin/env pwsh
# Run NeoStation in debug mode with environment variables from .env
# Usage: .\run-debug.ps1
# Or with a custom env file: .\run-debug.ps1 -EnvFile .\.env.local

param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Environment file not found: $EnvFile"
    exit 1
}

Write-Host "Loading environment from: $EnvFile" -ForegroundColor Cyan
flutter run --dart-define-from-file=$EnvFile @args
