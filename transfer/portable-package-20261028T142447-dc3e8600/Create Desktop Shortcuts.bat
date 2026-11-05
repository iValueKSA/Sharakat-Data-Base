@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-desktop-shortcuts.ps1"
exit /b %errorlevel%
