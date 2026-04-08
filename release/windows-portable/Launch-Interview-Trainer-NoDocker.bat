@echo off
setlocal
cd /d %~dp0

if not exist "InterviewTrainer.exe" (
  echo [ERROR] InterviewTrainer.exe not found in current folder.
  pause
  exit /b 1
)

echo Starting Interview Trainer (No Docker)...
start "InterviewTrainer" "%~dp0InterviewTrainer.exe"
timeout /t 2 >nul

if /I "%IT_OPEN_BROWSER%"=="0" (
  echo [INFO] Auto-open disabled. Open http://127.0.0.1:8000 manually.
) else (
  start "" "http://127.0.0.1:8000"
)
