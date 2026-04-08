$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Open-Url([string]$url) {
  Start-Process $url | Out-Null
}

try {
  docker --version | Out-Null
} catch {
  Write-Host "[ERROR] Docker Desktop not found."
  $ans = Read-Host "Open Docker download page now? [Y/n]"
  if ([string]::IsNullOrWhiteSpace($ans) -or $ans -match '^[Yy]$') {
    Open-Url "https://www.docker.com/products/docker-desktop/"
  }
  exit 1
}

try {
  docker compose version | Out-Null
} catch {
  Write-Host "[ERROR] docker compose not found."
  exit 1
}

try {
  docker info | Out-Null
} catch {
  Write-Host "[ERROR] Docker daemon is not running. Please start Docker Desktop first."
  exit 1
}

docker compose up -d --build
Write-Host "Interview Trainer started at http://localhost:8000"
if ($env:IT_OPEN_BROWSER -eq "0") {
  Write-Host "[INFO] Auto-open disabled. Open http://localhost:8000 manually."
} else {
  Open-Url "http://localhost:8000"
}
