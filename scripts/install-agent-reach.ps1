$ErrorActionPreference = "Stop"

$AgentReachCommit = "da5044d26fc6adddb6554d5679c94ac22e76e428"
$AgentReachVenv = Join-Path $env:USERPROFILE ".agent-reach-venv"
$AgentReachPython = Join-Path $AgentReachVenv "Scripts\python.exe"
$AgentReachExe = Join-Path $AgentReachVenv "Scripts\agent-reach.exe"
$AgentReachSource = "https://github.com/Panniantong/agent-reach/archive/$AgentReachCommit.zip"

Write-Host "Agent Reach 읽기 전용 도구를 설치합니다." -ForegroundColor Cyan

if (-not (Test-Path $AgentReachPython)) {
    py -3 -m venv $AgentReachVenv
}

& $AgentReachPython -m pip install --upgrade pip
& $AgentReachPython -m pip install $AgentReachSource

# Safe mode only checks dependencies and never reads browser cookies.
& $AgentReachExe install --env=local --safe
& $AgentReachExe doctor

Write-Host "설치 완료: $AgentReachExe" -ForegroundColor Green
Write-Host "쿠키가 필요한 Twitter, Instagram, Facebook 기능은 설치하지 않았습니다."
Write-Host "AI Content Factory Docker 백엔드에도 Agent Reach가 포함되므로 다음 명령으로 재빌드하세요:"
Write-Host "docker compose up -d --build"
