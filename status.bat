@echo off
title K13 AI Hub - Status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\k13ctl.ps1" status
echo.
pause
