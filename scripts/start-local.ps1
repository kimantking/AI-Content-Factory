<#
.SYNOPSIS
  One command to bring up the AI Content Factory local stack.
.DESCRIPTION
  cd C:\AI-Content-Factory ; .\scripts\start-local.ps1
  - checks Docker Desktop + (optionally) Ollama + gemma3:4b
  - ensures a .env exists (copies from .env.example, non-destructive)
  - validates docker-compose config
  - builds ALL services (backend and worker are SEPARATE images) and starts them
  - waits for postgres / redis / backend / worker / frontend health
  - prints a status summary + the Dashboard URL, and opens the browser
  Never runs `docker compose down -v`. Never deletes a volume. Never force-quits Ollama.
#>
[CmdletBinding()]
param(
  [switch]$NoBuild,       # skip the image build (faster restart)
  [switch]$NoBrowser,     # don't open the dashboard
  [int]$TimeoutSec = 240  # per-service health wait
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "AI Content Factory — local stack" -ForegroundColor Cyan
Write-Host "root: $root`n"

function Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red; exit 1 }
function Ok($msg)   { Write-Host "  [ OK ] $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "  [info] $msg" -ForegroundColor DarkGray }

# 1. project root
if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) { Fail "docker-compose.yml not found — run from the repo root" }
Ok "project root"

# 2. Docker Desktop
try { docker info *> $null; if ($LASTEXITCODE -ne 0) { throw } ; Ok "Docker Desktop reachable" }
catch { Fail "Docker Desktop is not running. Start Docker Desktop and retry." }

# 3. .env (non-destructive)
$envPath = Join-Path $root ".env"
if (-not (Test-Path $envPath)) {
  $ex = @((Join-Path $root ".env.example"), (Join-Path $root "backend\.env.example")) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($ex) { Copy-Item $ex $envPath; Ok ".env created from $(Split-Path -Leaf $ex) (fill in real keys later; MOCK_MODE stays true until then)" }
  else { Info "no .env and no .env.example — the stack will run on built-in defaults (MOCK_MODE)" }
} else { Ok ".env present" }

# 4. Ollama on the host (optional but recommended)
$ollamaUrl = "http://localhost:11434"
try {
  $tags = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 4
  $models = @($tags.models | ForEach-Object { $_.name })
  Ok "Ollama reachable on the host ($ollamaUrl)"
  if ($models -contains "gemma3:4b" -or ($models | Where-Object { $_ -like "gemma3:4b*" })) { Ok "gemma3:4b present" }
  else { Info "gemma3:4b NOT found. Run:  ollama pull gemma3:4b   (the stack still starts; local AI will be DEGRADED)" }
} catch {
  Info "Ollama not reachable on the host. Start it with 'ollama serve' and 'ollama pull gemma3:4b'."
  Info "The stack still starts; the AI Support Snapshot will show Ollama as ERROR until it is up."
}

# 5. compose config validation
docker compose config -q
if ($LASTEXITCODE -ne 0) { Fail "docker compose config is invalid" }
Ok "docker compose config valid"

# 6. build (backend AND worker are separate images — build all)
if (-not $NoBuild) {
  Write-Host "`n  building images (backend, worker, frontend)..." -ForegroundColor DarkGray
  docker compose build
  if ($LASTEXITCODE -ne 0) { Fail "image build failed" }
  Ok "images built"
}

# 7. up
Write-Host "`n  starting containers..." -ForegroundColor DarkGray
docker compose up -d
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }

# 8-11. wait for health
function Wait-Health($svc, [int]$timeout) {
  $deadline = (Get-Date).AddSeconds($timeout)
  while ((Get-Date) -lt $deadline) {
    $cid = (docker compose ps -q $svc 2>$null)
    if ($cid) {
      $state  = (docker inspect --format '{{.State.Status}}' $cid 2>$null)
      $health = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $cid 2>$null)
      if ($state -eq "running" -and ($health -eq "healthy" -or $health -eq "none")) {
        Ok ("{0,-9} {1}" -f $svc, ($(if ($health -eq "none") { "running (no healthcheck)" } else { "healthy" })))
        return $true
      }
      if ($state -eq "restarting" -or $state -eq "exited") {
        Write-Host "  [FAIL] $svc is $state — last logs:" -ForegroundColor Red
        docker compose logs --tail 25 $svc
        return $false
      }
    }
    Start-Sleep -Seconds 3
  }
  Write-Host "  [WARN] $svc not healthy within ${timeout}s" -ForegroundColor Yellow
  docker compose logs --tail 15 $svc
  return $false
}

Write-Host "`n  waiting for services..." -ForegroundColor DarkGray
$all = $true
foreach ($s in @("postgres","redis","backend","worker","frontend")) {
  if (-not (Wait-Health $s $TimeoutSec)) { $all = $false }
}

# 12. summary
Write-Host "`n----------------------------------------" -ForegroundColor Cyan
docker compose ps
Write-Host "----------------------------------------" -ForegroundColor Cyan
try {
  $ready = Invoke-RestMethod -Uri "http://localhost:8000/health/ready" -TimeoutSec 5
  Ok ("backend /health/ready: ready=$($ready.ready)")
} catch { Write-Host "  [WARN] backend /health/ready not answering yet" -ForegroundColor Yellow }
try {
  $prov = Invoke-RestMethod -Uri "http://localhost:8000/api/providers" -TimeoutSec 6
  Write-Host "  providers:" -ForegroundColor DarkGray
  $prov.providers | ForEach-Object { Write-Host ("    {0,-11} {1}" -f $_.provider, $_.status) }
} catch { }

Write-Host "`n  Dashboard : http://localhost:3000" -ForegroundColor Green
Write-Host "  Backend   : http://localhost:8000  (docs: /docs, health: /health/ready)" -ForegroundColor Green
Write-Host "  Support   : http://localhost:3000/support" -ForegroundColor Green

if (-not $NoBrowser -and $all) { Start-Process "http://localhost:3000" }
if (-not $all) { Write-Host "`n  Some services are not healthy — see the logs above." -ForegroundColor Yellow; exit 1 }
Write-Host "`n  Local stack is up." -ForegroundColor Cyan
