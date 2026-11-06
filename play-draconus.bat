@echo off
rem Double-click launcher for the recompiled Draconus build.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0play-draconus.ps1" %*
if errorlevel 1 pause
