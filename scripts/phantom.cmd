@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0phantom.ps1" %*
exit /b %ERRORLEVEL%
