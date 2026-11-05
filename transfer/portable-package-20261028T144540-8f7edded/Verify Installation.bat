@echo off
setlocal
cd /d "%~dp0"
title Verify Al-Ahsa Investment Platform
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify-installation.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
