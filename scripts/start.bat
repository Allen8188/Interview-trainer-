@echo off
setlocal
cd /d %~dp0\..

docker --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop not found.
  set /p OPEN_DOCKER="Open Docker download page now? [Y/n]: "
  if "%OPEN_DOCKER%"=="" set OPEN_DOCKER=Y
  if /I "%OPEN_DOCKER%"=="Y" start "" "https://www.docker.com/products/docker-desktop/"
  pause
  exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] docker compose not found.
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker daemon is not running. Please start Docker Desktop first.
  pause
  exit /b 1
)

docker compose up -d --build
if errorlevel 1 (
  echo [ERROR] Failed to start service.
  pause
  exit /b 1
)

echo Interview Trainer started at http://localhost:8000
if /I "%IT_OPEN_BROWSER%"=="0" (
  echo [INFO] Auto-open disabled. Open http://localhost:8000 manually.
) else (
  start "" "http://localhost:8000"
)
