@echo off
setlocal
cd /d %~dp0
call scripts\start.bat
if errorlevel 1 (
  echo.
  echo Startup failed. Please check the messages above.
  pause
)
