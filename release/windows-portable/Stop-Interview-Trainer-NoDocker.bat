@echo off
setlocal
taskkill /F /IM InterviewTrainer.exe >nul 2>&1
if errorlevel 1 (
  echo InterviewTrainer.exe is not running.
) else (
  echo Interview Trainer stopped.
)
pause
