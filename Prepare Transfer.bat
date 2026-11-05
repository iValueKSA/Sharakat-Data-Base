@echo off
setlocal
cd /d "%~dp0"
title Prepare Al-Ahsa Platform Transfer
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare Transfer.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Transfer preparation failed. Review the message and logs\portable-transfer.log.
pause
exit /b %RESULT%
