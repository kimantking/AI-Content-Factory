# Stop the local dev processes started by start-local.ps1.
# Leaves Docker containers and ALL data untouched.
$ErrorActionPreference = "SilentlyContinue"
Write-Host "Stopping AI Content Factory dev processes..." -ForegroundColor Cyan

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match "uvicorn app.main:app" -or
            $_.CommandLine -match "celery -A app.celery_app" -or
            $_.CommandLine -match "next dev" -or
            $_.CommandLine -match "npm run dev"
        )
    } |
    ForEach-Object {
        Write-Host "  kill PID $($_.ProcessId): $($_.Name)"
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "Done. Postgres / Redis containers and data are untouched." -ForegroundColor Green
