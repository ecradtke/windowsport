@echo off
title K13 AI Hub - Starting Services
echo ==========================================================
echo   Launching K13 AI Hub Services on Windows
echo ==========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\k13ctl.ps1" start all
timeout /t 3 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\k13ctl.ps1" status
echo.
echo Opening Web Portal in default browser...
start http://localhost:3000
echo.
pause
