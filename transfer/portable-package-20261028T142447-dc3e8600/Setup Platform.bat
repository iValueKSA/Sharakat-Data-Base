@echo off
setlocal
cd /d "%~dp0"
title Setup Al-Ahsa Investment Platform
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup Platform.ps1"
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="3010" (
  echo.
  echo يجب إعادة تشغيل الجهاز ثم تشغيل Setup Platform.bat مرة أخرى
  pause
) else if not "%RESULT%"=="0" (
  echo.
  echo SETUP FAILED. Review the clear failure reason and logs\setup-*.log.
  pause
)
exit /b %RESULT%
