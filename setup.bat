@echo off
rem Wrapper so setup runs regardless of the PowerShell execution policy.
rem Usage: setup.bat [-SkipBuild] [-Sdl3Dir <path>\cmake] [-VcVars <path>\vcvars64.bat]
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 pause
exit /b %errorlevel%
