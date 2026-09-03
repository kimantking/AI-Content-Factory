<#
.SYNOPSIS
  Reload the root .env into backend/worker and verify ElevenLabs safely.
.DESCRIPTION
  Run from C:\AI-Content-Factory after setting ELEVENLABS_API_KEY=sk_...
  in the repository-root .env. The secret itself is never printed.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".env"

Set-Location $ProjectRoot
if (-not (Test-Path $EnvPath)) {
  throw "Root .env not found: $EnvPath"
}

$KeyLine = Get-Content $EnvPath | Where-Object { $_ -match '^\s*ELEVENLABS_API_KEY\s*=' } | Select-Object -Last 1
if (-not $KeyLine) {
  throw "Add ELEVENLABS_API_KEY=sk_... to $EnvPath"
}

$Key = (($KeyLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
if (-not $Key.StartsWith("sk_")) {
  throw "ELEVENLABS_API_KEY must be the Secret API Key beginning with sk_, not the API Key ID."
}
if ($Key.Length -lt 12) {
  throw "ELEVENLABS_API_KEY looks too short."
}

Write-Host "[1/3] Root .env key format OK (secret not displayed)" -ForegroundColor Green
Write-Host "[2/3] Recreating backend and worker with the current .env..."
docker compose up -d --force-recreate backend worker
if ($LASTEXITCODE -ne 0) { throw "Docker Compose restart failed." }

$Deadline = (Get-Date).AddSeconds(90)
do {
  Start-Sleep -Seconds 3
  try {
    $Health = Invoke-RestMethod -Uri "http://localhost:8000/health/live" -TimeoutSec 4
    $Ready = $true
  } catch {
    $Ready = $false
  }
} until ($Ready -or (Get-Date) -ge $Deadline)
if (-not $Ready) {
  docker compose logs backend --tail=40
  throw "Backend did not become ready within 90 seconds."
}

Write-Host "[3/3] Running the read-only ElevenLabs connection check..."
try {
  $Result = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/providers/elevenlabs/test" -TimeoutSec 30
  if ($Result.ok) {
    Write-Host "ElevenLabs connected. Available voices: $($Result.voice_count)" -ForegroundColor Green
  } else {
    throw "status=$($Result.status) detail=$($Result.detail)"
  }
} catch {
  Write-Host "ElevenLabs verification failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Check only the root file: $EnvPath" -ForegroundColor Yellow
  exit 1
}
