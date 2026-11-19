@echo off
title Bakery V4 - Stopping All Big Data Services
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1"
echo.
pause
