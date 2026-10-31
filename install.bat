@echo off
title K13 AI Hub - Windows Installer
echo ==========================================================
echo   Starting K13 AI Hub Windows Setup
echo ==========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\install.ps1"
echo.
pause
