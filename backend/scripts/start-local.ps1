# AI Content Factory — one-click local start (Windows). Phase 8.
# NEVER resets the database. Safe to run repeatedly.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # ...\backend
$repo = Split-Path -Parent $root
Write-Host "== AI Content Factory local start ==" -ForegroundColor Cyan

function Test-Url($url, $timeoutSec = 4) {
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $timeoutSec | Out-Null; return $true }
    catch { return $false }
}

# 1. Docker infra (Postgres 5433 / Redis 6379)
try {
    docker info *> $null
    if ($LASTEXITCODE -eq 0 -and (Test-Path "$repo\docker-compose.yml")) {
        Write-Host "Docker OK — starting db + redis" -ForegroundColor Green
        docker compose -f "$repo\docker-compose.yml" up -d db redis
    }
} catch { Write-Warning "Docker not available — assuming Postgres:5433 / Redis:6379 are running" }

# 2. Ollama (do not fail if down)
if (Test-Url "http://localhost:11434/api/tags") {
    $tags = (Invoke-WebRequest -UseBasicParsing "http://localhost:11434/api/tags").Content | ConvertFrom-Json
    $models = $tags.models.name -join ", "
    Write-Host "Ollama OK — models: $models" -ForegroundColor Green
    if ($models -notmatch "gemma3:4b") {
        Write-Warning "gemma3:4b not found. Run:  ollama pull gemma3:4b   (not auto-pulled)"
    }
} else {
    Write-Warning "Ollama not reachable at http://localhost:11434 — the app still runs; local AI features degrade."
}

# 3. DB migrations (additive only)
Push-Location $root
& .\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location

# 4. Processes
$env:APP_ENV = "development"
Start-Process -WorkingDirectory $root powershell -ArgumentList '-NoExit','-Command',`
    '.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000'
Start-Process -WorkingDirectory $root powershell -ArgumentList '-NoExit','-Command',`
    '.\.venv\Scripts\python.exe -m celery -A app.celery_app worker --pool=solo -Q celery,image,video,render,audio'
Start-Process -WorkingDirectory "$repo\frontend" powershell -ArgumentList '-NoExit','-Command','npm run dev'

# 5. Wait for readiness, open browser
for ($i = 0; $i -lt 40; $i++) {
    if (Test-Url "http://localhost:8000/health/ready" 2) { break }
    Start-Sleep 1
}
Write-Host "Opening http://localhost:3000" -ForegroundColor Cyan
Start-Process "http://localhost:3000"
