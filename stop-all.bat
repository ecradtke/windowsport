@echo off
title K13 AI Hub - Stopping Services
echo ==========================================================
echo   Stopping K13 AI Hub Services
echo ==========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\k13ctl.ps1" stop all
echo.
pause
