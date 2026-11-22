@echo off
setlocal
cd /d "%~dp0"
title Restart Al-Ahsa Investment Platform
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\native\bootstrap.ps1" restart
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo Something needs attention. Details are in the logs folder shown above.
  pause
)
exit /b %RESULT%
