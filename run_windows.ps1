<#!
run_windows.ps1 — Build and run the Flood Monitoring dashboard container on Windows.
Usage (PowerShell):
  ./run_windows.ps1                       # defaults (AUTO serial scan in container)
  $env:SERIAL=COM5; ./run_windows.ps1     # attempt direct mapping (WSL only)
  $env:SERIAL_TCP=localhost:7777; ./run_windows.ps1  # use TCP bridge (recommended for native Windows)

Serial strategies on Windows:
1. WSL + /dev/tty* mapping (best if using Linux inside WSL). Run this script inside WSL; set SERIAL=/dev/ttyS4 etc.
2. TCP bridge (works on native Windows):
     a. Install com0com or use built-in app providing COM port.
     b. Run a bridge (example using pyserial):
          python -m serial.tools.miniterm COM5 115200 --raw | ncat -lk 7777 (simplified example)
        Or with socat (in WSL):
          socat -d -d TCP-LISTEN:7777,fork FILE:/dev/ttyS4,b115200,raw,echo=0
     c. Set env SERIAL_TCP=host:7777 so container reads lines over TCP.
3. Direct COM mapping to Linux container is generally unsupported by Docker Desktop; thus TCP is safest.

Inside the container, serial_worker.py will prefer SERIAL_TCP if provided; else it uses SERIAL_PORT (AUTO scan fallback).
#!>

param(
    [string]$Image = ${env:IMAGE} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { 'flood-monitoring' } },
    [string]$Port = ${env:PORT}   | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { '8501' } },
    [string]$CsvDir = ${env:CSV_DIR} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { (Join-Path (Get-Location) 'data') } },
    [string]$CsvFile = ${env:CSV_FILE} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { 'data.csv' } },
  [string]$Serial = ${env:SERIAL} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { 'AUTO' } },
  [string]$SerialTcp = ${env:SERIAL_TCP} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { '' } },
    [string]$ApiKey = ${env:OPENWEATHER_API_KEY} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { '' } },
    [string]$Lat = ${env:DEFAULT_LAT} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { '29.58145' } },
    [string]$Lon = ${env:DEFAULT_LON} | ForEach-Object { if ($_ -and $_.Length -gt 0) { $_ } else { '-98.616441' } }
)

$ErrorActionPreference = 'Stop'

function Info($msg){ Write-Host "[i] $msg" -ForegroundColor Cyan }
function Warn($msg){ Write-Warning $msg }
function Die($msg){ Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

# Ensure docker available
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Die 'Docker not found in PATH. Install Docker Desktop or run setup script.'
}

# Prepare CSV dir
if (-not (Test-Path $CsvDir)) { New-Item -ItemType Directory -Path $CsvDir | Out-Null }
$csvPathHost = Join-Path $CsvDir $CsvFile
if (-not (Test-Path $csvPathHost)) { '' | Out-File -FilePath $csvPathHost -Encoding utf8 }
Info "CSV host path: $csvPathHost"

# Build image
Info "Building image $Image"
 docker build -t $Image .

# Remove previous container if exists
try { docker rm -f floodDash | Out-Null } catch { }

# Detect WSL (for potential serial mapping). In native Windows, --device typically won't map COM ports.
$inWsl = Test-Path -Path /proc/version
$deviceArgs = @()
if ($SerialTcp) {
  Info "Using TCP serial bridge: $SerialTcp"
} elseif ($Serial -and $Serial -ne 'AUTO') {
  if ($inWsl -and (Test-Path $Serial)) {
    Info "Mapping serial device $Serial"
    $deviceArgs += '--device'
    $deviceArgs += "$Serial:$Serial"
  } else {
    Warn "Cannot map serial device '$Serial' directly (not in WSL or device missing). Container will use AUTO scan."
  }
} else {
  Info 'Serial AUTO mode (container will scan common ports).'
}

$envArgs = @(
  '-e', "OPENWEATHER_API_KEY=$ApiKey",
  '-e', "DEFAULT_LAT=$Lat",
  '-e', "DEFAULT_LON=$Lon",
  '-e', "CSV_PATH=/app/data/$CsvFile",
  '-e', "SERIAL_PORT=$Serial",
  '-e', 'BAUDRATE=115200'
)
if ($SerialTcp) { $envArgs += @('-e', "SERIAL_TCP=$SerialTcp") }

Info "Starting container -> http://localhost:$Port"
$runArgs = @('run','-it','--name','floodDash','-p',"$Port:$Port") + $deviceArgs + @('-v',"$CsvDir:/app/data") + $envArgs + @($Image)

# Show command (sanitized)
Info ("docker " + ($runArgs -join ' '))

docker @runArgs
