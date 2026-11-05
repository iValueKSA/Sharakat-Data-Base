@echo off
setlocal
cd /d "%~dp0"
title Install Al-Ahsa Investment Platform Requirements
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-local-requirements.ps1"
set "RESULT=%ERRORLEVEL%"
if exist "%~dp0.local-setup\reboot-required" (
  echo.
  echo A Windows restart is required. Restart your computer, then run this installer again.
  pause
)
if not "%RESULT%"=="0" (
  echo.
  echo Setup needs attention. See logs\local-requirements-diagnostic.log
  pause
)
exit /b %RESULT%
