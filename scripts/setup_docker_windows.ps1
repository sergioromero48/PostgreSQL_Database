<#!
PowerShell script to install Docker Desktop on Windows 10/11 (requires admin) and enable WSL2 features.
Run in elevated PowerShell:  Set-ExecutionPolicy Bypass -Scope Process -Force; ./setup_docker_windows.ps1
#!>

$ErrorActionPreference = 'Stop'

# Check admin
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'Please run this script in an elevated PowerShell session (Run as Administrator).'
}

Write-Host '[+] Enabling required Windows features (WSL & VirtualMachinePlatform)'
# Enable-WindowsOptionalFeature is idempotent
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart | Out-Null
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart | Out-Null

# Install WSL kernel update (if not present)
if (-not (wsl -l -v 2>$null)) { wsl --install }

# Download Docker Desktop installer if missing
$dockerUrl = 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
$tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::GetTempPath() + 'docker-install') -Force
$installer = Join-Path $tempDir 'DockerDesktopInstaller.exe'

if (-not (Test-Path $installer)) {
    Write-Host "[+] Downloading Docker Desktop installer -> $installer"
    Invoke-WebRequest -Uri $dockerUrl -OutFile $installer
}

Write-Host '[+] Launching Docker Desktop installer (silent)'
Start-Process $installer -ArgumentList 'install', '--quiet', '--accept-license' -Wait

Write-Host '[+] Configuring to start on login'
$desktopConfig = "$env:APPDATA/Docker/settings.json"
if (Test-Path $desktopConfig) {
    try {
        $json = Get-Content $desktopConfig | ConvertFrom-Json
        $json.autoStart = $true
        $json | ConvertTo-Json -Depth 10 | Set-Content $desktopConfig
    } catch { Write-Warning 'Could not modify settings.json (non-fatal).' }
}

Write-Host '[+] Adding current user to docker-users group (if needed)'
try {
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $group = 'docker-users'
    $groupExists = (Get-LocalGroup | Where-Object { $_.Name -eq $group }) -ne $null
    if ($groupExists) { Add-LocalGroupMember -Group $group -Member $user -ErrorAction SilentlyContinue }
} catch { Write-Warning 'Could not add user to docker-users group (non-fatal).' }

Write-Host '[i] A system restart might be required for all changes to take effect.'
Write-Host '[✓] Docker Desktop installation routine finished.'
Write-Host '    After restart, verify with: docker run --rm hello-world'
