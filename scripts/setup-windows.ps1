#Requires -RunAsAdministrator
<#
    Office-Connect - one-time Windows dev prerequisites.

    Run ONCE, elevated:
        Right-click this file > "Run with PowerShell" as administrator, OR from an
        elevated PowerShell:
        powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1

    Installs: WSL2 (Docker Desktop backend), Docker Desktop, and (optional) a
    host-side Python 3.12 for tooling. A REBOOT is required afterward before
    Docker can run.

    Nothing here touches your Laragon / dev_pims setup.
#>

$wingetArgs = @(
    "-e", "--source", "winget",
    "--accept-source-agreements", "--accept-package-agreements",
    "--disable-interactivity"
)

Write-Host "== 1/3  Enabling WSL2 (Docker Desktop backend) ==" -ForegroundColor Cyan
wsl --install --no-distribution
Write-Host "   (If it says WSL is already installed, that's fine.)"

Write-Host "`n== 2/3  Installing Docker Desktop ==" -ForegroundColor Cyan
winget install --id Docker.DockerDesktop @wingetArgs

Write-Host "`n== 3/3  Installing host Python 3.12 (tooling; optional) ==" -ForegroundColor Cyan
winget install --id Python.Python.3.12 @wingetArgs

Write-Host "`n==================== DONE ====================" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. REBOOT the machine (WSL2 + Docker require it)."
Write-Host "  2. Launch 'Docker Desktop' once; accept terms; wait for the whale"
Write-Host "     icon in the tray to stop animating (engine running)."
Write-Host "  3. In the project folder run:  .\scripts\smoke-test.ps1"
