@echo off
setlocal
cd /d "%~dp0"
title Check Al-Ahsa Platform PC Readiness
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-new-pc.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
