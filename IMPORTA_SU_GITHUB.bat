@echo off
cd /d "%~dp0"
echo IMPORTAZIONE Instagram News Bot su GitHub
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0IMPORTA_SU_GITHUB.ps1"
echo.
pause
