@echo off
setlocal
cd /d "%~dp0"
title Prepare Al-Ahsa Platform Transfer
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\native\bootstrap.ps1" export-transfer
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
