# One-Click Launch

Goal: run without polluting local Python environment.

## Windows

- CMD: Double-click `scripts\\start.bat` / `scripts\\stop.bat`
- PowerShell: run `.\scripts\start.ps1` / `.\scripts\stop.ps1`

## Linux / macOS

- Linux: run `./scripts/start.sh` / `./scripts/stop.sh`
- macOS: double-click `scripts/start.command` / `scripts/stop.command`

## Requirement

- Docker Desktop (or Docker Engine + Compose) must be installed.
- Start scripts perform preflight checks and will prompt/open Docker download page if missing.

## WSL

- Supported.
- Install Docker Desktop on Windows and enable WSL Integration for your distro.
- In WSL run `./scripts/start.sh`.
- Open app from Windows browser: http://localhost:8000

The app opens at: http://localhost:8000
