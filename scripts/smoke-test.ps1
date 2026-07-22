<#
    Office-Connect - verify the dev stack boots and is healthy.
    Run after Docker Desktop is up:  .\scripts\smoke-test.ps1
#>

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Checking Docker engine..." -ForegroundColor Cyan
docker version --format "{{.Server.Version}}" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker engine not reachable. Start Docker Desktop, wait for it to finish starting, then rerun." -ForegroundColor Red
    exit 1
}

Write-Host "Building and starting containers (db, redis, app)..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "Waiting for http://localhost:8001/health ..." -ForegroundColor Cyan
$ok = $false
foreach ($i in 1..30) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 3
        if ($r.status -eq "healthy") { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

if ($ok) {
    Write-Host "`nSTACK HEALTHY" -ForegroundColor Green
    Write-Host "  API   : http://localhost:8001   (interactive docs: /docs)"
    Write-Host "  DB    : localhost:5432   db=office_connect user=oc_dev"
    Write-Host "  Redis : localhost:6380"
    Write-Host "`nStop:        docker compose down"
    Write-Host "Stop + wipe: docker compose down -v   (deletes the DB volume)"
} else {
    Write-Host "`nStack did not become healthy in time." -ForegroundColor Red
    Write-Host "Inspect:  docker compose logs app"
    exit 1
}
