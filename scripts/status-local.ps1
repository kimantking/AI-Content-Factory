<#
.SYNOPSIS
  AI Content Factory 로컬 스택 상태 점검 (읽기 전용, 비밀값 미출력).
.DESCRIPTION
  cd C:\AI-Content-Factory ; .\scripts\status-local.ps1
  이 파일은 UTF-8 BOM 로 저장되어 있어야 Windows PowerShell 5.1 이 한글을 바르게 읽습니다.
#>
[CmdletBinding()] param()
$ErrorActionPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Set-Location (Split-Path -Parent $PSScriptRoot)

function Line($name, $val, $ok) {
  $mark = if ($ok) { "정상" } else { "비정상" }
  $c    = if ($ok) { "Green" } else { "Yellow" }
  Write-Host ("  {0,-22} {1,-30} {2}" -f $name, $val, $mark) -ForegroundColor $c
}

Write-Host "AI Content Factory - 로컬 상태`n" -ForegroundColor Cyan

$svcs = "postgres","redis","backend","worker","frontend"
foreach ($s in $svcs) {
  $cid = docker compose ps -q $s 2>$null
  if (-not $cid) { Line $s "미생성" $false; continue }
  $state  = docker inspect --format '{{.State.Status}}' $cid
  $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' $cid
  Line $s ("{0} ({1})" -f $state, $health) ($state -eq "running" -and $health -ne "unhealthy")
}

Write-Host ""
try {
  $r = Invoke-RestMethod "http://localhost:8000/health/ready" -TimeoutSec 4
  Line "backend /health/ready" ("ready=$($r.ready) db=$($r.checks.database.status) redis=$($r.checks.redis.status)") $r.ready
} catch { Line "backend /health/ready" "응답 없음" $false }

# Scheduler (celery beat, worker 컨테이너에 임베드)
$wid = docker compose ps -q worker 2>$null
if ($wid) {
  $ping = docker compose exec -T worker celery -A app.celery_app.celery_app inspect ping --timeout 8 2>$null
  Line "Scheduler (celery beat)" "임베드/worker" ([bool]($ping -match "pong|OK"))
} else { Line "Scheduler (celery beat)" "미생성" $false }

# FFmpeg (backend/worker 이미지 번들)
$bid = docker compose ps -q backend 2>$null
if ($bid) {
  $ff = docker compose exec -T backend sh -lc "ffmpeg -version 2>/dev/null | head -1" 2>$null
  if ($ff) { Line "FFmpeg" (($ff -split ' ')[0..2] -join ' ') $true }
  else     { Line "FFmpeg" "없음" $false }
} else { Line "FFmpeg" "미생성" $false }

try {
  $code = (Invoke-WebRequest "http://localhost:3000/" -TimeoutSec 4 -UseBasicParsing).StatusCode
  Line "대시보드 :3000" "HTTP $code" ($code -eq 200)
} catch { Line "대시보드 :3000" "응답 없음" $false }

try {
  $tags = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 4
  $models = @($tags.models | ForEach-Object { $_.name })
  Line "Ollama (호스트)" "연결됨" $true
  $has = ($models -contains "gemma3:4b") -or ($models | Where-Object { $_ -like "gemma3:4b*" })
  if ($has) { Line "gemma3:4b" "사용 가능" $true }
  else      { Line "gemma3:4b" "없음 (ollama pull gemma3:4b)" $false }
} catch { Line "Ollama (호스트)" "응답 없음 (ollama serve)" $false }

try {
  $p = Invoke-RestMethod "http://localhost:8000/api/providers" -TimeoutSec 6
  Write-Host "`n  provider 상태 (상태값만, 키 미출력 - 설정: 설정 -> AI 연결):" -ForegroundColor DarkGray
  $p.providers | ForEach-Object {
    $st = [string]$_.status
    $note = switch ($st) {
      "CONNECTED" { "실제 인증 확인됨" }
      "CONFIGURED" { "키 있음 (연결 확인 필요)" }
      "MOCK" { "키 있음 (MOCK 모드)" }
      "NOT_CONFIGURED" { "키 없음" }
      "AUTH_FAILED" { "인증 실패 - 키 재입력 필요" }
      "NEEDS_WORKSPACE_ID" { "ANTHROPIC_WORKSPACE_ID 필요" }
      default { "상태 확인 필요" }
    }
    $last4 = if ($_.last4) { "..." + $_.last4 } else { "" }
    Write-Host ("    {0,-11} {1,-18} {2,-8} {3}" -f $_.provider, $st, $last4, $note)
  }
} catch { }

Write-Host "`n  대시보드: http://localhost:3000    AI 지원: http://localhost:3000/support" -ForegroundColor Cyan
