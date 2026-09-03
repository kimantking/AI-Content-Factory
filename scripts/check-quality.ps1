param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    Write-Host "[1/3] Python production code lint"
    python -m ruff check backend/app

    Write-Host "[2/3] Python syntax check"
    python -m compileall -q backend/app

    if (-not $SkipFrontend) {
        Write-Host "[3/3] Frontend type check"
        Push-Location frontend
        try {
            npm run typecheck
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Host "[3/3] Frontend type check skipped"
    }

    Write-Host "Quality checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
