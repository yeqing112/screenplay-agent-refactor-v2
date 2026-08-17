param(
  [int]$BackendPort = 18765,
  [int]$FrontendPort = 5175,
  [ValidateSet("dev", "preview")]
  [string]$FrontendMode = "dev"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"
$apiTarget = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

function Test-PortListening {
  param([int]$Port)
  return [bool](Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" } | Select-Object -First 1)
}

if (Test-PortListening -Port $BackendPort) {
  Write-Warning "Backend port $BackendPort is already in use. The new backend may fail to start."
}

if (Test-PortListening -Port $FrontendPort) {
  Write-Warning "Frontend port $FrontendPort is already in use. The new frontend may fail to start."
}

Write-Host "Starting backend on $apiTarget"
Start-Process -FilePath python `
  -ArgumentList "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
  -WorkingDirectory $repoRoot

if ($FrontendMode -eq "preview") {
  Write-Host "Building frontend before preview start..."
  Push-Location $webRoot
  try {
    npm.cmd run build
  }
  finally {
    Pop-Location
  }
}

$frontendCommand = if ($FrontendMode -eq "preview") {
  "`$env:VITE_API_PROXY_TARGET='$apiTarget'; npm.cmd run preview -- --host 127.0.0.1 --port $FrontendPort"
}
else {
  "`$env:VITE_API_PROXY_TARGET='$apiTarget'; npm.cmd run dev -- --host 127.0.0.1 --port $FrontendPort"
}

Write-Host "Starting frontend on $frontendUrl ($FrontendMode mode)"
Start-Process -FilePath powershell `
  -ArgumentList "-NoProfile", "-Command", $frontendCommand `
  -WorkingDirectory $webRoot

Write-Host ""
Write-Host "Frontend: $frontendUrl"
Write-Host "Backend:  $apiTarget"
Write-Host "Mode:     $FrontendMode"
