param(
    [string]$TestDatabaseUrl = "postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host "`n==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path $python)) {
    throw "Missing .venv. Run the dependency installation steps in README.md first."
}

Push-Location $root
try {
    $configuredDemoAccessToken = $env:DEMO_ACCESS_TOKEN
    Remove-Item Env:DEMO_ACCESS_TOKEN -ErrorAction SilentlyContinue
    $env:DATABASE_URL = $TestDatabaseUrl
    $env:ENCOUNTER_TEST_DATABASE_URL = $TestDatabaseUrl
    $env:MIGRATION_DIR = "db/migrations"
    $env:AI_MODE = "fixture"

    Invoke-Checked "Start PostgreSQL and apply migrations" {
        docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db migrate
    }
    Invoke-Checked "Backend, HTTP contract and PostgreSQL integration tests" {
        & $python -m unittest discover -s tests -v
    }
    Invoke-Checked "Compile backend" {
        & $python -m compileall -q backend
    }
    Invoke-Checked "Validate development Compose" {
        docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
    }
    if (-not $env:APP_DOMAIN) { $env:APP_DOMAIN = "demo.example.com" }
    if (-not $env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD = "local-check-only" }
    $env:DEMO_ACCESS_TOKEN = if ($configuredDemoAccessToken) { $configuredDemoAccessToken } else { "local-check-only" }
    Invoke-Checked "Validate production Compose" {
        docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
    }
    Invoke-Checked "Build frontend" {
        Push-Location frontend
        try { npm.cmd run build } finally { Pop-Location }
    }

    Write-Host "`nAll demo checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
