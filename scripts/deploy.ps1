<#
    Office-Connect - deploy orchestrator (Windows dev convenience).

    The AUTHORITATIVE deploy procedure is docs/operations/deploy.md (POSIX sh,
    for the production Ubuntu VM). This .ps1 mirrors it for local dev. Sequence:
        backup -> deploy guard -> explicit migrate -> up -> health.

    Usage:
        .\scripts\deploy.ps1              # dev deploy (Guard A only)
        .\scripts\deploy.ps1 -Release     # phase-gate release (Guards A+B+C)
#>
param(
    [switch]$Release,
    [string]$Phase = "0"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$mode = if ($Release) { "release" } else { "dev" }
Write-Host "== Office-Connect deploy (mode=$mode) ==" -ForegroundColor Cyan

# 0. Release only: the git-tag existence check lives on the host (git + .git are
#    not in the container). Refuse if this phase was already tagged/shipped.
if ($Release) {
    $tag = "phase-$Phase-complete"
    $existing = git tag --list $tag
    if ($existing) {
        Write-Host "BLOCKED: tag $tag already exists (phase already shipped)." -ForegroundColor Red
        exit 1
    }
}

# 1. Ensure the database is up (backup + guard need it).
docker compose up -d db
if ($LASTEXITCODE -ne 0) { exit 1 }

# 2. Fresh backup BEFORE any migration (also satisfies Guard A3).
Write-Host "`n-- backup --" -ForegroundColor Cyan
docker compose run --rm worker python -m office_connect.ops backup
if ($LASTEXITCODE -ne 0) { Write-Host "backup failed" -ForegroundColor Red; exit 1 }

# 3. Deploy guard (OC_MIGRATE_ON_BOOT forced off so the guard container never migrates).
Write-Host "`n-- deploy guard --" -ForegroundColor Cyan
docker compose run --rm -e OC_MIGRATE_ON_BOOT=false -v "$($PWD.Path):/repo:ro" `
    app python -m office_connect.ops.deploy_guard --repo /repo --mode $mode
if ($LASTEXITCODE -ne 0) { Write-Host "deploy blocked by guard" -ForegroundColor Red; exit 1 }

# 4. Explicit migrate step (flag off; this is the prod-shaped path).
Write-Host "`n-- migrate --" -ForegroundColor Cyan
docker compose run --rm -e OC_MIGRATE_ON_BOOT=false app alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host "migration failed" -ForegroundColor Red; exit 1 }

# 5. Bring the stack up.
Write-Host "`n-- up --" -ForegroundColor Cyan
docker compose up -d --build app worker beat
if ($LASTEXITCODE -ne 0) { exit 1 }

# 6. Health poll (same loop as smoke-test.ps1).
Write-Host "`nWaiting for http://localhost:8001/health ..." -ForegroundColor Cyan
$ok = $false
foreach ($i in 1..30) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 3
        if ($r.status -eq "healthy") { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if ($ok) {
    Write-Host "`nDEPLOY OK - stack healthy." -ForegroundColor Green
} else {
    Write-Host "`nStack did not become healthy in time. Inspect: docker compose logs app" -ForegroundColor Red
    exit 1
}
