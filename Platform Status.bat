@echo off
setlocal
cd /d "%~dp0"
title Al-Ahsa Investment Platform Status
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\native\bootstrap.ps1" status
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
