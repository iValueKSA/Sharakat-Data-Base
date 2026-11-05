@echo off
cd /d "%~dp0"
call "%~dp0Stop Platform.bat"
if errorlevel 1 exit /b 1
call "%~dp0Start Platform.bat"
exit /b %errorlevel%
