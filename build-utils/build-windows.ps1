# Build Flutter Windows app
# Usage: .\build-utils\build-windows.ps1 [-EnvFile .env]

param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Flutter Windows app..." -ForegroundColor Green

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$envPath = Join-Path $projectRoot $EnvFile
if (-not (Test-Path $envPath)) {
    Write-Error "Environment file not found: $EnvFile`nCreate it with: Copy-Item .env.example .env"
    exit 1
}

$lines = Get-Content $envPath
$requiredKeys = @(
    "SCREENSCRAPER_DEV_ID",
    "SCREENSCRAPER_DEV_PASSWORD"
)

foreach ($key in $requiredKeys) {
    $escapedKey = [Regex]::Escape($key)
    $line = $lines |
        Where-Object { $_ -match "^\s*$escapedKey\s*=" } |
        Select-Object -Last 1

    if ($null -eq $line) {
        Write-Error "Missing required key '$key' in $EnvFile."
        exit 1
    }

    $value = ($line -split '=', 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Error "Required key '$key' is empty in $EnvFile."
        exit 1
    }
}

Write-Host "ScreenScraper developer configuration is present (values hidden)." -ForegroundColor Green

if (Test-Path "$projectRoot\build\windows\x64\runner\Release") {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    Remove-Item -Path "$projectRoot\build\windows\x64\runner\Release" -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Building Windows release..." -ForegroundColor Cyan
flutter build windows --release "--dart-define-from-file=$EnvFile"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error during build" -ForegroundColor Red
    exit 1
}

$version = (Select-String -Path "$projectRoot\pubspec.yaml" -Pattern "^version:\s*(.+)" | ForEach-Object { $_.Matches.Groups[1].Value }).Trim()

Write-Host "Creating output directory..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path "$projectRoot\release" -Force | Out-Null

$bundleDir = "$projectRoot\build\windows\x64\runner\Release"
$outputZip = "$projectRoot\release\neostation-windows-x64-$version.zip"

$sqliteNative = "$projectRoot\build\native_assets\windows\sqlite3.dll"
if (Test-Path $sqliteNative) {
    Write-Host "Copying sqlite3.dll from native_assets..." -ForegroundColor Cyan
    Copy-Item -Path $sqliteNative -Destination "$bundleDir\" -Force
} else {
    Write-Host "Warning: sqlite3.dll not found in native_assets" -ForegroundColor Yellow
}

Write-Host "Compressing bundle..." -ForegroundColor Cyan
Compress-Archive -Path "$bundleDir\*" -DestinationPath $outputZip -Force

if (Test-Path $outputZip) {
    Write-Host ""
    Write-Host "Build completed!" -ForegroundColor Green
    Write-Host "Output: release\" -ForegroundColor Cyan
    Get-ChildItem -Path "$projectRoot\release" -Filter "*.zip" | Format-Table Name, @{Name="Size (MB)";Expression={[math]::Round($_.Length/1MB, 2)}}, LastWriteTime
} else {
    Write-Host "Error creating ZIP archive" -ForegroundColor Red
    exit 1
}
