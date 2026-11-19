@echo off
title Bakery V4 - Starting All Big Data Services
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
echo.
pause
