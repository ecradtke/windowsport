@echo off
title K13 AI Hub - Hardware Check
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\k13ctl.ps1" check-hardware
echo.
pause
