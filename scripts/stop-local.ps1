<#
.SYNOPSIS
  Stop the AI Content Factory local containers — safely.
.DESCRIPTION
  cd C:\AI-Content-Factory ; .\scripts\stop-local.ps1
  Stops the compose services. Does NOT delete any volume (Postgres data is kept).
  Does NOT touch Ollama. Use -Down to also remove the stopped containers
  (still keeps the pgdata volume).
#>
[CmdletBinding()]
param([switch]$Down)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

try { docker info *> $null; if ($LASTEXITCODE -ne 0) { throw } }
catch { Write-Host "Docker Desktop is not running — nothing to stop." -ForegroundColor Yellow; exit 0 }

if ($Down) {
  Write-Host "docker compose down (containers removed; pgdata volume KEPT)..." -ForegroundColor Cyan
  docker compose down            # NOTE: no -v — volumes are preserved
} else {
  Write-Host "docker compose stop (containers stopped; data + containers KEPT)..." -ForegroundColor Cyan
  docker compose stop
}
docker compose ps -a
Write-Host "`nDone. Postgres data volume 'pgdata' was NOT deleted. Ollama was NOT touched." -ForegroundColor Green
Write-Host "Restart with: .\scripts\start-local.ps1" -ForegroundColor Green
